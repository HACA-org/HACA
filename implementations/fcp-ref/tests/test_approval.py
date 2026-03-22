"""Tests for fcp_base.approval — operator approval gate."""

from __future__ import annotations

import json
import shutil
import unittest
from pathlib import Path
from unittest.mock import patch

from fcp_base.approval import ApprovalDecision, request_approval
from tests.helpers import make_layout


def _base_kwargs(layout, **overrides):
    kwargs = dict(
        layout=layout,
        subject="test_skill",
        detail="some-value",
        prompt="Allow?",
        options=("allow_once", "allow_always", "deny"),
        notification_severity="test_skill_blocked",
        notification_payload={
            "message": "blocked",
            "value": "some-value",
            "context": "auto:session",
        },
    )
    kwargs.update(overrides)
    return kwargs


class TestAutoSessionAlwaysDenies(unittest.TestCase):

    def setUp(self):
        self.layout, self.tmp = make_layout()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_returns_deny_in_auto_session(self):
        with patch("fcp_base.approval.is_auto_session", return_value=True):
            result = request_approval(**_base_kwargs(self.layout))
        self.assertEqual(result, ApprovalDecision.DENY)

    def test_writes_notification_file_in_auto_session(self):
        notif_dir = self.layout.operator_notifications_dir
        with patch("fcp_base.approval.is_auto_session", return_value=True):
            request_approval(**_base_kwargs(self.layout))
        files = list(notif_dir.glob("*.test_skill_blocked.json"))
        self.assertEqual(len(files), 1)

    def test_notification_payload_content(self):
        with patch("fcp_base.approval.is_auto_session", return_value=True):
            request_approval(**_base_kwargs(self.layout))
        files = list(self.layout.operator_notifications_dir.glob("*.test_skill_blocked.json"))
        payload = json.loads(files[0].read_text())
        self.assertEqual(payload["message"], "blocked")
        self.assertEqual(payload["value"], "some-value")

    def test_no_notification_in_main_session_deny(self):
        notif_dir = self.layout.operator_notifications_dir
        # main:session, operator picks deny
        with patch("fcp_base.approval.is_auto_session", return_value=False), \
             patch("fcp_base.approval._interactive_prompt", return_value=ApprovalDecision.DENY):
            request_approval(**_base_kwargs(self.layout))
        files = list(notif_dir.glob("*.json"))
        self.assertEqual(len(files), 0)


class TestMainSessionInteractiveDecisions(unittest.TestCase):

    def setUp(self):
        self.layout, self.tmp = make_layout()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def _call(self, decision: ApprovalDecision) -> ApprovalDecision:
        with patch("fcp_base.approval.is_auto_session", return_value=False), \
             patch("fcp_base.approval._interactive_prompt", return_value=decision):
            return request_approval(**_base_kwargs(self.layout))

    def test_allow_once_returned(self):
        self.assertEqual(self._call(ApprovalDecision.ALLOW_ONCE), ApprovalDecision.ALLOW_ONCE)

    def test_allow_always_returned(self):
        self.assertEqual(self._call(ApprovalDecision.ALLOW_ALWAYS), ApprovalDecision.ALLOW_ALWAYS)

    def test_deny_returned(self):
        self.assertEqual(self._call(ApprovalDecision.DENY), ApprovalDecision.DENY)


class TestInteractivePromptFallbacks(unittest.TestCase):
    """_interactive_prompt must return DENY on any terminal error."""

    def setUp(self):
        self.layout, self.tmp = make_layout()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def _prompt(self, side_effect):
        from fcp_base.approval import _interactive_prompt
        with patch("fcp_base.approval.ui.pick_one", side_effect=side_effect), \
             patch("fcp_base.approval.ui.hr"), \
             patch("builtins.print"):
            return _interactive_prompt(
                subject="test_skill",
                detail="val",
                prompt="Allow?",
                options=("allow_once", "allow_always", "deny"),
            )

    def test_keyboard_interrupt_returns_deny(self):
        self.assertEqual(self._prompt(KeyboardInterrupt), ApprovalDecision.DENY)

    def test_eof_error_returns_deny(self):
        self.assertEqual(self._prompt(EOFError), ApprovalDecision.DENY)

    def test_value_error_returns_deny(self):
        # pick_one returns a label not in our list
        self.assertEqual(self._prompt(ValueError), ApprovalDecision.DENY)

    def test_index_error_returns_deny(self):
        # pick_one returns empty string
        self.assertEqual(self._prompt(IndexError), ApprovalDecision.DENY)

    def test_valid_deny_label_returns_deny(self):
        from fcp_base.approval import _interactive_prompt
        with patch("fcp_base.approval.ui.pick_one", return_value="N — deny"), \
             patch("fcp_base.approval.ui.hr"), \
             patch("builtins.print"):
            result = _interactive_prompt(
                subject="test_skill",
                detail="val",
                prompt="Allow?",
                options=("allow_once", "allow_always", "deny"),
            )
        self.assertEqual(result, ApprovalDecision.DENY)

    def test_valid_allow_once_label_returns_allow_once(self):
        from fcp_base.approval import _interactive_prompt
        with patch("fcp_base.approval.ui.pick_one", return_value="y — allow once"), \
             patch("fcp_base.approval.ui.hr"), \
             patch("builtins.print"):
            result = _interactive_prompt(
                subject="test_skill",
                detail="val",
                prompt="Allow?",
                options=("allow_once", "allow_always", "deny"),
            )
        self.assertEqual(result, ApprovalDecision.ALLOW_ONCE)

    def test_valid_allow_always_label_returns_allow_always(self):
        from fcp_base.approval import _interactive_prompt
        with patch("fcp_base.approval.ui.pick_one", return_value="a — allow always"), \
             patch("fcp_base.approval.ui.hr"), \
             patch("builtins.print"):
            result = _interactive_prompt(
                subject="test_skill",
                detail="val",
                prompt="Allow?",
                options=("allow_once", "allow_always", "deny"),
            )
        self.assertEqual(result, ApprovalDecision.ALLOW_ALWAYS)


class TestOptionsValidation(unittest.TestCase):

    def setUp(self):
        self.layout, self.tmp = make_layout()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_missing_deny_raises(self):
        with self.assertRaises(ValueError):
            request_approval(**_base_kwargs(self.layout, options=("allow_once", "allow_always")))


class TestApprovalDecisionValues(unittest.TestCase):

    def test_string_values(self):
        self.assertEqual(ApprovalDecision.ALLOW_ONCE, "allow_once")
        self.assertEqual(ApprovalDecision.ALLOW_ALWAYS, "allow_always")
        self.assertEqual(ApprovalDecision.DENY, "deny")


if __name__ == "__main__":
    unittest.main()
