# FCP-Ref — Architecture

This document explains how FCP-Ref works. It assumes you've read the [Quick Start](QUICKSTART.md) and want to understand the internals.

For the formal specifications, see [fcp-c-spec/](../fcp-c-spec/) and [HACA-Arch](../../spec/HACA-Arch-1.0.0.md).

---

## The core idea

Most AI agent frameworks separate the agent from its storage. FCP-Ref inverts this: **the filesystem is the agent**. There is no external database, no serialization format to worry about, no migration scripts. The directory is the system, in the same way that a Unix process's `/proc` entry is that process.

This has one profound consequence: the system is completely portable, inspectable, and recoverable using tools you already have — `cat`, `git`, `tar`.

---

## Execution cycle

Each run of FCP-Ref is one **cognitive cycle**:

```
┌─────────────────────────────────────────────────────┐
│                      sil.sh                          │
│                                                      │
│  Phase 0:  Confinement enforcement (unshare/namespace)
  Phase 0b: First Activation Protocol (FAP)
  Phase 1:  Crash recovery (repair incomplete writes)
  Phase 2:  Integrity check (SHA-256 all immutables)
  Phase 3:  RBAC resolution (skills/index.json)
  Phase 4:  Context Assembly (composition protocol)
  Phase 5:  Drift Probes (Unigram NCD Cascade)
  Phase 6:  Ignition (CPE invocation loop)
└─────────────────────────────────────────────────────┘
```

Between cycles, everything persists in the filesystem. The LLM receives no state from the previous cycle directly — it receives the assembled context, which *contains* that state.

## FCP Requirement Mapping

| FCP Requirement | Implementation |
|-----------------|----------------|
| Phase 0 — Host introspection | `sil.sh` → `state/env.md` |
| Phase 0b — First Activation Protocol | `FIRST_BOOT.md` injection + `skills/owner_bind/` |
| Phase 1 — Crash recovery | WAL + rotation repair in `sil.sh` |
| Phase 2 — Integrity validation | SHA-256 of 33 tracked files via `state/integrity.json` |
| Phase 3 — RBAC resolution | `skills/index.json` skill authorization |
| Phase 4 — Context assembly | `[PERSONA][BOOT][ENV][SKILLS][MEMORY][SESSION]` |
| Phase 5 — Drift probes | Two-Tier Cascade: NCD/gzip (Tier 1) → LLM Oracle (Tier 2) |
| Phase 6 — CPE ignition | Skill execution loop, intent envelope parsing |
| ACP envelopes | `skills/lib/acp.sh` — lockless spool/inbox writes |
| `.command` aliases | Resolved by SIL before CPE invocation |
| `sys_endure` evolution protocol | 9 subcommands — single gatekeeper for all mutations |

---

## Two execution modes

FCP-Ref adapts to the environment it finds itself in.

### Transparent Mode

The LLM is a remote API. `sil.sh` is the orchestrator:

```
sil.sh → assembles context → calls LLM API → parses fcp-actions → executes
```

The LLM emits a `fcp-actions` block in its response. `sil.sh` reads it and executes each line as a real system command.

### Opaque Mode

The LLM has direct filesystem access (Claude Code, Cursor, Copilot Workspace). The LLM is the orchestrator:

```
LLM reads BOOT.md → detects native tools → acts directly
```

No `sil.sh` needed. The LLM maps each intent to a native tool call (`Write`, `Bash`, etc.). It still emits `fcp-actions` blocks as an audit trace, but native tool calls are what execute.

Both modes preserve the same filesystem topology and HACA axioms. Only the orchestrating entity and the transport for Intent Envelopes differ. See FCP-RFC Section 2a for the normative mode definitions.

---

## Execution confinement

To satisfy HACA Axiom II without imposing deployment friction, FCP-Ref implements **Transparent Auto-Sandboxing** via Linux namespaces.

Instead of halting when deployed on an unconfined host, the SIL detects the confinement state and isolates itself dynamically — before any cognitive phase runs:

```
[Host Environment]
       |
       v
[sil.sh — Pre-Phase 0] → checks namespace confinement
       |
       +── (Confined: container / PID namespace) ──→ [Phase 0]
       |
       +── (Unconfined)
             |
             v
      [unshare -m -p -f -r --mount-proc]
      Creates private PID, mount, and user namespaces.
             |
             v
      [sil.sh re-executes inside namespace → Phase 0]
```

The tool used is `unshare` (part of `util-linux`, present on all Linux distributions). The flags create a rootless, isolated environment:

| Flag | Effect |
|------|--------|
| `-m` | Private mount namespace — host mounts invisible |
| `-p` | Private PID namespace — process tree isolated |
| `-f` | Fork before exec (required by `-p`) |
| `-r` | Map current UID to root inside namespace |
| `--mount-proc` | Fresh `/proc` for the new PID namespace |

If `unshare` is unavailable and the host is unconfined, the SIL aborts with a **Confinement Fault** — Axiom II cannot be satisfied.

---

## Context assembly

Before invoking the LLM, `sil.sh` assembles a structured context block in a fixed order:

```
--- [PERSONA] ---
identity.md, values.md, constraints.md

--- [BOOT PROTOCOL] ---
BOOT.md

--- [ENV] ---
state/env.md (OS, available binaries, context budget, execution mode)

--- [SKILLS INDEX] ---
skills/index.json (all aliases and authorized skills)

--- [SKILL:name] ---
Each authorized skill: SKILL.md + manifest.json

--- [MEMORY] ---
Symlinks in memory/active_context/, sorted by priority prefix

--- [SESSION] ---
Tail of memory/session.jsonl, newest-first, until context budget exhausted
```

