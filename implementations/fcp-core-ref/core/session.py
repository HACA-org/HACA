"""Cognitive Session Loop — FCP-Core §6.

Orquestra o ciclo cognitivo:
  drain inbox → consolidar → montar contexto → invocar CPE →
  → tool loop (dispatch tool calls ↔ tool results) → próximo ciclo

Gestão de sessão:
  - Operator input via terminal, injectado como MSG em io/inbox/
  - Slash commands resolvidos directamente no EXEC (bypass CPE)
  - SESSION_CLOSE por: CPE, SIL (budget crítico) ou Operator (EOF/Ctrl+D)

Session close MVP (Fase 1):
  Revoga token → escreve SLEEP_COMPLETE stub → remove token.
  Sleep Cycle completo (drift, consolidação, Endure) é Fase 2.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

from .acp import (
    ACTOR_FCP, ACTOR_CPE, ACTOR_SIL,
    TYPE_MSG, TYPE_SESSION_CLOSE, TYPE_EVOLUTION_PROPOSAL, TYPE_CLOSURE_PAYLOAD,
    TYPE_MEMO_RESULT,
    TYPE_SKILL_RESULT,
    GseqCounter, build_envelope, chunk_payload,
)
from .boot import BootContext
from .cpe import FCP_TOOLS, ToolResult
from .fs import drain_inbox, spool_msg, utcnow_iso
from .hooks import run_hook
from .mil import (
    consolidate_inbox, memory_write, memory_recall, append_session_event,
    write_working_memory, write_session_handoff, write_episodic,
)
from .sil import (
    append_integrity_log,
    revoke_session_token,
    remove_session_token,
    write_heartbeat,
    write_sleep_complete,
    log_closure_payload,
    run_endure,
    write_evolution_auth,
    write_evolution_rejected,
    write_proposal_pending,
)
from .ui import UI, PlainUI
from .operator import (
    assert_terminal_accessible, terminal_prompt,
    write_notification, SEVERITY_DEGRADED, SEVERITY_INFO,
)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run_session(ctx: BootContext, ui: UI | None = None) -> None:
    """Executa o session loop completo a partir de um BootContext.

    Args:
        ctx: Boot context from run_boot().
        ui:  Display interface.  Defaults to PlainUI() when None.

    Retorna quando a sessão fecha (normalmente ou por erro).
    Sempre executa o teardown (revoke → Evolution decisions → SLEEP_COMPLETE stub → remove token).
    """
    if ui is None:
        ui = PlainUI()
    pending_proposals: list[dict] = []
    try:
        _session_loop(ctx, ui, pending_proposals)
    finally:
        _teardown(ctx, ui, pending_proposals)


# ---------------------------------------------------------------------------
# Session loop
# ---------------------------------------------------------------------------

def _session_loop(ctx: BootContext, ui: UI, pending_proposals: list[dict]) -> None:
    root             = ctx.entity_root
    cpe              = ctx.cpe
    dispatcher       = ctx.dispatcher
    sil_gseq         = ctx.sil_gseq
    mil_gseq         = ctx.mil_gseq
    fcp_gseq         = ctx.fcp_gseq
    session_id       = ctx.session_id
    baseline         = ctx.baseline
    budget_tokens    = baseline.get("context_window", {}).get("budget_tokens", 200_000)
    critical_pct     = baseline.get("context_window", {}).get("critical_pct", 85)
    hb_cycle_thresh  = baseline.get("heartbeat", {}).get("cycle_threshold", 10)
    hb_interval_secs = baseline.get("heartbeat", {}).get("interval_seconds", 300)

    # System prompt: stays fixed throughout the session (persona + boot protocol
    # + skills + memory from previous sessions).
    system_prompt = ctx.assembled_context

    # Chat history: alternating user/assistant turns for this session.
    # Each user turn = formatted inbox events + operator input.
    # Each assistant turn = raw CPE response.
    chat_history: list[dict] = []
    cycle_count = 0
    last_hb_time = time.monotonic()

    ui.session_start(session_id)
    run_hook(ctx.entity_root, "on_boot", session_id)
    _setup_readline(ctx)

    while True:
        # ── Heartbeat Vital Check (simplified — no background thread in MVP) ──
        cycle_count += 1
        now = time.monotonic()
        if (cycle_count % hb_cycle_thresh == 0) or (now - last_hb_time >= hb_interval_secs):
            write_heartbeat(root, sil_gseq, session_id)
            last_hb_time = now

        # ── Drain inbox ────────────────────────────────────────────────────
        inbox_envs = drain_inbox(root)
        if inbox_envs:
            consolidate_inbox(root, inbox_envs)

        # ── Get Operator input (if inbox is empty) ─────────────────────────
        if not inbox_envs:
            try:
                ui.write_prompt()
                line = sys.stdin.readline()
            except KeyboardInterrupt:
                print()
                continue

            if not line:                            # EOF — close session
                ui.session_close("operator")
                break

            operator_input = line.rstrip("\n")

            if not operator_input.strip():
                continue                             # ignore blank lines

            # ── Slash command — bypass CPE ──────────────────────────────
            if operator_input.startswith("/"):
                _handle_slash(ctx, operator_input, ui)
                continue

            # ── Regular message — inject into inbox ─────────────────────
            msg_env = build_envelope(
                actor=ACTOR_FCP,
                type_=TYPE_MSG,
                data=operator_input,
                gseq=fcp_gseq.next(),
            )
            spool_msg(root, msg_env.to_dict())
            new_envs = drain_inbox(root)
            consolidate_inbox(root, new_envs)
            inbox_envs = new_envs

        # ── Build user message from inbox events ───────────────────────────
        user_parts = [_format_inbox_event(env) for env in inbox_envs]
        user_content = "\n\n".join(p for p in user_parts if p.strip())
        if not user_content.strip():
            continue

        chat_history.append({"role": "user", "content": user_content})

        # ── Context budget check ───────────────────────────────────────────
        history_chars = sum(len(m["content"]) for m in chat_history)
        used_tokens   = (len(system_prompt) + history_chars) // 4
        if used_tokens >= budget_tokens * critical_pct // 100:
            ui.warning(
                f"Context window at {critical_pct}% capacity. Closing session."
            )
            close_env = build_envelope(
                actor=ACTOR_SIL,
                type_=TYPE_SESSION_CLOSE,
                data=json.dumps({"reason": "context_budget_critical"}),
                gseq=sil_gseq.next(),
            )
            append_integrity_log(root, close_env)
            write_notification(root, SEVERITY_DEGRADED, {
                "event":        "SESSION_CLOSE_BUDGET",
                "session_id":   session_id,
                "used_tokens":  used_tokens,
                "budget_tokens": budget_tokens,
            })
            ui.session_close("budget")
            break

        # ── Verbose: show outbound turn ────────────────────────────────────
        ui.verbose_cycle(cycle_count, len(chat_history), used_tokens)
        ui.verbose_text("user_message", user_content)
        ui.refresh_status(cycle_count, used_tokens, budget_tokens)

        # ── Invoke CPE ─────────────────────────────────────────────────────
        try:
            cpe_resp = cpe.invoke(system_prompt, chat_history, tools=FCP_TOOLS)
        except Exception as exc:
            ui.error(f"[CPE] {exc}")
            # Remove the user turn — don't poison history with a failed request.
            chat_history.pop()
            continue

        # ── Tool loop ──────────────────────────────────────────────────────
        # The CPE may issue tool calls in response to any turn.  We dispatch
        # them and re-invoke until the model returns a text-only response.
        close_requested = False
        while cpe_resp.tool_calls:
            if cpe_resp.text.strip():
                ui.narrative(cpe_resp.text)
                _log_cpe_text(root, cpe_resp.text, fcp_gseq)

            # Append assistant message with full content (includes tool_use blocks)
            chat_history.append({"role": "assistant", "content": cpe_resp.raw_content})

            # Dispatch tool calls in MIL → EXEC → SIL order
            tool_results, close_requested = _dispatch_tool_calls(
                cpe_resp.tool_calls, root, dispatcher,
                sil_gseq, mil_gseq, fcp_gseq, ui, pending_proposals,
            )

            # Add tool_result messages to history
            for msg in cpe.make_tool_result_message(tool_results):
                chat_history.append(msg)

            if close_requested:
                break

            # Re-invoke so the CPE can react to tool results
            try:
                ui.verbose_text("↩ re-invoke", f"turns={len(chat_history)}")
                cpe_resp = cpe.invoke(system_prompt, chat_history, tools=FCP_TOOLS)
            except Exception as exc:
                ui.error(f"[CPE] tool-loop re-invoke: {exc}")
                break

        # ── Final text response ────────────────────────────────────────────
        # Append narrative from the last (text-only) CPE response.
        if cpe_resp.text.strip():
            ui.verbose_text("raw_cpe", cpe_resp.text[:1200])
            ui.narrative(cpe_resp.text)
            _log_cpe_text(root, cpe_resp.text, fcp_gseq)
        chat_history.append({"role": "assistant", "content": cpe_resp.text})

        if close_requested:
            ui.session_close("entity")
            break


# ---------------------------------------------------------------------------
# Teardown — MVP Sleep Cycle stub (§7, Fase 2 completo)
# ---------------------------------------------------------------------------

def _teardown(ctx: BootContext, ui: UI, pending_proposals: list[dict]) -> None:
    """Token revoke → Evolution decisions → Sleep Cycle Stages 1+3 → SLEEP_COMPLETE → remove token.

    Stage 0 (Semantic Drift Detection) and Stage 2 (Garbage Collection)
    are deferred to Fase 3.
    """
    root = ctx.entity_root
    ui.teardown("Revoking session token…")
    revoke_session_token(root)

    # Evolution Gate: collect Operator decisions (§10.5)
    _collect_evolution_decisions(root, pending_proposals, ctx.sil_gseq, ctx.operator_name, ui)

    # Stage 0: Semantic Drift Detection — deferred to Fase 3
    # Stage 1: Memory Consolidation — processed mid-session via _handle_closure_payload
    # Stage 2: Garbage Collection — deferred

    # Stage 3: Endure Execution
    checkpoint_interval = ctx.baseline.get("integrity_chain", {}).get("checkpoint_interval", 10)
    snapshot_keep       = ctx.baseline.get("endure", {}).get("snapshot_keep", 3)
    run_hook(ctx.entity_root, "on_session_close", ctx.session_id)
    errors = run_endure(root, ctx.sil_gseq, ctx.session_id, checkpoint_interval, snapshot_keep)
    if errors:
        ui.warning(f"[Endure] {len(errors)} error(s) during Stage 3 — affected proposals remain pending for next session:")
        for err in errors:
            ui.warning(f"[Endure]   {err}")

    write_sleep_complete(root, ctx.sil_gseq, ctx.session_id)
    remove_session_token(root)
    ui.teardown("Session closed cleanly.")


# ---------------------------------------------------------------------------
# Evolution decisions collector (§10.5)
# ---------------------------------------------------------------------------

def _collect_evolution_decisions(
    root:              Path,
    pending_proposals: list[dict],
    sil_gseq:          GseqCounter,
    operator_name:     str,
    ui:                UI,
) -> None:
    """Collect Operator decisions on pending Evolution Proposals at session close.

    If terminal is accessible, present each proposal interactively and write
    EVOLUTION_AUTH or EVOLUTION_REJECTED.  If terminal is inaccessible (e.g.
    unattended session), write PROPOSAL_PENDING for each — proposals will be
    re-presented via Phase 6 at the next boot.  Outcome is never returned to CPE.
    """
    if not pending_proposals:
        return

    try:
        assert_terminal_accessible()
    except OSError:
        for p in pending_proposals:
            write_proposal_pending(root, sil_gseq, p["content"], p["tx"])
        return

    print(f"\n[SIL] {len(pending_proposals)} Evolution Proposal(s) pending Operator decision:")
    for i, p in enumerate(pending_proposals, 1):
        print(f"\n  [{i}] tx={p['tx'][:8]}…")
        print(f"  {p['content'][:400]}")
        print()
        ans = terminal_prompt(
            "  Approve this Evolution Proposal? [yes/no]",
            options=["yes", "no"],
        )
        if ans == "yes":
            digest = hashlib.sha256(p["content"].encode()).hexdigest()
            write_evolution_auth(root, sil_gseq, p["tx"], digest, operator_name)
            ui.info(f"  Approved (tx={p['tx'][:8]}…).")
        else:
            write_evolution_rejected(root, sil_gseq, p["tx"])
            ui.info(f"  Rejected (tx={p['tx'][:8]}…).")
    print()


# ---------------------------------------------------------------------------
# Inbox event formatter
# ---------------------------------------------------------------------------

def _format_inbox_event(env: dict) -> str:
    """Format a single ACP envelope into human/model-readable text."""
    t     = env.get("type", "")
    actor = env.get("actor", "")
    data  = env.get("data", "")

    if t == "MSG":
        return data   # operator message text — pass through as-is

    if t == "MEMO_RESULT":
        try:
            d = json.loads(data)
        except Exception:
            return f"[Memory result]\n{data}"
        # memory_write confirmation: {"status": "ok", "path": ..., "ts": ...}
        if "path" in d:
            return f"[Memory saved: {d['path']}]"
        # memory_recall result: {"query": ..., "count": ..., "results": [...]}
        if "query" in d:
            count   = d.get("count", 0)
            results = d.get("results", [])
            if not results:
                return f"[Memory recall: {d['query']!r}] No matching entries found."
            parts = [f"[Memory recall: {d['query']!r}] {count} result(s):"]
            for r in results:
                parts.append(f"\n--- {r['path']} ---\n{r['excerpt'].strip()}")
            return "\n".join(parts)
        return f"[Memory result]\n{data}"

    if t == "SKILL_RESULT":
        try:
            d = json.loads(data)
        except Exception:
            return f"[Result]\n{data}"
        # EXEC skill result: {"skill": ..., "output": ..., "exit_code": ...}
        return f"[Skill result: {d.get('skill', '?')}]\n{d.get('output', '').strip()}"

    if t == "SKILL_ERROR":
        try:
            d = json.loads(data)
            return f"[Skill error: {d.get('skill', '?')}]\n{d.get('error', '').strip()}"
        except Exception:
            return f"[Error]\n{data}"

    if t == "SKILL_TIMEOUT":
        try:
            d = json.loads(data)
            return f"[Skill timeout: {d.get('skill', '?')}]\n{d.get('error', '').strip()}"
        except Exception:
            return f"[Timeout]\n{data}"

    # Generic fallback for any other envelope type
    return f"[{t}]\n{data}" if data else f"[{t}]"


# ---------------------------------------------------------------------------
# Tool call dispatcher (§6 — tool loop)
# ---------------------------------------------------------------------------

def _dispatch_tool_calls(
    tool_calls:        list[dict[str, Any]],
    root:              Path,
    dispatcher:        Any,
    sil_gseq:          GseqCounter,
    mil_gseq:          GseqCounter,
    fcp_gseq:          GseqCounter,
    ui:                Any,
    pending_proposals: list[dict],
) -> tuple[list[ToolResult], bool]:
    """Dispatch CPE tool calls in MIL → EXEC → SIL order.

    Returns:
        (tool_results, close_requested)
    """
    close_requested = False
    tool_results: list[ToolResult] = []

    # Process in component order: MIL first, EXEC second, SIL last.
    _ORDER = {"fcp_mil": 0, "fcp_exec": 1, "fcp_sil": 2}
    sorted_calls = sorted(tool_calls, key=lambda tc: _ORDER.get(tc["name"], 9))

    for tc in sorted_calls:
        tool_id = tc["id"]
        name    = tc["name"]
        inp     = tc["input"]
        atype   = inp.get("type", "")

        ui.verbose_text(f"→ {name}.{atype}", json.dumps(inp, ensure_ascii=False)[:400])

        if name == "fcp_mil":
            if atype == "memory_write":
                content = inp.get("content", "")
                envs    = memory_write(root, content, mil_gseq, spool=False)
                tr      = ToolResult(tool_id, _extract_env_text(envs))
            elif atype == "memory_recall":
                query = inp.get("query", "")
                envs  = memory_recall(root, query, mil_gseq, spool=False)
                tr    = ToolResult(tool_id, _extract_env_text(envs))
            elif atype == "closure_payload":
                _handle_closure_payload(root, inp, sil_gseq, mil_gseq, ui)
                tr = ToolResult(tool_id, "[Closure payload recorded]")
            else:
                tr = ToolResult(tool_id, f"Unknown fcp_mil type: {atype!r}", is_error=True)

        elif name == "fcp_exec":
            skill = inp.get("skill", "")
            if atype == "skill_request":
                params = inp.get("params") or {}
                envs   = dispatcher.dispatch_skill(skill, params, spool=False)
                text   = _extract_env_text(envs)
                is_err = bool(envs) and envs[0].get("type") != TYPE_SKILL_RESULT
                tr     = ToolResult(tool_id, text, is_error=is_err)
            elif atype == "skill_info":
                envs   = dispatcher.dispatch_skill_info(skill, spool=False)
                text   = _extract_env_text(envs)
                is_err = bool(envs) and envs[0].get("type") != TYPE_SKILL_RESULT
                tr     = ToolResult(tool_id, text, is_error=is_err)
            else:
                tr = ToolResult(tool_id, f"Unknown fcp_exec type: {atype!r}", is_error=True)

        elif name == "fcp_sil":
            if atype == "session_close":
                close_requested = True
                tr = ToolResult(tool_id, "[Session close initiated]")
            elif atype == "evolution_proposal":
                _handle_evolution_proposal(root, inp, sil_gseq, ui, pending_proposals)
                tr = ToolResult(
                    tool_id,
                    "[Evolution proposal registered. Awaiting Operator decision at session close.]",
                )
            else:
                tr = ToolResult(tool_id, f"Unknown fcp_sil type: {atype!r}", is_error=True)

        else:
            tr = ToolResult(tool_id, f"Unknown tool: {name!r}", is_error=True)

        ui.verbose_text(
            f"← {name}.{atype}",
            ("[ERR] " if tr.is_error else "") + tr.content[:600],
        )
        tool_results.append(tr)

    return tool_results, close_requested


def _extract_env_text(envs: list[dict[str, Any]]) -> str:
    """Extract the human-readable result string from a list of ACP envelope dicts."""
    for env in envs:
        try:
            d = json.loads(env.get("data", "{}"))
        except Exception:
            d = {}
        t = env.get("type", "")
        if t == TYPE_SKILL_RESULT:
            return d.get("output", "").strip() or d.get("path", "")
        elif t == TYPE_MEMO_RESULT:
            if "path" in d:
                return f"[Memory saved: {d['path']}]"
            count   = d.get("count", 0)
            results = d.get("results", [])
            if not results:
                return f"[Memory recall: {d.get('query', '')}] No matching entries."
            parts = [f"[Memory recall: {count} result(s)]"]
            for r in results:
                parts.append(f"--- {r['path']} ---\n{r['excerpt'].strip()}")
            return "\n".join(parts)
        else:
            return d.get("error", d.get("output", "")).strip()
    return ""


def _log_cpe_text(root: Path, text: str, gseq: GseqCounter) -> None:
    """Append CPE narrative text to session.jsonl."""
    env = build_envelope(
        actor=ACTOR_CPE,
        type_=TYPE_MSG,
        data=text[:3800],
        gseq=gseq.next(),
    )
    append_session_event(root, env.to_dict())


# ---------------------------------------------------------------------------
# Readline tab completion (TTY only, best-effort)
# ---------------------------------------------------------------------------

def _setup_readline(ctx: BootContext) -> None:
    """Register Tab completion for / commands.  No-op if readline unavailable."""
    if not sys.stdin.isatty():
        return
    try:
        import readline  # stdlib; absent on some minimal Pythons
    except ImportError:
        return

    _BUILTIN_CMDS = ["/help", "/?", "/verbose", "/verbose on", "/verbose off"]
    all_cmds = _BUILTIN_CMDS + list(ctx.skill_index.all_aliases())

    # Keep '/' as part of the completion token so '/ski' → ['/skill_create', …]
    readline.set_completer_delims(" \t\n")

    def _completer(text: str, state: int) -> str | None:
        if not readline.get_line_buffer().lstrip().startswith("/"):
            return None
        matches = [c for c in all_cmds if c.startswith(text)]
        return matches[state] if state < len(matches) else None

    readline.set_completer(_completer)
    try:
        readline.parse_and_bind("tab: complete")
    except Exception:
        readline.parse_and_bind("bind ^I rl_complete")  # libedit (macOS)


# ---------------------------------------------------------------------------
# Slash command handler
# ---------------------------------------------------------------------------

def _handle_slash(ctx: BootContext, slash_input: str, ui: UI) -> None:
    if slash_input.strip() in ("/help", "/?"):
        _print_help(ctx, ui)
        return

    parts = slash_input.strip().split(None, 1)
    if parts[0] == "/verbose":
        arg = (parts[1].lower() if len(parts) > 1 else "")
        if arg == "off":
            ui.set_verbose(False)
        elif arg == "on":
            ui.set_verbose(True)
        else:
            ui.set_verbose(not ui.verbose)  # toggle
        return

    ui.info(f"→ dispatching {slash_input.split()[0]}")
    ctx.dispatcher.dispatch_slash(slash_input)
    # Results will arrive in io/inbox/ — drain and show immediately
    time.sleep(0.1)   # brief settle for filesystem
    envs = drain_inbox(ctx.entity_root)
    consolidate_inbox(ctx.entity_root, envs)
    for env in envs:
        t = env.get("type", "")
        if t in ("SKILL_RESULT", "SKILL_ERROR"):
            try:
                d = json.loads(env.get("data", "{}"))
                if t == "SKILL_RESULT":
                    ui.skill_ok(d.get("skill", ""), d.get("output", ""))
                else:
                    ui.skill_err(d.get("skill", ""), d.get("error", ""))
            except Exception:
                ui.info(env.get("data", ""))


def _print_help(ctx: BootContext, ui: UI) -> None:
    ui.help_start()
    ui.help_item("/verbose [on|off]", "toggle verbose output (default: toggle)")
    for alias in sorted(ctx.skill_index.all_aliases()):
        sname = ctx.skill_index.resolve_alias(alias)
        entry = ctx.skill_index.get(sname or "")
        desc  = entry.get("description", "") if entry else ""
        ui.help_item(alias, desc)
    ui.help_end()


# ---------------------------------------------------------------------------
# Evolution Proposal handler (§10.5)
# ---------------------------------------------------------------------------

def _handle_evolution_proposal(
    root:              Path,
    action:            dict[str, Any],
    sil_gseq:          GseqCounter,
    ui:                UI,
    pending_proposals: list[dict],
) -> None:
    """Log proposal; queue for Operator decision at session close (§10.5)."""
    content     = action.get("content", "")
    target_file = action.get("target_file", "")
    env = build_envelope(
        actor=ACTOR_SIL,
        type_=TYPE_EVOLUTION_PROPOSAL,
        data=json.dumps({"content": content, "target_file": target_file, "ts": utcnow_iso()}),
        gseq=sil_gseq.next(),
    )
    append_integrity_log(root, env)
    write_notification(root, SEVERITY_INFO, {
        "type":    "EVOLUTION_PROPOSAL",
        "content": content,
        "note":    "Awaiting Operator approval. Will be presented at session close.",
    })
    pending_proposals.append({"tx": env.tx, "content": content})
    ui.info("[SIL] Evolution Proposal received. Decision at session close.")


# ---------------------------------------------------------------------------
# Closure Payload handler (§7.2, Fase 1 stub)
# ---------------------------------------------------------------------------

def _handle_closure_payload(
    root:      Path,
    action:    dict[str, Any],
    sil_gseq:  GseqCounter,
    mil_gseq:  GseqCounter,
    ui:        UI,
) -> None:
    """Sleep Cycle Stage 1 — Memory Consolidation (§7.2).

    Processes all three Closure Payload fields:
      - consolidation: written to episodic memory + appended to session.jsonl
      - working_memory: validated and written to working-memory.json
      - session_handoff: written to session-handoff.json
    """
    log_closure_payload(root, sil_gseq, action)

    # consolidation → episodic write + append to session.jsonl as MSG (§7.2)
    consolidation = action.get("consolidation", "")
    if consolidation:
        write_episodic(root, consolidation, label="consolidation")
        cenv = build_envelope(
            actor=ACTOR_CPE,
            type_=TYPE_MSG,
            data=consolidation[:3800],
            gseq=mil_gseq.next(),
        )
        append_session_event(root, cenv.to_dict())

    # working_memory → ensure session-handoff.json is included, write pointer map
    # Normalize: model may send plain strings (paths) instead of {priority, path} dicts.
    wm_raw = list(action.get("working_memory") or [])
    wm_entries = []
    for e in wm_raw:
        if isinstance(e, str):
            wm_entries.append({"priority": 50, "path": e})
        elif isinstance(e, dict) and "path" in e:
            wm_entries.append(e)
    handoff_path = "memory/session-handoff.json"
    if action.get("session_handoff") and not any(
        e.get("path") == handoff_path for e in wm_entries
    ):
        wm_entries.append({"priority": 90, "path": handoff_path})
    if wm_entries:
        write_working_memory(root, wm_entries, max_entries=20)

    # session_handoff → write atomically, replacing previous record
    handoff = action.get("session_handoff")
    if handoff:
        write_session_handoff(root, handoff)

