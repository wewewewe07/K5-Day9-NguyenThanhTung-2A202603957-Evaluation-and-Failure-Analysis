"""Statistics students implement (M2 judge calibration, M4 paired bootstrap).

Rules: a judge is a classifier -- measure it like one. A higher mean is not
"better" until the paired CI of the difference excludes 0.
Reference values to self-check are in tests/test_lab9_stats.py.
"""

from __future__ import annotations

from collections.abc import Sequence

POS = "FAIL"   # the judge's job is to FIND failures, so FAIL is the positive class


def confusion(human: Sequence[str], judge: Sequence[str]) -> dict[str, int]:
    """tp/fp/fn/tn with FAIL as positive."""
    tp = sum(1 for h, j in zip(human, judge) if h == POS and j == POS)
    fp = sum(1 for h, j in zip(human, judge) if h != POS and j == POS)
    fn = sum(1 for h, j in zip(human, judge) if h == POS and j != POS)
    tn = sum(1 for h, j in zip(human, judge) if h != POS and j != POS)
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn}


def precision_recall(human: Sequence[str], judge: Sequence[str]) -> tuple[float, float]:
    """precision = tp/(tp+fp), recall = tp/(tp+fn); return 0.0 when denominator is 0."""
    cm = confusion(human, judge)
    tp, fp, fn = cm["tp"], cm["fp"], cm["fn"]
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    return precision, recall


def cohen_kappa(human: Sequence[str], judge: Sequence[str]) -> float:
    """kappa = (p_o - p_e) / (1 - p_e). Raise ValueError when undefined (p_e == 1):
    a constant judge has no signal and must FAIL calibration, not pass on a technicality."""
    n = len(human)
    if n == 0:
        raise ValueError("Cannot compute kappa on empty sequences")
    if len(judge) != n:
        raise ValueError("Sequences must have the same length")

    # Tính tỷ lệ đồng thuận quan sát (observed agreement: p_o)
    p_o = sum(1 for h, j in zip(human, judge) if h == j) / n

    # Tính tỷ lệ đồng thuận ngẫu nhiên kỳ vọng (expected chance agreement: p_e)
    # Gom tất cả các nhãn xuất hiện
    labels = sorted(set(human) | set(judge))
    p_e = 0.0
    for lbl in labels:
        p_h = sum(1 for h in human if h == lbl) / n
        p_j = sum(1 for j in judge if j == lbl) / n
        p_e += p_h * p_j

    if p_e >= 1.0 or (1.0 - p_e) == 0.0:
        raise ValueError("Kappa is undefined for a constant judge (p_e == 1.0)")

    return (p_o - p_e) / (1.0 - p_e)


def rogan_gladen(observed_rate: float, sensitivity: float, specificity: float) -> float:
    """Correct an observed failure rate for judge error; clip to [0, 1].
    Formula: (p_obs + spec - 1) / (sens + spec - 1)"""
    denom = sensitivity + specificity - 1.0
    if denom == 0:
        return 0.0
    corrected = (observed_rate + specificity - 1.0) / denom
    return max(0.0, min(1.0, float(corrected)))


import math
import numpy as np
from scipy import stats as sp_stats


def paired_bootstrap(a: Sequence[float], b: Sequence[float], *, n_resamples: int = 1000,
                     rng: int = 2027, confidence: float = 0.95) -> tuple[float, float, float]:
    """a[i], b[i] = per-item mean over seeds, SAME items, SAME order.
    Return (mean(a)-mean(b), lo, hi) with scipy.stats.bootstrap(paired=True, method="percentile",
    rng=numpy.random.default_rng(rng)). If a == b everywhere return (0.0, 0.0, 0.0)."""
    if len(a) != len(b):
        raise ValueError("Sequences a and b must have the same length")
    if all(x == y for x, y in zip(a, b)):
        return (0.0, 0.0, 0.0)

    arr_a = np.asarray(a, dtype=float)
    arr_b = np.asarray(b, dtype=float)
    mean_diff = float(np.mean(arr_a) - np.mean(arr_b))

    def stat(x, y, axis=-1):
        return np.mean(x - y, axis=axis)

    res = sp_stats.bootstrap(
        (arr_a, arr_b),
        statistic=stat,
        paired=True,
        method="percentile",
        n_resamples=n_resamples,
        confidence_level=confidence,
        random_state=np.random.default_rng(rng),
    )
    return (mean_diff, float(res.confidence_interval.low), float(res.confidence_interval.high))


def pass_at_k(n: int, c: int, k: int) -> float:
    """Probability that AT LEAST ONE of k trials drawn from n (c of them passing) passes.
    Unbiased estimator (Chen et al. 2021): 1 - C(n-c, k) / C(n, k). Raise ValueError if k > n."""
    if k > n or k <= 0 or n <= 0 or c < 0 or c > n:
        raise ValueError(f"Invalid arguments for pass_at_k: n={n}, c={c}, k={k}")
    if c == 0:
        return 0.0
    if n - c < k:
        return 1.0
    return 1.0 - math.comb(n - c, k) / math.comb(n, k)


def pass_hat_k(n: int, c: int, k: int) -> float:
    """pass^k (tau-bench, Yao et al. 2024): probability that ALL k trials drawn from n pass.
    Unbiased estimator: C(c, k) / C(n, k). Raise ValueError if k > n.
    pass^k <= pass@1 <= pass@k; a reliable agent keeps pass^k close to pass@1."""
    if k > n or k <= 0 or n <= 0 or c < 0 or c > n:
        raise ValueError(f"Invalid arguments for pass_hat_k: n={n}, c={c}, k={k}")
    if c < k:
        return 0.0
    return math.comb(c, k) / math.comb(n, k)
