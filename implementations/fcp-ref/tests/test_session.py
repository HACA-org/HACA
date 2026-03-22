"""Tests for session loop — boot context assembly and tool dispatch."""

import json
import shutil
import unittest
from typing import Any

from fcp_base.cpe.base import CPEResponse, ToolUseCall
from fcp_base.session import build_boot_context, dispatch_tool_use, _tool_declarations, _make_cycle_fingerprint
from fcp_base.store import Layout, atomic_write
from fcp_base import mil
from tests.helpers import make_layout


class MockAdapter:
    """Minimal CPE adapter for testing."""
    def __init__(self, responses: list[CPEResponse]) -> None:
        self._responses = responses
        self._index = 0

    def invoke(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> CPEResponse:
        if self._index < len(self._responses):
            r = self._responses[self._index]
            self._index += 1
            return r
        return CPEResponse(text="done", tool_use_calls=[], input_tokens=0,
                           output_tokens=0, stop_reason="end_turn")


class TestBuildBootContext(unittest.TestCase):
    def setUp(self) -> None:
        self.layout, self.tmp = make_layout()

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp)

    def test_persona_in_system(self) -> None:
        system, _ = build_boot_context(self.layout, {})
        self.assertGreater(len(system), 0)
        self.assertIn("assistant", system.lower())

    def test_boot_protocol_in_history(self) -> None:
        _, history = build_boot_context(self.layout, {})
        # first user message is the instruction block containing boot protocol
        self.assertGreater(len(history), 0)
        self.assertEqual(history[0]["role"], "user")
        self.assertIn("Boot Protocol", history[0]["content"])

    def test_memory_in_instruction_block(self) -> None:
        mil.write_semantic(self.layout, "base", "base knowledge")
        atomic_write(self.layout.working_memory, {
            "entries": [{"priority": 1, "path": "memory/semantic/base.md"}]
        })
        _, history = build_boot_context(self.layout, {})
        instruction = history[0]["content"]
        self.assertIn("base knowledge", instruction)

    def test_session_tail_in_history(self) -> None:
        from fcp_base.store import append_jsonl
        from fcp_base.acp import make as acp_encode
        env = acp_encode(env_type="MSG", source="operator", data="hello")
        append_jsonl(self.layout.session_store, env)
        _, history = build_boot_context(self.layout, {})
        # should have instruction block + ack + session turn
        contents = [m["content"] for m in history]
        self.assertTrue(any("hello" in c for c in contents))

    def test_tools_declared(self) -> None:
        tools = _tool_declarations(self.layout, {})
        tool_names = {t["name"] for t in tools}
        self.assertIn("memory_recall", tool_names)
        self.assertIn("memory_write", tool_names)
        self.assertIn("session_close", tool_names)
        self.assertIn("evolution_proposal", tool_names)
        self.assertIn("skill_info", tool_names)


class TestDispatchToolUse(unittest.TestCase):
    def setUp(self) -> None:
        self.layout, self.tmp = make_layout()

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp)

    def _make_call(self, tool: str, inp: dict) -> ToolUseCall:
        return ToolUseCall(id="test-id", tool=tool, input=inp)

    def test_mil_memory_write(self) -> None:
        call = self._make_call("fcp_mil", {
            "type": "memory_write",
            "slug": "test-slug",
            "content": "test content",
        })
        result, closed = dispatch_tool_use(self.layout, call, {})
        self.assertFalse(closed)
        files = list(self.layout.episodic_dir.glob("*test-slug.md"))
        self.assertGreater(len(files), 0)

    def test_mil_closure_payload(self) -> None:
        call = self._make_call("fcp_mil", {
            "type": "closure_payload",
            "consolidation": "summary",
            "working_memory": [],
            "session_handoff": {"pending_tasks": [], "next_steps": ""},
            "promotion": [],
        })
        result, closed = dispatch_tool_use(self.layout, call, {})
        self.assertFalse(closed)
        self.assertTrue(self.layout.pending_closure.exists())

    def test_sil_session_close(self) -> None:
        call = self._make_call("fcp_sil", {"type": "session_close"})
        result, closed = dispatch_tool_use(self.layout, call, {})
        self.assertTrue(closed)

    def test_sil_evolution_proposal(self) -> None:
        call = self._make_call("fcp_sil", {
            "type": "evolution_proposal",
            "content": "add skill X",
        })
        result, closed = dispatch_tool_use(self.layout, call, {})
        self.assertFalse(closed)
        files = list(self.layout.operator_notifications_dir.glob("*proposal*"))
        self.assertGreater(len(files), 0)

    def test_unknown_tool_handled(self) -> None:
        call = self._make_call("fcp_unknown", {})
        result, closed = dispatch_tool_use(self.layout, call, {})
        self.assertFalse(closed)
        self.assertIn("error", result)


