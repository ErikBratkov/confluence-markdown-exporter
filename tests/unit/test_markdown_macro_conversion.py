"""Unit tests for Markdown macro conversion."""

from unittest.mock import MagicMock

from bs4 import BeautifulSoup

from confluence_markdown_exporter.confluence import Page

SOURCE_TABLE = "| Version | Date       |\n|---------|------------|\n| 1.0     | 16.10.2026 |"


def _make_page(body_storage: str = "", editor2: str = "") -> MagicMock:
    page = MagicMock(spec=Page)
    page.id = 12345
    page.title = "Test Page"
    page.html = "<h1>Test Page</h1>"
    page.labels = []
    page.ancestors = []
    page.attachments = []
    page.editor2 = editor2
    page.body_storage = body_storage
    return page


def _storage_macro(source: str, name: str = "markdown") -> str:
    return (
        f'<ac:structured-macro ac:name="{name}" ac:schema-version="1">'
        f"<ac:plain-text-body><![CDATA[{source}]]></ac:plain-text-body>"
        "</ac:structured-macro>"
    )


def _view_macro(rendered: str, name: str = "markdown", macro_id: str = "") -> str:
    """Rendered macro as Server / Data Center returns it in body.view."""
    id_attr = f' data-macro-id="{macro_id}"' if macro_id else ""
    return (
        f'<div class="conf-macro output-block" data-hasbody="true" '
        f'data-macro-name="{name}"{id_attr}>{rendered}'
        "<script>AJS.$('[data-macro-name=\"markdown\"] code').each(function(i, b) {});</script>"
        "<style>.hljs {display: inline;}</style>"
        "</div>"
    )


def _expand(content: str) -> str:
    return (
        '<div class="expand-container conf-macro output-block" data-macro-name="expand">'
        '<div class="expand-control"><span class="expand-control-text">Details</span></div>'
        f'<div class="expand-content">{content}</div>'
        "</div>"
    )


def test_server_source_is_taken_from_storage() -> None:
    storage = _storage_macro(f"# Source heading\n\n{SOURCE_TABLE}\n")
    view = _view_macro("<h1>Rendered heading</h1><p>rendered table</p>")

    out = Page.Converter(_make_page(storage)).convert(view)

    assert "# Source heading" in out
    assert SOURCE_TABLE in out
    assert "Rendered heading" not in out
    assert "rendered table" not in out
    assert "content not found" not in out


def test_server_macros_are_matched_by_position_including_expand() -> None:
    storage = (
        _storage_macro("first source")
        + '<ac:structured-macro ac:name="expand"><ac:rich-text-body>'
        + _storage_macro("second source")
        + "</ac:rich-text-body></ac:structured-macro>"
        + _storage_macro("third source")
    )
    view = (
        _view_macro("<p>first rendered</p>")
        + _expand(_view_macro("<p>second rendered</p>"))
        + _view_macro("<p>third rendered</p>")
    )

    out = Page.Converter(_make_page(storage)).convert(view)

    assert "rendered" not in out
    assert out.index("first source") < out.index("second source") < out.index("third source")
    assert out.count("second source") == 1


def test_macro_inside_include_is_not_matched_against_page_storage() -> None:
    storage = (
        _storage_macro("page source")
        + '<ac:structured-macro ac:name="include"><ac:parameter ac:name="">'
        + '<ac:link><ri:page ri:content-title="Other Page" /></ac:link>'
        + "</ac:parameter></ac:structured-macro>"
    )
    view = (
        _view_macro("<p>page rendered</p>")
        + '<div class="conf-macro output-block" data-macro-name="include">'
        + _view_macro("<p>included rendered</p>")
        + "</div>"
    )

    out = Page.Converter(_make_page(storage)).convert(view)

    assert out.count("page source") == 1
    assert "page rendered" not in out
    assert "included rendered" in out


def test_count_mismatch_falls_back_to_rendered_content() -> None:
    storage = _storage_macro("storage source")
    view = _view_macro("<p>first rendered</p>") + _view_macro("<p>second <b>rendered</b></p>")

    out = Page.Converter(_make_page(storage)).convert(view)

    assert "storage source" not in out
    assert "first rendered" in out
    assert "second **rendered**" in out
    assert "AJS" not in out
    assert "hljs" not in out
    assert "content not found" not in out


def test_mohamicorp_markdown_parameter_is_taken_from_storage() -> None:
    storage = (
        '<ac:structured-macro ac:name="mohamicorp-markdown" ac:schema-version="1">'
        '<ac:parameter ac:name="markdown">**param source**</ac:parameter>'
        "</ac:structured-macro>"
    )
    view = _view_macro("<p><strong>param rendered</strong></p>", name="mohamicorp-markdown")

    out = Page.Converter(_make_page(storage)).convert(view)

    assert "**param source**" in out
    assert "param rendered" not in out


def test_cloud_editor2_source_has_priority_over_storage() -> None:
    editor2 = (
        '<ac:structured-macro ac:name="markdown" ac:macro-id="md-1">'
        "<ac:plain-text-body><![CDATA[cloud source]]></ac:plain-text-body>"
        "</ac:structured-macro>"
    )
    storage = _storage_macro("storage source")
    view = _view_macro("<p>rendered</p>", macro_id="md-1")

    out = Page.Converter(_make_page(storage, editor2)).convert(view)

    assert "cloud source" in out
    assert "storage source" not in out


def test_element_outside_rendered_macros_is_not_resolved_from_storage() -> None:
    converter = Page.Converter(_make_page(_storage_macro("storage source")))
    soup = BeautifulSoup(
        '<div data-macro-name="markdown"></div>'
        '<span data-macro-name="markdown"><p>rendered</p></span>',
        "html.parser",
    )
    el = soup.find("span")

    result = converter.convert_markdown(el, "rendered", [])

    assert result.strip() == "rendered"


def test_no_source_and_empty_rendered_content_emits_comment() -> None:
    view = '<div class="conf-macro output-block" data-macro-name="markdown"></div>'

    out = Page.Converter(_make_page()).convert(view)

    assert "<!-- Markdown macro (markdown) content not found -->" in out
