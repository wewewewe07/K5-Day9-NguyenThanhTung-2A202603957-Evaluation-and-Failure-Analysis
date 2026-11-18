"""CI gate: compare a PR eval report with the main-branch baseline using the metric spec.

    python -m lab9.gate --pr reports/eval_workflow.json --baseline reports/baseline_v1.json

exit 0 = merge, exit 1 = blocked. Safety metrics: max 0, no averaging away.
Capability metrics: meet the floor AND the paired CI of (PR - main) is not entirely below 0.
Thresholds may only get stricter on the same eval-set version (ratchet).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from lab8.console import utf8_stdio
from lab9 import stats
from lab9.eval import SPEC, load_spec, per_item


import math


def integrity_check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> list[str]:
    """M7 (Expert): refuse to compare reports that cannot be trusted. Return a list of problems
    (empty = trustworthy). A gate that passes a broken report is worse than no gate."""
    problems: list[str] = []

    # 1. Bắt metric NaN hoặc inf
    for m, v in pr.get("metrics", {}).items():
        if v is not None and isinstance(v, (int, float)) and (math.isnan(v) or math.isinf(v)):
            problems.append(f"Metric {m} is NaN or inf")

    # 2. Số dòng dữ liệu phải bằng items x seeds
    manifest = pr.get("manifest", {})
    expected_rows = manifest.get("items", 0) * len(manifest.get("seeds", []))
    if expected_rows > 0 and len(pr.get("rows", [])) != expected_rows:
        problems.append(f"Row count {len(pr.get('rows', []))} != expected {expected_rows}")

    # 3. Tập (item_id, seed) phải trùng với baseline
    pr_pairs = {(r.get("item_id"), r.get("seed")) for r in pr.get("rows", [])}
    base_pairs = {(r.get("item_id"), r.get("seed")) for r in base.get("rows", [])}
    if pr_pairs != base_pairs:
        problems.append("The (item_id, seed) set of PR differs from baseline")

    # 4. evaluator_failures hoặc dòng có metric graded là None
    if pr.get("evaluator_failures"):
        problems.append(f"evaluator_failures is non-empty: {pr['evaluator_failures']}")
    graded_metric_ids = [m["id"] for m in spec.get("metrics", [])]
    for r in pr.get("rows", []):
        for mid in graded_metric_ids:
            if mid in r and r[mid] is None:
                problems.append(f"Row {r.get('item_id')}@{r.get('seed')} has None for graded metric {mid}")
                break

    # 5. Ratchet rule: Không được nới lỏng spec so với base_spec
    if base_spec and spec.get("eval_set_version") == base_spec.get("eval_set_version"):
        base_m_map = {m["id"]: m for m in base_spec.get("metrics", [])}
        for m in spec.get("metrics", []):
            mid = m["id"]
            if mid in base_m_map:
                bm = base_m_map[mid]
                if bm.get("blocking") and not m.get("blocking"):
                    problems.append(f"Metric {mid} loosened: blocking became False")
                b_th = bm.get("threshold", {})
                p_th = m.get("threshold", {})
                if "min" in b_th and p_th.get("min", float("-inf")) < b_th["min"]:
                    problems.append(f"Metric {mid} loosened: min threshold lowered")
                if "max" in b_th and p_th.get("max", float("inf")) > b_th["max"]:
                    problems.append(f"Metric {mid} loosened: max threshold raised")
                if "max_increase" in b_th and p_th.get("max_increase", float("inf")) > b_th["max_increase"]:
                    problems.append(f"Metric {mid} loosened: max_increase threshold raised")
                if b_th.get("no_significant_drop") and not p_th.get("no_significant_drop"):
                    problems.append(f"Metric {mid} loosened: no_significant_drop removed")
        for b_mid in base_m_map:
            if b_mid not in {m["id"]: m for m in spec.get("metrics", [])}:
                problems.append(f"Metric {b_mid} disappeared from spec")

        base_s_map = {s["name"]: s for s in base_spec.get("slices", [])}
        for s in spec.get("slices", []):
            sname = s["name"]
            if sname in base_s_map:
                bs = base_s_map[sname]
                if bs.get("blocking") and not s.get("blocking"):
                    problems.append(f"Slice {sname} loosened: blocking became False")
                if "min" in bs and s.get("min", float("-inf")) < bs["min"]:
                    problems.append(f"Slice {sname} loosened: min threshold lowered")
                if bs.get("no_significant_drop") and not s.get("no_significant_drop"):
                    problems.append(f"Slice {sname} loosened: no_significant_drop removed")
        for bs_name in base_s_map:
            if bs_name not in {s["name"]: s for s in spec.get("slices", [])}:
                problems.append(f"Slice {bs_name} disappeared from spec")

    # 6. Slice tags của item không được khác so với baseline
    pr_slices = {f"{r.get('item_id')}@{r.get('seed')}": sorted(r.get("slices", [])) for r in pr.get("rows", [])}
    base_slices = {f"{r.get('item_id')}@{r.get('seed')}": sorted(r.get("slices", [])) for r in base.get("rows", [])}
    for k, ps in pr_slices.items():
        if k in base_slices and ps != base_slices[k]:
            problems.append(f"Item slice tags differ from baseline for {k}")
            break

    return problems


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """M5 (Advanced): an average can hide a regression on a small, important slice.
    For each entry of spec["slices"] ({"name", "metric", "min"?, "no_significant_drop"?, "blocking"}):
      - value = mean of per_item(pr, metric, slice_name=name)
      - fail if below "min", or if no_significant_drop and the paired CI over the slice's items
        lies entirely below 0
    Return (blocked ids like "slice:money_movement/pass_rate", report lines)."""
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for sl in spec.get("slices", []):
        name = sl["name"]
        metric = sl["metric"]
        min_th = sl.get("min")
        blocking = sl.get("blocking", True)

        pr_items = per_item(pr, metric, slice_name=name)
        if not pr_items:
            continue
        vals = list(pr_items.values())
        val = sum(vals) / len(vals)
        verdict = "ok"
        note = ""

        if min_th is not None and val < min_th:
            verdict = "fail"

        if sl.get("no_significant_drop"):
            base_items = per_item(base, metric, slice_name=name)
            common = sorted(set(pr_items) & set(base_items))
            if common:
                d, lo, hi = stats.paired_bootstrap(
                    [pr_items[k] for k in common],
                    [base_items[k] for k in common],
                    n_resamples=bs.get("n_resamples", 1000),
                    rng=bs.get("rng", 2027),
                )
                note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
                if hi < 0:
                    verdict = "fail"

        slice_id = f"slice:{name}/{metric}"
        if verdict != "ok" and blocking:
            blocked.append(slice_id)
        status_lbl = "BLOCK" if (verdict != "ok" and blocking) else ("warn" if verdict != "ok" else "ok")
        lines.append(f"  {slice_id:<28} {val:<8.3f} min={min_th!s:<10} {note:<28} {status_lbl}")
    return blocked, lines


def check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> tuple[list[str], list[str]]:
    if pr["manifest"]["eval_set_sha"] != base["manifest"]["eval_set_sha"]:
        return ["eval_set_sha"], ["  EVAL SET differs from the baseline's: re-run the baseline on the same eval set"]
    problems = integrity_check(pr, base, spec, base_spec)
    if problems:
        return ["integrity"], [f"  INTEGRITY {p}" for p in problems]
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for m in spec["metrics"]:
        mid, th, val = m["id"], m.get("threshold", {}), pr["metrics"].get(m["id"])
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        elif "max" in th and val > th["max"]:
            verdict = "fail"
        elif "min" in th and val < th["min"]:
            verdict = "fail"
        elif "max_increase" in th and base["metrics"].get(mid):
            if val > base["metrics"][mid] * (1 + th["max_increase"]):
                verdict = "fail"
        if th.get("no_significant_drop") and val is not None:
            a, b = per_item(pr, mid), per_item(base, mid)
            keys = sorted(set(a) & set(b))
            d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                               n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
            note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            if hi < 0:
                verdict = "fail"
        if verdict != "ok" and m.get("blocking"):
            blocked.append(mid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if m.get("blocking") else "warn")
        lines.append(f"  {mid:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    if spec.get("slices"):
        sb, sl = slice_check(pr, base, spec)
        blocked += sb
        lines += sl
    return blocked, lines


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.gate")
    ap.add_argument("--pr", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--base-spec", help="metric spec on main, for the ratchet check (M7)")
    args = ap.parse_args(argv)
    pr = json.loads(Path(args.pr).read_text(encoding="utf-8"))
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    base_spec = load_spec(Path(args.base_spec)) if args.base_spec else None
    blocked, lines = check(pr, base, load_spec(Path(args.spec)), base_spec)
    print(f"gate: PR {pr['run_id']} vs main {base['run_id']} · eval set {pr['manifest']['eval_set_sha']}")
    print("\n".join(lines))
    if blocked:
        print(f"exit 1 — blocked: {', '.join(blocked)}")
        return 1
    print("exit 0 — merge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
