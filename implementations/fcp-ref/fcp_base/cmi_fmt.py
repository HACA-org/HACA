"""
CMI envelope formatting — FCP §8.

Converts raw CMI envelope dicts into human-readable strings for:
  - CPE stimulus injection  (format_cmi_stimulus, envelope_to_text)
  - Operator-facing indicators  (cmi_indicator, cmi_send_indicator)

All functions are pure text formatters; no I/O, no session state.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from . import ui

logger = logging.getLogger(__name__)

# ACP envelope types that are processed internally and must NOT be injected
# into the CPE chat history as text stimuli.
SYSTEM_TYPES: frozenset[str] = frozenset({
    "SESSION_START", "SESSION_CLOSE", "SLEEP_COMPLETE", "HEARTBEAT",
    "DRIFT_FAULT", "IDENTITY_DRIFT", "SEVERANCE_PENDING", "CRITICAL_CLEARED",
    "PROPOSAL_PENDING", "EVOLUTION_AUTH", "EVOLUTION_REJECTED",
    "ENDURE_COMMIT", "DECOMMISSION",
})


def parse_env_data(env: dict[str, Any]) -> Any:
    """Return the parsed data field of an ACP envelope."""
    raw_data = env.get("data", "")
    if isinstance(raw_data, str):
        try:
            return json.loads(raw_data)
        except json.JSONDecodeError:
            return raw_data
        except Exception as e:
            logger.debug("envelope data parse error in parse_env_data (%s)", e)
            return raw_data
    return raw_data


def format_cmi_stimulus(env: dict[str, Any]) -> str:
    """Format a CMI inbox envelope as a readable stimulus for the CPE."""
    msg_type = env.get("type", "")
    chan_id = env.get("channel_id", "?")
    sender = env.get("from", env.get("host_identity", ""))
    sender_short = sender[:16] + "..." if len(sender) > 16 else sender

    if msg_type == "CMI_CONTROL":
        event = env.get("event", "")
        if event == "channel_closing":
            return (
                f"[CMI] Channel {chan_id} is closing.\n"
                f"The Blackboard is now final. Review it with `/cmi bb {chan_id}` "
                f"and decide what to preserve in memory."
            )
        if event == "enrolled":
            role = env.get("role", "peer")
            task = env.get("task", "")
            bb = env.get("blackboard", [])
            bb_note = f" Blackboard has {len(bb)} existing contribution(s)." if bb else ""
            return (
                f"[CMI] You have been enrolled in channel {chan_id} as {role}.\n"
                f"Task: {task}{bb_note}\n"
                f"Use `cmi_send` to participate."
            )
        if event == "peer_enrolled":
            ni = env.get("node_identity", "?")
            ni_short = ni[:16] + "..." if len(ni) > 16 else ni
            return f"[CMI] Peer enrolled on channel {chan_id}: {ni_short}"
        return f"[CMI] Control event on channel {chan_id}: {event}"

    if msg_type == "CMI_MSG_GENERAL":
        content = env.get("content", "")
        return f"[CMI:{chan_id}] {sender_short}: {content}"

    if msg_type == "CMI_MSG_PEER":
        to = env.get("to", "")
        content = env.get("content", "")
        to_short = to[:16] + "..." if len(to) > 16 else to
        return f"[CMI:{chan_id}] {sender_short} → {to_short}: {content}"

    if msg_type == "CMI_MSG_BB":
        content = env.get("content", "")
        seq = env.get("seq", "?")
        return f"[CMI:{chan_id}] BB[{seq}] {sender_short}: {content}"

    return f"[CMI:{chan_id}] {msg_type}: {json.dumps(env, ensure_ascii=False)}"


def cmi_indicator(env: dict[str, Any]) -> str:
    """Return a short operator-facing indicator if env is a CMI stimulus, else ''."""
    data = parse_env_data(env)
    if not isinstance(data, dict):
        return ""
    data_type = data.get("type", "")
    if not isinstance(data_type, str) or not data_type.startswith("CMI_"):
        return ""
    chan_id = data.get("channel_id", "?")
    event = data.get("event", "")
    if data_type == "CMI_CONTROL":
        return f"  [cmi:{chan_id}] ← control:{event}"
    if data_type == "CMI_MSG_GENERAL":
        sender = data.get("from", "?")
        return f"  [cmi:{chan_id}] ← msg from {sender[:16]}"
    if data_type == "CMI_MSG_PEER":
        sender = data.get("from", "?")
        return f"  [cmi:{chan_id}] ← peer from {sender[:16]}"
    if data_type == "CMI_MSG_BB":
        seq = data.get("seq", "?")
        return f"  [cmi:{chan_id}] ← bb[{seq}]"
    return f"  [cmi:{chan_id}] ← {data_type}"


def cmi_send_indicator(params: dict[str, Any], result: dict[str, Any]) -> None:
    """Print a dim operator-facing line when the CPE sends a CMI message."""
    chan_id = params.get("chan_id", "?")
    msg_type = params.get("type", "?")
    if result.get("status") == "sent":
        print(f"{ui.DIM}  [cmi:{chan_id}] → {msg_type}{ui.RESET}")
    else:
        err = result.get("error", "failed")
        print(f"{ui.DIM}  [cmi:{chan_id}] → {msg_type} (error: {err}){ui.RESET}")


def envelope_to_text(env: dict[str, Any]) -> str:
    """Extract displayable text from an ACP envelope for chat history injection."""
    data = parse_env_data(env)

    if isinstance(data, dict):
        data_type = data.get("type", "")
        if isinstance(data_type, str) and data_type.startswith("CMI_"):
            return format_cmi_stimulus(data)
        if data_type in SYSTEM_TYPES:
            return ""
        return json.dumps(data, ensure_ascii=False)
    if isinstance(data, str):
        return data.strip()
    return json.dumps(data, ensure_ascii=False)
