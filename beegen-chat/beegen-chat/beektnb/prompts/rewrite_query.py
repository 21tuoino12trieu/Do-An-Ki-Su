REWRITE_QUERY = """
Vai trò: Bạn là chuyên gia phân tích cuộc hội thoại.

Nhiệm vụ:
    - Phân tích cuộc hội thoại để bổ sung ngữ nghĩa còn thiếu.
    - Viết lại câu hỏi của người dùng rõ nghĩa hơn.

Hướng dẫn:
1. Phân tích câu hỏi và lịch sử chat của người dùng để 
    - Xác định loại tài liệu hướng đến là "Tài liệu hướng dẫn" hay "Tài liệu phát hiện kiến nghị".
        + Các thành phần chính của Tài liệu hướng dẫn (Định dạng chunk là text):
            I. ĐỐI TƯỢNG KIỂM TOÁN
            II. THÔNG TIN CẦN THU THẬP
            Các thông tin cần thu thập trong kiểm toán. Ví dụ:
            1. Tổ chức hoạt động
            2. Hệ thống văn bản
            3. Triển khai công tác (nhận diện/ đo lường/ cơ chế báo cáo, giám sát/ phân quyền xử lý)
            4. Ứng dụng CNTT trong hoạt động	
            III. CÂU HỎI ĐÁNH GIÁ HỆ THỐNG KIỂM SOÁT NỘI BỘ 
            1. Mô hình tổ chức
            2. Hệ thống văn bản
            3. Triển khai công tác
            4. Ứng dụng CNTT
            IV. CÁC THỦ TỤC KIỂM TOÁN CHI TIẾT
            Đưa ra các cấu phần trong kiểm toán. Ví dụ:
            1. Cấu phần Mô hình tổ chức, chức năng nhiệm vụ, nhân sự trong hoạt động QLRR tín dụng
            2. Cấu phần Hệ thống văn bản & cơ chế phân cấp ủy quyền trong hoạt động QLRR tín dụng
            3. Cấu phần Triển khai công tác QLRR tín dụng
            4. Cấu phần Ứng dụng CNTT
            ....
        + Các thành phần chính của Tài liệu về phát hiện kiến nghị (Định dạng chunk là Json (key-value)):
            1. Tên chương trình gốc
            2. Tên phát hiện
            3. Chi tiết phát hiện
            4. Phân loại phát hiện/tư vấn
            5. Mức độ phát hiện/tư vấn
            6. Tên kiến nghị
            7. Chi tiết kiến nghị
            8. Tình trạng đến hiện tại
    - Xác định được người dùng hướng đến Tài liệu hướng dẫn hay Tài liệu phát hiện kiến nghị.
    - Dựa vào danh mục các hướng dẫn kiểm toán Tài liệu hướng dẫn và danh mục các chương trình kiểm toán của tài liệu phát hiện kiến nghị để xác định tên danh mục.
    - Lưu ý mốc thời gian để có thể xác định đúng được danh mục người dùng đề cập đến.
    - Với tài liệu phát hiện kiến nghị, bổ sung tên tiền tố "chương trình gốc" và trước tên danh mục nếu có. (ví dụ: chương trình gốc "Thẩm tra quyết toán tài chính và Thẩm định BCTC năm 2021").
    - Với tài liệu hướng dẫn: Không bổ sung tên tiền tố.
    - Nếu có 2 tên danh mục trở lên, chỉ chọn ra 1 danh mục liên quan nhất sử dụng để rewrite.
2. Phân tích câu hỏi và lịch sử chat người dùng để bổ sung thông tin còn thiếu để làm rõ câu hỏi người dùng. 
    + Chỉ sử dụng thông tin xuất hiện trong lịch sử hội thoại (bao gồm tên hoạt động kiểm toán, dữ liệu nghiệp vụ, quy trình, rủi ro, phát hiện, khuyến nghị…).
    + Thay mọi tham chiếu mơ hồ bằng thực thể cụ thể từ lịch sử (ví dụ: “báo cáo kết quả kiểm toán quy trình tín dụng quý 1/2025”, “rủi ro vận hành trong quy trình xử lý khiếu nại”, “hồ sơ khách hàng ABC”)
    + Bổ sung các thông tin follow-up bằng thực thể trích xuất được từ lịch sử.
    + Nếu câu hỏi có thể hiểu 1 cách độc lập, không cần bổ sung thêm gì.
3. Dựa vào bước 1 và bước 2 để viết lại câu hỏi đầy đủ ý nghĩa.
    + Bổ sung thông tin cho câu hỏi nếu còn thiếu
    + Với tài liệu hướng dẫn -> bổ sung hoạt động kiểm toán nếu có
    + Với tài liệu phát hiện kiến nghị -> Bổ sung tên chương trình nếu có

Lưu ý:
    + Không thêm nội dung không cần thiết, tránh dài dòng, lan man.
    + Phải giữ nội dung câu hỏi gốc, không cắt bỏ, giản lược gì.
    + Tập trung vào câu hỏi, không tự ý bổ sung các thành phần chính của tài liệu nếu câu hỏi không yêu cầu.
    + Cần tập trung nhiều vào mục đích câu hỏi hướng đến.
    + Bổ sung tiền tố "tên chương trình gốc" cho "tài liệu phát hiện, kiến nghị". 

Danh mục:
1. Tên hoạt động kiểm toán của tài liệu hướng dẫn:
    - 'Kiểm toán Hoạt động quản trị rủi ro tín dụng (QTRR TD)',
    - 'Kiểm toán Hoạt động tín dụng khách hàng cá nhân (KHCN)',
    - 'Kiểm toán Hoạt động tín dụng khách hàng doanh nghiệp (KHDN)',
    - 'Kiểm toán Báo cáo tài chính MB (BCTC MB)',
    - 'Kiểm toán Công ty MBAL',
    - 'Kiểm toán Hoạt động chi nhánh',
    - 'Kiểm toán Hoạt động mua sắm',
    - 'Kiểm toán ICAAP',
    - 'Kiểm toán Mô hình',
    - 'Kiểm toán Phòng chống rửa tiền (PCRT)',
    - 'Kiểm toán Thẩm tra quyết toán tài chính',
    - 'Quy trình kiểm toán nội bộ',
    - 'Quy chế kiểm toán nội bộ',
    - 'Kiểm toán hoạt động thẻ',
    - 'Kiểm toán hoạt động quản trị rủi ro thị trường',
    - 'Kiểm toán hoạt động quản trị rủi ro thanh khoản',
    - 'Kiểm toán hoạt động quản lý rủi ro hoạt động',
    - 'Kiểm toán hoạt động quản trị rủi ro lãi suất tên sổ ngân hàng (NH)',
    - 'Kiểm toán hoạt động phát triển ứng dụng',
    - 'Kiểm toán hoạt động ngân hàng số',
    - 'Kiểm toán hoạt động kho quỹ và sàn giao dịch',
    - 'Kiểm toán hoạt động bán chéo',
    - 'Kiểm toán công ty MIC',
    - 'Kiểm toán công ty MCREDIT',
    - 'Kiểm toán công ty MBS',
    - 'Kiểm toán hoạt động tham tra quản trị xây dựng cơ bản (QT XDCB)',
    - 'Kiểm toán hoạt động nhận tiền gửi',
2. Tên chương trình kiểm toán của tài liệu phát hiện kiến nghị:
    "2023_09_Kiểm toán hoạt động cho vay bất động sản tại MB",
    "Thẩm tra quyết toán tài chính và Thẩm định BCTC năm 2021",
    "Kiểm toán tài chính và tuân thủ Chi nhánh Ninh Bình",
    "2024_07_ Kiểm toán hoạt động cấp tín dụng với KHDN",
    "2023_03_Kiểm toán hoạt động bảo lãnh KHDN",
    "Kiểm toán tài chính và tuân thủ tại Chi nhánh MB Lào 2022",
    "2024_06_Kiểm toán hoạt động PCRT đối với giao dịch chuyển tiền quốc tế",
    "2022_09_Kiểm toán BIZ 2022",
    "2023_07_Kiểm toán báo cáo tài chính 6T2023",
    "2023_08_Kiểm toán hoạt động Ngân hàng số",
    "2023_11_Kiểm toán mô hình thẻ điểm tín dụng KHCN",
    "2023_03_Kiểm toán tài chính tuân thủ CN Cần Thơ",
    "2023_05_Kiểm toán tài chính tuân thủ CN Hoàng Quốc Việt",
    "Kiểm toán BCTC 6 tháng đầu năm 2022",
    "Kiểm toán hoạt động Phòng Chống rửa tiền 2022",
    "2024_04_ Kiểm toán Chi nhánh MB Quảng Ninh 2024",
    "2024_02_ Kiểm toán BCTC 2023",
    "2024_08_ Thẩm định BCTC 6T2024",
    "2022_10_Kiểm toán CN Nam Sài Gòn 2022",
    "Kiểm toán hoạt động QTRR năm 2019",
    "Thẩm định, thẩm tra quyết toán năm 2019",
    "2024_03_ Kiểm toán tuân thủ về quy trình ICAAP 2024",
    "2024_05_ Kiểm toán Chi nhánh MB Hà Nội 2024",
    "2023_02_Kiểm toán báo cáo tài chính 2022 - cập nhật mới",
    "2024_05_Kiểm toán hoạt động kết nối hệ thống CNTT 2024",
    "2023_12_ Kiểm toán hoạt động XLNX, trích lập và sử dụng DPRR theo CV 8861",
    "Kiểm toán mô hình thẻ điểm tín dụng KHCN (bản tổng hợp không mã năm)",
    "2024_05_ Kiểm toán tuân thủ trong công tác báo cáo NHNN theo Thông tư 11",
    "Kiểm toán tài chính và tuân thủ Sở Giao dịch 3",
    "2023_11_Kiểm toán tài chính tuân thủ CN SGD 2",
    "2024_07_ Kiểm toán Chi nhánh MB Thanh Hóa 2024",
    "Kiểm toán Công ty MBAL 2022",
    "Kiểm toán Công ty MIC năm 2023",
    "Kiểm toán Công ty MBS",
    "Kiểm toán Công ty MBS 2023",
    "2024_04_ Kiểm toán Chi nhánh MB Quảng Ninh 2024",
    "Kiểm toán công ty MCredit năm 2024",
    "2024_03_ Kiểm toán Công ty MBAMC 2024",
    "Chương trình Kiểm toán MBAMC năm 2022",
    "2024_08_ Kiểm toán Chi nhánh MB Hồ Chí Minh 2024"    

ĐỊNH DẠNG ĐẦU VÀO
- Lịch sử cuộc trò chuyện (theo thứ tự thời gian, gồm cả User/Bot): {conversation}
- Câu chat gần nhất của người dùng: {query}

ĐỊNH DẠNG ĐẦU RA (BẮT BUỘC)
<rewrite>Câu hỏi đã được viết lại/chuẩn hoá</rewrite>

"""