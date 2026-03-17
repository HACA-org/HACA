#!/usr/bin/env python3
"""core/config.py — Structural baseline loader."""

import json
import os
from pathlib import Path


class Config:
    def __init__(self, root: Path):
        self.root = root
        p = root / "state" / "baseline.json"
        with open(p) as f:
            self._data = json.load(f)

        t = self._data.get("thresholds", {})
        hb = self._data.get("heartbeat", {})
        wd = self._data.get("watchdog", {})
        ic = self._data.get("integrity_chain", {})
        psb = self._data.get("pre_session_buffer", {})
        oc = self._data.get("operator_channel", {})

        self.topology = self._data.get("topology", "transparent")
        self.heartbeat_T = hb.get("T", 10)
        self.heartbeat_I = hb.get("I_seconds", 300)
        self.N_boot = t.get("N_boot", 3)
        self.N_channel = t.get("N_channel", 3)
        self.N_retry = t.get("N_retry", 3)
        self.S_bytes = t.get("S_bytes", 10485760)
        self.C_commits = ic.get("checkpoint_interval_C", t.get("C_commits", 10))
        self.context_budget_chars = t.get("context_budget_chars", 600000)
        self.context_window_critical_pct = t.get("context_window_critical_pct", 85)
        self.watchdog_sil_threshold = wd.get("sil_threshold_seconds", 300)
        self.skill_timeout_seconds = wd.get("skill_timeout_seconds", 60)
        self.pre_session_buffer_capacity = psb.get("capacity", 100)
        self.operator_channel_path = oc.get("path", "state/operator_notifications")
        self.integrity_chain_log_path = ic.get("log_path", "state/integrity.log")

    def get(self, key: str):
        """Access a value by dot-path, e.g. 'thresholds.N_boot'."""
        parts = key.split(".")
        val = self._data
        for part in parts:
            if not isinstance(val, dict) or part not in val:
                raise KeyError(f"Key not found in baseline: {key}")
            val = val[part]
        return val
