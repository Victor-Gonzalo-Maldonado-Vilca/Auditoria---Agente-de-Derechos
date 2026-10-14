"""Integracion de Gemini y Claude con el orquestador y la interfaz web.

Los modelos se sustituyen por dobles de prueba: no se usa red ni cuota.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agents.common import CLAUDE, LLM, VALIDATOR  # noqa: E402
from agents.orchestrator import AIUnavailable, CaseInputError, Orchestrator  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures"
WEB_AVAILABLE = all(
    importlib.util.find_spec(name) for name in ("fastapi", "httpx", "jinja2", "multipart")
)


def read_json(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class FakeGemini:
    def __init__(self, *answers: str, fail: bool = False):
        self.answers = list(answers)
        self.fail = fail
        self.bodies: list[dict] = []

    def __call__(self, url, headers, body):
        self.bodies.append(body)
        if self.fail:
            raise LLM.LLMError("Cuota del modelo agotada (HTTP 429). Intente mas tarde.")
        return {"candidates": [{"content": {"parts": [{"text": self.answers.pop(0)}]}}]}


class FakeClaude:
    """Stands in for `claude -p`, recording the command and the prompt."""

    def __init__(self, result: str, is_error: bool = False):
        self.result = result
        self.is_error = is_error
        self.calls: list[tuple[list[str], str]] = []

    def __call__(self, args, stdin, cwd, timeout):
        self.calls.append((args, stdin))
        payload = {
            "type": "result",
            "is_error": self.is_error,
            "result": self.result,
            "num_turns": 3,
            "duration_ms": 1200,
            "permission_denials": [],
            "modelUsage": {
                "claude-haiku-5-5": {"outputTokens": 20},
                "claude-opus-5-5": {"outputTokens": 900},
            },
        }
        return subprocess.CompletedProcess(args, 0, json.dumps(payload), "")


def gemini(*answers: str, fail: bool = False):
    transport = FakeGemini(*answers, fail=fail)
    return LLM.DsarAssistant("gemini", "clave", "gemini-prueba", transport=transport), transport


def claude(result: str, is_error: bool = False):
    runner = FakeClaude(result, is_error)
    return CLAUDE.ClaudeCodeAgent("claude", runner=runner), runner


class OrchestratorAITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.temp.cleanup()

    def orchestrator(self, assistant=None, claude_agent=None):
        return Orchestrator(
            runtime_dir=Path(self.temp.name), assistant=assistant, claude_agent=claude_agent
        )

    def test_suggestion_is_confirmed_and_recorded(self):
        assistant, _ = gemini(
            '{"right": "objection", "confidence": 0.9, "rationale": "Pide dejar de usar sus datos."}'
        )
        orchestrator = self.orchestrator(assistant)
        request = read_json("request-access.json")
        request["request_text"] = "Ya no quiero que usen mis datos para publicidad"
        suggestion = orchestrator.suggest_right(request["request_text"])
        self.assertEqual(suggestion["suggested_right"], "objection")

        request["request_type"] = "objection"
        request["ai_suggestion_token"] = suggestion["token"]
        package = orchestrator.submit(request)
        classification = package["llm"]["classification"]
        self.assertTrue(classification["confirmed_by_human"])
        self.assertTrue(classification["accepted"])
        self.assertEqual(package["coordination"][1]["agent"], "gemini/gemini-prueba")
        self.assertNotIn("ai_suggestion_token", orchestrator.get_request(package["case_id"]))
        self.assertEqual(VALIDATOR.validate(package), [])

    def test_human_can_correct_the_suggestion(self):
        assistant, _ = gemini('{"right": "erasure", "confidence": 0.6, "rationale": "Ambiguo."}')
        orchestrator = self.orchestrator(assistant)
        request = read_json("request-access.json")
        token = orchestrator.suggest_right(request["request_text"])["token"]
        package = orchestrator.submit({**request, "ai_suggestion_token": token})
        self.assertEqual(package["request_type"], "access")
        self.assertFalse(package["llm"]["classification"]["accepted"])

    def test_suggestion_cannot_be_reused_for_another_text(self):
        assistant, _ = gemini('{"right": "access", "confidence": 0.9, "rationale": ""}')
        orchestrator = self.orchestrator(assistant)
        token = orchestrator.suggest_right("Quiero ver mis datos")["token"]
        request = {**read_json("request-access.json"), "ai_suggestion_token": token}
        with self.assertRaises(CaseInputError):
            orchestrator.submit(request)

    def test_suggestion_without_model_is_unavailable(self):
        with self.assertRaises(AIUnavailable):
            self.orchestrator().suggest_right("Borren mis datos")

    def test_gemini_draft_can_be_chosen_and_sent(self):
        assistant, transport = gemini("Estimada persona titular: su solicitud esta en revision.")
        orchestrator = self.orchestrator(assistant)
        case_id = orchestrator.submit(read_json("request-access.json"))["case_id"]
        draft = orchestrator.generate_ai_draft(case_id, "gemini", "Ana")
        sent = json.dumps(transport.bodies[-1], ensure_ascii=False)
        self.assertNotIn("persona@example.test", sent)
        package = orchestrator.get_case(case_id)
        self.assertEqual(package["status"], "APPROVAL_REQUIRED")
        self.assertEqual(package["ai_drafts"][0]["draft_id"], draft["draft_id"])
        self.assertIn("Borrador generado por gemini", package["audit_trail"][-1]["description"])

        orchestrator.approve(case_id, "Ana", "DPO", "Entregar copia")
        orchestrator.fulfill(case_id, "Ana")
        package = orchestrator.send_response(case_id, "Ana", "email-simulado", draft["draft_id"])
        self.assertEqual(package["outbox"]["body"], draft["body"])
        self.assertEqual(package["outbox"]["source"], draft["draft_id"])
        self.assertEqual(VALIDATOR.validate(package), [])

        package["outbox"]["body_sha256"] = "0" * 64
        self.assertTrue(VALIDATOR.validate(package))

    def test_tampered_ai_draft_is_detected(self):
        assistant, _ = gemini("Borrador original")
        orchestrator = self.orchestrator(assistant)
        case_id = orchestrator.submit(read_json("request-access.json"))["case_id"]
        orchestrator.generate_ai_draft(case_id, "gemini", "Ana")
        package = orchestrator.get_case(case_id)
        package["ai_drafts"][0]["body"] += "\nAccion ejecutada."
        self.assertTrue(any("huella del borrador" in error for error in VALIDATOR.validate(package)))

    def test_gemini_failure_keeps_case_unchanged(self):
        assistant, _ = gemini(fail=True)
        orchestrator = self.orchestrator(assistant)
        case_id = orchestrator.submit(read_json("request-access.json"))["case_id"]
        before = orchestrator.get_case(case_id)
        with self.assertRaises(AIUnavailable):
            orchestrator.generate_ai_draft(case_id, "gemini", "Ana")
        self.assertEqual(orchestrator.get_case(case_id), before)

    def test_claude_agent_drafts_with_read_only_tools(self):
        agent, runner = claude("```markdown\n# Borrador\n\nSu solicitud esta en revision [iso-control-map-03].\n```")
        orchestrator = self.orchestrator(claude_agent=agent)
        case_id = orchestrator.submit(read_json("request-erasure.json"))["case_id"]
        draft = orchestrator.generate_ai_draft(case_id, "claude", "Ana")

        args, prompt = runner.calls[0]
        self.assertEqual(args[args.index("--tools") + 1], "Read,Grep,Glob")
        self.assertEqual(args[args.index("--allowedTools") + 1], "Read,Grep,Glob")
        self.assertIn('"case_id"', prompt)
        self.assertEqual(draft["provider"], "claude-code")
        self.assertEqual(draft["model"], "claude-opus-5-5")
        self.assertIn("[iso-control-map-03]", draft["body"])
        self.assertNotIn("```", draft["body"])
        self.assertIn(CLAUDE.AGENT_NOTICE, draft["body"])
        self.assertNotIn("hechos minimizados", draft["body"])
        self.assertEqual(draft["run"]["num_turns"], 3)
        package = orchestrator.get_case(case_id)
        self.assertFalse(package["proposed_action"]["executed"])
        self.assertEqual(VALIDATOR.validate(package), [])

    def test_claude_error_is_reported(self):
        agent, _ = claude("Not logged in", is_error=True)
        orchestrator = self.orchestrator(claude_agent=agent)
        case_id = orchestrator.submit(read_json("request-access.json"))["case_id"]
        with self.assertRaises(AIUnavailable):
            orchestrator.generate_ai_draft(case_id, "claude", "Ana")

    def test_claude_agent_can_be_disabled(self):
        self.assertIsNone(CLAUDE.ClaudeCodeAgent.from_env({"CLAUDE_AGENT": "0"}))
        agent = CLAUDE.ClaudeCodeAgent.from_env({"CLAUDE_CLI": "C:/tools/claude.exe"})
        self.assertEqual(agent.executable, "C:/tools/claude.exe")


@unittest.skipUnless(WEB_AVAILABLE, "Instale requirements.txt y requirements-dev.txt")
class WebAITests(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient

        from app.main import create_app

        self.temp = tempfile.TemporaryDirectory()
        assistant, _ = gemini(
            '{"right": "erasure", "confidence": 0.95, "rationale": "Pide borrar sus datos."}',
            "Borrador de Gemini",
        )
        agent, _ = claude("Borrador de Claude")
        self.orchestrator = Orchestrator(
            runtime_dir=Path(self.temp.name), assistant=assistant, claude_agent=agent
        )
        self.client = TestClient(create_app(self.orchestrator))

    def tearDown(self):
        self.temp.cleanup()

    def test_web_flow_with_both_models(self):
        status = self.client.get("/api/assist/status").json()
        self.assertEqual(status["assistant"]["provider"], "gemini")
        self.assertEqual(status["claude"]["provider"], "claude-code")

        text = "Borren todos mis datos"
        suggestion = self.client.post("/api/assist/classify", json={"request_text": text}).json()
        self.assertEqual(suggestion["suggested_right"], "erasure")

        form = {
            "request_type": "erasure",
            "principal_id": "person-001",
            "policy_id": "LAB-30",
            "request_text": text,
            "identity_verified": "on",
            "identity_reference": "ref-web",
            "ai_suggestion_token": suggestion["token"],
        }
        response = self.client.post("/solicitudes", data=form, follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        case_id = response.headers["location"].split("/casos/")[1].split("?")[0]

        page = self.client.get(f"/casos/{case_id}").text
        self.assertIn("Redactar con Gemini", page)
        self.assertIn("Redactar con Claude", page)
        self.assertIn("Triaje IA", page)

        for provider in ("gemini", "claude"):
            response = self.client.post(
                f"/casos/{case_id}/borrador/{provider}", data={"actor": "Ana"},
                follow_redirects=False,
            )
            self.assertEqual(response.status_code, 303)
            self.assertNotIn("error=", response.headers["location"])
        drafts = self.orchestrator.get_case(case_id)["ai_drafts"]
        self.assertEqual([item["provider"] for item in drafts], ["gemini", "claude-code"])
        self.assertIn("Borrador de Claude", self.client.get(f"/casos/{case_id}").text)

    def test_classify_without_model_returns_503(self):
        from fastapi.testclient import TestClient

        from app.main import create_app

        client = TestClient(create_app(Orchestrator(runtime_dir=Path(self.temp.name))))
        response = client.post("/api/assist/classify", json={"request_text": "Borren mis datos"})
        self.assertEqual(response.status_code, 503)
        page = client.get("/solicitudes/nueva").text
        self.assertIn("GEMINI_API_KEY", page)


if __name__ == "__main__":
    unittest.main()
