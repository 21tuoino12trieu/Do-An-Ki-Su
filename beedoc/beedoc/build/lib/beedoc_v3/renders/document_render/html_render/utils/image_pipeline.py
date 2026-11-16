from __future__ import annotations

import base64
import binascii
import copy
import re
from html import escape
from typing import Any, Dict, Iterator, List, Optional

DATA_IMAGE_RE = re.compile(
    r"^data:image/(?P<format>[a-zA-Z0-9.+-]+);base64,(?P<data>.+)$", re.DOTALL,
)
HTML_ATTRIBUTE_NAME_RE = re.compile(r"^[A-Za-z_:][A-Za-z0-9:._-]*$")


def render_image_output(
    extracted_text: str = "",
    html_attrs: Optional[Dict[str, Any]] = None,
) -> str:
    extracted = str(extracted_text or "").strip()
    if extracted:
        return extracted

    attributes: List[str] = []
    for raw_name, raw_value in (html_attrs or {}).items():
        name = str(raw_name or "").strip()
        if not HTML_ATTRIBUTE_NAME_RE.fullmatch(name) or name.lower() == "src":
            continue
        if raw_value is None:
            attributes.append(name)
        else:
            attributes.append(f"{name}='{escape(str(raw_value), quote=True)}'")
    suffix = f" {' '.join(attributes)}" if attributes else ""
    return f"<img{suffix}>"


def build_gate_lookup(gate_results: Any) -> Dict[str, str]:
    lookup: Dict[str, str] = {}
    for item in gate_results or []:
        if not isinstance(item, dict):
            continue
        result = item.get("gate_result", item)
        if not isinstance(result, dict):
            continue
        image_id = str(result.get("image_id") or "").strip()
        if not image_id:
            continue
        lookup[image_id] = str(result.get("extracted") or "").strip()
    return lookup


def normalize_image_format(image_format: str) -> str:
    normalized = str(image_format or "").lower().strip()
    if normalized == "jpg":
        return "jpeg"
    if normalized in {"jpeg", "png", "gif", "bmp", "webp", "svg", "svg+xml"}:
        return normalized
    return "png"


def parse_data_image_source(src: str) -> Dict[str, Any]:
    match = DATA_IMAGE_RE.match((src or "").strip())
    result: Dict[str, Any] = {
        "image_base64": "",
        "image_format": None,
    }
    if not match:
        return result

    image_base64 = re.sub(r"\s+", "", match.group("data") or "")
    if not image_base64:
        return result

    try:
        base64.b64decode(image_base64, validate=True)
    except (binascii.Error, ValueError):
        return result

    result.update(
        {
            "image_base64": image_base64,
            "image_format": normalize_image_format(match.group("format")),
        }
    )
    return result


def resolve_image_source(src: str) -> Dict[str, Any]:
    clean_src = (src or "").strip()
    result: Dict[str, Any] = {
        "image_base64": "",
        "image_format": None,
    }
    if not clean_src:
        return result

    data_image = parse_data_image_source(clean_src)
    if data_image["image_base64"]:
        result.update(data_image)
    return result


def iter_blocks(blocks: List[Dict[str, Any]]) -> Iterator[Dict[str, Any]]:
    for block in blocks:
        if not isinstance(block, dict):
            continue
        yield block
        yield from iter_blocks(list(block.get("children") or []))
        for nested in block.get("nested_blocks") or []:
            if not isinstance(nested, dict):
                continue
            nested_block = nested.get("block")
            if isinstance(nested_block, dict):
                yield from iter_blocks([nested_block])
        for row in block.get("rows") or []:
            if not isinstance(row, dict):
                continue
            for cell in row.get("cells") or []:
                if not isinstance(cell, dict):
                    continue
                yield from iter_blocks(list(cell.get("blocks") or []))


def resolve_html_images(parsed_html_payload: Any = None,) -> Dict[str, Any]:
    payload = copy.deepcopy(
        parsed_html_payload if isinstance(parsed_html_payload, dict) else {}
    )
    blocks = list(payload.get("blocks") or [])
    batch_data: List[Dict[str, Any]] = []
    image_index = 0

    for block in iter_blocks(blocks):
        if block.get("type") != "image":
            continue

        image_index += 1
        image_id = f"html_image_{image_index}"
        attrs = block.setdefault("attrs", {})
        attrs["image_id"] = image_id
        image_source = str(attrs.get("src") or "")
        resolved = resolve_image_source(image_source)
        if resolved["image_base64"]:
            batch_data.append(
                {
                    "image_id": image_id,
                    "image_base64": resolved["image_base64"] or "",
                    "image_format": resolved["image_format"] or "png",
                }
            )
    payload["blocks"] = blocks
    return {
        "html_payload": payload,
        "image_batch_data": batch_data,
    }


def finalize_html_images(
    resolved_html_payload: Any = None, gate_results: Any = None,
) -> Dict[str, Any]:
    payload = copy.deepcopy(
        resolved_html_payload if isinstance(resolved_html_payload, dict) else {}
    )
    gate_lookup = build_gate_lookup(gate_results)

    for block in iter_blocks(list(payload.get("blocks") or [])):
        if block.get("type") != "image":
            continue

        attrs = block.setdefault("attrs", {})
        image_id = str(attrs.pop("image_id", "") or "")
        extracted_text = gate_lookup.get(image_id, "")
        if extracted_text:
            attrs["gate_extracted_text"] = extracted_text
            continue

        attrs.pop("gate_extracted_text", None)
        attrs.pop("src", None)

    return {
        "html_payload": payload,
    }


def prepare_image_gate_prompt(
    image_id: str, image_format: str = "png", image_base64: str = "",
) -> Dict[str, Any]:
    from beedoc_v3.renders.utils.vlm_image_gate import build_image_gate_messages

    image_bytes = base64.b64decode(image_base64, validate=True)
    messages = build_image_gate_messages("", image_bytes, image_format or "png")
    return {
        "messages": messages,
        "payload": {"image_id": image_id},
    }


def collect_image_gate_result(content: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    from beedoc_v3.renders.utils.vlm_image_gate import parse_image_gate_response

    extracted = parse_image_gate_response(content or "")
    return {
        "gate_result": {"image_id": payload.get("image_id"), "extracted": extracted,}
    }
