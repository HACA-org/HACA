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
            self.assertNotIn("workspace/", content)
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


# ---------------------------------------------------------------------------
# cli/commands — run_update
# ---------------------------------------------------------------------------

def _make_fake_fcp_ref(version: str = "1.1.0") -> Path:
    """Create a minimal fcp-ref directory tree simulating a downloaded update."""
    tmp = Path(tempfile.mkdtemp())
    # pyproject.toml with version
    (tmp / "pyproject.toml").write_text(f'[project]\nversion = "{version}"\n', encoding="utf-8")
    # fcp launcher
    fcp_exe = tmp / "fcp"
    fcp_exe.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    fcp_exe.chmod(0o755)
    # boot.md
    (tmp / "boot.md").write_text(f"# boot v{version}\n", encoding="utf-8")
    # fcp_base/
    (tmp / "fcp_base").mkdir()
    (tmp / "fcp_base" / "version.py").write_text(f'__version__ = "{version}"\n', encoding="utf-8")
    # skills/lib/
    (tmp / "skills" / "lib" / "builtin_skill").mkdir(parents=True)
    (tmp / "skills" / "lib" / "builtin_skill" / "run.py").write_text("# builtin\n", encoding="utf-8")
    # hooks/
    (tmp / "hooks").mkdir()
    (tmp / "hooks" / "on_boot.sh").write_text("#!/bin/bash\n# boot hook\n", encoding="utf-8")
    return tmp


def _make_entity_with_version(version: str = "1.0.0") -> Path:
    """Create a minimal entity root with a versioned .fcp-entity marker."""
    tmp = Path(tempfile.mkdtemp())
    for d in ["state", "memory/episodic", "memory/semantic", "memory/active_context",
              "state/operator_notifications", "skills/lib", "persona", "hooks", "fcp_base"]:
        (tmp / d).mkdir(parents=True, exist_ok=True)
    (tmp / "boot.md").write_text(f"# boot v{version}\n", encoding="utf-8")
    (tmp / "fcp_base" / "version.py").write_text(f'__version__ = "{version}"\n', encoding="utf-8")
    (tmp / "hooks" / "on_boot.sh").write_text("#!/bin/bash\n# old hook\n", encoding="utf-8")
    (tmp / "hooks" / "on_custom.sh").write_text("#!/bin/bash\n# custom hook\n", encoding="utf-8")
    (tmp / "state" / "baseline.json").write_text(
        json.dumps({"cpe": {"backend": "ollama", "model": "llama3"}}), encoding="utf-8"
    )
    (tmp / ".fcp-entity").write_text(
        json.dumps({"profile": "haca-core", "version": version}), encoding="utf-8"
    )
    (tmp / "fcp").write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    return tmp


