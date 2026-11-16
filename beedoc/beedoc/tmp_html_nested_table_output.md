1. **[Kiểm tra trạng thái giao dịch](https://confluence.mbbank.com.vn/pages/viewpage.action?pageId=290857605#H%C6%B0%E1%BB%9Bngd%E1%BA%ABnki%E1%BB%83mtratr%E1%BA%A1ngth%C3%A1i/y%C3%AAuc%E1%BA%A7ucungc%E1%BA%A5pGBCchoGDlu%E1%BB%93ngACHtr%C3%AAnCardportal(D%C3%A0nhchoTuy%E1%BA%BFn2)-1)**
2. **[Yêu cầu cung cấp chứng từ báo có](https://confluence.mbbank.com.vn/pages/viewpage.action?pageId=290857605#H%C6%B0%E1%BB%9Bngd%E1%BA%ABnki%E1%BB%83mtratr%E1%BA%A1ngth%C3%A1i/y%C3%AAuc%E1%BA%A7ucungc%E1%BA%A5pGBCchoGDlu%E1%BB%93ngACHtr%C3%AAnCardportal(D%C3%A0nhchoTuy%E1%BA%BFn2)-2)**
3. **[Hướng dẫn kiểm tra tình trạng phê duyệt/tra soát đã được đẩy thành công hay chưa](https://confluence.mbbank.com.vn/pages/viewpage.action?pageId=290857605#H%C6%B0%E1%BB%9Bngd%E1%BA%ABnki%E1%BB%83mtratr%E1%BA%A1ngth%C3%A1i/y%C3%AAuc%E1%BA%A7ucungc%E1%BA%A5pGBCchoGDlu%E1%BB%93ngACHtr%C3%AAnCardportal(D%C3%A0nhchoTuy%E1%BA%BFn2)-3)**

| Kiểm tra trạng thái giao dịch luồng ACH |  |  |
| --- | --- | --- |
| Bước 1 | Đăng nhập vào hệ thống Cardportal theo đường dẫn: https://cardportal.mbbank.com.vn/Modules/SysAdmin/Login/frmLogin.aspx Nhập user và pass email, chọn sign in |  |
| Bước 2 | Nhấn chọn vào menu Nghiệp vụ → Nghiệp vụ đối soát → Đối soát NAPAS → Tra soát Napas |  |
| Bước 3 | Tại màn hình, tích chọn "Thêm mới ISS" trên thanh công cụ |  |
| Bước 4 | Agent thực hiện copy mã OrgData (chi tiết FT trên CEP) và paste vào trường MsgID => hệ thống sẽ tự động tích hợp các trường tương ứng còn lại: Ngày GD Số tiền GD Số tiền tra soát Ngày tra soát Ngân hàng chuyển (DeBank) NH thụ hưởng (CrBank) Trạng thái giao dịch Trạng thái quyết toán |  |
| Bước 5 | Kiểm tra Trường trạng thái quyết toán và trạng thái giao dịch tại trường và tham chiếu theo các mã sau để trả lời KH: Xem Bảng chi tiết 1 |  |
| 2. Yêu cầu cung cấp chứng từ báo có Thực hiện các bước hướng dẫn như mục 1: Kiểm tra trạng thái giao dịch, trường hợp KH yêu cầu cung cấp chứng từ báo có, Agent thực hiện nhập tiếp như sau: |  |  |
| Bước 5 | Chọn loại giao dịch tra soát: Yêu cầu cung cấp chứng từ Sau khi nhập liệu xong thông tin, tích chọn “Lưu” và “ gửi KSV” => Sau khi thực hiện gửi KSV, Agent thông báo tới Teamlead để thực hiện duyệt yêu cầu. |  |
| 3. Hướng dẫn kiểm tra tình trạng phê duyệt/tra soát đã được đẩy thành công hay chưa |  |  |
| Bước 1 | - Tại màn hình của nghiệp vụ,  thực hiện nhập liệu các thông tin tương ứng và tích chọn “tra cứu” + Loại GD tra soát: chọn loại tra soát muốn kiểm tra hoặc chọn all + Từ ngày đến ngày: chọn theo ngày GD của KH + Chiều giao dịch: chọn ISS |  |
| Bước 2 | Tại màn hình giao diện hiện ra, thực hiện kiểm tra các thông tin: Xem Bảng chi tiết 2 |  |

Bảng chi tiết 1:

| Trạng thái quyết toán - Trạng thái NHNL | Tình trạng GD | Cách thức xử lý | SLA |
| --- | --- | --- | --- |
| RJCT | GD không thành công | Thông báo KH GD đang được thực hiện đối soát nếu không thành công sẽ hoàn tiền trong tối đa 2 ngày làm việc. | 2 ngày làm việc |
| ACSP - NOAN | Giao dịch được quyết toán, nhưng chưa xác định TK thụ hưởng nhận được tiền chưa. | - Thông báo tới KH giao dịch đã được TQT. - Lập Yêu cầu cung cấp chứng từ trên hệ thống ACH để gửi sang NH thụ hưởng. | 4 ngày làm việc |
| ACSP - AUTH | Giao dịch được quyết toán, tài khoản đã được báo có | - Thông báo tới KH người thụ hưởng đã được báo có. - Trường hợp KH vẫn yêu cầu chứng từ, lập yêu cầu tra soát Yêu cầu cung cấp chứng từ trên hệ thống ACH để gửi NH thụ hưởng. | 4 ngày làm việc |
| ACSP- NOAUT | Giao dịch được quyết toán, Ngân hàng thụ hưởng không báo có được vào tài khoản KH, Ngân hàng thụ hưởng sẽ thực hiện hoàn tiền cho KH. | - Thông báo tới KH giao dịch được thanh quyết toán, nhưng Ngân hàng thụ hưởng không báo có được vào TK KH. GD sẽ được hoàn trả lại cho KH. | 4 ngày làm việc |
| ACSC | Giao dịch được hệ thống ACH xác nhận quyết toán. | - Thông báo với KH, GD sẽ được thanh quyết toán - Thực hiện lập yêu cầu tra soát Yêu cầu hoàn trả trên hệ thống ACH để gửi NH thụ hưởng | 4 ngày làm việc |

Bảng chi tiết 2:

| Loại tra soát | Để kiểm tra loại yêu cầu tra soát đã tạo |
| --- | --- |
| Trạng thái tra soát | Để kiểm tra tình trạng đã tạo thành công hay chưa và kết quả trả về. Cụ thể: + Tạo tra soát thành công: là tra soát đã được khởi tạo thành công + Trạng thái đồng ý: NHNL trả lời đồng ý yêu cầu tra soát + Trạng thái từ chối: NHNL từ chối yêu cầu tra soát + Giao dịch quá thời gian trả lời tra soát: NHNL không phản hồi yêu cầu tra soát và GD đã quá hạn |
| Trạng thái phê duyệt | Thể hiện tình trạng phê duyệt của KSV. Cụ thể: + APPROVE: KSV đã duyệt yêu cầu tra soát thành công + REJECT: KSV từ chối yêu cầu tra soát + WAIT: KSV chưa duyệt yêu cầu tra soát |
| Trạng thái lỗi Napas | Thể hiện tình trạng trả về của napas + Trạng thái thành công: OK + Trạng thái lỗi: giao diện sẽ hiện 1 mã lỗi tương ứng sinh ra từ hệ thống |
| Trạng thái gửi napas | Thể hiện tình trạng gửi tra soát sang napas thành công hay thất bại + Trạng thái thành công: 000/napas/reconsite/v1…. + Trạng thái thất bại: giao diện sẽ hiện 1 mã lỗi tương ứng sinh ra từ hệ thống |