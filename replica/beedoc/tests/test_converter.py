import unittest
from unittest.mock import patch

from beedoc import ConversionError, UnsupportedHtmlError, convert_html


class ConverterTests(unittest.TestCase):
    def test_vietnamese_headings_paragraphs_and_order(self):
        html = "<h1>Quy định</h1><p>Hạn mức 100.000 đồng.</p><h2>Điều kiện</h2><p>Còn hiệu lực.</p>"
        self.assertEqual(convert_html(html), "# Quy định\n\nHạn mức 100.000 đồng.\n\n## Điều kiện\n\nCòn hiệu lực.")

    def test_lists(self):
        self.assertEqual(convert_html("<ul><li>Một</li><li>Hai</li></ul><ol><li>Ba</li><li>Bốn</li></ol>"), "- Một\n- Hai\n\n1. Ba\n2. Bốn")

    def test_nested_list(self):
        self.assertEqual(convert_html("<ul><li>Một<ul><li>Hai</li></ul></li></ul>"), "- Một\n  - Hai")

    def test_links(self):
        self.assertEqual(convert_html('<p><a href="/wiki/page?a=1&amp;b=2">Nguồn</a></p>'), "[Nguồn](/wiki/page?a=1&b=2)")

    def test_link_escaping(self):
        self.assertEqual(convert_html('<a href="https://example.com/f(a)">Link [mới]</a>'), r"[Link \[mới\]](https://example.com/f%28a%29)")

    def test_table_with_header(self):
        result = convert_html("<table><tr><th>Tên</th><th>Giá trị</th></tr><tr><td>A</td><td>1 | 2</td></tr></table>")
        self.assertEqual(result, "| Tên | Giá trị |\n| --- | --- |\n| A | 1 \\| 2 |")

    def test_table_without_header_keeps_first_row(self):
        self.assertEqual(convert_html("<table><tr><td>A</td></tr><tr><td>B</td></tr></table>"), "|  |\n| --- |\n| A |\n| B |")

    def test_breaks_and_inline_formatting(self):
        self.assertEqual(convert_html("<p><strong>Đậm</strong><br><em>Nghiêng</em></p>"), "**Đậm**<br>*Nghiêng*")

    def test_images_are_preserved_exactly(self):
        tags = [
            '<img src="/anh?a=1&amp;b=2" alt="Sơ đồ" width="100" data-id="a">',
            "<IMG  alt='Đồ thị' src='data:image/png;base64,AAAA' />",
            '<img src="https://example.invalid/a.png" loading="lazy" disabled>',
            '<img src="a.png" alt="Dòng\n mới">',
        ]
        with patch("socket.socket", side_effect=AssertionError("Không được gọi mạng")):
            for tag in tags:
                with self.subTest(tag=tag):
                    self.assertEqual(convert_html(tag), tag)

    def test_image_inline_and_in_table(self):
        tag = '<img src="/a.png" alt="A">'
        self.assertEqual(convert_html(f"<p>Trước {tag} sau</p>"), f"Trước {tag} sau")
        self.assertIn(f"| {tag} |", convert_html(f"<table><tr><td>{tag}</td></tr></table>"))

    def test_linked_image(self):
        self.assertEqual(convert_html('<a href="/page"><img src="/a.png"></a>'), '[<img src="/a.png">](/page)')

    def test_comment_and_script_do_not_become_images(self):
        self.assertEqual(convert_html('<!-- <img src="a"> --><script>const x = \'<img src="b">\';</script><p>Hiện</p>'), "Hiện")

    def test_entities_remain_text(self):
        self.assertEqual(convert_html("<p>&lt;script&gt; &amp; tiếng Việt</p>"), "&lt;script&gt; &amp; tiếng Việt")

    def test_empty(self):
        for html in ("", " \n ", "<p></p>"):
            self.assertEqual(convert_html(html), "")

    def test_invalid_input(self):
        for value in (None, b"<p>A</p>", 123):
            with self.assertRaises(ConversionError):
                convert_html(value)

    def test_unsupported_tables(self):
        for html in (
            '<table><tr><td colspan="2">A</td></tr></table>',
            '<table><tr><td rowspan="2">A</td></tr></table>',
            '<table><tr><td><table><tr><td>A</td></tr></table></td></tr></table>',
            '<table><tr><td>A</td></tr><tr><td>B</td><td>C</td></tr></table>',
        ):
            with self.subTest(html=html), self.assertRaises(UnsupportedHtmlError):
                convert_html(html)

    def test_failure_is_not_silently_empty(self):
        with patch("beedoc_v3.renders.document_render.html_render.utils.converter.parse_html_to_structure", side_effect=RuntimeError("failure")):
            with self.assertRaises(ConversionError) as caught:
                convert_html("<p>Nội dung</p>")
            self.assertIsInstance(caught.exception.__cause__, RuntimeError)

    def test_deterministic_and_no_placeholder_collision(self):
        html = 'BEEDOCIMAGETOKEN0END<p><img src="/a"></p>'
        first = convert_html(html)
        self.assertEqual(first, convert_html(html))
        self.assertIn("BEEDOCIMAGETOKEN0END", first)
        self.assertIn('<img src="/a">', first)


if __name__ == "__main__":
    unittest.main()
