import requests
import json

from beegenerate.loggings import LOGGER


url = "http://10.1.87.71:30043/rerank"
api_key = 'mb123456789'

payload = json.dumps({
    "model": "model/bge-reranker-v2-m3",
    "query": "Tổng giám đốc MB là ai",
    "documents": [
        """Ban điều hành của MB:
- năm 2022, Ông Lưu Trung Thái là Phó chủ tịch HĐQT kiêm Tổng giám đốc
- năm 2023, Ông Phạm Như Ánh là Tổng giám đốc""",
        """Sự thay đổi về nhân sự cấp cao của ngân hàng MB:
Thay đổi về nhân sự trong Hội đồng quản trị và Ban điều hành: Năm 2023, MB có sự chuyển giao Chủ tịch HĐQT: Theo nguyện vọng cá nhân, Ông Lê Hữu Đức đã xin từ nhiệm vị trí Chủ tịch HĐQT và thôi là Thành viên HĐQT MB. Theo đó, HĐQT đã bầu Ông Lưu Trung Thái giữ vị trí Chủ tịch HĐQT MB từ 12/04/2023 và trong thời gian còn lại của nhiệm kỳ 2019 - 2024. Ông Phạm Như Ánh được bổ nhiệm Phó Tổng Giám Đốc phụ trách Ban Điều hành từ ngày 12/4/2023 và Tổng Giám đốc từ ngày 18/5/2023""",
        """Thông điệp của tổng giám đốc năm 2022:
Năm 2022, tiếp tục kiên định, bám sát mục tiêu chiến lược "Top 3 thị trường về hiệu quả, hướng đến Top đầu Châu Á" MB chú trọng tổ chức hoạt động kinh doanh an toàn, bền vững mọi mặt hoạt động của Ngân hàng, Tập đoàn. Từ triển khai kinh doanh an toàn, hiệu quả, chú trọng đời sống và sức khỏe cho cán bộ nhân viên, đảm bảo quyền lợi của các cổ đông, nhà đầu tư và tăng giá trị mới cho khách hàng đến trách nhiệm với cộng đồng, xã hội.""",
        """Chủ tịch hội đồng quản trị:
- năm 2022, Ông Lê Hữu Đức là Chủ tịch Hội đồng quản trị
- năm 2023, Ông Lưu Trung Thái là Chủ tịch Hội đồng quản trị""",
        """Thông điệp của chủ tịch hội đồng quản trị năm 2023:
Năm 2024 là một năm đặc biệt khi MB đón chào tuổi 30 với những thử thách lớn hơn và giấc mơ lớn hơn với thông điệp Move for Big – Tiến bước vững vàng. Đồng thời, cũng là năm nhiệm kỳ mới HĐQT, BKS giai đoạn 2024 – 2029. Theo đó, MB đặt ra các mục tiêu cụ thể là: Top 3 ngân hàng về hiệu quả và an toàn, phấn đấu lợi nhuận trước thuế Tập đoàn đạt 30 nghìn tỷ đồng, chinh phục cột mốc 30 triệu khách hàng. Ngân hàng MB sẽ triển khai nhiều chương trình, dự án hướng đến các nhóm đối tượng: Đất nước và Cộng đồng: Move for Big Vietnam – Tiến bước vì một Việt Nam hùng cường; CBNV: Move for Big Ambition - Tiến bước Diệu kỳ; Khách hàng: Move for Big Generation - Tiến bước Thành công. Đồng thời, MB sẽ tiếp tục hoàn thiện và triển khai mạnh mẽ, tối ưu các Sáng kiến Chiến lược thuộc Chiến lược tập đoàn giai đoạn 2022 - 2026, đẩy mạnh "Hiệp lực Tập đoàn"."""
             ]
})
headers = {
    'Authorization': f'Bearer {api_key}',
    'Content-Type': 'application/json'
}

response = requests.request("POST", url, headers=headers, data=payload)
LOGGER.info(response.json())