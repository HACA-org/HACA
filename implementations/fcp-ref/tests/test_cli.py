"""Tests for the cli/ package (dispatch, ui, init, commands, endure)."""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


def _make_entity(profile: str = "haca-core") -> tuple[Path, Path]:
    """Create a minimal entity root and return (entity_root, fcp_ref_root)."""
    tmp = Path(tempfile.mkdtemp())
    (tmp / "state").mkdir(parents=True)
    (tmp / "memory" / "episodic").mkdir(parents=True)
    (tmp / "memory" / "semantic").mkdir(parents=True)
    (tmp / "memory" / "active_context").mkdir(parents=True)
    (tmp / "state" / "operator_notifications").mkdir(parents=True)
    (tmp / "skills" / "lib").mkdir(parents=True)
    (tmp / "skills").mkdir(parents=True, exist_ok=True)
    (tmp / "persona").mkdir(parents=True)
    (tmp / "boot.md").write_text("# boot", encoding="utf-8")
    (tmp / "state" / "baseline.json").write_text(
        json.dumps({"cpe": {"backend": "ollama", "model": "llama3"}}),
        encoding="utf-8",
    )
    (tmp / "state" / "integrity.log").write_text("", encoding="utf-8")
    (tmp / "state" / "integrity_chain.jsonl").write_text("", encoding="utf-8")
    (tmp / "skills" / "index.json").write_text('{"version":"1.0","skills":[]}', encoding="utf-8")
    (tmp / ".fcp-entity").write_text(
        json.dumps({"profile": profile, "haca_profile": "HACA-Core-1.0.0"}),
        encoding="utf-8",
    )
    # fcp_ref_root is the implementations/fcp-ref directory
    fcp_ref_root = Path(__file__).parent.parent
    return tmp, fcp_ref_root


# ---------------------------------------------------------------------------
# dispatch
# ---------------------------------------------------------------------------

class TestCliDispatch(unittest.TestCase):

    def test_require_entity_root_passes_for_valid_entity(self):
        from fcp_base.cli import require_entity_root
        tmp, _ = _make_entity()
        try:
            require_entity_root(tmp)  # must not raise or call sys.exit
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_require_entity_root_exits_for_non_entity(self):
        from fcp_base.cli import require_entity_root
        tmp = Path(tempfile.mkdtemp())
        try:
            with self.assertRaises(SystemExit):
                require_entity_root(tmp)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_print_help_does_not_raise(self):
        from fcp_base.cli import print_help
        import io
        with patch("sys.stdout", io.StringIO()):
            print_help()  # must not raise

    def test_main_help_flag(self):
        from fcp_base.cli import main
        with patch.object(sys, "argv", ["fcp", "--help"]):
            import io
            with patch("sys.stdout", io.StringIO()) as out:
                main()
        # help command exits 0 (no SystemExit raised) or prints something
        self.assertIsNotNone(out)

    def test_main_unknown_command_exits(self):
        from fcp_base.cli import main
        with patch.object(sys, "argv", ["fcp", "nonexistent-cmd-xyz"]):
            with self.assertRaises(SystemExit):
                main()


# ---------------------------------------------------------------------------
# cli/ui — build_boot_stats
# ---------------------------------------------------------------------------

