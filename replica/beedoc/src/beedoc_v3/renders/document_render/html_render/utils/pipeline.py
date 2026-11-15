"""Các hàm xử lý để CodeNode gọi trong workflow HTML."""

from pathlib import Path

from beedoc_v3.utils.encoding import detect_html_encoding

from .converter import _protect_images, _validate_tables
from .processor import render_blocks_to_markdown


def prepare_html_source(file_path: str) -> dict:
    raw = Path(file_path).read_bytes()
    # Giữ logic nhận diện encoding của bản gốc; lỗi giải mã không bị bỏ qua.
    html = raw.decode(detect_html_encoding(raw))
    _validate_tables(html)
    protected, images = _protect_images(html)
    return {"normalized_raw_content": protected, "image_tags": images}


def render_html_source(html_payload: dict, image_tags: dict) -> dict:
    result = render_blocks_to_markdown(html_payload)
    markdown = result["reconstructed_content"]
    for token, raw_tag in image_tags.items():
        markdown = markdown.replace(token, raw_tag)
    return {"reconstructed_content": markdown}