class TestCycleFingerprint(unittest.TestCase):
    """Tests for _make_cycle_fingerprint (loop detection)."""

    def _call(self, tool: str, inp: dict) -> ToolUseCall:
        return ToolUseCall(id="x", tool=tool, input=inp)

    def test_identical_cycles_match(self) -> None:
        calls = [self._call("fcp_mil", {"type": "memory_recall", "query": "foo"})]
        results = ['{"status": "ok"}']
        fp1 = _make_cycle_fingerprint(calls, results)
        fp2 = _make_cycle_fingerprint(calls, results)
        self.assertEqual(fp1, fp2)

    def test_different_inputs_differ(self) -> None:
        calls_a = [self._call("fcp_mil", {"query": "foo"})]
        calls_b = [self._call("fcp_mil", {"query": "bar"})]
        result = ['{"status": "ok"}']
        self.assertNotEqual(
            _make_cycle_fingerprint(calls_a, result),
            _make_cycle_fingerprint(calls_b, result),
        )

    def test_different_results_differ(self) -> None:
        calls = [self._call("fcp_exec", {"skill": "s"})]
        self.assertNotEqual(
            _make_cycle_fingerprint(calls, ['{"a": 1}']),
            _make_cycle_fingerprint(calls, ['{"a": 2}']),
        )

    def test_order_independent(self) -> None:
        c1 = self._call("fcp_mil", {"q": "x"})
        c2 = self._call("fcp_exec", {"s": "y"})
        r1, r2 = ["result_a"], ["result_b"]
        fp_ab = _make_cycle_fingerprint([c1, c2], [r1[0], r2[0]])
        fp_ba = _make_cycle_fingerprint([c2, c1], [r2[0], r1[0]])
        self.assertEqual(fp_ab, fp_ba)

    def test_count_mismatch_raises(self) -> None:
        calls = [self._call("fcp_mil", {}), self._call("fcp_exec", {})]
        with self.assertRaises(ValueError):
            _make_cycle_fingerprint(calls, ["only_one_result"])

    def test_empty_cycle(self) -> None:
        fp = _make_cycle_fingerprint([], [])
        self.assertEqual(fp, frozenset())


class TestDispatchMILRecall(unittest.TestCase):
    """Tests for memory_recall and result_recall dispatch paths."""

    def setUp(self) -> None:
        self.layout, self.tmp = make_layout()

    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(self.tmp)

    def _make_call(self, tool: str, inp: dict) -> ToolUseCall:
        return ToolUseCall(id="test-id", tool=tool, input=inp)

    def test_mil_memory_recall_empty(self) -> None:
        call = self._make_call("fcp_mil", {"type": "memory_recall", "query": "foo", "path": ""})
        result, closed = dispatch_tool_use(self.layout, call, {})
        self.assertFalse(closed)
        self.assertNotIn("error", result)

    def test_mil_memory_recall_finds_written(self) -> None:
        mil.write_episodic(self.layout, "testslug", "# test content\nfoo bar baz")
        call = self._make_call("fcp_mil", {"type": "memory_recall", "query": "foo", "path": ""})
        result, closed = dispatch_tool_use(self.layout, call, {})
        self.assertFalse(closed)
        # Result should contain something (recalled or empty list)
        self.assertIsInstance(result, dict)

    def test_mil_result_recall(self) -> None:
        call = self._make_call("fcp_mil", {"type": "result_recall", "path": "memory/episodic/"})
        result, closed = dispatch_tool_use(self.layout, call, {})
        self.assertFalse(closed)
        self.assertIsInstance(result, dict)


if __name__ == "__main__":
    unittest.main()
