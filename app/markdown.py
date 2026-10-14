"""Safe Markdown to HTML for drafts and responses shown in the web interface.

Drafts come from the deterministic template and from language models, and may
quote the data subject's text, so the input is untrusted. Every line is
HTML-escaped first and only a fixed subset of Markdown is turned into tags:
headings, paragraphs, line breaks, bold, italics, inline and fenced code,
lists (nested), tables, quotes, rules and http(s) or relative links.
Only the standard library is used.
"""

from __future__ import annotations

import html
import re

from markupsafe import Markup

FENCE_RE = re.compile(r"^\s*(```|~~~)")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
RULE_RE = re.compile(r"^\s*([-*_])(\s*\1){2,}\s*$")
LIST_RE = re.compile(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$")
TABLE_SEP_RE = re.compile(r"^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$")
CODE_SPAN_RE = re.compile(r"`([^`]+)`")
LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
BOLD_RE = re.compile(r"\*\*(?=\S)(.+?)(?<=\S)\*\*|__(?=\S)(.+?)(?<=\S)__")
ITALIC_RE = re.compile(r"(?<![\w*])\*(?=\S)(.+?)(?<=\S)\*(?![\w*])|(?<!\w)_(?=\S)(.+?)(?<=\S)_(?!\w)")
SAFE_URL_RE = re.compile(r"^(https?://|/|#|\./|\.\./)", re.IGNORECASE)


def inline(text: str) -> str:
    """Escape the text and apply inline formatting; code spans stay literal."""
    codes: list[str] = []

    def keep_code(match: re.Match) -> str:
        codes.append(f"<code>{html.escape(match.group(1), quote=False)}</code>")
        return f"\x00{len(codes) - 1}\x00"

    text = CODE_SPAN_RE.sub(keep_code, text)
    text = html.escape(text, quote=False)

    def link(match: re.Match) -> str:
        label, url = match.group(1), html.unescape(match.group(2))
        if not SAFE_URL_RE.match(url):
            return match.group(0)
        return f'<a href="{html.escape(url, quote=True)}" rel="noopener noreferrer">{label}</a>'

    text = LINK_RE.sub(link, text)
    text = BOLD_RE.sub(lambda m: f"<strong>{m.group(1) or m.group(2)}</strong>", text)
    text = ITALIC_RE.sub(lambda m: f"<em>{m.group(1) or m.group(2)}</em>", text)
    return re.sub(r"\x00(\d+)\x00", lambda m: codes[int(m.group(1))], text)


def split_row(line: str) -> list[str]:
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return [cell.strip() for cell in re.split(r"(?<!\\)\|", line)]


def render_table(lines: list[str]) -> str:
    header = split_row(lines[0])
    rows = [split_row(line) for line in lines[2:]]
    head = "".join(f"<th>{inline(cell)}</th>" for cell in header)
    body = "".join(
        "<tr>" + "".join(f"<td>{inline(cell)}</td>" for cell in row) + "</tr>" for row in rows
    )
    return f'<div class="md-table"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def indent_of(line: str) -> int:
    return len(line.expandtabs(4)) - len(line.expandtabs(4).lstrip())


def render_list(lines: list[str], start: int) -> tuple[str, int]:
    """Render a (possibly nested) list beginning at `start`; return html and next index."""
    first = LIST_RE.match(lines[start])
    base = indent_of(lines[start])
    ordered = first.group(2)[0].isdigit()
    tag = "ol" if ordered else "ul"
    items: list[str] = []
    index = start
    while index < len(lines):
        line = lines[index]
        match = LIST_RE.match(line)
        if not line.strip():
            following = next((item for item in lines[index + 1:] if item.strip()), "")
            nested = LIST_RE.match(following)
            if nested and indent_of(following) >= base:
                index += 1
                continue
            break
        if match and indent_of(line) == base:
            if match.group(2)[0].isdigit() != ordered:
                break
            items.append(inline(match.group(3)))
            index += 1
        elif match and indent_of(line) > base and items:
            nested_html, index = render_list(lines, index)
            items[-1] += nested_html
        elif not match and indent_of(line) > base and items:
            items[-1] += "<br>" + inline(line.strip())
            index += 1
        else:
            break
    body = "".join(f"<li>{item}</li>" for item in items)
    return f"<{tag}>{body}</{tag}>", index


def is_block_start(lines: list[str], index: int) -> bool:
    line = lines[index]
    return bool(
        FENCE_RE.match(line)
        or HEADING_RE.match(line)
        or RULE_RE.match(line)
        or LIST_RE.match(line)
        or line.lstrip().startswith(">")
        or (
            line.lstrip().startswith("|")
            and index + 1 < len(lines)
            and TABLE_SEP_RE.match(lines[index + 1])
        )
    )


def render_blocks(lines: list[str]) -> str:
    out: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            index += 1
            continue
        if FENCE_RE.match(line):
            fence = FENCE_RE.match(line).group(1)
            code: list[str] = []
            index += 1
            while index < len(lines) and not lines[index].strip().startswith(fence):
                code.append(lines[index])
                index += 1
            index += 1
            out.append(f"<pre><code>{html.escape(chr(10).join(code), quote=False)}</code></pre>")
            continue
        heading = HEADING_RE.match(line)
        if heading:
            level = len(heading.group(1))
            out.append(f"<h{level}>{inline(heading.group(2))}</h{level}>")
            index += 1
            continue
        if RULE_RE.match(line):
            out.append("<hr>")
            index += 1
            continue
        if line.lstrip().startswith("|") and index + 1 < len(lines) and TABLE_SEP_RE.match(lines[index + 1]):
            table = [line, lines[index + 1]]
            index += 2
            while index < len(lines) and lines[index].lstrip().startswith("|"):
                table.append(lines[index])
                index += 1
            out.append(render_table(table))
            continue
        if line.lstrip().startswith(">"):
            quoted: list[str] = []
            while index < len(lines) and lines[index].lstrip().startswith(">"):
                quoted.append(re.sub(r"^\s*>\s?", "", lines[index]))
                index += 1
            out.append(f"<blockquote>{render_blocks(quoted)}</blockquote>")
            continue
        if LIST_RE.match(line):
            rendered, index = render_list(lines, index)
            out.append(rendered)
            continue
        paragraph: list[str] = []
        while index < len(lines) and lines[index].strip() and (
            not paragraph or not is_block_start(lines, index)
        ):
            paragraph.append(lines[index])
            index += 1
        parts = []
        for position, item in enumerate(paragraph):
            hard_break = item.endswith("  ") or item.rstrip().endswith("\\")
            text = inline(item.strip().rstrip("\\").rstrip())
            if position < len(paragraph) - 1:
                text += "<br>" if hard_break else " "
            parts.append(text)
        out.append(f"<p>{''.join(parts).strip()}</p>")
    return "\n".join(out)


def render_markdown(text: str | None) -> Markup:
    """Markdown subset to HTML; the result is safe to insert in a template."""
    if not text:
        return Markup("")
    lines = str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n")
    return Markup(render_blocks(lines))
