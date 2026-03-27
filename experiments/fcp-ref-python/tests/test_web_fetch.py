"""Tests for web_fetch skill and exec_ web allowlist prompt."""

from __future__ import annotations
import importlib.util
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

_SKILLS_LIB = Path(__file__).parent.parent / "skills" / "lib"


def _run_skill(entity_root: Path, params: dict, env: dict | None = None) -> dict:
    """Invoke web_fetch/run.py directly, returning parsed JSON output."""
    skill_path = _SKILLS_LIB / "web_fetch" / "run.py"
    spec = importlib.util.spec_from_file_location("skill_web_fetch", skill_path)
    mod = importlib.util.module_from_spec(spec)

    stdin_data = json.dumps({"params": params, "entity_root": str(entity_root)})
    stdout_capture = io.StringIO()

    extra_env = {**os.environ, **(env or {})}
    with patch("sys.stdin", io.StringIO(stdin_data)), \
         patch("sys.stdout", stdout_capture), \
         patch.dict(os.environ, env or {}, clear=False):
        try:
            spec.loader.exec_module(mod)
        except SystemExit:
            pass

    output = stdout_capture.getvalue().strip()
    return json.loads(output) if output else {}


def _make_entity(allowlist: list[str] | None = None, max_bytes: int | None = None) -> Path:
    """Create a minimal entity root with web_fetch manifest."""
    tmp = Path(tempfile.mkdtemp())
    manifest_dir = tmp / "skills" / "lib" / "web_fetch"
    manifest_dir.mkdir(parents=True)
    manifest: dict = {
        "name": "web_fetch",
        "version": "1.1.0",
        "allowlist": allowlist if allowlist is not None else [],
    }
    if max_bytes is not None:
        manifest["max_bytes"] = max_bytes
    (manifest_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return tmp


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

class TestWebFetchValidation(unittest.TestCase):

    def setUp(self):
        self.tmp = _make_entity(allowlist=["https://example.com/"])

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_missing_url_returns_error(self):
        result = _run_skill(self.tmp, {})
        self.assertIn("error", result)
        self.assertIn("missing required param", result["error"])

    def test_empty_url_returns_error(self):
        result = _run_skill(self.tmp, {"url": ""})
        self.assertIn("error", result)

    def test_ftp_scheme_rejected(self):
        result = _run_skill(self.tmp, {"url": "ftp://example.com/file"})
        self.assertIn("error", result)
        self.assertIn("scheme not permitted", result["error"])

    def test_file_scheme_rejected(self):
        result = _run_skill(self.tmp, {"url": "file:///etc/passwd"})
        self.assertIn("error", result)
        self.assertIn("scheme not permitted", result["error"])


# ---------------------------------------------------------------------------
# Allowlist enforcement
# ---------------------------------------------------------------------------

class TestWebFetchAllowlist(unittest.TestCase):

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_empty_allowlist_blocks_all(self):
        self.tmp = _make_entity(allowlist=[])
        result = _run_skill(self.tmp, {"url": "https://example.com/data"})
        self.assertIn("error", result)
        self.assertIn("URL not in allowlist", result["error"])

    def test_url_not_matching_prefix_blocked(self):
        self.tmp = _make_entity(allowlist=["https://allowed.com/"])
        result = _run_skill(self.tmp, {"url": "https://other.com/page"})
        self.assertIn("error", result)
        self.assertIn("URL not in allowlist", result["error"])

    def test_url_matching_prefix_allowed(self):
        self.tmp = _make_entity(allowlist=["https://example.com/"])
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"hello world"
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = _run_skill(self.tmp, {"url": "https://example.com/page"})
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["content"], "hello world")

    def test_url_without_trailing_slash_matches_prefix(self):
        """https://example.com (no slash) must match allowlist prefix https://example.com/."""
        self.tmp = _make_entity(allowlist=["https://example.com/"])
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"hello"
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = _run_skill(self.tmp, {"url": "https://example.com"})
        self.assertEqual(result["status"], "ok")

    def test_multiple_prefixes_any_match_allowed(self):
        self.tmp = _make_entity(allowlist=["https://a.com/", "https://b.com/"])
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"data"
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = _run_skill(self.tmp, {"url": "https://b.com/resource"})
        self.assertEqual(result["status"], "ok")

    def test_allow_once_env_bypasses_allowlist(self):
        self.tmp = _make_entity(allowlist=[])  # empty = block all normally
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"bypassed"
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        url = "https://example.com/once"
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = _run_skill(self.tmp, {"url": url}, env={"FCP_WEB_FETCH_ALLOW_ONCE": url})
        self.assertEqual(result["status"], "ok")

    def test_allow_once_wrong_url_still_blocked(self):
        self.tmp = _make_entity(allowlist=[])
        result = _run_skill(
            self.tmp,
            {"url": "https://example.com/other"},
            env={"FCP_WEB_FETCH_ALLOW_ONCE": "https://example.com/once"},
        )
        self.assertIn("error", result)
        self.assertIn("URL not in allowlist", result["error"])


