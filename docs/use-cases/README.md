# Sơ đồ Use Case và hướng dẫn chỉnh sửa

[← Đặc tả yêu cầu](../requirements.md)

- Bộ sơ đồ gồm ba góc nhìn theo tác nhân: nhân viên, khách hàng và quản trị.
- Tác nhân dùng hình người; liên kết tác nhân–Use Case thể hiện quyền tham gia chức năng.
- Mỗi quan hệ `«extend»` được vẽ bằng một mũi tên nét đứt riêng nối trực tiếp hai elip; không dùng đoạn đường chung hoặc điểm rẽ nhánh. Sơ đồ chỉ ghi `«extend»`; điểm mở rộng (Extension Point, viết tắt EP) và điều kiện kích hoạt được mô tả tại mục 6.4 và 7 của đặc tả.
- UC03 mở rộng UC01, UC02 và UC11 khi người dùng chọn nguồn; UC09 mở rộng UC08 khi quản trị chọn xử lý lại công việc lỗi đủ điều kiện.
- UC05: đồng bộ và cập nhật kho; UC08: trạng thái/thông báo; UC09: xử lý lại thủ công.
- Đặc tả chức năng và luồng nghiệp vụ nằm trong [SRS](../requirements.md), mục 7–8.
- Sửa mã PlantUML trong tài liệu này rồi xuất SVG; `.puml` được script sinh từ Markdown.

```powershell
python docs/use-cases/render_usecases.py
```

