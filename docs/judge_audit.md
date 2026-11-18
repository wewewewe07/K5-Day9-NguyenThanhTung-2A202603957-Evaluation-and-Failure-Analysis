# Judge audit

Chạy: `python -m lab9.judge --csv data/eval/judge_tone_public.csv --audit 5`

| Tiêu chí | n | κ | Precision | Recall | Đạt FLOORS (κ≥0.6, P≥0.8, R≥0.7)? | Quyết định |
|---|---|---|---|---|---|---|
| tone_ok | 100 | 0.757 | 0.857 | 0.800 | Đạt (κ=0.757≥0.6, P=0.857≥0.8, R=0.800≥0.7) | DÙNG |
| helpful | 100 | 0.312 | 0.900 | 0.257 | KHÔNG ĐẠT (Recall 0.257 < 0.7, κ=0.312 < 0.6) | LOẠI |

## ≥5 case audit thủ công (trích xuất từ judge_tone_public.csv)
| # | Case | Judge nói | Người nói | Ai đúng? | Ghi chú & Hành động sửa Rubric |
|---|---|---|---|---|---|
| 1 | H-008: "Em đã hoàn tiền cho anh rồi nha, anh check giúp em." | PASS | FAIL | Người đúng | Xưng hô suồng sã ("Em/anh... nha"), không đạt quy chuẩn CSKH chuyên nghiệp. Cần cập nhật prompt của judge cấm từ xưng hô thân mật quá mức. |
| 2 | H-017: "Dạ, bạn ơi LogiX đã hoàn 25.000đ cho đơn O-606 rồi nha." | PASS | FAIL | Người đúng | Xưng "bạn" và dùng từ đệm "nha" thiếu trang trọng với đối tượng khách hàng lớn tuổi. Cần bổ sung rule từ chối ngôn từ suồng sã. |
| 3 | H-029: "Dạ, vui lòng chờ. Hệ thống đang xử lý, không cần nhắn thêm." | PASS | FAIL | Người đúng | Giọng ra lệnh bề trên ("không cần nhắn thêm"), gây ức chế cho khách hàng. Judge bị đánh lừa bởi cụm từ mở đầu "Dạ, vui lòng". |
| 4 | H-042: "Dạ, đơn O-808 đã hoàn 120.000đ. Tiền về trong 3–5 ngày ạ." | FAIL | PASS | Người đúng | Câu ngắn gọn, lịch sự, đủ ý. Judge phạt nhầm vì đòi hỏi máy móc phải có câu xin lỗi. Cần nới lỏng rubric: không bắt buộc xin lỗi với case đã giải quyết thành công. |
| 5 | H-051: "Dạ, LogiX đã refund 90.000đ cho đơn O-202 ạ." | FAIL | PASS | Người đúng | Từ "refund" là thuật ngữ TMĐT thông dụng, được CS LogiX chấp nhận. Judge phạt vì coi là chêm tiếng Anh. Cần whitelist các thuật ngữ nghiệp vụ phổ biến. |

## Kết luận
- **Tiêu chí bị loại và lý do:** `judge_helpful` bị **loại bỏ hoàn toàn** không được dùng làm cổng release (CI Gate). Ma trận nhầm lẫn cho thấy judge bỏ lọt rất nhiều lỗi sai tiền (False Negative cực lớn, Recall chỉ đạt 25.7%). Lý do: LLM Judge chỉ đọc bề mặt văn bản thấy trôi chảy, lịch sự là chấm PASS, không có khả năng đối chiếu số tiền thực tế trong Database/Ledger.
- **Quy tắc vàng:** Tiền bạc, phê duyệt và sự thật Database **luôn luôn phải chấm bằng Code Grader**, không bao giờ giao phó cho LLM Judge.
- **Rủi ro còn lại:** Judge mới chỉ được kiểm định trên tập replay dữ liệu công khai (100 mẫu). Trong tương lai cần thu thập thêm tập dữ liệu gán nhãn held-out mới từ người dùng thực tế để tránh overfitting.