# ---------------------------------------------------------------------------
# Network errors
# ---------------------------------------------------------------------------

class TestWebFetchNetworkErrors(unittest.TestCase):

    def setUp(self):
        self.tmp = _make_entity(allowlist=["https://example.com/"])

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_http_error_returned(self):
        import urllib.error
        with patch("urllib.request.urlopen", side_effect=urllib.error.HTTPError(
            url="https://example.com/404", code=404, msg="Not Found", hdrs=None, fp=None
        )):
            result = _run_skill(self.tmp, {"url": "https://example.com/404"})
        self.assertIn("error", result)
        self.assertIn("404", result["error"])

    def test_url_error_returned(self):
        import urllib.error
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("connection refused")):
            result = _run_skill(self.tmp, {"url": "https://example.com/page"})
        self.assertIn("error", result)
        self.assertIn("network error", result["error"])


# ---------------------------------------------------------------------------
# max_bytes
# ---------------------------------------------------------------------------

class TestWebFetchMaxBytes(unittest.TestCase):

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_max_bytes_limits_response(self):
        self.tmp = _make_entity(allowlist=["https://example.com/"], max_bytes=10)
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"0123456789"  # exactly 10 bytes
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = _run_skill(self.tmp, {"url": "https://example.com/big"})
        self.assertEqual(result["status"], "ok")
        # verify read was called with the configured max_bytes
        mock_resp.read.assert_called_once_with(10)


# ---------------------------------------------------------------------------
# exec_.py: _web_allowlist_add
# ---------------------------------------------------------------------------

class TestWebAllowlistAdd(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        manifest_dir = self.tmp / "skills" / "lib" / "web_fetch"
        manifest_dir.mkdir(parents=True)
        self.manifest_path = manifest_dir / "manifest.json"
        self.manifest_path.write_text(json.dumps({
            "name": "web_fetch", "version": "1.1.0", "allowlist": []
        }), encoding="utf-8")

        sys.path.insert(0, str(Path(__file__).parent.parent))
        from fcp_base.store import Layout
        self.layout = Layout(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_add_prefix_from_url(self):
        from fcp_base.exec_ import web_allowlist_add as _web_allowlist_add
        _web_allowlist_add(self.layout, "https://example.com/some/path")
        manifest = json.loads(self.manifest_path.read_text())
        self.assertIn("https://example.com/", manifest["allowlist"])

    def test_add_is_idempotent(self):
        from fcp_base.exec_ import web_allowlist_add as _web_allowlist_add
        _web_allowlist_add(self.layout, "https://example.com/page1")
        _web_allowlist_add(self.layout, "https://example.com/page2")
        manifest = json.loads(self.manifest_path.read_text())
        self.assertEqual(manifest["allowlist"].count("https://example.com/"), 1)

    def test_add_multiple_hosts(self):
        from fcp_base.exec_ import web_allowlist_add as _web_allowlist_add
        _web_allowlist_add(self.layout, "https://a.com/x")
        _web_allowlist_add(self.layout, "https://b.com/y")
        manifest = json.loads(self.manifest_path.read_text())
        self.assertIn("https://a.com/", manifest["allowlist"])
        self.assertIn("https://b.com/", manifest["allowlist"])


if __name__ == "__main__":
    unittest.main()