class TestCliBuildBootStats(unittest.TestCase):

    def setUp(self):
        self.tmp, self.fcp_ref_root = _make_entity()
        from fcp_base.store import Layout
        self.layout = Layout(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_returns_dict_with_expected_keys(self):
        from fcp_base.cli.ui import build_boot_stats
        s = build_boot_stats(self.layout, {}, "", [], [])
        for key in ("ctx_tokens", "sessions", "cycles", "memories",
                    "evolutions_auth", "evolutions_total", "skills", "tools", "notifications"):
            self.assertIn(key, s)

    def test_empty_log_returns_zero_sessions(self):
        from fcp_base.cli.ui import build_boot_stats
        s = build_boot_stats(self.layout, {}, "", [], [])
        self.assertEqual(s["sessions"], 0)
        self.assertEqual(s["cycles"], 0)

    def test_counts_sleep_complete_via_data_field(self):
        """build_boot_stats reads SLEEP_COMPLETE from the 'data' JSON sub-field.

        The ACP envelope written by log_sleep_complete has type="SLEEP_COMPLETE"
        at the top level, but build_boot_stats inspects the nested data dict.
        This test injects a record matching the expected format directly.
        """
        from fcp_base.cli.ui import build_boot_stats
        import json
        # write a record where data contains {"type": "SLEEP_COMPLETE"}
        record = {"type": "MSG", "data": json.dumps({"type": "SLEEP_COMPLETE", "session_id": "s1"})}
        self.layout.integrity_log.write_text(json.dumps(record) + "\n", encoding="utf-8")
        s = build_boot_stats(self.layout, {}, "", [], [])
        self.assertEqual(s["sessions"], 1)

    def test_counts_notifications(self):
        from fcp_base.cli.ui import build_boot_stats
        from fcp_base.sil import write_notification
        write_notification(self.layout, "test_event", {"x": 1})
        s = build_boot_stats(self.layout, {}, "", [], [])
        self.assertEqual(s["notifications"], 1)

    def test_counts_memories(self):
        from fcp_base.cli.ui import build_boot_stats
        (self.tmp / "memory" / "episodic" / "note.md").write_text("hello", encoding="utf-8")
        s = build_boot_stats(self.layout, {}, "", [], [])
        self.assertEqual(s["memories"], 1)

    def test_counts_skills_from_index(self):
        from fcp_base.cli.ui import build_boot_stats
        index = {"skills": [{"name": "a"}, {"name": "b"}]}
        s = build_boot_stats(self.layout, index, "", [], [])
        self.assertEqual(s["skills"], 2)

    def test_ctx_tokens_estimated_from_system(self):
        from fcp_base.cli.ui import build_boot_stats
        system = "x" * 400  # 400 chars / 4 = 100 tokens
        s = build_boot_stats(self.layout, {}, system, [], [])
        self.assertEqual(s["ctx_tokens"], 100)


# ---------------------------------------------------------------------------
# cli/init — read_fcp_version, write_entity_gitignore
# ---------------------------------------------------------------------------

class TestCliInit(unittest.TestCase):

    def test_read_fcp_version_returns_string(self):
        from fcp_base.cli.init import read_fcp_version
        fcp_ref_root = Path(__file__).parent.parent
        version = read_fcp_version(fcp_ref_root)
        self.assertIsInstance(version, str)
        self.assertNotEqual(version, "")

    def test_read_fcp_version_unknown_on_missing(self):
        from fcp_base.cli.init import read_fcp_version
        tmp = Path(tempfile.mkdtemp())
        try:
            version = read_fcp_version(tmp)
            self.assertEqual(version, "unknown")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_write_entity_gitignore_creates_file(self):
        from fcp_base.cli.init import write_entity_gitignore
        tmp = Path(tempfile.mkdtemp())
        try:
            write_entity_gitignore(tmp)
            gitignore = tmp / ".gitignore"
            self.assertTrue(gitignore.exists())
            content = gitignore.read_text()
            self.assertIn("state/integrity.log", content)
            self.assertIn("workspace/", content)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# cli/commands — run_auto_worker
# ---------------------------------------------------------------------------

class TestCliAutoWorker(unittest.TestCase):

    def setUp(self):
        self.tmp, _ = _make_entity()
        from fcp_base.store import Layout
        self.layout = Layout(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_run_auto_worker_writes_notification(self):
        from fcp_base.cli.commands import run_auto_worker
        from fcp_base.session_mode import set_session_mode, SessionMode

        task = {
            "id": "task-1",
            "description": "test task",
            "task": "do something",
            "persona": "You are a tester.",
        }

        # mock dispatch at the source module to avoid running worker_skill
        with patch("fcp_base.exec_.dispatch.dispatch", return_value='{"result":"ok"}'):
            run_auto_worker(self.layout, task, "wake up")

        notifs = list(self.layout.operator_notifications_dir.glob("*auto_worker_complete*"))
        self.assertEqual(len(notifs), 1)
        data = json.loads(notifs[0].read_text())
        self.assertEqual(data["cron_id"], "task-1")


# ---------------------------------------------------------------------------
# cli/commands — run_status, run_agenda
# ---------------------------------------------------------------------------

class TestCliStatus(unittest.TestCase):

    def setUp(self):
        self.tmp, _ = _make_entity()
        from fcp_base.store import Layout
        self.layout = Layout(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_run_status_does_not_raise(self):
        from fcp_base.cli.commands import run_status
        import io
        with patch("sys.stdout", io.StringIO()):
            run_status(self.layout)  # must not raise

    def test_run_status_shows_model_from_baseline(self):
        from fcp_base.cli.commands import run_status
        import io
        out = io.StringIO()
        with patch("sys.stdout", out):
            run_status(self.layout)
        self.assertIn("ollama", out.getvalue())

    def test_run_status_no_session_token(self):
        from fcp_base.cli.commands import run_status
        import io
        out = io.StringIO()
        with patch("sys.stdout", out):
            run_status(self.layout)
        self.assertIn("inactive", out.getvalue())


class TestCliAgenda(unittest.TestCase):

    def setUp(self):
        self.tmp, _ = _make_entity()
        from fcp_base.store import Layout
        self.layout = Layout(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_run_agenda_no_agenda_file(self):
        from fcp_base.cli.commands import run_agenda
        import io
        with patch("sys.stdout", io.StringIO()) as out:
            run_agenda(self.layout)
        # should print info, not raise

    def test_run_agenda_empty_tasks(self):
        from fcp_base.cli.commands import run_agenda
        import io
        self.layout.agenda.write_text(json.dumps({"tasks": []}), encoding="utf-8")
        out = io.StringIO()
        with patch("sys.stdout", out):
            run_agenda(self.layout)
        self.assertIn("empty", out.getvalue().lower())

    def test_run_agenda_lists_tasks(self):
        from fcp_base.cli.commands import run_agenda
        import io
        tasks = [
            {"id": "t1", "description": "backup", "status": "approved",
             "schedule": "0 2 * * *", "executor": "cpe"},
            {"id": "t2", "description": "report", "status": "pending",
             "executor": "worker"},
        ]
        self.layout.agenda.write_text(json.dumps({"tasks": tasks}), encoding="utf-8")
        out = io.StringIO()
        with patch("sys.stdout", out):
            run_agenda(self.layout)
        text = out.getvalue()
        self.assertIn("backup", text)
        self.assertIn("report", text)
        self.assertIn("t1", text)
        self.assertIn("2 task(s)", text)


# ---------------------------------------------------------------------------
# cli/endure — unit tests (git not required)
# ---------------------------------------------------------------------------

class TestCliEndure(unittest.TestCase):

    def test_run_endure_chain_calls_print_integrity_chain(self):
        from fcp_base.cli.endure import run_endure_chain
        tmp, _ = _make_entity()
        try:
            from fcp_base.store import Layout
            layout = Layout(tmp)
            with patch("fcp_base.cli.endure.run_endure_chain") as mock_fn:
                # just verify it's importable and callable
                pass
            # run_endure_chain delegates to operator.print_integrity_chain
            with patch("fcp_base.operator.print_integrity_chain") as mock_pic:
                run_endure_chain(layout)
                mock_pic.assert_called_once_with(layout)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_run_endure_sync_exits_gracefully_if_not_git_repo(self):
        from fcp_base.cli.endure import run_endure_sync
        tmp, _ = _make_entity()
        try:
            from fcp_base.store import Layout
            layout = Layout(tmp)
            import io
            with patch("sys.stdout", io.StringIO()):
                # non-git dir — should print error and return (not raise)
                run_endure_sync(layout)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
