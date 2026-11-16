"""
table_detector.py
-----------------
Detect markdown tables from a raw markdown string.

Public API:
    detect_tables(markdown_text: str) -> list[str]
        Trả về list các table string (mỗi phần tử là 1 table markdown hoàn chỉnh).
"""

import re
import textwrap
from pathlib import Path


# Markdown table pattern:
#   - exactly 1 header row
#   - 1 separator row (| :--- | --- | ... |)
#   - 1+ data rows
_TABLE_RE = re.compile(
    r'(^[ \t]*\|[^\n]+\|[ \t]*\n'                 # header row
    r'^[ \t]*\|[ \t]*:?-{3,}:?[ \t]*(?:\|[ \t]*:?-{3,}:?[ \t]*)+\|?[ \t]*\n'  # separator
    r'(?:^[ \t]*\|[^\n]+\|[ \t]*\n)+)',           # data rows
    re.MULTILINE,
)


def detect_tables(markdown_text: str) -> list[str]:
    """
    Nhận vào một đoạn markdown text.
    Trả về list[str], mỗi phần tử là một markdown table hoàn chỉnh (bao gồm header + separator + data rows).

    Ví dụ:
        tables = detect_tables(markdown_text)
        # tables[0] -> "| col1 | col2 |\\n| --- | --- |\\n| val1 | val2 |\\n"
    """
    normalized = textwrap.dedent(markdown_text).strip()
    if normalized and not normalized.endswith("\n"):
        normalized += "\n"
    return [m.group(0) for m in _TABLE_RE.finditer(normalized)]


def main() -> None:
    sample_markdown = """
anag ddg sd
asdf adsf a

afs af 

fas 

    
| Thông tin chung | <merged> Thông tin chung | <merged> Thông tin chung | <merged> Thông tin chung | <merged> Thông tin chung | <merged> Thông tin chung |
| :--- | :--- | :--- | :--- | :--- | :--- |
| QR động | KH thanh toán mua hàng tại hệ thống của hàng Yody, thay vì việc KH thanh toán bằng tiền mặt/thẻ KH có thể quét mã QR động từ các APP Ngân hàng, giao dịch sau khi thực hiện thành công, tiền được ghi có ngay vào tài khoản của siêu thị. | <merged> KH thanh toán mua hàng tại hệ thống của hàng Yody, thay vì việc KH thanh toán bằng tiền mặt/thẻ KH có thể quét mã QR động từ các APP Ngân hàng, giao dịch sau khi thực hiện thành công, tiền được ghi có ngay vào tài khoản của siêu thị. | <merged> KH thanh toán mua hàng tại hệ thống của hàng Yody, thay vì việc KH thanh toán bằng tiền mặt/thẻ KH có thể quét mã QR động từ các APP Ngân hàng, giao dịch sau khi thực hiện thành công, tiền được ghi có ngay vào tài khoản của siêu thị. | <merged> KH thanh toán mua hàng tại hệ thống của hàng Yody, thay vì việc KH thanh toán bằng tiền mặt/thẻ KH có thể quét mã QR động từ các APP Ngân hàng, giao dịch sau khi thực hiện thành công, tiền được ghi có ngay vào tài khoản của siêu thị. | <merged> KH thanh toán mua hàng tại hệ thống của hàng Yody, thay vì việc KH thanh toán bằng tiền mặt/thẻ KH có thể quét mã QR động từ các APP Ngân hàng, giao dịch sau khi thực hiện thành công, tiền được ghi có ngay vào tài khoản của siêu thị. |
| <merged> QR động | QR động là mã QR gắn thông tin riêng của mã hóa đơn KH đã mua hàng, mỗi hóa đơn có 1 mã QR riêng. | <merged> QR động là mã QR gắn thông tin riêng của mã hóa đơn KH đã mua hàng, mỗi hóa đơn có 1 mã QR riêng. | <merged> QR động là mã QR gắn thông tin riêng của mã hóa đơn KH đã mua hàng, mỗi hóa đơn có 1 mã QR riêng. | <merged> QR động là mã QR gắn thông tin riêng của mã hóa đơn KH đã mua hàng, mỗi hóa đơn có 1 mã QR riêng. | <merged> QR động là mã QR gắn thông tin riêng của mã hóa đơn KH đã mua hàng, mỗi hóa đơn có 1 mã QR riêng. |
| STK/Tên đơn vị thụ hưởng | 6401348842260 | <merged> 6401348842260 | <merged> 6401348842260 | <merged> 6401348842260 | <merged> 6401348842260 |
| <merged> STK/Tên đơn vị thụ hưởng | CONG TY CO PHAN THOI TRANG YODY | <merged> CONG TY CO PHAN THOI TRANG YODY | <merged> CONG TY CO PHAN THOI TRANG YODY | <merged> CONG TY CO PHAN THOI TRANG YODY | <merged> CONG TY CO PHAN THOI TRANG YODY |
| Hướng dẫn xử lý các trường hợp | <merged> Hướng dẫn xử lý các trường hợp | <merged> Hướng dẫn xử lý các trường hợp | <merged> Hướng dẫn xử lý các trường hợp | <merged> Hướng dẫn xử lý các trường hợp | <merged> Hướng dẫn xử lý các trường hợp |
| Danh sách cửa hàng & SĐT | Thông tin cửa hàng Yody.xlsx | <merged> Thông tin cửa hàng Yody.xlsx | <merged> Thông tin cửa hàng Yody.xlsx | <merged> Thông tin cửa hàng Yody.xlsx | <merged> Thông tin cửa hàng Yody.xlsx |
| <merged> Danh sách cửa hàng & SĐT | Tên cửa hàng | Tên viết tắt | SĐT (Cố định hoặc di động, ưu tiên ĐT cố định của cửa hàng) | Full địa chỉ | TerminalID |
| <merged> Danh sách cửa hàng & SĐT | Yody Admin |  | 397918995 | 90 Đ. Nguyễn Tuân, Thanh Xuân Trung, Thanh Xuân, Hà Nội |  |
| <merged> Danh sách cửa hàng & SĐT | YODY Quy Nhơn 2 | YODYTQNH2 | 888589259 | Số 442a, Đường Trần Hưng Đạo, Phường Trần Hưng Đạo, Thành phố Quy Nhơn, Tỉnh Bình Định | YODY2 |
| <merged> Danh sách cửa hàng & SĐT | YODY Yên Phong | YODYYP | 911026258 | Số 284, Đường 295, Thị trấn Chờ, Yên Phong, Bắc Ninh | YODY26 |

afa sdf
afsdafasf

afsafasf

afsafasf
"""

    tables = detect_tables(sample_markdown)
    print(f"Detected tables: {len(tables)}")
    for i, table in enumerate(tables, start=1):
        output_path = Path(__file__).resolve().parent / f"detected_table_{i}.md"
        output_path.write_text(table, encoding="utf-8")
        lines = table.splitlines()
        print(f"\n--- Table {i} ---")
        print(f"Rows: {len(lines)}")
        print(f"Saved to: {output_path}")
        print("\n".join(lines[: min(4, len(lines))]))


if __name__ == "__main__":
    main()
