"""Cognitive Session Loop — FCP-Core §6.

Orquestra o ciclo cognitivo:
  drain inbox → consolidar → montar contexto → invocar CPE →
  → parsear fcp-actions → despachar → próximo ciclo

Gestão de sessão:
  - Operator input via terminal, injectado como MSG em io/inbox/
  - Slash commands resolvidos directamente no EXEC (bypass CPE)
  - SESSION_CLOSE por: CPE, SIL (budget crítico) ou Operator (EOF/Ctrl+D)

Session close MVP (Fase 1):
  Revoga token → escreve SLEEP_COMPLETE stub → remove token.
  Sleep Cycle completo (drift, consolidação, Endure) é Fase 2.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

from .acp import (
    ACTOR_FCP, ACTOR_CPE, ACTOR_SIL,
    TYPE_MSG, TYPE_SESSION_CLOSE,
    GseqCounter, build_envelope, chunk_payload,
)
from .boot import BootContext
from .fs import drain_inbox, spool_msg, utcnow_iso
from .mil import consolidate_inbox, memory_write, memory_recall, append_session_event
from .sil import (
    append_integrity_log,
    revoke_session_token,
    remove_session_token,
    write_heartbeat,
    write_sleep_complete,
)
from .ui import UI, PlainUI
from .operator import write_notification, SEVERITY_DEGRADED

# ── regex para bloco fcp-actions ──────────────────────────────────────────
_FCP_ACTIONS_RE = re.compile(
    r"```fcp-actions\s*\n(.*?)\n```",
    re.DOTALL,
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
    Sempre executa o teardown (revoke → SLEEP_COMPLETE stub → remove token).
    """
    if ui is None:
        ui = PlainUI()
    try:
        _session_loop(ctx, ui)
    finally:
        _teardown(ctx, ui)


# ---------------------------------------------------------------------------
# Session loop
# ---------------------------------------------------------------------------

def _session_loop(ctx: BootContext, ui: UI) -> None:
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

    # System prompt: stays fixed throughout the session (persona + boot protocol
    # + skills + memory from previous sessions).
    system_prompt = ctx.assembled_context

    # Chat history: alternating user/assistant turns for this session.
    # Each user turn = formatted inbox events + operator input.
    # Each assistant turn = raw CPE response.
    chat_history: list[dict] = []
    cycle_count = 0

    ui.session_start(session_id)

    while True:
        # ── Heartbeat Vital Check (simplified — no background thread in MVP) ──
        cycle_count += 1
        if cycle_count % hb_cycle_thresh == 0:
            write_heartbeat(root, sil_gseq, session_id)

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

        # ── Invoke CPE ─────────────────────────────────────────────────────
        try:
            raw_response = cpe.invoke(system_prompt, chat_history)
        except Exception as exc:
            ui.error(str(exc))
            # Remove the user turn — don't poison history with a failed request.
            # Do NOT post the error to inbox: that would re-inject it back to the
            # CPE on the next cycle, causing an infinite error loop.
            chat_history.pop()
            continue

        # ── Append assistant response to history ───────────────────────────
        chat_history.append({"role": "assistant", "content": raw_response})

        # ── Verbose: show raw response ─────────────────────────────────────
        preview = raw_response[:600] + ("…" if len(raw_response) > 600 else "")
        ui.verbose_text("raw_cpe", preview)

        # ── Record CPE response in session.jsonl ───────────────────────────
        cpe_env = build_envelope(
            actor=ACTOR_CPE,
            type_=TYPE_MSG,
            data=raw_response[:3800],   # truncate for ACP limit; full stored below
            gseq=fcp_gseq.next(),
        )
        append_session_event(root, cpe_env.to_dict())

        # ── Parse fcp-actions block ─────────────────────────────────────────
        narrative, actions, parse_error = _parse_fcp_actions(raw_response)

        if narrative.strip():
            ui.narrative(narrative)

        if parse_error:
            ui.warning(parse_error)
            _log_parse_error(root, parse_error, fcp_gseq)
            continue

        ui.verbose_actions(actions)

        # ── Dispatch actions ────────────────────────────────────────────────
        close_requested = False
        for action in actions:
            target = action.get("target")
            atype  = action.get("type")

            if target == "sil" and atype == "session_close":
                close_requested = True

            elif target == "sil" and atype == "evolution_proposal":
                _handle_evolution_proposal(root, action, sil_gseq, ui)

            elif target == "exec" and atype == "skill_request":
                skill  = action.get("skill", "")
                params = action.get("params", {})
                dispatcher.dispatch_skill(skill, params)
                # Results arrive in inbox next cycle

            elif target == "mil" and atype == "memory_write":
                content = action.get("content", "")
                memory_write(root, content, mil_gseq)

            elif target == "mil" and atype == "memory_recall":
                query = action.get("query", "")
                memory_recall(root, query, mil_gseq)

            else:
                ui.warning(f"Unknown action target/type: {target}/{atype}")

        if close_requested:
            ui.session_close("entity")
            break


# ---------------------------------------------------------------------------
# Teardown — MVP Sleep Cycle stub (§7, Fase 2 completo)
# ---------------------------------------------------------------------------

