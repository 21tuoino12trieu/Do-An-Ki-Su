SCENARIO_ROUTING_PROMPT = """
NHIỆM VỤ: Phân loại ý định của khách hàng vào đúng 1 trong các kịch bản bên dưới dựa vào tin nhắn khách hàng và lịch sử hội thoại.

DANH SÁCH KỊCH BẢN & ĐIỀU KIỆN KHỚP:
1. handle_card_swallowed: Khách hàng bị nuốt thẻ, kẹt thẻ tại cây ATM/CRM MB hoặc ngân hàng khác, mong muốn/yêu cầu lấy lại thẻ bị nuốt.
2. handle_atm_withdrawal_dispute: Khách hàng thực hiện rút tiền tại cây ATM (bao gồm cả rút bằng thẻ hoặc QR/App) nhưng bị trừ tiền trên tài khoản/thẻ mà chưa nhận được tiền, nhận thiếu tiền, hoặc không rút tiền bằng thẻ được ("tại sao tôi k rút tiền bằng thẻ được", "không rút tiền bằng thẻ được", "rút tiền atm bị lỗi").
3. handle_pos_transaction_dispute: Khách hàng quẹt thẻ tại máy POS bị trừ tiền nhưng đơn vị thanh toán chưa nhận được, bị trừ trùng lặp nhiều lần, không quẹt thẻ mà bị trừ tiền, hoặc hỏi thủ tục tra soát tại Chi nhánh/PGD MB ("ts ở chi nhánh mb đc k", "làm tra soát ở PGD được không").
4. handle_online_payment_dispute: Khách hàng thanh toán online (web/app, e-commerce, các thương hiệu như Steam, YouTube, Shopee, Lazada, TikTok, Netflix, App Store, Google Play...) bị trừ tiền nhưng đơn vị thanh toán chưa nhận được, hoặc giao dịch bị lỗi/không thành công.
5. handle_unknown_transaction_dispute: Thẻ bị trừ tiền không rõ nguyên nhân (không biết phát sinh từ ATM, POS hay Online).
6. handle_early_installment_settlement: Yêu cầu tất toán khoản đăng ký trả góp trên thẻ tín dụng/thẻ đa năng MB trước hạn.
7. check_card_delivery_status: Phát hành/đăng ký mở thẻ đã lâu nhưng chưa nhận được thẻ giao tới nhà hoặc chi nhánh.
8. check_credit_card_statement_payment: Khách hàng BÁO SỰ CỐ / KHIẾU NẠI việc nộp tiền/chuyển tiền từ tài khoản MB (hoặc từ ngân hàng khác) VÀO THẺ VISA / THẺ TÍN DỤNG / HẠN MỨC THẺ MB để thanh toán dư nợ sao kê / nạp tiền vào thẻ nhưng thẻ chưa nhận được tiền, chưa được hạ dư nợ hoặc chưa được tăng hạn mức.
9. check_failed_card_transaction: Giao dịch qua thẻ (ATM/POS/Online, bao gồm Steam/YouTube) bị lỗi/thất bại và tài khoản CHƯA bị trừ tiền.
10. check_failed_refund_to_account: Giao dịch RÚT TIỀN TỪ THẺ VỀ TÀI KHOẢN hoặc HOÀN TIỀN TỪ THẺ/HẠN MỨC THẺ VỀ TÀI KHOẢN NGÂN HÀNG bị thất bại (ngược lại hoàn toàn với kịch bản 8).

QUY TẮC PHÂN LOẠI QUAN TRỌNG:
- QUY TẮC NGOẠI LỆ CHO CÂU HỎI THÔNG TIN / CÚ PHÁP HƯỚNG DẪN (GENERAL INFORMATIONAL INQUIRIES):
  + Nếu khách hàng CHỈ HỎI HƯỚNG DẪN THAO TÁC / CÚ PHÁP / CÁCH GHI THÔNG TIN (Ví dụ: "ghi thông tin chuyển khoản sao em", "cú pháp thanh toán sao kê từ ngân hàng khác là gì", "cách thanh toán thẻ tín dụng qua app", "stk trung gian là gì"): BẮT BUỘC TRẢ VỀ "None" để luồng RAG tư vấn câu trả lời trực tiếp. KHÔNG đẩy vào kịch bản 8 hay bất kỳ kịch bản khiếu nại nào.
- Từ viết tắt thông dụng: "ts" = tra soát, "đc k" / "dc ko" = được không, "stk" = số tài khoản, "gd" = giao dịch, "củ" = triệu, "lít" = trăm nghìn.
- Nếu tin nhắn thuộc bất kỳ kịch bản nào ở trên, chỉ trả về DUY NHẤT tên nhãn kịch bản (ví dụ: handle_card_swallowed).
- QUY TẮC DUY TRÌ KỊCH BẢN ĐANG CHẠY (STICKY SCENARIO RULE):
  + Nếu "Kịch bản hiện tại" (current_scenario) KHÁC "None" (ví dụ: handle_card_swallowed, handle_atm_withdrawal_dispute, check_credit_card_statement_payment...) và tin nhắn khách hàng là câu trả lời bổ sung thông tin (mã máy, số thẻ, STK, số tiền, ngày tháng, địa điểm CN/PGD, giấy tờ) hoặc câu thoại tiếp nối/xác nhận ("ok bạn", "dạ vâng", "mình khoá xong r ạ", "số thẻ đầy đủ ạ?", "hỗ trợ mình", "tiền chưa bị trừ", "đợi tí check", "chịu", "1", "0đ"): BẮT BUỘC giữ nguyên và trả về tên của current_scenario.
  + CHỈ đổi sang nhãn kịch bản khác hoặc trả về "None" khi người dùng chủ động muốn hủy luồng hiện tại hoặc hỏi sang một dịch vụ/nghiệp vụ hoàn toàn mới không liên quan.
- QUY TẮC PHÂN LOẠI & ƯU TIÊN CHUYỂN HƯỚNG Tra cứu Địa Điểm:
  + Nếu tin nhắn khách hàng KHÔNG nằm trong luồng kịch bản thu thập thông tin và chủ động hỏi vị trí Chi nhánh/PGD/SmartBank/ATM MB (ví dụ: "ở gần Hòa Bình có chi nhánh nào không", "địa chỉ PGD gần nhất"): Trả về "None" để hệ thống ưu tiên gọi dịch vụ tra cứu vị trí địa lý cho khách hàng.
  + PHÂN BIỆT RÕ QUẢN LÝ MÃ RÚT TIỀN ATM VỚI TRA CỨU ĐỊA ĐIỂM: Các câu hỏi về "Mã rút tiền ATM", "tạo/hủy mã rút tiền ATM", "mã rút tiền hết hạn", "quản lý mã rút tiền trên App" là thắc mắc nghiệp vụ/tính năng Ngân hàng số. KHÔNG PHẢI câu hỏi tra cứu địa điểm ATM.
- KHÔNG thêm bất kỳ từ ngữ, dấu câu, thẻ XML hay lời giải thích nào khác.
- Nếu câu hỏi chỉ tìm kiếm thông tin chung và KHÔNG thuộc 10 kịch bản trên, trả về đúng từ: None

Kịch bản hiện tại: {current_scenario}

Lịch sử hội thoại:
{conversation_history}

Tin nhắn khách hàng: {query}
"""