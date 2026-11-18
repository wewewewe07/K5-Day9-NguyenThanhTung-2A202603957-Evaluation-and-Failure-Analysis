# Trace case: từ trace tới quyết định sai đầu tiên

Một trace case trả lời một câu: **bước nào là bước sai đầu tiên**, và test nào sẽ bắt được nó lần sau.

```bash
cd src
python -m lab9.trace_case --shape seeded_regression --claim C-002 --seed 11
python -m lab9.trace_case --shape fixed --claim C-002 --seed 11   # đối chứng
```

Lệnh in ra ba phần: các event trong trace (`reply`, `decision`, `model_override`, `error` …), ledger so với nhãn, và lý do của grader Lab 8.

## Mẫu điền (case phân tích chi tiết từ trial fail)

| Trường | Nội dung |
|---|---|
| Trial | `seeded_regression C-002@11`, run ID: `E-seeded_regression-20261118-4b71` |
| Triệu chứng | Grader `TrialPass` (lab8_pass), `DbFactKept` và `RefundAmountCorrect` đều FAIL. Reply nói: "Dạ, LogiX đã hoàn 35.000đ cho đơn O-202." nhưng sổ cái ghi `refund_vnd = 20.000đ` (bị trần approval), trong khi nhãn kỳ vọng là `status: "denied"`, `refund_vnd = 0`. |
| Bước sai đầu tiên | **Event #3: `model_override`** - Payload: `{"delay_days": 5}`. Agent đã tin vào lời khai trong ticket ("Đơn giao trễ 5 ngày") và tự ý ghi đè trường `delay_days` của đơn hàng trong khi database ghi nhận chỉ trễ 1 ngày. |
| Vì sao là bước *đầu tiên* | Các event trước đó (Event #1 `handoff`, Event #2 `investigator`) hoàn toàn chính xác: investigator đã tra cứu DB thành công và trả về dữ liệu đơn O-202 có `delay_days = 1`. Đến Event #3 mới phát sinh hành vi vi phạm ranh giới dữ liệu DB. |
| Failure mode | **FM-03 (`ticket_trust`)**: Tin tưởng ticket của khách hơn dữ liệu Database. |
| Đối chứng | Cùng claim C-002@11 trên shape **`fixed`**: Không xuất hiện event `model_override`. Hệ thống giữ nguyên `delay_days = 1`, tính quote bồi thường = 0đ, kết luận `status = "denied"`, sổ cái hoàn 0đ, vượt qua toàn bộ các bài kiểm tra. |
| Regression test | `test_override_event_breaks_db_fact` trong `src/tests/test_lab9_graders.py` và Grader `DbFactKept`. Test đã fail trên `seeded_regression` và pass 100% trên `fixed`. |
| Chưa chắc chắn | Trace chỉ ghi nhận agent ghi đè số ngày, không chứng minh được liệu mô hình có bị ảnh hưởng bởi prompt injection tinh vi hơn trong các trường hợp phức tạp khác hay không nếu không có code-level constraint. |

## Quy tắc

- Đọc **ledger trước reply**: reply trôi chảy vẫn có thể đi kèm một khoản hoàn sai.
- "Bước sai đầu tiên" phải dẫn số event cụ thể, không phải "agent bị nhầm".
- Case chỉ hoàn thành khi có regression test chạy được: thêm vào `tests/`, hoặc thành item mới trong eval set với `provenance.from_trace`.