class TestRunUpdate(unittest.TestCase):
    """Tests for run_update — network call is mocked via _download_fcp_ref."""

    def _patch_download(self, new_fcp_ref: Path):
        """Patch urllib.request.urlopen and tarfile.open to serve new_fcp_ref."""
        import io as _io
        import tarfile as _tarfile

        def fake_urlopen(url, timeout=30):
            # Build an in-memory tarball containing new_fcp_ref/ as HACA-main/implementations/fcp-ref/
            buf = _io.BytesIO()
            with _tarfile.open(fileobj=buf, mode="w:gz") as tf:
                prefix = "HACA-main/implementations/fcp-ref"
                for item in new_fcp_ref.rglob("*"):
                    arcname = prefix + "/" + str(item.relative_to(new_fcp_ref))
                    tf.add(item, arcname=arcname)
            buf.seek(0)

            class _FakeResp:
                def read(self): return buf.read()
                def __enter__(self): return self
                def __exit__(self, *a): pass

            return _FakeResp()

        return patch("urllib.request.urlopen", side_effect=fake_urlopen)

    def test_dry_run_does_not_write_files(self):
        """--dry-run must not modify fcp_ref_root or any entity."""
        from fcp_base.cli.commands import run_update
        from fcp_base.store import FCP_ENTITIES_DIR

        new_ref = _make_fake_fcp_ref("1.1.0")
        entity = _make_entity_with_version("1.0.0")

        try:
            original_boot = (entity / "boot.md").read_text()

            with self._patch_download(new_ref), \
                 patch("fcp_base.store.FCP_ENTITIES_DIR", entity.parent), \
                 patch("fcp_base.store.list_entities", return_value=[entity.name]), \
                 patch("fcp_base.store.entity_root_for", return_value=entity), \
                 patch("fcp_base.cli.commands.Path.__file__", create=True), \
                 patch("sys.stdout", __import__("io").StringIO()):
                # patch fcp_ref_root resolution via __file__
                fake_cli = entity.parent / "fcp_ref" / "fcp_base" / "cli" / "commands.py"
                fake_cli.parent.mkdir(parents=True, exist_ok=True)
                with patch.object(
                    __import__("fcp_base.cli.commands", fromlist=["run_update"]),
                    "__file__", str(fake_cli)
                ):
                    pass  # can't easily patch __file__ — use alternative below

            # Simpler: call the internal logic directly by patching cli file path
            import fcp_base.cli.commands as _cmd_mod
            orig_file = _cmd_mod.__file__

            fake_cli_file = str(new_ref / "fcp_base" / "cli" / "commands.py")
            with self._patch_download(new_ref), \
                 patch.object(_cmd_mod, "__file__", fake_cli_file), \
                 patch("fcp_base.store.list_entities", return_value=[entity.name]), \
                 patch("fcp_base.store.entity_root_for", return_value=entity), \
                 patch("sys.stdout", __import__("io").StringIO()):
                run_update(dry_run=True)

            # boot.md must be unchanged
            self.assertEqual((entity / "boot.md").read_text(), original_boot)
            # .fcp-entity version must be unchanged
            marker = json.loads((entity / ".fcp-entity").read_text())
            self.assertEqual(marker["version"], "1.0.0")
        finally:
            shutil.rmtree(new_ref, ignore_errors=True)
            shutil.rmtree(entity, ignore_errors=True)

    def test_update_replaces_fcp_base_and_boot(self):
        """Confirmed update must overwrite fcp_base/ and boot.md."""
        from fcp_base.cli.commands import run_update
        import fcp_base.cli.commands as _cmd_mod

        new_ref = _make_fake_fcp_ref("1.1.0")
        entity = _make_entity_with_version("1.0.0")

        try:
            fake_cli_file = str(new_ref / "fcp_base" / "cli" / "commands.py")
            with self._patch_download(new_ref), \
                 patch.object(_cmd_mod, "__file__", fake_cli_file), \
                 patch("fcp_base.store.list_entities", return_value=[entity.name]), \
                 patch("fcp_base.store.entity_root_for", return_value=entity), \
                 patch("fcp_base.cli.commands.ui.confirm", return_value=True), \
                 patch("sys.stdout", __import__("io").StringIO()):
                run_update(dry_run=False)

            # boot.md updated
            self.assertIn("1.1.0", (entity / "boot.md").read_text())
            # fcp_base updated
            self.assertIn("1.1.0", (entity / "fcp_base" / "version.py").read_text())
            # .fcp-entity version bumped
            marker = json.loads((entity / ".fcp-entity").read_text())
            self.assertEqual(marker["version"], "1.1.0")
        finally:
            shutil.rmtree(new_ref, ignore_errors=True)
            shutil.rmtree(entity, ignore_errors=True)

    def test_update_preserves_custom_hooks(self):
        """hooks/on_custom.sh (not in template) must survive an update."""
        from fcp_base.cli.commands import run_update
        import fcp_base.cli.commands as _cmd_mod

        new_ref = _make_fake_fcp_ref("1.1.0")
        entity = _make_entity_with_version("1.0.0")

        try:
            fake_cli_file = str(new_ref / "fcp_base" / "cli" / "commands.py")
            with self._patch_download(new_ref), \
                 patch.object(_cmd_mod, "__file__", fake_cli_file), \
                 patch("fcp_base.store.list_entities", return_value=[entity.name]), \
                 patch("fcp_base.store.entity_root_for", return_value=entity), \
                 patch("fcp_base.cli.commands.ui.confirm", return_value=True), \
                 patch("sys.stdout", __import__("io").StringIO()):
                run_update(dry_run=False)

            self.assertTrue((entity / "hooks" / "on_custom.sh").exists())
            self.assertIn("custom hook", (entity / "hooks" / "on_custom.sh").read_text())
        finally:
            shutil.rmtree(new_ref, ignore_errors=True)
            shutil.rmtree(entity, ignore_errors=True)

    def test_update_skipped_on_decline(self):
        """Declining confirmation must leave entity untouched."""
        from fcp_base.cli.commands import run_update
        import fcp_base.cli.commands as _cmd_mod

        new_ref = _make_fake_fcp_ref("1.1.0")
        entity = _make_entity_with_version("1.0.0")

        try:
            original_boot = (entity / "boot.md").read_text()
            fake_cli_file = str(new_ref / "fcp_base" / "cli" / "commands.py")
            with self._patch_download(new_ref), \
                 patch.object(_cmd_mod, "__file__", fake_cli_file), \
                 patch("fcp_base.store.list_entities", return_value=[entity.name]), \
                 patch("fcp_base.store.entity_root_for", return_value=entity), \
                 patch("fcp_base.cli.commands.ui.confirm", return_value=False), \
                 patch("sys.stdout", __import__("io").StringIO()):
                run_update(dry_run=False)

            self.assertEqual((entity / "boot.md").read_text(), original_boot)
            marker = json.loads((entity / ".fcp-entity").read_text())
            self.assertEqual(marker["version"], "1.0.0")
        finally:
            shutil.rmtree(new_ref, ignore_errors=True)
            shutil.rmtree(entity, ignore_errors=True)

    def test_skills_lib_replaced_custom_skills_preserved(self):
        """skills/lib/ is replaced; custom skills outside lib/ are untouched."""
        from fcp_base.cli.commands import run_update
        import fcp_base.cli.commands as _cmd_mod

        new_ref = _make_fake_fcp_ref("1.1.0")
        entity = _make_entity_with_version("1.0.0")
        # add a custom skill
        custom_skill = entity / "skills" / "my_custom_skill"
        custom_skill.mkdir(parents=True)
        (custom_skill / "run.py").write_text("# custom\n", encoding="utf-8")

        try:
            fake_cli_file = str(new_ref / "fcp_base" / "cli" / "commands.py")
            with self._patch_download(new_ref), \
                 patch.object(_cmd_mod, "__file__", fake_cli_file), \
                 patch("fcp_base.store.list_entities", return_value=[entity.name]), \
                 patch("fcp_base.store.entity_root_for", return_value=entity), \
                 patch("fcp_base.cli.commands.ui.confirm", return_value=True), \
                 patch("sys.stdout", __import__("io").StringIO()):
                run_update(dry_run=False)

            # builtin skill updated
            self.assertTrue((entity / "skills" / "lib" / "builtin_skill" / "run.py").exists())
            # custom skill preserved
            self.assertTrue((entity / "skills" / "my_custom_skill" / "run.py").exists())
        finally:
            shutil.rmtree(new_ref, ignore_errors=True)
            shutil.rmtree(entity, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
