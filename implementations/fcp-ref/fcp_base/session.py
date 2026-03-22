"""
Session loop — FCP §6.

Drives the cognitive cycle:
  drain io/inbox/ → consolidate → invoke CPE with growing chat_history
  → process tool_use → return tool_results → repeat

Context is assembled once at session start (system prompt + initial history from
session tail). Each cycle appends only the new stimulus to the in-memory
chat_history — the CPE never re-receives the boot manifest.

Session ends on session_close signal (CPE, SIL, or Operator).
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from .acp import drain_inbox, make as acp_encode
from .cpe.base import AdapterRef, CPEAdapter, CPEResponse, CPEError, CPEAuthError, CPERateLimitError
from .mil import memory_recall, process_closure, result_recall, summarize_session, write_episodic, SESSION_CACHE_FILE
from .operator import is_verbose as _is_verbose, get_debugger as _get_debugger, is_compact_pending as _is_compact_pending, set_compact_pending as _set_compact_pending, is_endure_approved as _is_endure_approved, set_endure_approved as _set_endure_approved
from .session_mode import SessionMode, set_session_mode, get_session_mode, is_auto_session, is_main_session
from .tools import build_tools_index as _build_tools_index, build_tool_declarations as _tool_declarations
from .sil import sha256_str as _sha256_str, stage_evolution_proposal as _stage_evolution_proposal, write_evolution_auth as _write_evolution_auth, write_notification as _write_notification
from .stimuli import inject_evolution_result as _write_evolution_stimuli
from .store import Layout, append_jsonl, atomic_write, load_baseline, read_json, read_jsonl
from . import cmi_fmt as _cmi_fmt
from . import ui
from . import vital as _vital


# ---------------------------------------------------------------------------
# Chat History Management — Bounded Growth
# ---------------------------------------------------------------------------

def _estimate_message_tokens(msg: dict[str, Any]) -> int:
    """Estimate token count for a single message.

    Uses character-based heuristic: ~4 chars per token (rough average).
    """
    content = msg.get("content", "")
    return max(1, len(content) // 4)


def _trim_chat_history(
    chat_history: list[dict[str, Any]],
    max_messages: int | None = None,
    target_tokens: int | None = None,
) -> None:
    """Trim chat history by removing oldest non-critical messages.

    Keeps initial boot context (first message) and recent messages.
    Removes from oldest to newest until constraints are met.

    Args:
        chat_history: In-place list to trim
        max_messages: Max number of messages to keep (None = no limit)
        target_tokens: Target token count (drop oldest until under this)
    """
    if not chat_history:
        return

    # Keep first message (boot context)
    if len(chat_history) <= 1:
        return

    if max_messages and len(chat_history) > max_messages:
        # Drop oldest non-first messages
        excess = len(chat_history) - max_messages
        for _ in range(excess):
            if len(chat_history) > 1:
                chat_history.pop(1)  # Remove 2nd message (first is boot context)

    if target_tokens:
        # Calculate current token count
        current_tokens = sum(_estimate_message_tokens(msg) for msg in chat_history)

        # Drop oldest messages until under target
        while current_tokens > target_tokens and len(chat_history) > 1:
            removed = chat_history.pop(1)  # Remove 2nd message (first is boot context)
            current_tokens -= _estimate_message_tokens(removed)


# ---------------------------------------------------------------------------
# Stimulus Collection and Input Handling
# ---------------------------------------------------------------------------

def _process_stimulus_and_input(
    layout: Layout,
    chat_history: list[dict[str, Any]],
    adapter_ref: AdapterRef,
) -> tuple[bool, bool, str]:
    """Collect stimuli from inbox and user input, return (stimulus_ready, session_closed, close_reason).

    Processes:
    1. Inbox drainage and consolidation
    2. User input handling (operator commands, text input)
    3. Command dispatch (/verbose, /exit, /new, /compact)

    Returns:
    - stimulus_ready: True if chat_history was updated with new content
    - session_closed: True if /exit or error occurred
    - close_reason: Reason for session close (if session_closed)
    """
    close_reason = ""
    stimulus_ready = False

    # Drain io/inbox/ → consolidate to session.jsonl
    inbox_envs = _drain_and_consolidate(layout)
    for env in inbox_envs:
        indicator = _cmi_indicator(env)
        if indicator:
            print(f"{_DIM}{indicator}{_RESET}")
        text = _envelope_to_text(env)
        if text:
            chat_history.append({"role": "user", "content": text})
            stimulus_ready = True

    # If no stimulus from inbox, wait for operator input before invoking CPE
    if not stimulus_ready:
        try:
            user_input = _readline_with_history("> ")
        except KeyboardInterrupt:
            print()
            return True, True, "operator_interrupt"
        except EOFError:
            return True, True, "operator_eof"

        stripped = user_input.strip()
        if not stripped:
            return False, False, ""

        # Platform commands — handle without invoking CPE
        if stripped.startswith("/"):
            from .operator import handle_platform_command
            handled = handle_platform_command(layout, stripped, adapter_ref=adapter_ref)
            if handled:
                cmd, _args = _parse_command(stripped)
                if cmd in ("/verbose", "/debugger"):
                    pass  # debug output appears on next CPE cycle
                if _is_endure_approved():
                    _set_endure_approved(False)
                    return True, True, "endure_approved"
                if cmd in ("/exit", "/bye", "/close"):
                    return True, True, "operator_exit"
                if cmd in ("/new", "/clear", "/reset"):
                    return True, True, "operator_reset"
                # Check if /compact was requested
                if _is_compact_pending():
                    _set_compact_pending(False)
                    compact_msg = (
                        "[COMPACT_REQUEST] The operator has requested session compaction. "
                        "Generate a closure_payload now via fcp_mil to preserve your working context. "
                        "The session will continue after compaction — use session_handoff.next_steps "
                        "to describe where to resume."
                    )
                    _append_msg(layout, "fcp", compact_msg)
                    chat_history.append({"role": "user", "content": compact_msg})
                    return True, False, "compact_requested"
                return False, False, ""
            if not handled:
                from .operator import _cmd_output
                cmd, _args = _parse_command(stripped)
                with _cmd_output():
                    if cmd:
                        print(f"unknown command: {cmd}")
                    else:
                        print("invalid command (must start with /)")
                return False, False, ""

        _append_msg(layout, "operator", user_input)
        chat_history.append({"role": "user", "content": stripped})
        stimulus_ready = True

    return stimulus_ready, False, ""


# ---------------------------------------------------------------------------
# Command Parsing Helper
# ---------------------------------------------------------------------------

def _parse_command(line: str) -> tuple[str, list[str]]:
    """Parse a command line into command name and arguments.

    Returns (command, args) tuple. Command is lowercased.
    Returns ('', []) if line is empty or doesn't start with '/'.

    Example:
    >>> _parse_command('/verbose --debug')
    ('/verbose', ['--debug'])
    >>> _parse_command('/')
    ('', [])
    >>> _parse_command('hello')
    ('', [])
    """
    stripped = line.strip()
    if not stripped.startswith('/'):
        return ('', [])

    parts = stripped.split()
    if not parts:
        return ('', [])

    command = parts[0].lower()
    args = parts[1:] if len(parts) > 1 else []
    return (command, args)


# ---------------------------------------------------------------------------
# Loop Detection — Deterministic Fingerprinting
# ---------------------------------------------------------------------------

def _make_cycle_fingerprint(
    tool_calls: list[Any],
    tool_results: list[str],
) -> frozenset[tuple[str, str, str]]:
    """Create deterministic fingerprint of cycle (tool calls + results).

    Returns frozenset of (tool_name, input_hash, result_hash) tuples.
    Frozenset ensures order-independence and proper set comparison.

    Raises ValueError if tool_calls and tool_results counts don't match.
    """
    import hashlib

    if len(tool_calls) != len(tool_results):
        raise ValueError(
            f"Tool call/result count mismatch: {len(tool_calls)} calls, "
            f"{len(tool_results)} results"
        )

    fingerprints = []
    for call, result in zip(tool_calls, tool_results):
        # Hash input to avoid JSON stringification issues
        input_str = json.dumps(call.input, sort_keys=True, ensure_ascii=False)
        input_hash = hashlib.sha256(input_str.encode()).hexdigest()[:8]

        # Hash result similarly
        result_hash = hashlib.sha256(result.encode()).hexdigest()[:8]

        fingerprints.append((call.tool, input_hash, result_hash))

    return frozenset(fingerprints)


# ---------------------------------------------------------------------------
# Main session loop
# ---------------------------------------------------------------------------

def run_session(
    layout: Layout,
    adapter: CPEAdapter | AdapterRef,
    index: dict[str, Any],
    *,
    inject: list[dict[str, Any]] | None = None,
    greeting: bool = False,
    tools: list[dict[str, Any]] | None = None,
) -> str:
    """Run the cognitive session loop until session close (FCP §6).

    Executes the main session cycle:
    1. Build boot context (system prompt + history)
    2. Consume and inject first stimulus (FAP onboarding, post-evolution notices)
    3. Optionally inject additional stimuli
    4. Enter agentic loop: invoke CPE → dispatch tool calls → append results
    5. Continue until CPE requests close or operator exits
    6. Persist session store and compact if needed

    Args:
        layout: Entity store layout for session persistence.
        adapter: CPE adapter (Ollama, Claude, etc.) or reference for lazy initialization.
        index: Skill index for tool discovery and execution.
        inject: Optional list of ACP envelopes to prepend as initial stimuli (after first_stimuli).
        greeting: If True, inject SESSION_START stimulus to wake CPE for greeting.
        tools: Optional pre-built tool declarations. If None, auto-discovered from index.

    Returns:
        str: Close reason code (e.g., "session_close", "operator_exit", "max_turns").

    Raises:
        CPEError: If CPE invocation fails (model unavailable, API error).
        ExecError: If tool execution fails or security check blocks an operation.
        BootError: If critical conditions (session token, session store) are unmet.
    """
    if tools is None:
        tools = _tool_declarations(layout, index)
    adapter_ref = adapter if isinstance(adapter, AdapterRef) else AdapterRef(adapter)
    _set_endure_approved(False)


    # --- Build system prompt and initial chat history once at session start ---
    system, chat_history = build_boot_context(layout, index)
    _vlog("fcp", f"boot context: system={len(system)} chars, history={len(chat_history)} msgs")

    from .stimuli import pop_stimulus
    first_stimuli_injected = False
    # Consume first_stimuli if present (e.g. FAP onboarding, post-evolution notice)
    fs = pop_stimulus(layout)
    if fs:
        msg = str(fs.get("message", ""))
        if msg:
            env = acp_encode(env_type="MSG", source="fcp",
                             data={"type": "FIRST_STIMULI", "source": fs.get("source", "fcp"), "msg": msg})
            append_jsonl(layout.session_store, env)
            chat_history.append({"role": "user", "content": msg})
            first_stimuli_injected = True
            _vlog("fcp", f"first_stimuli injected (source={fs.get('source')})")

    if inject:
        for env in inject:
            append_jsonl(layout.session_store, env)
            text = _envelope_to_text(env)
            if text:
                chat_history.append({"role": "user", "content": text})

    close_reason = "session_close"
    cycle = 0
    compact_in_progress = False
    stimulus_ready = bool(greeting or inject or first_stimuli_injected)
    tokens_used = 0

    # loop detection: track last N cycle fingerprints (each a frozenset of (tool, input_json, result) tuples)
    _loop_window: list[Any] = []
    _LOOP_THRESHOLD = 3

    # CPE error handling — exponential backoff for transient failures
    _cpe_consecutive_errors = 0
    _cpe_last_error_time = 0.0
    _CPE_MAX_CONSECUTIVE_ERRORS = 5
    _CPE_INITIAL_BACKOFF_SECS = 1.0

    # Vital Check state — triggers on cycle_threshold or interval_seconds
    _baseline = None
    _vital_state = None
    _ctx_window = 0
    try:
        from .formats import StructuralBaseline
        _baseline = StructuralBaseline.from_dict(read_json(layout.baseline))
        _ctx_window = _baseline.context_window_budget_tokens
        _session_id = ""
        if layout.session_token.exists():
            _session_id = str(read_json(layout.session_token).get("session_id", ""))
        _vital_state = _vital.VitalCheckState(session_id=_session_id)
    except FileNotFoundError:
        _vlog("fcp", "baseline file not found — vital check disabled")
    except json.JSONDecodeError as e:
        _vlog("fcp", f"baseline file corrupted ({e}) — vital check disabled")
    except Exception as e:
        _vlog("fcp", f"baseline load error ({e}) — vital check disabled")

    while True:
        # If pre-loaded stimulus (first_stimuli, greeting, inject), skip input collection
        if not stimulus_ready:
            stimulus_ready, should_close, close_reason = _process_stimulus_and_input(
                layout, chat_history, adapter_ref
            )
            if should_close:
                if close_reason == "compact_requested":
                    # Compact was requested; set flag and inject message
                    compact_in_progress = True
                    stimulus_ready = True
                else:
                    # Session should close
                    break

        if not stimulus_ready:
            continue

        stimulus_ready = False
        cycle += 1
        cycle_start_time = time.time()
        _vlog_request(system, chat_history, tools, cycle)

        # invoke CPE (adapter_ref.current may be swapped mid-session via /model)
        try:
            response = adapter_ref.current.invoke(system, chat_history, tools)
            # Reset consecutive error counter on success
            _cpe_consecutive_errors = 0
            _cpe_last_error_time = 0.0
        except CPEAuthError as exc:
            # Authentication errors are not retryable — exit immediately
            err_msg = f"CPE authentication failed: {str(exc)}"
            print(f"\n{_DIM}  [fcp] {err_msg}{_RESET}")
            _append_msg(layout, "fcp", err_msg)
            _vlog("fcp", f"auth error: {err_msg}")
            close_reason = "cpe_auth_error"
            break
        except CPERateLimitError as exc:
            # Rate limit is transient — apply exponential backoff
            _cpe_consecutive_errors = _cpe_consecutive_errors + 1
            backoff_secs = _CPE_INITIAL_BACKOFF_SECS * (2 ** (_cpe_consecutive_errors - 1))
            err_msg = f"CPE rate limited (attempt {_cpe_consecutive_errors}): {str(exc)}"
            print(f"\n{_DIM}  [fcp] {err_msg} (backoff {backoff_secs:.1f}s){_RESET}")
            _append_msg(layout, "fcp", f"{err_msg} — retrying in {backoff_secs:.0f}s")
            _vlog("fcp", f"rate limit backoff: {backoff_secs}s")
            if _cpe_consecutive_errors >= _CPE_MAX_CONSECUTIVE_ERRORS:
                close_reason = "cpe_rate_limit_exceeded"
                break
            time.sleep(backoff_secs)
            stimulus_ready = False
            continue
        except CPEError as exc:
            # Other CPE errors (network, model errors) are retryable
            _cpe_consecutive_errors = _cpe_consecutive_errors + 1
            backoff_secs = _CPE_INITIAL_BACKOFF_SECS * (2 ** (_cpe_consecutive_errors - 1))
            err_msg = f"CPE error (attempt {_cpe_consecutive_errors}): {str(exc)}"
            print(f"\n{_DIM}  [fcp] {err_msg} (backoff {backoff_secs:.1f}s){_RESET}")
            _append_msg(layout, "fcp", f"{err_msg} — retrying in {backoff_secs:.0f}s")
            _vlog("fcp", f"cpe error backoff: {backoff_secs}s")
            if _cpe_consecutive_errors >= _CPE_MAX_CONSECUTIVE_ERRORS:
                close_reason = "cpe_error_max_retries"
                break
            time.sleep(backoff_secs)
            stimulus_ready = False
            continue
        except Exception as exc:
            # Unexpected error (shouldn't happen with proper exception hierarchy)
            _cpe_consecutive_errors = _cpe_consecutive_errors + 1
            err_msg = f"CPE unexpected error (attempt {_cpe_consecutive_errors}): {str(exc)}"
            print(f"\n{_DIM}  [fcp] {err_msg}{_RESET}")
            _append_msg(layout, "fcp", err_msg)
            _vlog("fcp", f"unexpected error: {err_msg}")
            if _cpe_consecutive_errors >= _CPE_MAX_CONSECUTIVE_ERRORS:
                close_reason = "cpe_error_max_retries"
                break
            stimulus_ready = False
            continue
        cycle_elapsed = time.time() - cycle_start_time
        tokens_used = tokens_used + response.input_tokens + response.output_tokens

        # add CPE response to chat history and display status
        if response.tool_use_calls and not _is_verbose():
            tools_repr = ", ".join(c.tool for c in response.tool_use_calls)
            print(f"\n{_DIM}  [fcp] working... cycle {cycle} — {tools_repr}{_RESET}")
        if response.text:
            _append_msg(layout, "cpe", response.text)
            _model_label = getattr(adapter_ref.current, "_model", "")
            _print_cpe_block(response.text, _model_label, response.input_tokens, response.output_tokens, _ctx_window)
            chat_history.append({"role": "assistant", "content": response.text})
        if response.tool_use_calls:
            # Always append an empty assistant sentinel when there are tool calls.
            # Adapters detect tool-result turns by checking that the preceding assistant
            # turn has empty content. Without this sentinel, text+tool_calls responses
            # leave a non-empty assistant turn, causing tool results to be treated as
            # plain text in subsequent cycles ("soluço" / hiccup bug).
            chat_history.append({"role": "assistant", "content": ""})

        # process tool_use calls — fcp_mil before fcp_exec before fcp_sil (per spec)
        tool_calls = sorted(
            response.tool_use_calls,
            key=lambda c: 0 if c.tool == "fcp_mil" else (1 if c.tool == "fcp_exec" else 2),
        )

        session_closed = False
        tool_results: list[str] = []
        tool_log_lines: list[dict[str, Any]] = []

        for i, call in enumerate(tool_calls):
            tool_start = time.time()
            result, closed = dispatch_tool_use(layout, call, index)
            tool_elapsed = time.time() - tool_start

            # Accumulate tool execution info (printed later in cycle summary)
            is_last = i == len(tool_calls) - 1
            input_size = _format_bytes(len(json.dumps(call.input, ensure_ascii=False)))
            result_size = _format_bytes(len(json.dumps(result, ensure_ascii=False)))
            status = "OK" if isinstance(result, dict) and result.get("error") is None else "FAIL"
            timing_ms = tool_elapsed * 1000

            tool_log_lines.append({
                "tool": call.tool,
                "is_last": is_last,
                "input": call.input,
                "output": result,
                "input_size": input_size,
                "result_size": result_size,
                "status": status,
                "timing_ms": timing_ms,
            })

            _return_tool_result(layout, call.id, call.tool, result)
            # Serialize result once and reuse for chat history
            # This avoids triple JSON serialization (verbose logging, chat history, loop detection)
            result_str = json.dumps(result, ensure_ascii=False)
            tool_results.append(f"[{call.tool}] {result_str}")
            if call.tool == "cmi_send":
                _cmi_send_indicator(call.input, result)
            if closed:
                close_reason = "session_close"
                session_closed = True
            if _is_endure_approved():
                close_reason = "endure_approved"
                session_closed = True

        # Print cycle summary: [DISPATCH] + [← CPE] in correct order
        _vlog_cycle_summary(response, cycle_elapsed, tool_log_lines)

        if session_closed:
            break

        # tool results go into chat history as full payloads.
        # result_recall remains available as fallback for results from previous sessions.
        if tool_results:
            chat_history.append({"role": "user", "content": "\n".join(tool_results)})
            stimulus_ready = True  # tool results need a follow-up CPE cycle

        # --- loop detection: same set of (tool, input, result) tuples repeated >= threshold ---
        if tool_calls:
            try:
                # Create deterministic fingerprint (handles JSON stringification issues)
                cycle_fingerprint = _make_cycle_fingerprint(tool_calls, tool_results)
                _loop_window.append(cycle_fingerprint)
                if len(_loop_window) > _LOOP_THRESHOLD:
                    _loop_window.pop(0)

                # Detect loop: same fingerprint repeated THRESHOLD times
                if len(_loop_window) == _LOOP_THRESHOLD and len(set(_loop_window)) == 1:
                    _loop_window.clear()
                    tools_repr = ", ".join(c.tool for c in tool_calls)
                    intervention = (
                        f"[FCP] Loop detected: the same tool call(s) ({tools_repr}) returned "
                        f"identical results {_LOOP_THRESHOLD} times in a row. "
                        "Stop and report the situation to the Operator. Do not retry."
                    )
                    _vlog("fcp", f"loop detected: {tools_repr}")
                    _append_msg(layout, "fcp", intervention)
                    chat_history.append({"role": "user", "content": intervention})
                    stimulus_ready = True
            except ValueError as e:
                # Tool call/result count mismatch (shouldn't happen, but log if it does)
                _vlog("fcp", f"loop detection skipped: {e}")
                _loop_window.clear()
        else:
            _loop_window.clear()

        # Vital Check — tick counter; run if either trigger threshold is reached
        if _vital_state is not None and _baseline is not None:
            _vital.tick(_vital_state)
            if _vital.should_run(_vital_state, _baseline):
                _vital.run(layout, _baseline, _vital_state, tokens_used)

        # compact: if closure_payload was written during this cycle, execute Stage 1
        # and rebuild chat_history with the condensed context
        if compact_in_progress and layout.pending_closure.exists():
            compact_in_progress = False
            _vlog("fcp", "compact: processing closure payload")
            process_closure(layout)
            chat_history[:] = _rebuild_compact_history(layout, index, system)
            summarize_session(layout)
            _vlog("fcp", f"compact: done — history={len(chat_history)} msgs")
            print(f"\n{_DIM}  [fcp] session compacted{_RESET}")

    _vlog("fcp", f"session closed — reason: {close_reason}")
    return close_reason


# ---------------------------------------------------------------------------
# Boot context assembly  §5.1
# ---------------------------------------------------------------------------

_SYSTEM_TYPES = _cmi_fmt.SYSTEM_TYPES


def build_boot_context(
    layout: Layout,
    index: dict[str, Any],
) -> tuple[str, list[dict[str, Any]]]:
    """Build the fixed system prompt and initial chat history (session tail).

    Called once at session start.  Returns:
      system       — persona + boot protocol + skills + memory (never changes)
      chat_history — tail of session.jsonl reconstructed as message dicts

    Each cognitive cycle appends only the new stimulus to chat_history.
    """
    # --- system prompt: [IDENTITY] = persona + imprint line ---
    persona_parts: list[str] = []
    if layout.persona_dir.exists():
        for p in sorted(layout.persona_dir.iterdir()):
            if p.is_file():
                persona_parts.append(p.read_text(encoding="utf-8").strip())
    persona_text = "\n\n".join(persona_parts) if persona_parts else "You are a helpful assistant."

    imprint_line = ""
    imprint_path = layout.root / "memory" / "imprint.json"
    if imprint_path.exists():
        try:
            imp = json.loads(imprint_path.read_text(encoding="utf-8"))
            ob = imp.get("operator_bound", {})
            activated = imp.get("activated_at", "")
            profile = imp.get("haca_profile", "")
            op_name = ob.get("operator_name", "")
            op_email = ob.get("operator_email", "")
            op_str = f"{op_name} <{op_email}>" if op_email else op_name
            imprint_line = f"Activated: {activated} | Profile: {profile} | Operator: {op_str}"
        except Exception:
            pass

    identity_parts = ["[IDENTITY]", persona_text]
    if imprint_line:
        identity_parts.append(imprint_line)
    system_persona = "\n\n".join(identity_parts)

    # --- instruction block: boot protocol + memory + skills ---
    boot_protocol = ""
    if layout.boot_md.exists():
        boot_protocol = layout.boot_md.read_text(encoding="utf-8").strip()

    memory_parts: list[str] = []
    if layout.working_memory.exists():
        wm = read_json(layout.working_memory)
        for entry in sorted(wm.get("entries", []), key=lambda e: int(e.get("priority", 99))):
            rel = entry.get("path", "")
            if not rel:
                continue
            p = layout.root / rel
            if p.is_file():
                memory_parts.append(p.read_text(encoding="utf-8").strip())

    tools_index = _build_tools_index(layout, index)

    instruction_parts: list[str] = [boot_protocol, tools_index]
    if memory_parts:
        instruction_parts.append("## Active Memory\n\n" + "\n\n---\n\n".join(memory_parts))

    instruction_block = "\n\n".join(instruction_parts)

    # system = persona; instruction block is the first user/assistant exchange
    system = system_persona

    # --- presession ---
    presession_lines: list[str] = []
    if layout.presession_dir.exists():
        for f in sorted(layout.presession_dir.iterdir()):
            if f.suffix == ".json":
                try:
                    presession_lines.append(f.read_text(encoding="utf-8").strip())
                except UnicodeDecodeError as e:
                    _vlog("fcp", f"presession file {f.name} has encoding error: {e}")
                except OSError as e:
                    _vlog("fcp", f"presession file {f.name} cannot be read: {e}")
                except Exception as e:
                    _vlog("fcp", f"presession file {f.name} error: {e}")

    # --- initial chat history: instruction block + session tail ---
    chat_history: list[dict[str, Any]] = [
        {"role": "user", "content": instruction_block},
        {"role": "assistant", "content": "Understood. I am ready."},
    ]

    if presession_lines:
        pre_text = "[Pre-session context]\n" + "\n".join(presession_lines)
        chat_history.append({"role": "user", "content": pre_text})
        chat_history.append({"role": "assistant", "content": "Noted."})

    # Reconstruct session tail as conversation turns
    for role, text in _session_to_turns(layout):
        chat_history.append({"role": role, "content": text})

    return system, chat_history


def _session_to_turns(layout: Layout) -> list[tuple[str, str]]:
    """Convert session.jsonl into (role, text) pairs for chat history.

    Uses cached session tail from .session-cache.json (after sleep) for
    faster boots. Cache is refreshed on every sleep cycle.
    """
    # Try to load cached session tail (populated after each sleep)
    cache_file = layout.root / "memory" / SESSION_CACHE_FILE
    if cache_file.exists():
        try:
            cache = read_json(cache_file)
            cached_turns = cache.get("turns", [])
            # Convert back to list of tuples
            pairs = [(turn["role"], turn["content"]) for turn in cached_turns]
            return pairs
        except json.JSONDecodeError as e:
            _vlog("fcp", f"session cache corrupted ({e}) — performing full scan")
        except (KeyError, TypeError) as e:
            _vlog("fcp", f"session cache schema error ({e}) — performing full scan")
        except Exception as e:
            _vlog("fcp", f"session cache error ({e}) — performing full scan")

    # Full scan if no cache (cold boot)
    pairs: list[tuple[str, str]] = []

    for env in read_jsonl(layout.session_store):
        actor = str(env.get("actor", env.get("source", "")))
        raw_data = env.get("data", "")

        if isinstance(raw_data, str):
            try:
                data = json.loads(raw_data)
            except json.JSONDecodeError:
                # Not JSON — treat as raw string data
                data = raw_data
            except Exception as e:
                _vlog("fcp", f"envelope data parse error ({e}) — using raw data")
                data = raw_data
        else:
            data = raw_data

        # filter system envelopes
        if isinstance(data, dict) and data.get("type") in _SYSTEM_TYPES:
            continue

        if actor in ("operator", "user"):
            role = "user"
        elif actor in ("cpe", "assistant"):
            role = "assistant"
        else:
            role = "user"

        if isinstance(data, str):
            text = data.strip()
        elif isinstance(data, dict):
            if "tool_result" in data:
                tr = data["tool_result"]
                text = f"[tool result: {tr.get('tool', '?')}]\n{json.dumps(tr.get('content', ''), ensure_ascii=False)}"
            else:
                text = json.dumps(data, ensure_ascii=False)
        else:
            text = json.dumps(data, ensure_ascii=False)

        if not text:
            continue

        # merge consecutive same-role entries
        if pairs and pairs[-1][0] == role:
            prev_role, prev_text = pairs[-1]
            pairs[-1] = (prev_role, prev_text + "\n\n" + text)
        else:
            pairs.append((role, text))

    return pairs


_format_cmi_stimulus = _cmi_fmt.format_cmi_stimulus
_parse_env_data      = _cmi_fmt.parse_env_data
_cmi_indicator       = _cmi_fmt.cmi_indicator
_cmi_send_indicator  = _cmi_fmt.cmi_send_indicator
_envelope_to_text    = _cmi_fmt.envelope_to_text


# ---------------------------------------------------------------------------
# Tool dispatch  §6.2
# ---------------------------------------------------------------------------

def dispatch_tool_use(
    layout: Layout,
    call: Any,
    index: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    """Dispatch a single tool_use call. Returns (result_dict, session_closed)."""
    tool = call.tool
    inp = call.input if isinstance(call.input, dict) else {}

    # Some models (e.g. Ollama/llama) wrap the action as a JSON string under "action".
    if "action" in inp and isinstance(inp["action"], str) and len(inp) == 1:
        try:
            inp = json.loads(inp["action"])
        except json.JSONDecodeError:
            # Not JSON — use raw action string as-is
            pass
        except Exception as e:
            _vlog("fcp", f"tool input action parse error ({e}) — using raw action")

    # --- MIL tools ---
    if tool in ("memory_recall", "memory_write", "result_recall", "closure_payload"):
        action = dict(inp)
        action["type"] = tool
        return _dispatch_mil(layout, action)

    # --- CMI tools ---
    if tool in ("cmi_send", "cmi_req"):
        return _dispatch_cmi(layout, tool, inp)

    # --- SIL tools ---
    if tool in ("session_close", "evolution_proposal"):
        action = dict(inp)
        action["type"] = tool
        return _dispatch_sil(layout, action)

    # --- skill_info ---
    if tool == "skill_info":
        skill_name = str(inp.get("skill", ""))
        return _skill_info(layout, skill_name, index), False

    # --- skills by name ---
    skill_names = {s.get("name") for s in index.get("skills", [])}
    if tool in skill_names:
        exec_inp = {"type": "skill_request", "skill": tool, "params": inp}
        return _dispatch_exec(layout, exec_inp, index)

    # --- legacy fcp_* names (backwards compat during transition) ---
    if tool == "fcp_mil":
        return _dispatch_mil(layout, inp)
    if tool == "fcp_exec":
        return _dispatch_exec(layout, inp, index)
    if tool == "fcp_sil":
        return _dispatch_sil(layout, inp)

    return {"error": f"unknown tool: {tool}"}, False


def _dispatch_cmi(
    layout: Layout, tool: str, params: dict[str, Any]
) -> tuple[dict[str, Any], bool]:
    """Dispatch CMI tools (cmi_send, cmi_req) to the CMI component."""
    from .cmi.dispatch import dispatch_send, dispatch_req
    if tool == "cmi_send":
        result = dispatch_send(layout, params)
    else:
        result = dispatch_req(layout, params)
    return result, False


def _dispatch_mil(
    layout: Layout, inp: dict[str, Any]
) -> tuple[dict[str, Any], bool]:
    """Dispatch Memory Interface Layer (MIL) actions.

    Handles memory operations: recall (episodic/semantic), write, and closure.

    Args:
        layout: Entity store layout for memory access.
        inp: Single action dict or list of actions with type field.

    Returns:
        Tuple of (results_dict, session_closed) where results_dict contains
        outcome of each action (ok, conflict, error).
    """
    actions: list[Any] = inp if isinstance(inp, list) else [inp]
    results: list[dict[str, Any]] = []
    for action in actions:
        atype = action.get("type", "")
        if atype == "memory_recall":
            raw_path = action.get("path") or ""
            result = memory_recall(layout, str(action.get("query", "")),
                                   str(raw_path) if raw_path else "")
            results.append({"type": "memory_recall", "result": result})
        elif atype == "result_recall":
            ts = int(action.get("ts", 0))
            result = result_recall(layout, ts)
            results.append({"type": "result_recall", "result": result})
        elif atype == "memory_write":
            slug = str(action.get("slug", "")).strip()
            content = str(action.get("content", ""))
            overwrite = bool(action.get("overwrite", False))
            if not slug:
                results.append({"type": "memory_write", "status": "error", "message": "slug is required and must not be empty."})
            else:
                outcome = write_episodic(layout, slug, content, overwrite=overwrite)
                if isinstance(outcome, dict):
                    results.append({
                        "type": "memory_write",
                        "status": "conflict",
                        "slug": slug,
                        "existing_content": outcome["existing_content"],
                        "message": "A memory with this slug already exists. Call memory_write again with overwrite=true to replace it, or use a different slug.",
                    })
                else:
                    results.append({"type": "memory_write", "status": "ok"})
        elif atype == "closure_payload":
            payload = {k: v for k, v in action.items() if k != "type"}
            atomic_write(layout.pending_closure, payload)
            results.append({"type": "closure_payload", "status": "acknowledged"})
        else:
            results.append({"type": atype, "error": "unknown mil action"})
    return {"results": results}, False


def _dispatch_exec(
    layout: Layout,
    inp: dict[str, Any],
    index: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    """Dispatch Execution Interface (skill requests).

    Handles skill execution via exec_ module with error recovery.

    Args:
        layout: Entity store layout for skill execution context.
        inp: Single action dict or list of actions with type="skill_request".
        index: Skill index for skill discovery and invocation.

    Returns:
        Tuple of (results_dict, session_closed) where results_dict contains
        skill output or error details.
    """
    from .exec_ import dispatch, ExecError, SkillRejected
    actions: list[Any] = inp if isinstance(inp, list) else [inp]
    results: list[dict[str, Any]] = []
    for action in actions:
        atype = action.get("type", "")
        if atype == "skill_request":
            skill_name = str(action.get("skill", ""))
            params = action.get("params", {})
            # Some models serialize params as a JSON string instead of an object.
            if isinstance(params, str):
                try:
                    params = json.loads(params)
                except json.JSONDecodeError:
                    _vlog("fcp", f"skill params not valid JSON, using empty dict")
                    params = {}
                except Exception as e:
                    _vlog("fcp", f"skill params parse error ({e}), using empty dict")
                    params = {}
            if not isinstance(params, dict):
                params = {}
            try:
                output = dispatch(layout, skill_name, params, index)
                results.append({"type": "skill_request", "skill": skill_name,
                                 "status": "dispatched", "output": output})
            except (SkillRejected, ExecError) as exc:
                results.append({"type": "skill_request", "skill": skill_name,
                                 "error": str(exc)})
        elif atype == "skill_info":
            skill_name = str(action.get("skill", ""))
            results.append(_skill_info(layout, skill_name, index))
        else:
            results.append({"type": atype, "error": "unknown exec action"})
    return {"results": results}, False


def _dispatch_sil(
    layout: Layout, inp: dict[str, Any]
) -> tuple[dict[str, Any], bool]:
    """Dispatch System Interface Layer (SIL) actions.

    Handles system-level operations: evolution proposals, runtime directives.

    Args:
        layout: Entity store layout for system state access.
        inp: Single action dict or list of actions with type="evolution_proposal".

    Returns:
        Tuple of (results_dict, session_closed) where session_closed indicates
        if CPE triggered session close via evolution.
    """
    actions: list[Any] = inp if isinstance(inp, list) else [inp]
    results: list[dict[str, Any]] = []
    session_closed = False
    for action in actions:
        atype = action.get("type", "")
        if atype == "evolution_proposal":
            payload = {k: v for k, v in action.items() if k != "type"}
            content = json.dumps(payload)
            proposal_file = _stage_evolution_proposal(layout, content)
            # Auto-approve for Evolve with autonomous_evolution=True
            try:
                baseline = load_baseline(layout)
                profile = baseline.get("profile", "haca-core")
                autonomous = (
                    profile == "haca-evolve"
                    and baseline.get("evolve", {}).get("scope", {}).get("autonomous_evolution", False)
                )
            except FileNotFoundError:
                _vlog("fcp", "baseline not found — autonomous evolution disabled")
                autonomous = False
            except Exception as e:
                _vlog("fcp", f"baseline load error ({e}) — autonomous evolution disabled")
                autonomous = False
            if autonomous:
                auth_digest = _sha256_str(content)
                _write_evolution_auth(layout, content, auth_digest)
                _write_evolution_stimuli(layout, payload.get("description", content), approved=True)
                proposal_file.unlink(missing_ok=True)
                _set_endure_approved(True)
                results.append({"type": "evolution_proposal", "status": "auto_approved"})
                session_closed = True
            else:
                results.append({"type": "evolution_proposal", "status": "queued"})
        elif atype == "session_close":
            session_closed = True
            results.append({"type": "session_close", "status": "acknowledged"})
        else:
            results.append({"type": atype, "error": "unknown sil action"})
    return {"results": results}, session_closed


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _skill_info(
    layout: Layout, skill_name: str, index: dict[str, Any]
) -> dict[str, Any]:
    """Return the manifest JSON of a skill, or an error."""
    for entry in index.get("skills", []):
        if entry.get("name") == skill_name:
            rel = entry.get("manifest", "")
            if rel:
                mpath = layout.root / rel
                if mpath.exists():
                    return {"type": "skill_info", "skill": skill_name,
                            "content": mpath.read_text(encoding="utf-8")}
            return {"type": "skill_info", "skill": skill_name, "error": "no manifest path"}
    return {"type": "skill_info", "skill": skill_name, "error": "skill not in index"}


def _rebuild_compact_history(
    layout: Layout,
    index: dict[str, Any],
    system: str,
) -> list[dict[str, Any]]:
    """Rebuild a minimal chat_history after session compaction.

    Structure:
      [0] user  — instruction block (boot protocol + skills)
      [1] asst  — "Understood. I am ready."
      [2] user  — working memory entries (freshly loaded from disk)
      [3] asst  — "Noted."
      [4] user  — [session compacted] + consolidation + handoff
      [5] asst  — ""  (placeholder for next CPE turn)
    """
    # Re-use build_boot_context to get fresh instruction block + working memory
    _, base_history = build_boot_context(layout, index)
    # base_history = [instruction_block, ack, (optional presession), ...]
    # We want only the first two (instruction block + ack) as the clean base.
    new_history: list[dict[str, Any]] = list(base_history[:2])

    # Load fresh working memory entries as context
    wm_parts: list[str] = []
    if layout.working_memory.exists():
        wm = read_json(layout.working_memory)
        for entry in sorted(wm.get("entries", []), key=lambda e: int(e.get("priority", 99))):
            p = layout.root / entry.get("path", "")
            if p.exists():
                wm_parts.append(p.read_text(encoding="utf-8").strip())
    if wm_parts:
        new_history.append({"role": "user", "content": "## Working Memory\n\n" + "\n\n---\n\n".join(wm_parts)})
        new_history.append({"role": "assistant", "content": "Noted."})

    # Load consolidation + handoff from session_handoff.json
    compact_parts: list[str] = ["[session compacted]"]
    if layout.session_handoff.exists():
        try:
            handoff = read_json(layout.session_handoff)
            if handoff.get("pending_tasks"):
                compact_parts.append("Pending tasks:\n" + "\n".join(f"- {t}" for t in handoff["pending_tasks"]))
            if handoff.get("next_steps"):
                compact_parts.append(f"Next steps: {handoff['next_steps']}")
        except json.JSONDecodeError as e:
            _vlog("fcp", f"session handoff corrupted ({e}) — skipping")
        except (KeyError, TypeError) as e:
            _vlog("fcp", f"session handoff schema error ({e}) — skipping")
        except Exception as e:
            _vlog("fcp", f"session handoff load error ({e}) — skipping")
    new_history.append({"role": "user", "content": "\n\n".join(compact_parts)})
    new_history.append({"role": "assistant", "content": ""})

    return new_history


def _drain_and_consolidate(layout: Layout) -> list[dict[str, Any]]:
    import dataclasses
    envelopes = drain_inbox(layout.inbox_dir)
    result = []
    for env in envelopes:
        d = dataclasses.asdict(env) if dataclasses.is_dataclass(env) else env
        append_jsonl(layout.session_store, d)
        result.append(d)
    return result


def _append_msg(layout: Layout, source: str, text: str) -> None:
    envelope = acp_encode(env_type="MSG", source=source, data=text)
    append_jsonl(layout.session_store, envelope)


def _return_tool_result(
    layout: Layout, call_id: str, tool: str, result: dict[str, Any]
) -> int:
    """Write tool result to session.jsonl and return its numeric timestamp (ms)."""
    import time as _time
    ts_ms = int(_time.time() * 1000)
    envelope = acp_encode(
        env_type="MSG",
        source="fcp",
        data={"tool_result": {"tool_use_id": call_id, "tool": tool,
                              "content": result, "_ts_ms": ts_ms}},
    )
    append_jsonl(layout.session_store, envelope)
    return ts_ms


def _session_byte_size(layout: Layout) -> int:
    if not layout.session_store.exists():
        return 0
    return layout.session_store.stat().st_size


def build_boot_stats(
    layout: Layout,
    index: dict[str, Any],
    system: str,
    chat_history: list[dict[str, Any]],
    tools: list[dict[str, Any]],
) -> dict[str, Any]:
    """Collect stats for the boot header printed before session starts."""
    # context % — estimate tokens as chars / 4
    total_chars = len(system) + sum(len(str(m.get("content", ""))) for m in chat_history)
    total_tokens = total_chars // 4
    baseline = load_baseline(layout)
    ctx_window = baseline.get("context_window", {}).get("budget_tokens", 0)
    ctx_pct = round(total_tokens / ctx_window * 100, 1) if ctx_window else None

    # sessions — count SLEEP_COMPLETE entries in integrity.log
    sessions = 0
    if layout.integrity_log.exists():
        for line in layout.integrity_log.read_text(encoding="utf-8").splitlines():
            try:
                rec = json.loads(line)
                raw = rec.get("data", "{}")
                d = json.loads(raw) if isinstance(raw, str) else raw
                if isinstance(d, dict) and d.get("type") == "SLEEP_COMPLETE":
                    sessions = sessions + 1
            except json.JSONDecodeError:
                # Malformed line in log — skip
                pass
            except Exception as e:
                _vlog("fcp", f"integrity log parse error ({e}) — skipping line")

    # cycles — count ENDURE_COMMIT entries in integrity_chain.jsonl
    cycles = 0
    if layout.integrity_chain.exists():
        for line in layout.integrity_chain.read_text(encoding="utf-8").splitlines():
            try:
                rec = json.loads(line)
                if rec.get("type") == "ENDURE_COMMIT":
                    cycles = cycles + 1
            except json.JSONDecodeError:
                # Malformed line in chain — skip
                pass
            except Exception as e:
                _vlog("fcp", f"integrity chain parse error ({e}) — skipping line")

    # memories — episodic + semantic files
    memories = 0
    for d in (layout.episodic_dir, layout.semantic_dir):
        if d.exists():
            memories += sum(1 for f in d.rglob("*") if f.is_file())

    # evolutions — authorized vs total EVOLUTION_AUTH
    evolutions_auth = 0
    evolutions_total = 0
    if layout.integrity_log.exists():
        for line in layout.integrity_log.read_text(encoding="utf-8").splitlines():
            try:
                rec = json.loads(line)
                raw = rec.get("data", "{}")
                d = json.loads(raw) if isinstance(raw, str) else raw
                if isinstance(d, dict) and d.get("type") == "EVOLUTION_AUTH":
                    evolutions_total = evolutions_total + 1
                    evolutions_auth = evolutions_auth + 1
                elif isinstance(d, dict) and d.get("type") == "ENDURE_COMMIT":
                    evolutions_total = evolutions_total + 1
            except json.JSONDecodeError:
                # Malformed line in log — skip
                pass
            except Exception as e:
                _vlog("fcp", f"evolution stats parse error ({e}) — skipping line")

    # skills and tools
    n_skills = len(index.get("skills", []))
    n_tools = len(tools)

    # notifications
    n_notif = 0
    if layout.operator_notifications_dir.exists():
        n_notif = sum(
            1 for f in layout.operator_notifications_dir.iterdir()
            if f.suffix == ".json" and not f.name.endswith(".tmp")
        )

    return {
        "ctx_tokens": total_tokens,
        "ctx_pct": ctx_pct,
        "sessions": sessions,
        "cycles": cycles,
        "memories": memories,
        "evolutions_auth": evolutions_auth,
        "evolutions_total": evolutions_total,
        "skills": n_skills,
        "tools": n_tools,
        "notifications": n_notif,
    }


# ---------------------------------------------------------------------------
# Verbose logging helpers
# ---------------------------------------------------------------------------

# Pure display helpers live in ui — import aliases for local use
_DIM  = ui.DIM
_RESET = ui.RESET
_GRAY  = ui.GRAY
_print_cpe_block      = ui.print_cpe_block
_vprint               = ui.vprint
_format_bytes         = ui.format_bytes
_compact_json         = ui.compact_json
_readline_with_history = ui.readline_with_history


def _vlog(actor: str, msg: str) -> None:
    if not _is_verbose():
        return
    _vprint(f"[{actor}] {msg}")


def _vlog_json(label: str, data: Any) -> None:
    if not _is_verbose():
        return
    _vprint(f"[{label}]")
    _vprint(json.dumps(data, indent=2, ensure_ascii=False))


def _vlog_request(
    system: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    cycle: int,
) -> None:
    """Log cycle header (before CPE invoke)."""
    dbg = _get_debugger()
    if not _is_verbose() and dbg is None:
        return

    if _is_verbose():
        sys_size = _format_bytes(len(system))
        _vprint(f"[CYCLE {cycle}] [→ CPE] {sys_size} system + {len(messages)} msgs + {len(tools)} tools")
        return

    # debugger mode — keep original detailed format
    _vprint("[debugger] fcp→cpe request")
    if dbg in ("boot", "all"):
        _vprint(f"  [system] {len(system)} chars:")
        for line in system.splitlines():
            _vprint(f"    {line}")
        _vprint(f"  [0] user (instruction block) {len(str(messages[0].get('content', '')))} chars:")
        for line in str(messages[0].get("content", "")).splitlines():
            _vprint(f"    {line}")
        _vprint(f"  [1] assistant: {messages[1].get('content', '')}")

    if dbg in ("chat", "all"):
        _vprint(f"  history ({len(messages) - 2} turns):")
        for i, msg in enumerate(messages):
            if i < 2:
                continue
            content = str(msg.get("content", ""))
            _vprint(f"    [{i}] {msg['role']}: {content}")

    _vprint(f"  tools: {[t['name'] for t in tools]}")


def _vlog_cycle_summary(
    response: CPEResponse,
    elapsed_secs: float,
    tool_log_lines: list[dict[str, Any]],
) -> None:
    """Print cycle summary: [DISPATCH] tree + [← CPE] line (always visible).

    Tree is always shown. With verbose: includes input/output JSON payloads.
    Without verbose: compact format with sizes and timing only.

    tool_log_lines: list of dicts with tool, input, output, input_size, result_size, status, timing_ms, is_last
    """
    dbg = _get_debugger()
    verbose = _is_verbose()

    # Dispatch block — ALWAYS show (if tools were called)
    if tool_log_lines:
        print(f"{_DIM}  ├─ [DISPATCH]{_RESET}")
        for tool_info in tool_log_lines:
            tool = tool_info["tool"]
            is_last = tool_info["is_last"]
            input_size = tool_info["input_size"]
            result_size = tool_info["result_size"]
            status = tool_info["status"]
            timing_ms = tool_info["timing_ms"]
            timing_str = f", {timing_ms:.0f}ms" if timing_ms > 10 else ""

            prefix = "  │  └─" if is_last else "  │  ├─"

            if verbose:
                print(f"{_DIM}{prefix} {tool}{_RESET}")
                input_json = _compact_json(tool_info["input"])
                output_json = _compact_json(tool_info["output"])
                print(f"{_DIM}{prefix[:-2]}│  ├─ input: {input_json}{_RESET}")
                print(f"{_DIM}{prefix[:-2]}│  └─ output: {output_json}{_RESET}")
            else:
                print(f"{_DIM}{prefix} {tool} ... input ({input_size}) → {status} ({result_size}{timing_str}){_RESET}")

    # CPE response line — ALWAYS show
    print(f"{_DIM}  └─ [← CPE] ⏱ {elapsed_secs:.1f}s | {response.stop_reason}{_RESET}")
    if verbose and response.text:
        preview = response.text[:50].replace("\n", " ")
        print(f"{_DIM}     └─ text: {preview!r} ({len(response.text)} chars){_RESET}")

    print()

    # Debugger mode
    if dbg and not verbose:
        print(f"{_DIM}[cpe→fcp] response{_RESET}")
        print(f"{_DIM}  stop_reason  : {response.stop_reason}{_RESET}")
        print(f"{_DIM}  tokens       : {response.input_tokens} in / {response.output_tokens} out{_RESET}")
        if response.text:
            preview = response.text[:200].replace("\n", " ")
            print(f"{_DIM}  text         : {preview!r}{_RESET}")
        for call in response.tool_use_calls:
            print(f"{_DIM}  tool_use     : {call.tool} (id={call.id}){_RESET}")

