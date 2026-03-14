"""Tests for session loop — context assembly and tool dispatch."""

import json
import shutil
import unittest
from typing import Any

from fcp_core.cpe.base import CPEResponse, FCPContext, ToolUseCall
from fcp_core.session import assemble_context, dispatch_tool_use
from fcp_core.store import Layout, atomic_write
from fcp_core import mil
from tests.helpers import make_layout


class MockAdapter:
    """Minimal CPE adapter for testing."""
    def __init__(self, responses: list[CPEResponse]) -> None:
        self._responses = responses
        self._index = 0

    def invoke(self, context: FCPContext) -> CPEResponse:
        if self._index < len(self._responses):
            r = self._responses[self._index]
            self._index += 1
            return r
        return CPEResponse(text="done", tool_use_calls=[], input_tokens=0,
                           output_tokens=0, stop_reason="end_turn")


class TestAssembleContext(unittest.TestCase):
    def setUp(self) -> None:
        self.layout, self.tmp = make_layout()

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp)

    def test_persona_loaded(self) -> None:
        ctx = assemble_context(self.layout, {})
        self.assertGreater(len(ctx.persona), 0)
        self.assertIn("assistant", ctx.persona[0].lower())

    def test_boot_protocol_loaded(self) -> None:
        ctx = assemble_context(self.layout, {})
        self.assertIn("Boot Protocol", ctx.boot_protocol)

    def test_memory_loaded(self) -> None:
        mil.write_semantic(self.layout, "base", "base knowledge")
        atomic_write(self.layout.working_memory, {
            "entries": [{"priority": 1, "path": "memory/semantic/base.md"}]
        })
        ctx = assemble_context(self.layout, {})
        self.assertGreater(len(ctx.memory), 0)
        self.assertIn("base knowledge", ctx.memory[0])

    def test_session_records_loaded(self) -> None:
        from fcp_core.store import append_jsonl
        from fcp_core.acp import make as acp_encode
        env = acp_encode(env_type="MSG", source="operator", data="hello")
        append_jsonl(self.layout.session_store, env)
        ctx = assemble_context(self.layout, {})
        self.assertGreater(len(ctx.session), 0)

    def test_tools_declared(self) -> None:
        ctx = assemble_context(self.layout, {})
        tool_names = {t["name"] for t in ctx.tools}
        self.assertIn("fcp_exec", tool_names)
        self.assertIn("fcp_mil", tool_names)
        self.assertIn("fcp_sil", tool_names)


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


if __name__ == "__main__":
    unittest.main()
