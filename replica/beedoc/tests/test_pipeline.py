import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from beedoc_v3 import BeedocEngine, Document, Page, Zone
from beedoc_v3.core.constants import DocumentStatus
from beedoc_v3.core.exceptions import ReaderError, RendererError, UnsupportedFormatError
from beedoc_v3.readers.base import BaseReader
from beedoc_v3.readers.factory import ReaderFactory
from beedoc_v3.renders.base import BaseRenderer
from beedoc_v3.renders.factory import RendererFactory
from beedoc_v3.renders.document_render.html_render.utils.pipeline import (
    prepare_html_source, render_html_source,
)
from beedoc_v3.renders.document_render.html_render.utils.processor import parse_html_to_structure


class HtmlPipelineTests(unittest.TestCase):
    def test_file_metadata_and_conversion_stages(self):
        html = '<h1>Quy trình</h1><p>100 đồng.</p><img src="/a" alt="Ảnh">'
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/"page.html"
            path.write_text(html, encoding="utf-8")
            metadata = BaseReader._hashing_logic(str(path))
            doc = Document(file_path=str(path))
            BaseReader._update_document_logic(doc, metadata)
            self.assertEqual(doc.file_size_bytes, len(html.encode("utf-8")))
            self.assertEqual(doc.file_name, "page.html")
            self.assertIsNotNone(doc.file_hash)
            prepared = prepare_html_source(str(path))
            parsed = parse_html_to_structure(prepared["normalized_raw_content"])
            result = render_html_source(parsed["html_payload"], prepared["image_tags"])
            self.assertEqual(result["reconstructed_content"], '# Quy trình\n\n100 đồng.\n\n<img src="/a" alt="Ảnh">')

    def test_reader_reports_missing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ReaderError):
                BaseReader._hashing_logic(str(Path(tmp)/"missing.html"))

    def test_factory_inheritance_and_scope(self):
        self.assertIsInstance(ReaderFactory.get_reader(".HTML"), BaseReader)
        self.assertIsInstance(RendererFactory.get_renderer("html"), BaseRenderer)
        with self.assertRaises(UnsupportedFormatError):
            ReaderFactory.get_reader("pdf")
        with self.assertRaises(RendererError):
            RendererFactory.get_renderer("pdf")

    def test_document_model(self):
        doc = Document()
        doc.add_page(Page(page_number=1, content=[Zone(content="A"), Zone(content="B")]))
        self.assertEqual(doc.pages[0].to_markdown(), "A\n\nB")
        doc.update_status(DocumentStatus.COMPLETED)
        self.assertEqual(doc.to_dict()["status"], "completed")


class EngineLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_engine_dispatches_reader_then_renderer(self):
        states = []

        async def read(doc):
            states.append(doc.status)
            doc.file_name = "page.html"
            return doc

        async def render(doc):
            states.append(doc.status)
            doc.reconstructed_content = "# Nội dung"
            return doc

        with patch.object(ReaderFactory, "get_reader") as factory_r, patch.object(RendererFactory, "get_renderer") as factory_w:
            factory_r.return_value.read = AsyncMock(side_effect=read)
            factory_w.return_value.render = AsyncMock(side_effect=render)
            doc = await BeedocEngine().process("page.html")
        self.assertEqual(states, [DocumentStatus.READING, DocumentStatus.RECONSTRUCTING])
        self.assertEqual(doc.status, DocumentStatus.COMPLETED)
        self.assertEqual(doc.reconstructed_content, "# Nội dung")

    async def test_engine_returns_failed_document_on_reader_error(self):
        with patch.object(ReaderFactory, "get_reader") as reader, patch.object(RendererFactory, "get_renderer") as renderer:
            reader.return_value.read = AsyncMock(side_effect=ReaderError("Lỗi đọc"))
            doc = await BeedocEngine().process("page.html")
            renderer.assert_not_called()
        self.assertEqual(doc.status, DocumentStatus.FAILED)
        self.assertEqual(doc.error_message, "Lỗi đọc")
        self.assertIsNone(doc.reconstructed_content)

    async def test_engine_rejects_non_html(self):
        with self.assertRaises(UnsupportedFormatError):
            await BeedocEngine().process("page.pdf")


if __name__ == "__main__":
    unittest.main()