def _teardown(ctx: BootContext, ui: UI) -> None:
    """Token revoke → SLEEP_COMPLETE stub → token remove.

    TODO Fase 2: substituir pelo Sleep Cycle completo (Stages 0-3):
      Stage 0: Semantic Drift Detection
      Stage 1: Memory Consolidation (Closure Payload)
      Stage 2: Garbage Collection
      Stage 3: Endure Execution
    """
    root = ctx.entity_root
    ui.teardown("Revoking session token…")
    revoke_session_token(root)
    # MVP stub: write SLEEP_COMPLETE immediately (no actual sleep stages)
    write_sleep_complete(root, ctx.sil_gseq, ctx.session_id)
    remove_session_token(root)
    ui.teardown("Session closed cleanly.")


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

    if t == "SKILL_RESULT":
        try:
            d = json.loads(data)
        except Exception:
            return f"[Result]\n{data}"

        if actor == "mil":
            # Memory write confirmation: {"status": "ok", "path": ..., "ts": ...}
            if "path" in d:
                return f"[Memory saved: {d['path']}]"
            # Memory recall result: {"query": ..., "count": ..., "results": [...]}
            if "query" in d:
                count   = d.get("count", 0)
                results = d.get("results", [])
                if not results:
                    return f"[Memory recall: {d['query']!r}] No matching entries found."
                parts = [f"[Memory recall: {d['query']!r}] {count} result(s):"]
                for r in results:
                    parts.append(f"\n--- {r['path']} ---\n{r['excerpt'].strip()}")
                return "\n".join(parts)
            # Fallback for unknown MIL result
            return f"[MIL]\n{data}"

        # EXEC skill result: {"skill": ..., "output": ..., "exit_code": ...}
        return f"[Skill result: {d.get('skill', '?')}]\n{d.get('output', '').strip()}"

    if t == "SKILL_ERROR":
        try:
            d = json.loads(data)
            if actor == "mil":
                return f"[Memory error]\n{d.get('error', data)}"
            return f"[Skill error: {d.get('skill', '?')}]\n{d.get('error', '').strip()}"
        except Exception:
            return f"[Error]\n{data}"

    # Generic fallback for any other envelope type
    return f"[{t}]\n{data}" if data else f"[{t}]"


# ---------------------------------------------------------------------------
# fcp-actions parser (§6.2)
# ---------------------------------------------------------------------------

def _parse_fcp_actions(
    raw: str,
) -> tuple[str, list[dict[str, Any]], str]:
    """Parse CPE response into (narrative, actions, error).

    Rules (§6.2):
      - Zero fcp-actions blocks → valid conversational turn (no external actions).
      - Exactly one block → parsed normally.
      - Multiple blocks → rejected.
      - Malformed JSON → rejected.
      - Missing actions array → rejected.

    Returns:
        (narrative_text, actions_list, error_message)
        On rejection: actions_list=[], error_message set.
    """
    matches = _FCP_ACTIONS_RE.findall(raw)

    if len(matches) == 0:
        # No fcp-actions block — valid conversational turn, no external actions.
        return raw, [], ""

    if len(matches) > 1:
        narrative = _FCP_ACTIONS_RE.sub("", raw).strip()
        return narrative, [], f"Multiple fcp-actions blocks found ({len(matches)}). Rejected."

    # Exactly one block
    block_json = matches[0].strip()
    narrative  = _FCP_ACTIONS_RE.sub("", raw).strip()

    try:
        payload = json.loads(block_json)
    except json.JSONDecodeError as exc:
        return narrative, [], f"fcp-actions JSON malformed: {exc}"

    actions = payload.get("actions")
    if not isinstance(actions, list):
        return narrative, [], "fcp-actions payload missing 'actions' array."

    return narrative, actions, ""


# ---------------------------------------------------------------------------
# Slash command handler
# ---------------------------------------------------------------------------

def _handle_slash(ctx: BootContext, slash_input: str, ui: UI) -> None:
    if slash_input.strip() in ("/help", "/?"):
        _print_help(ctx, ui)
        return

    ui.info(f"→ dispatching {slash_input.split()[0]}")
    ctx.dispatcher.dispatch_slash(slash_input)
    # Results will arrive in io/inbox/ — drain and show immediately
    import time; time.sleep(0.1)   # brief settle for filesystem
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
    root: Path,
    action: dict[str, Any],
    sil_gseq: GseqCounter,
    ui: UI,
) -> None:
    """Log proposal to integrity.log and write to operator_notifications/."""
    from .operator import write_notification, SEVERITY_INFO

    content = action.get("content", "")
    env = build_envelope(
        actor=ACTOR_SIL,
        type_="EVOLUTION_PROPOSAL",
        data=json.dumps({"content": content, "ts": utcnow_iso()}),
        gseq=sil_gseq.next(),
    )
    append_integrity_log(root, env)
    write_notification(root, SEVERITY_INFO, {
        "type":    "EVOLUTION_PROPOSAL",
        "content": content,
        "note":    "Awaiting Operator approval. Will be presented at session close.",
    })
    # Per §10.5, outcome is never returned to the CPE.
    ui.info("[SIL] Evolution Proposal received and logged.")
    ui.info("Awaiting Operator decision at session close.")


# ---------------------------------------------------------------------------
# Error logging
# ---------------------------------------------------------------------------

def _log_parse_error(root: Path, error: str, gseq: GseqCounter) -> None:
    env = build_envelope(
        actor=ACTOR_FCP,
        type_="MSG",
        data=json.dumps({"parse_error": error, "ts": utcnow_iso()}),
        gseq=gseq.next(),
    )
    append_session_event(root, env.to_dict())
