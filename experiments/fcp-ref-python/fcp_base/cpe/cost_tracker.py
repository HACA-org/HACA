"""CPE Cost Tracking — Persistent cost tracking across sessions.

Tracks token usage and cost per adapter, model, and session.
Enables cost monitoring and optimization.

Date: 2026-03-21
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .benchmark import calculate_cost

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class CostEntry:
    """Single adapter invocation cost record."""
    timestamp: str  # ISO 8601
    adapter: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: float

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CostEntry:
        """Create from dict."""
        return cls(**data)


@dataclass(slots=True)
class SessionCostSummary:
    """Cost summary for a single session."""
    session_id: str
    start_time: str  # ISO 8601
    end_time: str | None
    adapter: str
    model: str
    total_input_tokens: int
    total_output_tokens: int
    total_cost_usd: float
    invocation_count: int
    avg_latency_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict."""
        return asdict(self)


class CostTracker:
    """Persistent cost tracker for CPE adapters.

    Tracks token usage and cost per adapter/model.
    Enables cost monitoring and budgeting.
    """

    def __init__(self, log_file: str | Path | None = None) -> None:
        """Initialize cost tracker.

        Args:
            log_file: Path to cost log (JSON lines format).
                     Defaults to ~/.cache/fcp/cpe_costs.jsonl
        """
        if log_file is None:
            cache_dir = Path.home() / ".cache" / "fcp"
            cache_dir.mkdir(parents=True, exist_ok=True)
            log_file = cache_dir / "cpe_costs.jsonl"

        self.log_file = Path(log_file)
        self.log_file.parent.mkdir(parents=True, exist_ok=True)

        # In-memory cache
        self._entries: list[CostEntry] = []
        self._load_existing()

    def _load_existing(self) -> None:
        """Load existing cost entries from log file."""
        if not self.log_file.exists():
            return

        try:
            with open(self.log_file) as f:
                for line in f:
                    if line.strip():
                        data = json.loads(line)
                        self._entries.append(CostEntry.from_dict(data))
        except FileNotFoundError:
            # Log file doesn't exist yet; will be created on first write
            pass
        except Exception as e:
            logger.warning(f"Cost tracker failed to load from {self.log_file}: {e}")

    def record(
        self,
        adapter: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        latency_ms: float,
    ) -> CostEntry:
        """Record a single invocation.

        Args:
            adapter: Adapter name
            model: Model name
            input_tokens: Input token count
            output_tokens: Output token count
            latency_ms: Latency in milliseconds

        Returns:
            CostEntry that was recorded
        """
        cost = calculate_cost(adapter, model, input_tokens, output_tokens)

        entry = CostEntry(
            timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            adapter=adapter,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            latency_ms=latency_ms,
        )

        self._entries.append(entry)
        self._save_entry(entry)
        return entry

    def _save_entry(self, entry: CostEntry) -> None:
        """Append entry to log file."""
        try:
            # Ensure directory exists
            self.log_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.log_file, "a") as f:
                f.write(json.dumps(entry.to_dict()) + "\n")
        except Exception as e:
            logger.error(f"Cost tracker failed to save to {self.log_file}: {e}")

    def get_summary(self, adapter: str | None = None, model: str | None = None) -> dict[str, Any]:
        """Get cost summary, optionally filtered by adapter/model.

        Args:
            adapter: Filter by adapter (optional)
            model: Filter by model (optional)

        Returns:
            Dict with summary stats
        """
        entries = self._entries
        if adapter:
            entries = [e for e in entries if e.adapter == adapter]
        if model:
            entries = [e for e in entries if e.model == model]

        if not entries:
            return {
                "invocation_count": 0,
                "total_input_tokens": 0,
                "total_output_tokens": 0,
                "total_cost_usd": 0.0,
                "avg_cost_per_call": 0.0,
                "avg_latency_ms": 0.0,
            }

        total_input = sum(e.input_tokens for e in entries)
        total_output = sum(e.output_tokens for e in entries)
        total_cost = sum(e.cost_usd for e in entries)
        latencies = [e.latency_ms for e in entries]

        return {
            "invocation_count": len(entries),
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "total_cost_usd": round(total_cost, 6),
            "avg_cost_per_call": round(total_cost / len(entries), 6),
            "avg_latency_ms": round(sum(latencies) / len(latencies), 2),
            "min_latency_ms": round(min(latencies), 2),
            "max_latency_ms": round(max(latencies), 2),
        }

    def get_adapter_summary(self, adapter: str) -> dict[str, Any]:
        """Get summary for a specific adapter."""
        return self.get_summary(adapter=adapter)

    def get_all_adapters_summary(self) -> dict[str, dict[str, Any]]:
        """Get summary for all adapters."""
        adapters = set(e.adapter for e in self._entries)
        return {adapter: self.get_adapter_summary(adapter) for adapter in sorted(adapters)}

    def print_summary(self) -> None:
        """Print human-readable summary."""
        all_summary = self.get_all_adapters_summary()

        if not all_summary:
            print("No cost tracking data yet.")
            return

        print("\n" + "=" * 100)
        print("CPE Cost Tracking Summary")
        print("=" * 100)

        for adapter, summary in all_summary.items():
            if summary["invocation_count"] == 0:
                continue

            print(
                f"\n{adapter:12} | Calls: {summary['invocation_count']:4} | "
                f"Input: {summary['total_input_tokens']:7} | Output: {summary['total_output_tokens']:7} | "
                f"Cost: ${summary['total_cost_usd']:8.4f} (avg: ${summary['avg_cost_per_call']:.6f}/call) | "
                f"Latency: {summary['avg_latency_ms']:.1f}ms"
            )

        total_cost = sum(s["total_cost_usd"] for s in all_summary.values())
        print(f"\nTotal Cost: ${total_cost:.4f}")
        print("=" * 100)
        print()
