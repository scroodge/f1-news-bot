"""Validate inline JS in index.html — catch stray braces before deploy."""

import subprocess
import tempfile
from pathlib import Path

INDEX_HTML = Path(__file__).resolve().parents[1] / "src" / "webapp" / "static" / "index.html"


def _script_content() -> str:
    html = INDEX_HTML.read_text(encoding="utf-8")
    start = html.rfind("<script>")
    end = html.rfind("</script>")
    assert start != -1 and end != -1, "No <script> block found"
    return html[start + len("<script>") : end]


def test_js_syntax():
    """Validate inline JS with Node.js — catches stray braces, missing parens, etc."""
    js = _script_content()
    # node --check only works on files, so write to temp
    with tempfile.NamedTemporaryFile(suffix=".js", mode="w", delete=False) as f:
        f.write(js)
        tmp = f.name
    try:
        result = subprocess.run(
            ["node", "--check", tmp],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0, f"JS syntax error:\n{result.stderr}"
    finally:
        Path(tmp).unlink(missing_ok=True)


def test_js_has_show_queue():
    js = _script_content()
    assert 'show("queue")' in js, "Missing initial show('queue') call"


def test_js_has_try_catch():
    js = _script_content()
    assert "try {" in js
    assert "catch (" in js


def test_js_async_handlers():
    js = _script_content()
    assert "addEventListener" in js
    assert "async" in js


def test_html_has_translate_button():
    html = INDEX_HTML.read_text(encoding="utf-8")
    assert "Перакласці" in html or "translate" in html
