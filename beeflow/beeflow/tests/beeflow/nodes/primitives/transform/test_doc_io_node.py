"""Unit tests for DocumentIONode.

Covers:
1) Processing from in-memory bytes (image).
2) Processing from a file path (image).
3) Data precedence: when both 'path' and 'data' are provided, 'data' is used.
4) specific_metadata() returns configuration info.

Notes:
- We use a tiny 1x1 PNG for reliability (no OCR required).
- We set OutputFormat.BASE64 to assert presence of base64 image data in pages.
"""

import base64
from typing import Dict, Any

import pytest

from beeflow.configs import NodeType
from beeflow.nodes import BaseNode

from beedoc.core.entities import OutputFormat, DocumentType

# Import the node under test
from beeflow.nodes.primitives.transform.doc_io_node import DocumentIONode


# A tiny 1x1 PNG (base64) used for stable tests (no external dependencies)
_PNG_1x1_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4//8/AAX+Av4N70a4AAAAAElFTkSuQmCC"
)
PNG_BYTES: bytes = base64.b64decode(_PNG_1x1_B64)


async def _execute(node: BaseNode, inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Execute a node via simulate() and return the resulting state dict."""
    return await node.simulate(inputs=inputs)


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["bytes", "path"])
async def test_document_io_process_image_base64(tmp_path, source):
    """Process an image and return base64 pages for both 'bytes' and 'path' inputs."""
    node = DocumentIONode(
        name=f"doc_{source}",
        document_type=DocumentType.IMAGE,
        output_format=OutputFormat.BASE64,
    )

    if source == "bytes":
        # When using bytes, 'path' is only for naming; it may not exist on disk.
        inputs = {"path": "inline.png", "data": PNG_BYTES}
    else:
        # Write the PNG to a real file and process by path
        p = tmp_path / "sample.png"
        p.write_bytes(PNG_BYTES)
        inputs = {"path": str(p)}

    state = await _execute(node, inputs)

    # Common assertions
    name = f"doc_{source}"
    assert (name, "document_name") in state
    assert (name, "document_type") in state
    assert (name, "document_path") in state
    assert (name, "total_pages") in state
    assert (name, "pages") in state

    print(state)
    assert state[(name, "document_type")] == DocumentType.IMAGE.value
    assert isinstance(state[(name, "total_pages")], (int, type(None)))

    pages = state[(name, "pages")]
    assert isinstance(pages, list)
    assert len(pages) >= 1

    first = pages[0]
    # In BASE64 mode, expect image_data to be a string; text_data may be None/empty.
    assert isinstance(first.get("image_data"), (str, bytes))
    assert "page_number" in first
    assert "width" in first and "height" in first


@pytest.mark.asyncio
async def test_document_io_bytes_precedence_over_path(tmp_path):
    """If both 'data' and 'path' are provided, the node must process from bytes."""
    # Create a node and pass a *non-existent* path to ensure it doesn't try to read from disk.
    node = DocumentIONode(
        name="doc_bytes_precedence",
        document_type=DocumentType.IMAGE,
        output_format=OutputFormat.BASE64,
    )

    inputs = {"path": "nonexistent.png", "data": PNG_BYTES}
    state = await _execute(node, inputs)

    name = "doc_bytes_precedence"
    # Should still succeed, because it processed from bytes.
    assert (name, "document_name") in state
    assert (name, "document_type") in state
    assert (name, "pages") in state

    assert state[(name, "document_type")] == DocumentType.IMAGE.value
    pages = state[(name, "pages")]
    assert isinstance(pages, list) and len(pages) >= 1


@pytest.mark.asyncio
async def test_document_io_specific_metadata():
    """specific_metadata() should reflect the configured values."""
    node = DocumentIONode(
        name="doc_meta",
        document_type=DocumentType.IMAGE,
        output_format=OutputFormat.BASE64,
        max_dimension=1024,
    )

    meta = node.specific_metadata()
    assert meta["max_dimension"] == 1024
    assert meta["document_type"] == DocumentType.IMAGE
    assert meta["output_format"] == OutputFormat.BASE64
