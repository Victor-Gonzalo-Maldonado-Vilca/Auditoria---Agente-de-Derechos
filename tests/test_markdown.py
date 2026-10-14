from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

WEB_AVAILABLE = all(
    importlib.util.find_spec(name) for name in ("fastapi", "httpx", "jinja2", "multipart")
)


@unittest.skipUnless(WEB_AVAILABLE, "Instale requirements.txt y requirements-dev.txt")
class MarkdownRenderTests(unittest.TestCase):
    def render(self, text: str) -> str:
        from app.markdown import render_markdown

        return str(render_markdown(text))

    def test_template_header_and_line_breaks(self):
        out = self.render("# Borrador\n\n**Caso:** X-1  \n**Estado:** `REVIEW`")
        self.assertIn("<h1>Borrador</h1>", out)
        self.assertIn("<strong>Caso:</strong> X-1<br><strong>Estado:</strong> <code>REVIEW</code>", out)

    def test_nested_lists(self):
        out = self.render("1. Uno\n2. Dos\n    * a\n    * b\n3. Tres")
        self.assertIn("<ol><li>Uno</li><li>Dos<ul><li>a</li><li>b</li></ul></li><li>Tres</li></ol>", out)

    def test_table(self):
        out = self.render("| A | B |\n|---|:-:|\n| `x` | **y** |")
        self.assertIn("<th>A</th><th>B</th>", out)
        self.assertIn("<td><code>x</code></td><td><strong>y</strong></td>", out)

    def test_rule_quote_and_fenced_code(self):
        out = self.render("> nota\n\n---\n\n```json\n{\"a\": \"<b>\"}\n```")
        self.assertIn("<blockquote><p>nota</p></blockquote>", out)
        self.assertIn("<hr>", out)
        self.assertIn("<pre><code>{\"a\": \"&lt;b&gt;\"}</code></pre>", out)

    def test_raw_html_is_escaped(self):
        out = self.render("Hola <script>alert(1)</script> <img src=x onerror=alert(1)>")
        self.assertNotIn("<script>", out)
        self.assertNotIn("<img", out)
        self.assertIn("&lt;script&gt;", out)

    def test_only_safe_links(self):
        out = self.render("[ok](https://www.iso.org) [no](javascript:alert(1)) [x](data:text/html,1)")
        self.assertIn('<a href="https://www.iso.org" rel="noopener noreferrer">ok</a>', out)
        self.assertNotIn('href="javascript', out)
        self.assertNotIn('href="data', out)

    def test_snake_case_is_not_italic(self):
        out = self.render("campo manager_email y *enfasis*")
        self.assertIn("manager_email", out)
        self.assertIn("<em>enfasis</em>", out)

    def test_code_span_keeps_markdown_literal(self):
        self.assertIn("<code>**no**</code>", self.render("`**no**`"))

    def test_empty(self):
        self.assertEqual(self.render(""), "")


@unittest.skipUnless(WEB_AVAILABLE, "Instale requirements.txt y requirements-dev.txt")
class CasePageMarkdownTests(unittest.TestCase):
    def test_case_page_renders_draft_as_html(self):
        from fastapi.testclient import TestClient

        from agents.orchestrator import Orchestrator
        from app.main import create_app

        with tempfile.TemporaryDirectory() as directory:
            orchestrator = Orchestrator(runtime_dir=Path(directory))
            request = json.loads(
                (ROOT / "tests" / "fixtures" / "request-access.json").read_text(encoding="utf-8")
            )
            case_id = orchestrator.submit(request)["case_id"]
            page = TestClient(create_app(orchestrator)).get(f"/casos/{case_id}").text
        self.assertIn('<div class="markdown"><h1>Borrador de respuesta DSAR</h1>', page)
        self.assertIn("<strong>Caso:</strong>", page)
        self.assertIn("Ver Markdown original", page)


if __name__ == "__main__":
    unittest.main()
