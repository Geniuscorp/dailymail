"""Inbound HTML keeps its layout but loses everything that can run or fetch."""
import pytest

from app.services.html_sanitizer import clean_style, sanitize_html

PNG = "data:image/png;base64,iVBORw0KGgo="


class TestLayoutIsKept:
    def test_table_borders_colours_and_widths_survive(self):
        html = (
            '<table border="1" cellpadding="6" cellspacing="0" width="600" '
            'style="border:1px solid #000;border-collapse:collapse">'
            '<tr><th bgcolor="#5bc0de" style="background-color:#5bc0de;font-weight:bold">Name</th>'
            '<td colspan="2" valign="top" align="center">x</td></tr></table>'
        )
        out = sanitize_html(html)
        for fragment in (
            'border="1"', 'cellpadding="6"', 'cellspacing="0"', 'width="600"',
            'bgcolor="#5bc0de"', "border:1px solid #000", "border-collapse:collapse",
            "background-color:#5bc0de", "font-weight:bold", 'colspan="2"', 'valign="top"',
        ):
            assert fragment in out

    def test_font_center_and_embedded_images_survive(self):
        out = sanitize_html(f'<center><font color="red" size="2">Aviso</font></center><img src="{PNG}" alt="logo" width="40">')
        assert '<font color="red" size="2">' in out
        assert "<center>" in out
        assert f'src="{PNG}"' in out
        assert 'alt="logo"' in out


class TestNothingDangerousSurvives:
    @pytest.mark.parametrize(
        "html,absent",
        [
            ("<p>a<script>alert(1)</script></p>", "script"),
            ('<img src="x" onerror="alert(1)">', "onerror"),
            ('<a href="javascript:alert(1)">x</a>', "javascript"),
            ('<a href="data:text/html,<b>x</b>">x</a>', "data:"),
            ('<a href="vbscript:x">x</a>', "vbscript"),
            ("<style>body{background:url(http://evil/x)}</style><p>a</p>", "evil"),
            ("<iframe src='http://evil'></iframe>", "iframe"),
            ("<form action='http://evil'><input name=a></form>", "form"),
            ('<div onclick="x()">a</div>', "onclick"),
            ('<svg onload="x()"></svg>', "svg"),
            ('<link rel="stylesheet" href="http://evil/x.css">', "evil"),
        ],
    )
    def test_active_content_is_removed(self, html, absent):
        assert absent not in sanitize_html(html).lower()

    @pytest.mark.parametrize(
        "image",
        ["http://tracker.example/pixel.gif", "https://tracker.example/p.png", "data:image/svg+xml;base64,PHN2Zz4=", "data:text/html;base64,PHA+"],
    )
    def test_only_embedded_raster_images_are_kept(self, image):
        out = sanitize_html(f'<img src="{image}">')
        assert "src=" not in out

    @pytest.mark.parametrize(
        "style",
        [
            "background:url(http://evil/x)",
            "background-image:url(x)",
            "position:fixed",
            "z-index:999",
            "behavior:url(x.htc)",
            "width:expression(alert(1))",
            "color:red\\0072",
            "content:'x'",
            "cursor:url(x),auto",
        ],
    )
    def test_unsafe_css_is_dropped(self, style):
        assert clean_style(style) is None

    def test_safe_and_unsafe_declarations_are_separated(self):
        assert clean_style("color:#111; position:absolute; padding:4px 8px; background:url(x)") == "color:#111;padding:4px 8px"

    def test_links_keep_a_safe_rel_and_http_targets(self):
        out = sanitize_html('<a href="https://example.org/x">x</a>')
        assert 'href="https://example.org/x"' in out
        assert "noopener" in out and "noreferrer" in out


def test_empty_input_stays_empty():
    assert sanitize_html(None) is None
    assert sanitize_html("") is None
