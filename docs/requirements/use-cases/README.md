# Sơ đồ Use Case và hướng dẫn chỉnh sửa

[← Đặc tả yêu cầu](../README.md)

- Bộ sơ đồ gồm tổng quan, nhân viên, khách hàng và quản trị.
- Tác nhân dùng hình người; quan hệ sử dụng dùng mũi tên thẳng.
- Hình tổng quan đặt nhân viên/khách hàng bên trái, quản trị bên phải.
- UC05: đồng bộ và cập nhật kho; UC08: trạng thái/thông báo; UC09: xử lý lại thủ công.
- Đặc tả chức năng và luồng nghiệp vụ nằm trong [SRS](../README.md), mục 7–8.
- Sửa mã PlantUML trong tài liệu này rồi xuất SVG; `.puml` được script sinh từ Markdown.

```powershell
python docs/requirements/use-cases/render_usecases.py
```

Tiện ích cần PlantUML `1.2026.9` trong cache hoặc truyền `--jar <path>`. Mặc định là `%USERPROFILE%/.codex/tmp/usecase-plantuml/plantuml-1.2026.9.jar`. Có thể tải jar từ [release chính thức](https://github.com/plantuml/plantuml/releases/tag/v1.2026.9).

Cần Java + Graphviz local hoặc Docker Desktop. Nếu dùng Docker, tiện ích dựng image renderer từ [Dockerfile](renderer/Dockerfile) khi chưa có, rồi xuất hình trong container tạm. Lần build đầu cần mạng tải dependency; không khởi động Kafka broker. Font Arial Windows được sao vào cache để chữ tiếng Việt nhất quán. Jar/font không đưa vào repo.

- Script giữ bố cục PlantUML/Graphviz và dựng liên kết SVG thành mũi tên thẳng tới cạnh elip.
- Dùng script để tái tạo sơ đồ nhất quán với mã nguồn.

## Tổng quan

![Tổng quan](diagrams/01-usecase-tong-the.svg)

<details>
<summary>Mã PlantUML</summary>

```plantuml
@startuml 01-usecase-tong-the

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
actor "Khách hàng có tài khoản" as KH
actor "Quản trị kho tri thức" as QT
rectangle "Hệ thống kho tri thức doanh nghiệp" as HT {
  usecase "UC10\nĐăng nhập và kết thúc phiên" as LOGIN
  usecase "UC01\nTìm kiếm cả hai Space" as SEARCH
  usecase "UC02\nHỏi đáp chính sách công ty" as POLICY
  usecase "UC11\nHỏi đáp chương trình khuyến mãi" as PROMO
  usecase "UC03\nXem và kiểm chứng nguồn được phép" as SOURCE
  usecase "UC04\nCấu hình nguồn và phạm vi" as CONFIG
  usecase "UC05\nThu thập và đồng bộ" as SYNC
  usecase "UC08\nTheo dõi trạng thái và lịch sử xử lý" as STATUS
  usecase "UC09\nXử lý lại công việc lỗi" as RETRY
}
NV --> LOGIN
NV --> SEARCH
NV --> POLICY
NV --> PROMO
NV --> SOURCE
KH --> LOGIN
KH --> PROMO
KH --> SOURCE
LOGIN <-- QT
SEARCH <-- QT
POLICY <-- QT
PROMO <-- QT
SOURCE <-- QT
CONFIG <-- QT
SYNC <-- QT
STATUS <-- QT
RETRY <-- QT
@enduml
```

</details>

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
NV --> N03
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
  usecase "UC10\nĐăng nhập bằng tài khoản khách hàng" as K10
  usecase "UC11\nHỏi đáp chương trình khuyến mãi" as K11
  usecase "UC03\nXem nguồn khuyến mãi được phép" as K03
}
KH --> K10
KH --> K11
KH --> K03
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
rectangle "Chức năng quản trị sau xác thực" as ADMIN {
  usecase "UC10\nĐăng nhập và kết thúc phiên" as A10
  usecase "UC01\nTìm kiếm cả hai Space" as A01
  usecase "UC02\nHỏi đáp chính sách" as A02
  usecase "UC11\nHỏi đáp khuyến mãi" as A11
  usecase "UC03\nXem nguồn cả hai Space" as A03
  usecase "UC04\nCấu hình hai Space và ánh xạ phạm vi" as A04
  usecase "UC05\nChạy thu thập và đồng bộ" as A05
  usecase "UC08\nTheo dõi trạng thái xử lý" as A08
  usecase "UC09\nYêu cầu xử lý lại lỗi" as A09
}
QT --> A10
QT --> A01
QT --> A02
QT --> A11
QT --> A03
QT --> A04
QT --> A05
QT --> A08
QT --> A09
@enduml
```

</details>
