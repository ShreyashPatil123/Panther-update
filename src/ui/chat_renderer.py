"""Chat renderer — converts raw AI response text into styled HTML.

Handles:
  ‑ Markdown → HTML (headers, bold, italic, lists, tables, inline code)
  ‑ Fenced code blocks → Pygments syntax‑highlighted HTML with language badge
  ‑ <think>…</think> blocks → collapsible "Thinking" sections
  ‑ Panther orange resin dark theme CSS
"""
import re
import html as html_module

import markdown
from pygments import highlight
from pygments.lexers import get_lexer_by_name, TextLexer
from pygments.formatters import HtmlFormatter


# ── Pygments Formatter ──────────────────────────────────────────────────────
_PYGMENTS_FORMATTER = HtmlFormatter(
    style="monokai",
    noclasses=True,  # inline styles for portability inside QTextBrowser
    nowrap=False,
)


# ── CSS Theme (panther orange resin dark) ────────────────────────────────────
CHAT_CSS = """
<style>
/* Base */
body {
    font-family: 'Inter', 'Segoe UI', -apple-system, BlinkMacSystemFont, sans-serif;
    color: #e8e0d8;
    background: transparent;
    margin: 0;
    padding: 0;
    font-size: 14px;
    line-height: 1.7;
    word-wrap: break-word;
}

/* Headings — glowing orange */
h1, h2, h3, h4 {
    color: #FF6B35;
    margin: 18px 0 8px 0;
    font-weight: 600;
}
h1 { font-size: 1.5em; border-bottom: 1px solid #2a2218; padding-bottom: 6px; }
h2 { font-size: 1.3em; }
h3 { font-size: 1.15em; }

/* Paragraphs */
p { margin: 8px 0; }

/* Bold / Italic */
strong { color: #ffffff; font-weight: 600; }
em { color: #b8a898; }

/* Links — orange resin */
a { color: #FF8C42; text-decoration: none; }
a:hover { text-decoration: underline; color: #FFB347; }

/* Lists */
ul, ol { margin: 8px 0; padding-left: 24px; }
li { margin: 4px 0; }
li::marker { color: #FF6B35; }

/* Inline code */
code {
    background: #1e1a14;
    color: #FFB347;
    padding: 2px 7px;
    border-radius: 5px;
    font-family: 'Cascadia Code', 'Consolas', 'Monaco', monospace;
    font-size: 0.92em;
    border: 1px solid #2a2218;
}

/* Fenced code blocks */
.code-container {
    position: relative;
    margin: 12px 0;
    border-radius: 10px;
    overflow: hidden;
    border: 1px solid #2a2218;
}
.code-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    background: #161210;
    padding: 6px 14px;
    font-size: 12px;
}
.code-lang {
    color: #FF6B35;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}
.code-copy {
    color: #8a8078;
    cursor: pointer;
    font-size: 11px;
    padding: 2px 10px;
    border: 1px solid #2a2218;
    border-radius: 5px;
    background: transparent;
}
.code-copy:hover {
    color: #fff;
    border-color: #FF6B35;
}
.code-body {
    background: #0f0e0c;
    padding: 14px;
    overflow-x: auto;
    font-family: 'Cascadia Code', 'Consolas', 'Monaco', monospace;
    font-size: 13px;
    line-height: 1.6;
}
.code-body code {
    background: transparent;
    padding: 0;
    color: inherit;
    font-size: inherit;
    border: none;
}

/* Thinking block (panther-themed) */
.thinking-block {
    margin: 12px 0;
    border-left: 3px solid #9333ea;
    border-radius: 0 10px 10px 0;
    background: linear-gradient(135deg, #1a1218, #1e1520);
    overflow: hidden;
}
.thinking-header {
    display: flex;
    align-items: center;
    padding: 10px 14px;
    cursor: pointer;
    color: #b388ff;
    font-weight: 600;
    font-size: 13px;
    user-select: none;
}
.thinking-header:hover {
    background: rgba(147, 51, 234, 0.1);
}
.thinking-toggle {
    margin-right: 8px;
    font-size: 10px;
    transition: transform 0.15s;
}
.thinking-content {
    padding: 0 14px 12px 14px;
    color: #9a8abf;
    font-size: 13px;
    line-height: 1.6;
    font-style: italic;
    display: none;
}
.thinking-content.open {
    display: block;
}

/* Blockquotes — orange resin accent */
blockquote {
    border-left: 3px solid #FF6B35;
    margin: 10px 0;
    padding: 8px 16px;
    background: rgba(255, 107, 53, 0.06);
    color: #b0a898;
    border-radius: 0 8px 8px 0;
}

/* Tables */
table {
    border-collapse: collapse;
    width: 100%;
    margin: 12px 0;
    font-size: 13px;
}
th {
    background: #161210;
    color: #FF6B35;
    font-weight: 600;
    padding: 10px 14px;
    text-align: left;
    border-bottom: 2px solid #2a2218;
}
td {
    padding: 8px 14px;
    border-bottom: 1px solid #1e1a14;
}
tr:nth-child(even) td {
    background: rgba(255,255,255,0.02);
}

/* Horizontal rule */
hr {
    border: none;
    border-top: 1px solid #2a2218;
    margin: 20px 0;
}
</style>
"""

THINKING_JS = """
<script>
function toggleThinking(el) {
    var content = el.nextElementSibling;
    var toggle = el.querySelector('.thinking-toggle');
    if (content.classList.contains('open')) {
        content.classList.remove('open');
        toggle.textContent = '▶';
    } else {
        content.classList.add('open');
        toggle.textContent = '▼';
    }
}
</script>
"""


