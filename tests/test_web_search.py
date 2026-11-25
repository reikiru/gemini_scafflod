"""Unit tests for tools/web-search (Tavily and Exa CLI)."""

import importlib.machinery
import importlib.util
import io
import json
import os
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent
TOOL_PATH = REPO_ROOT / "tools" / "web-search"


def load_web_search_module():
    loader = importlib.machinery.SourceFileLoader("web_search_cli", str(TOOL_PATH))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


class FakeHTTPResponse:
    def __init__(self, payload, status=200):
        self._body = json.dumps(payload).encode("utf-8")
        self.status = status

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class TestWebSearchCLI(unittest.TestCase):
    def setUp(self):
        self.mod = load_web_search_module()

    def test_tavily_search_request_and_formatting(self):
        captured = {}

        def fake_urlopen(req, timeout=30):
            captured["url"] = req.full_url
            captured["body"] = json.loads(req.data.decode("utf-8"))
            return FakeHTTPResponse({
                "answer": "Short summary",
                "results": [
                    {"title": "Doc A", "url": "https://example.com/a", "content": "Snippet A"},
                ],
            })

        out = io.StringIO()
        with mock.patch.dict(os.environ, {"TAVILY_API_KEY": "tvly-test-key"}, clear=False):
            with mock.patch.object(self.mod.urllib.request, "urlopen", side_effect=fake_urlopen):
                with redirect_stdout(out):
                    rc = self.mod.main(["tavily", "gemini sandbox", "--max-results", "3", "--depth", "advanced"])

        self.assertEqual(rc, 0)
        self.assertEqual(captured["url"], "https://api.tavily.com/search")
        self.assertEqual(captured["body"]["api_key"], "tvly-test-key")
        self.assertEqual(captured["body"]["query"], "gemini sandbox")
        self.assertEqual(captured["body"]["max_results"], 3)
        self.assertEqual(captured["body"]["search_depth"], "advanced")
        self.assertIn("Short summary", out.getvalue())
        self.assertIn("Doc A", out.getvalue())
        self.assertIn("https://example.com/a", out.getvalue())

    def test_exa_search_json_and_headers(self):
        captured = {}

        def fake_urlopen(req, timeout=30):
            captured["url"] = req.full_url
            captured["headers"] = {k.lower(): v for k, v in req.header_items()}
            captured["body"] = json.loads(req.data.decode("utf-8"))
            return FakeHTTPResponse({
                "results": [
                    {"title": "Exa Hit", "url": "https://exa.ai/doc", "text": "Exa content"},
                ],
            })

        out = io.StringIO()
        with mock.patch.dict(os.environ, {"EXA_API_KEY": "exa-test-key"}, clear=False):
            with mock.patch.object(self.mod.urllib.request, "urlopen", side_effect=fake_urlopen):
                with redirect_stdout(out):
                    rc = self.mod.main(["exa", "neural search", "--num-results", "4", "--type", "neural", "--contents", "--json"])

        self.assertEqual(rc, 0)
        self.assertEqual(captured["url"], "https://api.exa.ai/search")
        self.assertEqual(captured["headers"].get("x-api-key"), "exa-test-key")
        self.assertEqual(captured["body"]["numResults"], 4)
        self.assertEqual(captured["body"]["type"], "neural")
        self.assertIn("contents", captured["body"])
        parsed = json.loads(out.getvalue())
        self.assertEqual(parsed["results"][0]["title"], "Exa Hit")

    def test_missing_api_key_returns_nonzero(self):
        err = io.StringIO()
        with mock.patch.dict(os.environ, {}, clear=True):
            with redirect_stderr(err):
                rc = self.mod.main(["tavily", "hello"])
        self.assertEqual(rc, 2)
        self.assertIn("TAVILY_API_KEY", err.getvalue())


if __name__ == "__main__":
    unittest.main()
