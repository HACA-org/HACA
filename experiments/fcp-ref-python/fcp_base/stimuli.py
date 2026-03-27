"""
Stimuli — FCP §6.1.

Manages the first-stimulus file (io/first_stimuli.json): written by the
operator before session start to inject an initial user message, consumed
once by the session loop at boot.
"""

from __future__ import annotations
import json
from .store import Layout, atomic_write, read_json

def pop_stimulus(layout: Layout) -> dict | None:
    """Read and delete the pending stimulus if it exists. (Used by session loop)."""
    if not layout.first_stimuli.exists():
        return None
    try:
        data = read_json(layout.first_stimuli)
        layout.first_stimuli.unlink(missing_ok=True)
        return data
    except Exception:
        # If unreadable, clear it to avoid blocking boot cycles
        layout.first_stimuli.unlink(missing_ok=True)
        return None

def inject_onboarding(layout: Layout, profile: str) -> None:
    """First Activation stimuli (FAP onboarding)."""
    message = (
        f"[SYSTEM_DIRECTIVE] Initial activation successful. You are now operational (Profile: {profile}).\n\n"
        "Your Task: Greet the Operator and initiate an onboarding dialogue to personalize this collaboration. "
        "In your first message, proactively ask for:\n"
        "1. Preferred language and communication style (concise vs. detailed).\n"
        "2. Current project context or primary area of work.\n"
        "3. Any specific constraints or operational preferences.\n\n"
        "Goal: Establish an intuitive partnership and store these insights in structured memory "
        "(slugs: operator-profile, session-preferences)."
    )
    _write(layout, "fap", message)

def inject_evolution_result(layout: Layout, description: str, approved: bool) -> None:
    """Post-Evolution stimuli (Operator decision). Only applied to haca-evolve entities."""
    try:
        profile = read_json(layout.baseline).get("profile", "haca-core")
    except Exception:
        profile = "haca-core"

    if profile != "haca-evolve":
        return

    if approved:
        message = (
            f"[EVOLUTION COMPLETE] Your evolution proposal was approved and applied: "
            f"{description}. "
            "Review the changes and confirm they are working as expected."
        )
    else:
        message = (
            f"[EVOLUTION REJECTED] Your evolution proposal was rejected by the Operator: "
            f"{description}."
        )
    _write(layout, "evolution", message)

def inject_wakeup(layout: Layout, cron_id: str, message: str) -> None:
    """Autonomous Task stimuli (Cron wakeup)."""
    _write(layout, "cron", message, extra={"cron_id": cron_id})

def _write(layout: Layout, source: str, message: str, extra: dict | None = None) -> None:
    """Internal helper for atomic writing."""
    payload = {"source": source, "message": message}
    if extra:
        payload.update(extra)
    atomic_write(layout.first_stimuli, payload)
