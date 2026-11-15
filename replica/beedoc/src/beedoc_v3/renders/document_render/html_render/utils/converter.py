"""Giao diện chuyển đổi; không có I/O mạng, model hoặc trạng thái toàn cục."""

from html.parser import HTMLParser

from bs4 import BeautifulSoup

from .processor import parse_html_to_structure, render_blocks_to_markdown


class ConversionError(ValueError):
    """Đầu vào không hợp lệ hoặc quá trình chuyển đổi thất bại."""


class UnsupportedHtmlError(ConversionError):
    """HTML chứa cấu trúc bảng nằm ngoài phạm vi hỗ trợ."""


class _ImageLocator(HTMLParser):
    """Ghi vị trí thẻ ảnh thật; bỏ qua chuỗi giả trong comment/script."""

    def __init__(self, source: str):
        super().__init__(convert_charrefs=False)
        self.offsets = [0]
        for index, char in enumerate(source):
            if char == "\n":
                self.offsets.append(index + 1)
        self.images: list[tuple[int, str]] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag == "img":
            line, column = self.getpos()
            self.images.append((self.offsets[line - 1] + column, self.get_starttag_text()))

    def handle_startendtag(self, tag: str, attrs: list) -> None:
        self.handle_starttag(tag, attrs)


def _protect_images(html: str) -> tuple[str, dict[str, str]]:
    locator = _ImageLocator(html)
    locator.feed(html)
    locator.close()
    prefix = "BEEDOCIMAGETOKEN"
    while prefix in html:
        prefix += "X"
    parts = []
    replacements = {}
    cursor = 0
    for index, (offset, raw_tag) in enumerate(locator.images):
        token = f"{prefix}{index}END"
        parts.extend((html[cursor:offset], token))
        replacements[token] = raw_tag
        cursor = offset + len(raw_tag)
    parts.append(html[cursor:])
    return "".join(parts), replacements


def _validate_tables(html: str) -> None:
    soup = BeautifulSoup(html, "html.parser")
    for table in soup.find_all("table"):
        if table.find("table") is not None:
            raise UnsupportedHtmlError("Không hỗ trợ bảng lồng nhau.")
        widths = set()
        for row in table.find_all("tr"):
            cells = row.find_all(["th", "td"], recursive=False)
            if not cells:
                continue
            widths.add(len(cells))
            for cell in cells:
                if any(str(cell.get(key, "1")).strip() != "1" for key in ("rowspan", "colspan")):
                    raise UnsupportedHtmlError("Không hỗ trợ bảng gộp ô.")
        if len(widths) > 1:
            raise UnsupportedHtmlError("Bảng phải có cùng số cột ở mỗi hàng.")


def convert_html(html: str) -> str:
    """Nhận HTML đã giải mã, trả Markdown; chuỗi rỗng hợp lệ trả chuỗi rỗng.

    Giữ nguyên từng thẻ img, kể cả cách viết thuộc tính. HTML sai cú pháp nhẹ
    được html.parser phục hồi; hàm này không phải bộ kiểm định/sanitizer HTML.
    """
    if not isinstance(html, str):
        raise ConversionError("Đầu vào phải là chuỗi HTML đã giải mã.")
    if not html.strip():
        return ""
    try:
        _validate_tables(html)
        protected, images = _protect_images(html)
        payload = parse_html_to_structure(protected)["html_payload"]
        markdown = render_blocks_to_markdown(payload)["reconstructed_content"]
        for token, raw_tag in images.items():
            markdown = markdown.replace(token, raw_tag)
        return markdown
    except ConversionError:
        raise
    except Exception as exc:
        raise ConversionError("Chuyển HTML sang Markdown thất bại.") from exc