The LLM sees a deterministic snapshot of the system's state. Nothing hidden, nothing ambient — only what's in the filesystem.

---

## Memory model

Memory has three layers:

### Active context (always loaded)
`memory/active_context/` contains symlinks to memory fragments. Every boot, all symlinks are resolved and their targets loaded into the `[MEMORY]` context block.

Symlinks are named with a numeric priority prefix: `10_self_analysis.md`, `50_project_notes.jsonl`. Lower number = higher priority = dropped last when context fills.

This is the system's "working memory" — the knowledge it carries into every session.

### Session log (recent history)
`memory/session.jsonl` is an append-only log in ACP envelope format. The tail is loaded into `[SESSION]` until the context budget is exhausted. Older entries are archived automatically.

### Archive (long-term storage)
`memory/archive/` contains rotated session logs. Not automatically loaded, but searchable with `.recall` and retrievable with `.swapin`.

---

## ACP envelopes

All structured writes to the session log and inbox use the **Atomic Chunked Protocol (ACP)** envelope format:

```json
{
  "actor": "fcp-ref",
  "gseq": 42,
  "tx": "uuid-...",
  "seq": 1,
  "eof": true,
  "type": "MSG",
  "ts": "2026-02-25T14:00:00Z",
  "data": "{\"event\": \"memory_stored\", \"content\": \"...\"}",
  "crc": "a1b2c3d4"
}
```

Key properties:
- `gseq` is monotonically increasing — enables ordering and gap detection
- `crc` is CRC-32 of the `data` field — detects accidental corruption
- `data` is always a JSON-serialized string — type-safe deserialization
- Files are append-only — no in-place modification, ever

---

## Skills

A skill is an executable capability. Skills live in `skills/<name>/` and contain:
- `manifest.json` — name, `.command` alias, parameters, sandbox declaration
- `<name>.sh` (or `.py`) — the implementation

The **RBAC registry** (`skills/index.json`) controls which skills the LLM can invoke. Skills not in the registry are never loaded. The registry also contains the `.command` alias map — a flat lookup table from shorthand to skill name.

When the operator types `.save "something"`, `sil.sh` looks up `.save` in the alias map, finds `memory_store`, builds a `skill_request` intent, and executes the skill directly — without involving the LLM.

---

## Integrity and immutability

`state/integrity.json` maps relative file paths to SHA-256 hashes:

```json
{
  "signatures": {
    "BOOT.md": "680ca9d...",
    "persona/identity.md": "2fb9a96...",
    "skills/index.json": "df42687..."
  }
}
```

During Phase 2 of every boot, `sil.sh` recomputes the hash of each listed file and compares it to the stored value. Any mismatch aborts boot. This means:

- The LLM cannot modify its own instruction manual
- The LLM cannot expand its own permissions
- The LLM cannot alter its own identity at runtime

Changes to immutable files require operator intervention and use the `sys_endure` protocol (`.endure`), which runs a full validation cycle before committing.

---

## Behavioral drift detection

FCP-Ref implements the **Identity Drift Invariant** (HACA-Core Axiom VIII) using a **Two-Tier Cascade** architecture (HACA-Core §4.5.3). This is a native, Living-off-the-Land approach with zero external dependencies.

### Tier 1 — Unigram NCD (Heuristic Sensor)

This tier is implemented in `skills/lib/drift.sh`. It computes the **Unigram Normalized Compression Distance (NCD)** using POSIX tools (`tr`, `sort`, `uniq`, `gzip`).

- **Logic**: It extracts the sorted unique word set (unigrams) from both the anchor and the current response before compression. This ensures the metric is sensitive to vocabulary shifts rather than length or repetition.
- **Formula**: See [HACA-Core §4.1](../../spec/HACA-Core-1.0.0.md) for the normative math.
- **Performance**: Near-zero CPU cost. Checks every boot.

### Tier 2 — Semantic Oracle (Deep Path)

If Tier 1 breaches the `warning_threshold`, `sil.sh` escalates to Tier 2. The reference implementation uses the actual LLM backend to compare the semantic meaning of the response against the probe's reference.

A `DRIFT_FAULT` is triggered if either tier confirms critical drift, putting the system into **Read-Only** mode to prevent the persistence of corrupted cognitive state.

---

## First activation

On a fresh clone, `FIRST_BOOT.md` is present in the root. The system detects this, skips drift probes (no baseline exists yet), and runs the **First Activation Protocol**:

1. Ask the operator for name, handle, timezone
2. Store the operator binding to `memory/preferences/operator.json`
3. Read all persona, skills, and integrity files
4. Create a self-knowledge document in `memory/concepts/`
5. Pin it to `memory/active_context/` at priority 10
6. Log the activation event to `memory/session.jsonl`
7. Delete `FIRST_BOOT.md`

After this, every subsequent boot loads the operator binding and self-knowledge automatically. The system wakes up knowing who it is and who its operator is.

---

## Formal specifications

FCP-Ref implements two formal specifications:

**[FCP (Filesystem Cognitive Platform)](../fcp-c-spec/)**
The concrete implementation spec. Defines the directory topology, ACP wire format, boot phases, memory paging, drift measurement, and skill invocation protocol.

**[HACA (Host-Agnostic Cognitive Architecture)](../../spec/HACA-Arch-1.0.0.md)**
The abstract architecture. Defines the eight compliance axioms, trust model, component topology, and the relationships between CPE, MIL, EL, and SIL. FCP is a conforming implementation of HACA-Core.

The specs are written in RFC style. They're dense — start with FCP if you want the concrete picture, start with HACA-Arch if you want the abstract model.