Tiện ích cần PlantUML `1.2026.9` trong cache hoặc truyền `--jar <path>`. Mặc định là `%USERPROFILE%/.codex/tmp/usecase-plantuml/plantuml-1.2026.9.jar`. Có thể tải jar từ [release chính thức](https://github.com/plantuml/plantuml/releases/tag/v1.2026.9).

Cần Java + Graphviz local hoặc Docker Desktop. Nếu dùng Docker, tiện ích dựng image renderer từ [Dockerfile](renderer/Dockerfile) khi chưa có, rồi xuất hình trong container tạm. Lần build đầu cần mạng tải dependency; không khởi động Kafka broker. Font Arial Windows được sao vào cache để chữ tiếng Việt nhất quán. Jar/font không đưa vào repo.

Nếu có Java nhưng không có Graphviz, dùng bộ bố trí Smetana tích hợp trong PlantUML. Java phải có trong `PATH`; có thể truyền vị trí jar bằng `--jar`:

```powershell
python docs/use-cases/render_usecases.py --smetana --jar <path-to-plantuml.jar>
```

- Tác nhân ở bên trái; chức năng chính xếp thành cột; UC03 và UC09 nằm ở cột bên phải. Đường tham gia dùng mũi tên nét liền từ tác nhân tới chức năng; quan hệ `«extend»` dùng nét đứt và đầu mũi tên mở.
- Tiện ích giữ tác nhân, elip và nhãn từ PlantUML, sắp lại vị trí và định tuyến đường nối theo từng tác nhân; không kéo đường xuyên qua elip. UC03 và UC09 được kích hoạt qua điểm mở rộng của UC gốc; không lặp lại liên kết trực tiếp từ tác nhân tới hai UC này. Quyền sử dụng vẫn theo ma trận tại mục 4 của SRS.
- Dùng script để tái tạo sơ đồ nhất quán với mã nguồn.

## Nhân viên nội bộ

![Nhân viên nội bộ](diagrams/02-usecase-nhan-vien.svg)

<details>
<summary>Mã PlantUML</summary>

```plantuml
@startuml 02-usecase-nhan-vien

left to right direction
skinparam shadowing false
skinparam linetype polyline
skinparam nodesep 45
skinparam ranksep 95
skinparam defaultFontName Arial
skinparam defaultFontSize 17
skinparam actorStyle stickman
skinparam BackgroundColor white
skinparam ArrowColor #253746
skinparam usecaseBackgroundColor #F7FAFC
skinparam usecaseBorderColor #253746
skinparam rectangleBorderColor #253746
skinparam actorBorderColor #253746
actor "Nhân viên nội bộ" as NV
rectangle "Phạm vi nhân viên · Cả hai Space" as INTERNAL {
  usecase "UC10\nĐăng nhập và kết thúc phiên" as N10
  usecase "UC01\nTìm kiếm tài liệu ở cả hai Space" as N01
  usecase "UC02\nHỏi đáp chính sách công ty" as N02
  usecase "UC11\nHỏi đáp khuyến mãi" as N11
  usecase "UC03\nXem nguồn ở cả hai Space" as N03
}
NV --> N10
NV --> N01
NV --> N02
NV --> N11
N03 ..> N01 : <<extend>>
N03 ..> N02 : <<extend>>
N03 ..> N11 : <<extend>>
@enduml
```

</details>

## Khách hàng có tài khoản

![Khách hàng có tài khoản](diagrams/03-usecase-khach-hang.svg)

<details>
<summary>Mã PlantUML</summary>

```plantuml
@startuml 03-usecase-khach-hang

left to right direction
skinparam shadowing false
skinparam linetype polyline
skinparam nodesep 45
skinparam ranksep 95
skinparam defaultFontName Arial
skinparam defaultFontSize 17
skinparam actorStyle stickman
skinparam BackgroundColor white
skinparam ArrowColor #253746
skinparam usecaseBackgroundColor #F7FAFC
skinparam usecaseBorderColor #253746
skinparam rectangleBorderColor #253746
skinparam actorBorderColor #253746
actor "Khách hàng" as KH
rectangle "Phạm vi khách hàng · Space khuyến mãi" as CUSTOMER {
  usecase "UC10\nĐăng nhập và đăng xuất" as K10
  usecase "UC11\nHỏi đáp chương trình khuyến mãi" as K11
  usecase "UC03\nXem nguồn khuyến mãi được phép" as K03
}
KH --> K10
KH --> K11
K03 ..> K11 : <<extend>>
@enduml
```

</details>

## Quản trị kho tri thức

![Quản trị kho tri thức](diagrams/04-usecase-quan-tri.svg)

<details>
<summary>Mã PlantUML</summary>

```plantuml
@startuml 04-usecase-quan-tri

left to right direction
skinparam shadowing false
skinparam linetype polyline
skinparam nodesep 45
skinparam ranksep 95
skinparam defaultFontName Arial
skinparam defaultFontSize 17
skinparam actorStyle stickman
skinparam BackgroundColor white
skinparam ArrowColor #253746
skinparam usecaseBackgroundColor #F7FAFC
skinparam usecaseBorderColor #253746
skinparam rectangleBorderColor #253746
skinparam actorBorderColor #253746
actor "Quản trị kho tri thức" as QT
rectangle "Chức năng quản trị kho tri thức" as ADMIN {
  usecase "UC10\nĐăng nhập và kết thúc phiên" as A10
  usecase "UC01\nTìm kiếm cả hai Space" as A01
  usecase "UC02\nHỏi đáp chính sách" as A02
  usecase "UC11\nHỏi đáp khuyến mãi" as A11
  usecase "UC03\nXem nguồn cả hai Space" as A03
  usecase "UC04\nCấu hình hai Space và ánh xạ phạm vi" as A04
  usecase "UC05\nChạy thu thập và đồng bộ" as A05
  usecase "UC08\nTheo dõi trạng thái và nhận thông báo" as A08
  usecase "UC09\nYêu cầu xử lý lại lỗi" as A09
}
QT --> A10
QT --> A01
QT --> A02
QT --> A11
QT --> A04
QT --> A05
QT --> A08
A03 ..> A01 : <<extend>>
A03 ..> A02 : <<extend>>
A03 ..> A11 : <<extend>>
A09 ..> A08 : <<extend>>
@enduml
```

</details>
