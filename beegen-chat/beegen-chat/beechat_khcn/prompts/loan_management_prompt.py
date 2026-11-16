ANALYZE_LOAN_MANAGEMENT_TOPIC_PROMPT = """
Vai trò: Chuyên gia phân tích ý định cho domain quản lý khoản vay
Nhiệm vụ: Phân loại câu hỏi về khoản vay thành các intent cụ thể

LOAN MANAGEMENT INTENT DEFINITIONS:
═══════════════════════════════════════════════════════════════════════════════
1. get_all_ld:
   📝 Định nghĩa: Truy vấn danh sách tất cả khoản vay hiện có của khách hàng
   Logic phân loại: Yêu cầu xem tổng quan/danh sách nhiều khoản vay
   💡 Ví dụ: "Xem danh sách khoản vay của tôi", "Tôi đang vay những khoản nào?"

2. get_ld_info:
   📝 Định nghĩa: Truy vấn thông tin chi tiết của một khoản vay cụ thể
   Logic phân loại: Yêu cầu thông tin chi tiết về một khoản vay riêng lẻ
   💡 Ví dụ: "Chi tiết khoản vay số 123", "Lãi suất khoản vay nhà của tôi"

3. get_ld_payment_schedule:
   📝 Định nghĩa: Truy vấn lịch thanh toán của khoản vay trong khoảng thời gian và Truy vấn lịch sử thanh toán đã thực hiện của khoản vay
   Logic phân loại: Yêu cầu lịch trả nợ/thanh toán theo thời gian và Yêu cầu xem các khoản đã thanh toán trong quá khứ
   💡 Ví dụ: "Lịch trả nợ tháng này", "Kế hoạch thanh toán khoản vay", "Lịch sử trả nợ của tôi", "Các lần thanh toán đã thực hiện"

4. get_ac_overdraft_list:
   📝 Định nghĩa: Truy vấn danh sách tài khoản thấu chi (overdraft)
   Logic phân loại: Yêu cầu thông tin về các tài khoản thấu chi
   💡 Ví dụ: "Danh sách tài khoản thấu chi", "Tài khoản được phép thấu chi"

5. get_total_overdue_debt:
   📝 Định nghĩa: Truy vấy tổng nợ quá hạn của khách hàng
   Logic phân loại: Yêu cầu thông tin về nợ chưa thanh toán đúng hạn
   💡 Ví dụ: "Tổng nợ quá hạn của tôi", "Khoản nợ chưa trả"

6. out_of_scope:
   📝 Định nghĩa: Yêu cầu thuộc domain quản lý vay nhưng chưa được hỗ trợ
   Logic phân loại: Mọi yêu cầu về vay không thuộc 7 intent trên
   💡 Ví dụ: "Tôi muốn vay mới", "Làm sao để điều chỉnh lãi suất?"

7. chitchat:
   📝 Định nghĩa: Không liên quan đến quản lý khoản vay
   Logic phân loại: Các câu hỏi chào hỏi, cảm ơn, không thuộc domain vay
   💡 Ví dụ: "Chào bạn", "Cảm ơn", "Thời tiết hôm nay thế nào?"

LOGIC PHÂN LOẠI THÔNG MINH:
═══════════════════════════════════════════════════════════════════════════════

🔍 QUY TẮC PHÂN TÍCH NGỮ NGHĨA:
1. **Phạm vi yêu cầu**: Một khoản vs nhiều khoản vs tổng thể
   - Nhiều khoản/tổng quan → get_all_ld
   - Một khoản cụ thể → get_ld_info
   - Tổng hợp nợ quá hạn → get_total_overdue_debt

2. **Thời gian tham chiếu**: Quá khứ vs tương lai vs hiện tại
   - Lịch sử đã thực hiện → get_ld_payment_schedule 
   - Kế hoạch sắp tới → get_ld_payment_schedule
   - Trạng thái hiện tại → get_ld_info

3. **Loại thông tin**: Chi tiết vs khả năng vs danh sách
   - Thông tin chi tiết → get_ld_info
   - Danh sách thấu chi → get_ac_overdraft_list

4. **Tính chất yêu cầu**: Truy vấn vs thao tác vs tư vấn
   - Truy vấn thông tin hiện có → các intent get_*
   - Thao tác mới (vay mới, thay đổi) → out_of_scope
   - Tư vấn chung → out_of_scope

⚠️ ĐẶC BIỆT LƯU Ý:
- "Nợ quá hạn" vs "thông tin khoản vay" là khác nhau
- "Thấu chi" là dạng tín dụng đặc biệt, khác với khoản vay thường

PHÂN TÍCH NGỮ CẢNH:
═══════════════════════════════════════════════════════════════════════════════
Ngữ cảnh hội thoại: {{conversation_summary}}
Tin nhắn gần đây: {{recent_messages}}
Câu hỏi hiện tại: {{query}}

Trả về intent name duy nhất:
<intent>get_all_ld/get_ld_info/get_ld_payment_schedule/get_ac_overdraft_list/get_total_overdue_debt/out_of_scope/chitchat</intent>
"""
