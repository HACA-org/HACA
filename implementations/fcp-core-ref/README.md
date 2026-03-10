# FCP-Ref — Reference Implementation of the Filesystem Cognitive Platform

FCP-Ref is the minimal, spec-complete implementation of [FCP v1.0](../fcp-spec/FCP-v1.0-RFC-Draft.md). It runs a persistent cognitive agent entirely on a POSIX filesystem with no external dependencies beyond a shell and an LLM backend.

## Suggested Reading Order

To understand FCP-Ref, we recommend reading the documentation in this order:

1.  **[QUICKSTART.md](QUICKSTART.md)** — Start here. Get the system running in 5 minutes with no prior knowledge.
2.  **[ARCHITECTURE.md](ARCHITECTURE.md)** — Learn how it works under the hood: the execution cycle, memory model, and drift detection.
3.  **[Formal Specifications](../README.md)** — Once you understand the implementation, dive into the normative HACA and FCP specs for the rigorous details.

---

## What it implements

## Structure

```
BOOT.md                   — CPE instruction manual (integrity-sealed)
FIRST_BOOT.md.example     — FAP template — copy to FIRST_BOOT.md on first deploy
sil.sh                    — Session Interface Layer (Transparent Mode adapter)
persona/                  — Agent identity (example — replace for your deployment)
  identity.md
  values.md
  constraints.md
skills/                   — Capability modules
  index.json              — RBAC registry + .command aliases
  memory_store/           — Append to session.jsonl
  memory_retrieve/        — Query memory fragments
  memory_swap_in/         — Promote archive → active_context
  snapshot_create/        — Create tar.gz point-in-time backup
  snapshot_list/          — List available snapshots
  summarize_session/      — Summarize and archive session log
  ws_create/              — Create sandboxed workspace
  recon_env/              — Emit environment diagnostic report
  owner_bind/             — First-boot operator binding (cold_start_only)
  cron_wake/              — External cron trigger (not CPE-invocable)
  sys_endure/             — Unified evolution protocol
  lib/                    — Shared libraries (acp, rotation, params, drift)
hooks/
  hook_dispatch.sh        — Lifecycle hook runner
  pre_memory_store/       — Validate ACP envelope before write
state/
  integrity.json          — SHA-256 registry of all sealed files
  drift-probes.jsonl      — Active behavioral consistency probes
  drift-pool.jsonl        — Probe rotation pool
  drift-config.json       — Drift threshold configuration
tools/
  rotate_probes.sh        — Rotate active probe set from pool
  calibrate_probes.sh     — Recalibrate probe embeddings
  calibrate_threshold.sh  — Calibrate drift detection threshold
```

## Identity is Operator Configuration

The `persona/` directory ships with a demonstration identity called **Agent-Zero**. Every file in it carries an explicit `<!-- EXAMPLE PERSONA -->` comment.

**Agent-Zero is not part of the FCP protocol.** It exists so the system runs out of the box and you have a concrete reference for how a well-formed persona looks. Before deploying in production, replace `identity.md`, `values.md`, and `constraints.md` with your own. The FAP (`FIRST_BOOT.md`) guides you through this.

The protocol only requires that `persona/` contains these three files and that they are cryptographically sealed in `state/integrity.json`. What they contain is entirely up to the operator.

---

## Running

### Transparent Mode — via shell (SIL adapter)

```bash
# First deployment
cp FIRST_BOOT.md.example FIRST_BOOT.md
# Edit FIRST_BOOT.md if needed, then:
./sil.sh

# Normal boot (after FAP completed and FIRST_BOOT.md deleted)
./sil.sh
```

### Opaque Mode — via prompt (no shell required)

If you are using an IDE assistant or agent with native filesystem tools — Claude Code, VS Code Copilot Chat, a web app with file access, or similar — you can boot the agent without running `sil.sh`. Just paste the following into the prompt:

```
execute BOOT.md
```

Or, on first deployment before the FAP has run:

```
execute FIRST_BOOT.md
```

The model reads `BOOT.md`, detects its native tools, and acts directly via tool calls — it is the adapter. No shell process, no `fcp-actions` parsing: the CPE executes intents natively.

## Configuration

| Environment variable | Default | Description |
|---------------------|---------|-------------|
| `FCP_REF_ROOT` | auto-detected | Absolute path to this directory |
| `CONTEXT_BUDGET` | `60000` | Max chars in CPE context |
| `SKIP_DRIFT` | unset | Set to `1` to skip Phase 5 |
| `PROBE_ROTATE_DAYS` | `30` | Days between probe pool rotations |
| `INTEGRITY_HASH` | unset | SHA-256 anchor for `state/integrity.json` |

## LLM Backend

Configure your backend in `skills/llm_backends/`. The SIL calls `skills/llm_query.sh` to invoke the CPE. See `skills/llm_backends/` for available adapters.
