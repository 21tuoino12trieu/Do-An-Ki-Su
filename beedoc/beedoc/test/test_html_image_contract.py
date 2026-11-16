from beedoc_v3.renders.document_render.html_render.utils.image_pipeline import (
    finalize_html_images,
    resolve_html_images,
)
from beedoc_v3.renders.document_render.html_render.utils.processor import (
    parse_html_to_structure,
    render_blocks_to_markdown,
)


def _parse_image() -> dict:
    html = (
        '<img data-image-id="asset-123" alt="Chart" width="640" '
        'class="hero responsive" data-owner="documents" '
        'src="data:image/png;base64,aGVsbG8=">'
    )
    return parse_html_to_structure(html)["html_payload"]


def test_unextracted_image_keeps_business_id_without_src() -> None:
    resolved = resolve_html_images(_parse_image())["html_payload"]
    finalized = finalize_html_images(
        resolved,
        [{"gate_result": {"image_id": "html_image_1", "extracted": ""}}],
    )["html_payload"]

    markdown = render_blocks_to_markdown(finalized)["reconstructed_content"]

    assert markdown == (
        "<img data-image-id='asset-123' alt='Chart' width='640' "
        "class='hero responsive' data-owner='documents'>"
    )
    assert "src=" not in markdown


def test_extracted_image_is_replaced_by_vlm_content() -> None:
    resolved = resolve_html_images(_parse_image())["html_payload"]
    finalized = finalize_html_images(
        resolved,
        [
            {
                "gate_result": {
                    "image_id": "html_image_1",
                    "extracted": "Extracted chart content",
                }
            }
        ],
    )["html_payload"]

    markdown = render_blocks_to_markdown(finalized)["reconstructed_content"]

    assert markdown == "Extracted chart content"
