# Quy trình tiếp nhận yêu cầu chuyển khoản

**Dữ liệu giả lập phục vụ kiểm thử đồ án.** Nội dung này không phải quy định nghiệp vụ của ngân hàng thực tế.

Mã tài liệu: `KB-DEMO-001` — Phiên bản: **1.2**<br>Ngày cập nhật giả lập: 03/11/2026.

## 1. Mục đích và phạm vi

Kiểm tra khả năng giữ nguyên tiếng Việt, dấu câu và cấu trúc khi chuyển HTML sang Markdown. Ví dụ số tiền: **1.250.000 VNĐ**; ký tự đặc biệt: A &amp; B, 5 &lt; 10.

*Lưu ý:* Chỉ dùng khách hàng và giao dịch giả lập; không đưa thông tin khách hàng thật vào bộ kiểm thử.

## 2. Các bước thực hiện

1. Tiếp nhận yêu cầu từ khách hàng giả lập.
  - Kiểm tra mã yêu cầu `DEMO-0001`.
  - Đối chiếu thông tin:
    - Người gửi: Nguyễn Văn Mẫu.
    - Người nhận: Trần Thị Thử.
2. Kiểm tra dữ liệu đầu vào.
  1. Đọc số tiền và nội dung.
  2. Ghi nhận kết quả kiểm tra.
3. Chuyển yêu cầu sang bước xử lý tiếp theo.

### 2.1. Danh sách kiểm tra

| Trường | Ví dụ | Ghi chú |
| --- | --- | --- |
| Mã yêu cầu | `DEMO-0001` | Không được trống |
| Trạng thái | Chờ \| Đang xử lý | Kiểm tra ký tự phân cách bảng |
| Nội dung | Thanh toán mẫu<br>Đợt 1 | **Chỉ dữ liệu giả** |

#### 2.1.1. Trường hợp cần bổ sung

> Nếu thiếu thông tin, yêu cầu bổ sung trước khi chuyển tiếp.

### 2.2. Bảng không có tiêu đề

|  |  |
| --- | --- |
| Kênh tiếp nhận | Cổng nội bộ giả lập |
| Người xử lý | Nhân viên demo |

## 3. Nguồn tham khảo và hình ảnh

- [Trang Confluence nội bộ](/wiki/spaces/DEMO/pages/12345)
- [Chính sách mẫu](https://example.invalid/policy?type=demo&version=1)
- [Hộp thư hỗ trợ giả lập](mailto:demo@example.invalid)

Hình minh họa giữ nguyên thẻ ảnh, không OCR hoặc mô tả bằng AI:

<img src="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='360' height='60'%3E%3Crect width='360' height='60' fill='%23dbeafe'/%3E%3Ctext x='20' y='38' font-size='20'%3EDEMO: Input - Check - Output%3C/text%3E%3C/svg%3E" alt="Sơ đồ xử lý giả lập" width="360" height="60" data-attachment-id="demo-img-01">

Ảnh tham chiếu từ Confluence (đường dẫn giả, không tải ảnh): <img src="/wiki/download/attachments/12345/demo.png" alt="Ảnh đính kèm mẫu" data-image-id="demo-img-02" />

## 4. Mẫu dữ liệu kỹ thuật

```
{
  "request_id": "DEMO-0001",
  "amount": 1250000,
  "status": "pending"
}
```

Kết thúc tài liệu kiểm thử.