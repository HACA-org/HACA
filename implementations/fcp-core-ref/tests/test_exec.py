"""Tests for EXEC — Execution Layer."""

import json
import shutil
import unittest
from pathlib import Path

from fcp_core import exec_
from fcp_core.store import Layout, atomic_write
from tests.helpers import make_layout


def _make_index(skills: list[dict]) -> dict:
    return {"version": "1.0.0", "skills": skills, "aliases": {}}


class TestDispatchRejectsOperatorClass(unittest.TestCase):
    def setUp(self) -> None:
        self.layout, self.tmp = make_layout()

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp)

    def test_operator_class_rejected(self) -> None:
        index = _make_index([{
            "name": "secret_op",
            "class": "operator",
            "manifest": "skills/lib/secret_op/manifest.json",
        }])
        with self.assertRaises(exec_.SkillRejected):
            exec_.dispatch(self.layout, "secret_op", {}, index)

    def test_missing_skill_rejected(self) -> None:
        index = _make_index([])
        with self.assertRaises(exec_.SkillRejected):
            exec_.dispatch(self.layout, "nonexistent", {}, index)


class TestDispatchBuiltinSkill(unittest.TestCase):
    def setUp(self) -> None:
        self.layout, self.tmp = make_layout()
        # install a minimal test skill
        skill_dir = self.layout.skills_lib_dir / "echo_skill"
        skill_dir.mkdir(parents=True, exist_ok=True)
        manifest = {
            "name": "echo_skill",
            "version": "1.0.0",
            "description": "Echo input params",
            "timeout_seconds": 5,
            "background": False,
            "irreversible": False,
            "class": "builtin",
            "permissions": [],
        }
        atomic_write(skill_dir / "manifest.json", manifest)
        (skill_dir / "run.py").write_text(
            'import json, sys\n'
            'req = json.loads(sys.stdin.read())\n'
            'print(json.dumps({"echo": req.get("params", {})}))\n',
            encoding="utf-8"
        )
        self.index = _make_index([{
            "name": "echo_skill",
            "class": "builtin",
            "manifest": "skills/lib/echo_skill/manifest.json",
        }])

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp)

    def test_dispatch_succeeds(self) -> None:
        output = exec_.dispatch(self.layout, "echo_skill", {"key": "val"}, self.index)
        data = json.loads(output)
        self.assertEqual(data["echo"]["key"], "val")

    def test_result_written_to_inbox(self) -> None:
        exec_.dispatch(self.layout, "echo_skill", {}, self.index)
        files = list(self.layout.inbox_dir.glob("*skill_result*"))
        self.assertGreater(len(files), 0)

    def test_failure_writes_error_to_inbox(self) -> None:
        # break the executable so it fails
        skill_dir = self.layout.skills_lib_dir / "echo_skill"
        (skill_dir / "run.py").write_text("import sys; sys.exit(1)\n", encoding="utf-8")
        with self.assertRaises(Exception):
            exec_.dispatch(self.layout, "echo_skill", {}, self.index)
        files = list(self.layout.inbox_dir.glob("*skill_error*"))
        self.assertGreater(len(files), 0)


class TestActionLedger(unittest.TestCase):
    def setUp(self) -> None:
        self.layout, self.tmp = make_layout()
        skill_dir = self.layout.skills_lib_dir / "irrev_skill"
        skill_dir.mkdir(parents=True, exist_ok=True)
        manifest = {
            "name": "irrev_skill",
            "version": "1.0.0",
            "description": "Irreversible skill",
            "timeout_seconds": 5,
            "background": False,
            "irreversible": True,
            "class": "builtin",
            "permissions": [],
        }
        atomic_write(skill_dir / "manifest.json", manifest)
        (skill_dir / "run.py").write_text(
            'import json, sys\nprint(json.dumps({"status": "done"}))\n',
            encoding="utf-8"
        )
        self.index = _make_index([{
            "name": "irrev_skill",
            "class": "builtin",
            "manifest": "skills/lib/irrev_skill/manifest.json",
        }])

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp)

    def test_ledger_write_ahead_and_resolve(self) -> None:
        exec_.dispatch(self.layout, "irrev_skill", {}, self.index)
        from fcp_core.store import read_jsonl
        records = read_jsonl(self.layout.session_store)
        import json as _json
        def _status(r: dict) -> object:
            d = r.get("data", {})
            if isinstance(d, str):
                try:
                    d = _json.loads(d)
                except Exception:
                    return None
            return d.get("status") if isinstance(d, dict) else None
        types = [_status(r) for r in records]
        self.assertIn("in_progress", types)
        self.assertIn("complete", types)


class TestCheckSilHeartbeat(unittest.TestCase):
    def setUp(self) -> None:
        self.layout, self.tmp = make_layout()

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp)

    def test_no_heartbeat_passes(self) -> None:
        # no heartbeat yet — should not fail
        result = exec_.check_sil_heartbeat(self.layout)
        self.assertTrue(result)

    def test_recent_heartbeat_passes(self) -> None:
        import time
        from fcp_core.acp import make as acp_encode
        from fcp_core.store import append_jsonl
        hb = acp_encode(env_type="HEARTBEAT", source="sil",
                        data={"ts": time.time()})
        append_jsonl(self.layout.integrity_log, hb)
        result = exec_.check_sil_heartbeat(self.layout)
        self.assertTrue(result)


if __name__ == "__main__":
    unittest.main()
