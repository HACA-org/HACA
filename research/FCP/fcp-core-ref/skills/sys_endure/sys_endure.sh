#!/bin/bash
# sys_endure — Unified evolution protocol for all integrity-protected system files (FCP §12)
#
# Every file tracked in state/integrity.json can only be changed through this skill.
# sys_endure is the protocol (backup → dispatch → seal → audit).
# Handlers in handlers/ provide operation-specific logic.
#
# Usage: .endure <subcommand> [object] [options]
#
#   .endure add skill     --name <n> --description <d> [--command <.cmd>] [--script <path>]
#   .endure add hook      --event <e> --name <n> [--script <path>] [--priority <nn>]
#   .endure evolve identity --file <f> --content <c> [--commit-msg <m>] [--dry-run]
#   .endure evolve boot   --content <c> [--commit-msg <m>] [--dry-run]
#   .endure remove skill  --name <n> --confirm
#   .endure remove hook   --event <e> --name <n> --confirm
#   .endure seal          [--add <path>]
#   .endure sync          [--remote] [--message <m>]
#   .endure status

set -euo pipefail

FCP_REF_ROOT="${FCP_REF_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
HANDLERS_DIR="$FCP_REF_ROOT/skills/sys_endure/handlers"

source "$FCP_REF_ROOT/skills/lib/acp.sh"

SUBCOMMAND="${1:-}"
shift || true

if [ -z "$SUBCOMMAND" ]; then
    echo "[sys_endure] Usage: .endure <subcommand> [object] [options]"
    echo "  Subcommands: add, evolve, remove, seal, sync, status"
    exit 1
fi

# ── Backup before any mutation ────────────────────────────────────────────────
endure_backup() {
    local reason="$1"
    local snap="$FCP_REF_ROOT/skills/snapshot_create/snapshot_create.sh"
    if [ -f "$snap" ]; then
        "$snap" "{\"reason\": \"pre_endure: $reason\"}" 2>/dev/null || true
    fi
}

# ── Audit log ─────────────────────────────────────────────────────────────────
endure_audit() {
    local op="$1"
    local detail="$2"
    local ts
    ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    acp_write "sil" "MSG" \
        "{\"event\": \"sys_endure\", \"op\": $(python3 -c "import json,sys; print(json.dumps(sys.argv[1]))" "$op"), \"detail\": $(python3 -c "import json,sys; print(json.dumps(sys.argv[1]))" "$detail"), \"ts\": \"$ts\"}" \
        >/dev/null 2>&1 || true
}

# ── Dispatch ──────────────────────────────────────────────────────────────────
case "$SUBCOMMAND" in

    add)
        OBJECT="${1:-}"
        shift || true
        case "$OBJECT" in
            skill)
                endure_backup "add skill $*"
                endure_audit "add_skill" "$*"
                exec "$HANDLERS_DIR/add_skill.sh" "$@"
                ;;
            hook)
                endure_backup "add hook $*"
                endure_audit "add_hook" "$*"
                exec "$HANDLERS_DIR/add_hook.sh" "$@"
                ;;
            *)
                echo "[sys_endure] Unknown object: '$OBJECT'. Use: skill, hook" >&2
                exit 1
                ;;
        esac
        ;;

    evolve)
        OBJECT="${1:-}"
        shift || true
        case "$OBJECT" in
            identity)
                endure_backup "evolve identity"
                endure_audit "evolve_identity" "$*"
                exec "$HANDLERS_DIR/evolve_identity.sh" "$@"
                ;;
            boot)
                endure_backup "evolve boot"
                endure_audit "evolve_boot" "$*"
                exec "$HANDLERS_DIR/evolve_boot.sh" "$@"
                ;;
            *)
                echo "[sys_endure] Unknown object: '$OBJECT'. Use: identity, boot" >&2
                exit 1
                ;;
        esac
        ;;

    remove)
        OBJECT="${1:-}"
        shift || true
        case "$OBJECT" in
            skill)
                endure_backup "remove skill $*"
                endure_audit "remove_skill" "$*"
                exec "$HANDLERS_DIR/remove_skill.sh" "$@"
                ;;
            hook)
                endure_backup "remove hook $*"
                endure_audit "remove_hook" "$*"
                exec "$HANDLERS_DIR/remove_hook.sh" "$@"
                ;;
            *)
                echo "[sys_endure] Unknown object: '$OBJECT'. Use: skill, hook" >&2
                exit 1
                ;;
        esac
        ;;

    seal)
        exec "$HANDLERS_DIR/seal.sh" "$@"
        ;;

    sync)
        exec "$HANDLERS_DIR/sync.sh" "$@"
        ;;

    status)
        exec "$HANDLERS_DIR/status.sh" "$@"
        ;;

    *)
        echo "[sys_endure] Unknown subcommand: '$SUBCOMMAND'" >&2
        echo "  Use: add, evolve, remove, seal, sync, status" >&2
        exit 1
        ;;
esac
