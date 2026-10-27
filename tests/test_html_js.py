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
            capture_output=True,
            text=True,
            timeout=10,
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


def test_html_accessibility_attributes():
    html = INDEX_HTML.read_text(encoding="utf-8")
    assert 'aria-label="Адхіліць"' in html
    assert 'aria-label="Рэдагаваць"' in html


def test_accessibility_attributes_present():
    html = INDEX_HTML.read_text(encoding="utf-8")
    assert 'role="tablist"' in html
    assert 'role="tab"' in html
    assert "aria-selected=" in html
    assert "aria-expanded=" in html
    assert "aria-controls=" in html
    assert 'aria-label="Пагінацыя"' in html
    assert ":focus-visible" in html


def test_processed_card_and_history_accessibility_attributes():
    """Verify processedCardHtml and evidenceHtml render aria-controls and aria-expanded for controls."""
    import json

    script = _script_content()
    functions = script[script.index("const esc =") : script.index("// --- wiring")]
    assertions = r"""
const assert = require('node:assert/strict');
let editingId = null;
const sample = {
  id: 'item123',
  title: 'Test Article',
  content: 'Original content',
  preview: 'Preview text',
  source: 'F1.com',
  importance_level: 4,
  relevance_score: 0.9,
  original_language: 'en'
};
const processed = processedCardHtml(sample);
assert(processed.includes('aria-controls="edit-item123"'), 'edit button should have aria-controls');
assert(processed.includes('aria-controls="hist-item123"'), 'history button should have aria-controls');
assert(processed.includes('aria-expanded="false"'), 'collapsible components should start collapsed');
"""
    result = subprocess.run(
        ["node", "-e", "const code = " + json.dumps(functions + assertions) + "; eval(code);"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr


def test_story_cards_escape_evidence_and_incomplete_translation_requires_confirmation():
    """Run the actual rendering and action functions with a small DOM/network stub."""
    import json

    script = _script_content()
    functions = script[script.index("const esc =") : script.index("// --- wiring")]
    assertions = r"""
const assert = require('node:assert/strict');
(async () => {
  const sample = {id:'one', title:'Ferrari <img src=x onerror=alert(1)>',
    content:'F1 news', url:'https://example.com/article', source:'test', relevance_score:0.8,
    editorial_reasons:[{label:'source', evidence:'<script>unsafe</script>'}],
    text_quality:{needs_confirmation:true, label:'RSS-анонс', characters:20},
    source_references:[{url:'javascript:alert(1)', source:'test', evidence:'<script>unsafe</script>'}],
    related_items:[{id:'two', title:'Other facts', content:'Extra', source:'other', relevance_score:0.8}]
  };
  const rendered = storyCardHtml(sample);
  assert(rendered.includes('data-id="one"'));
  assert(rendered.includes('data-id="two"'));
  assert(!rendered.includes('<script>unsafe</script>'));
  assert(!rendered.includes('href="javascript:'));
  assert(rendered.includes('&lt;img'));
  let posts = 0;
  global.call = async (path) => {if (path.includes('/translate')) posts++; return sample;};
  global.confirm = () => false;
  const card = {querySelector:()=>null, style:{}};
  await handleAction('one', 'translate', card);
  assert.equal(posts, 0);
  assert.equal(card.style.pointerEvents, undefined);
})().catch(error => {console.error(error); process.exitCode=1;});
"""
    result = subprocess.run(
        ["node", "-e", "const code = " + json.dumps(functions + assertions) + "; eval(code);"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
