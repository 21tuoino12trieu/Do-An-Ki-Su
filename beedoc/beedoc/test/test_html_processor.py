from beedoc_v3.renders.document_render.html_render.utils.processor import (
    detect_html_encoding,
    parse_html_to_structure,
    render_blocks_to_markdown,
)


def render_html(html: str) -> str:
    parsed = parse_html_to_structure(html)["html_payload"]
    return render_blocks_to_markdown(parsed)["reconstructed_content"]


def test_table_cell_pipe_is_escaped() -> None:
    markdown = render_html(
        "<table><tr><th>Name</th><th>Formats</th></tr>"
        "<tr><td>BeeDoc</td><td>PDF | HTML</td></tr></table>"
    )

    assert "| BeeDoc | PDF \\| HTML |" in markdown


def test_br_is_preserved_in_paragraph_and_table() -> None:
    markdown = render_html(
        "<p>First<br>Second</p>"
        "<table><tr><th>Value</th></tr><tr><td>A<br>B</td></tr></table>"
    )

    assert "First<br>Second" in markdown
    assert "| A<br>B |" in markdown


def test_link_destination_and_label_are_escaped() -> None:
    markdown = render_html(
        '<p><a href="https://example.com/search?q=func(a)">Link [new]</a></p>'
    )

    assert markdown == r"[Link \[new\]](https://example.com/search?q=func%28a%29)"


def test_unsafe_link_scheme_is_removed_but_text_is_kept() -> None:
    markdown = render_html('<p><a href="javascript:alert(1)">Click me</a></p>')

    assert markdown == "Click me"


def test_relative_and_mailto_links_are_allowed() -> None:
    markdown = render_html(
        '<p><a href="../docs/page.html#intro">Docs</a> '
        '<a href="mailto:user@example.com">Email</a></p>'
    )

    assert markdown == (
        "[Docs](../docs/page.html#intro) [Email](mailto:user@example.com)"
    )


def test_youtube_iframe_is_preserved_as_a_markdown_link() -> None:
    markdown = render_html(
        '<p><iframe class="youtube-player" title="Video giới thiệu" '
        'src="//www.youtube.com/embed/4Ws8wivpGI?mode=opaque"></iframe></p>'
    )

    assert markdown == (
        "[Video giới thiệu]"
        "(https://www.youtube.com/embed/4Ws8wivpGI?mode=opaque)"
    )


def test_video_source_is_preserved_as_a_markdown_link() -> None:
    markdown = render_html(
        '<video aria-label="Demo"><source src="https://example.com/demo.mp4"></video>'
    )

    assert markdown == "[Demo](https://example.com/demo.mp4)"


def test_unsafe_embedded_media_url_is_removed() -> None:
    markdown = render_html('<iframe src="javascript:alert(1)"></iframe>')

    assert markdown == ""


def test_embedded_media_uses_default_label() -> None:
    markdown = render_html('<iframe src="https://example.com/embed/demo"></iframe>')

    assert markdown == "[Video minh hoa](https://example.com/embed/demo)"


def test_table_does_not_double_escape_existing_markdown_backslashes() -> None:
    markdown = render_html(
        '<table><tr><th>Link</th></tr><tr><td>'
        '<a href="/docs">Link [new]</a></td></tr></table>'
    )

    assert "| [Link \\[new\\]](/docs) |" in markdown
    assert r"\\[new" not in markdown


def test_table_without_th_keeps_first_row_as_data() -> None:
    markdown = render_html(
        "<table><tr><td>A</td><td>B</td></tr>"
        "<tr><td>C</td><td>D</td></tr></table>"
    )

    assert markdown.splitlines() == [
        "|  |  |",
        "| --- | --- |",
        "| A | B |",
        "| C | D |",
    ]


def test_inline_script_and_style_are_ignored() -> None:
    markdown = render_html(
        "<p>Safe<script>alert(1)</script><style>.bad{}</style> text</p>"
    )

    assert markdown == "Safe text"


def test_html_encoded_markup_stays_text() -> None:
    markdown = render_html("<p>&lt;script&gt;alert(1)&lt;/script&gt;</p>")

    assert markdown == "&lt;script&gt;alert(1)&lt;/script&gt;"


def test_html_encoded_markup_stays_text_in_other_block_types() -> None:
    markdown = render_html(
        "<h1>&lt;script&gt;</h1>"
        "<blockquote>&lt;button&gt;</blockquote>"
        "<pre>&lt;div&gt;</pre>"
    )

    assert "# &lt;script&gt;" in markdown
    assert "> &lt;button&gt;" in markdown
    assert "&lt;div&gt;" in markdown


def test_link_preserves_inline_formatting() -> None:
    markdown = render_html(
        '<p><a href="/docs"><strong>Bold</strong> and <em>italic</em></a></p>'
    )

    assert markdown == "[**Bold** and *italic*](/docs)"


def test_code_uses_a_longer_backtick_fence_when_needed() -> None:
    markdown = render_html("<p><code>a ` b</code></p><pre>a ``` b</pre>")

    assert "``a ` b``" in markdown
    assert "````\na ``` b\n````" in markdown


def test_utf16_bom_is_detected() -> None:
    assert detect_html_encoding("<p>Xin chào</p>".encode("utf-16")) == "utf-16-le"