# ── Rendering functions ─────────────────────────────────────────────────────

def _highlight_code_block(match: re.Match) -> str:
    """Replace a fenced code block with Pygments‑highlighted HTML."""
    language = (match.group(1) or "").strip()
    code = match.group(2)

    # Get lexer
    try:
        lexer = get_lexer_by_name(language) if language else TextLexer()
    except Exception:
        lexer = TextLexer()

    lang_display = language or "text"
    highlighted = highlight(code, lexer, _PYGMENTS_FORMATTER)

    return (
        f'<div class="code-container">'
        f'<div class="code-header">'
        f'<span class="code-lang">{html_module.escape(lang_display)}</span>'
        f'<span class="code-copy" onclick="copyCode(this)">📋 Copy</span>'
        f'</div>'
        f'<div class="code-body">{highlighted}</div>'
        f'</div>'
    )


def _process_thinking_blocks(text: str) -> str:
    """Convert <think>…</think> tags into collapsible HTML blocks."""

    def _replace_thinking(match: re.Match) -> str:
        content = match.group(1).strip()
        # Convert thinking content markdown
        md = markdown.Markdown(extensions=["tables", "nl2br"])
        html_content = md.convert(content)
        return (
            '<div class="thinking-block">'
            '<div class="thinking-header" onclick="toggleThinking(this)">'
            '<span class="thinking-toggle">▶</span>'
            '<span>🧠 Thinking</span>'
            '</div>'
            f'<div class="thinking-content">{html_content}</div>'
            '</div>'
        )

    # Handle both complete and streaming (unclosed) thinking blocks
    # Complete blocks
    text = re.sub(
        r"<think>(.*?)</think>",
        _replace_thinking,
        text,
        flags=re.DOTALL,
    )

    # Streaming: unclosed <think> block (still being generated)
    unclosed = re.search(r"<think>(.*?)$", text, re.DOTALL)
    if unclosed:
        content = unclosed.group(1).strip()
        if content:
            md = markdown.Markdown(extensions=["tables", "nl2br"])
            html_content = md.convert(content)
            replacement = (
                '<div class="thinking-block">'
                '<div class="thinking-header" onclick="toggleThinking(this)">'
                '<span class="thinking-toggle">▼</span>'
                '<span>🧠 Thinking…</span>'
                '</div>'
                f'<div class="thinking-content open">{html_content}</div>'
                '</div>'
            )
            text = text[: unclosed.start()] + replacement

    return text


def render_markdown(raw_text: str) -> str:
    """Convert raw AI response text into fully styled HTML.

    Pipeline:
      1. Extract and convert <think> blocks
      2. Syntax‑highlight fenced code blocks (before markdown to avoid conflicts)
      3. Convert remaining markdown to HTML
      4. Wrap in CSS + JS
    """
    if not raw_text:
        return ""

    text = raw_text

    # Step 1: Handle thinking blocks
    text = _process_thinking_blocks(text)

    # Step 2: Handle fenced code blocks BEFORE markdown conversion
    CODE_BLOCK_RE = re.compile(r"```(\w*)\n(.*?)```", re.DOTALL)
    text = CODE_BLOCK_RE.sub(_highlight_code_block, text)

    # Handle unclosed code block during streaming
    unclosed_code = re.search(r"```(\w*)\n(.*?)$", text, re.DOTALL)
    if unclosed_code and '<div class="code-container">' not in text[unclosed_code.start():]:
        language = (unclosed_code.group(1) or "").strip()
        code = unclosed_code.group(2)
        try:
            lexer = get_lexer_by_name(language) if language else TextLexer()
        except Exception:
            lexer = TextLexer()
        lang_display = language or "text"
        highlighted = highlight(code, lexer, _PYGMENTS_FORMATTER)
        replacement = (
            f'<div class="code-container">'
            f'<div class="code-header">'
            f'<span class="code-lang">{html_module.escape(lang_display)}</span>'
            f'<span style="color:#8a8078;font-size:11px;">⏳ streaming…</span>'
            f'</div>'
            f'<div class="code-body">{highlighted}</div>'
            f'</div>'
        )
        text = text[: unclosed_code.start()] + replacement

    # Step 3: Convert remaining markdown
    parts = re.split(r'(<div class="(?:code-container|thinking-block)".*?</div>\s*</div>\s*</div>)', text, flags=re.DOTALL)

    rendered_parts = []
    for part in parts:
        if part and ('class="code-container"' in part or 'class="thinking-block"' in part):
            rendered_parts.append(part)
        elif part and part.strip():
            md = markdown.Markdown(
                extensions=["tables", "fenced_code", "nl2br", "sane_lists"],
            )
            rendered_parts.append(md.convert(part))
        else:
            rendered_parts.append(part or "")

    html_body = "".join(rendered_parts)

    # Step 4: Wrap in full HTML document with CSS and JS
    full_html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
{CHAT_CSS}
{THINKING_JS}
<script>
function copyCode(el) {{
    var codeBody = el.closest('.code-container').querySelector('.code-body');
    var text = codeBody.innerText || codeBody.textContent;
    if (navigator.clipboard) {{
        navigator.clipboard.writeText(text);
    }}
    el.textContent = '✓ Copied!';
    setTimeout(function() {{ el.textContent = '📋 Copy'; }}, 1500);
}}
</script>
</head>
<body>
{html_body}
</body>
</html>"""

    return full_html


def render_user_message(text: str) -> str:
    """Render user message text (minimal formatting)."""
    escaped = html_module.escape(text)
    # Preserve newlines
    escaped = escaped.replace("\n", "<br>")
    return escaped
