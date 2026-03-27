---
title: "Filesystem Cognitive Platform (FCP)"
short_title: "FCP"
version: "1.0.0"
compliance: "HACA-Arch v1.0.0 / HACA-Core v1.0.0 / HACA-Evolve v1.0.0"
status: "Draft"
date: 2026-03-11
---

# Filesystem Cognitive Platform (FCP)

## Abstract

The Filesystem Cognitive Platform (FCP) is a concrete implementation specification for HACA-compliant entities. Where HACA-Arch, HACA-Core, and HACA-Evolve define architecture and behavioral contracts, FCP defines exact implementation: directory layout, file formats, protocol envelopes, boot sequence, and operational procedures — all built exclusively on POSIX filesystem primitives, requiring no external databases, message brokers, or runtime daemons.

This document assumes familiarity with HACA-Arch, HACA-Core, and HACA-Evolve. It does not restate their concepts — it operationalizes them. A reader who knows what a Sleep Cycle is will find here exactly how it runs: which files are written, in what order, under what conditions, and what constitutes a valid completion. The level of detail is intentional — FCP is meant to be implemented, not interpreted.

Where this document defines profile-specific behavior, sections are annotated **[HACA-Core]** or **[HACA-Evolve]**. Unmarked sections apply to both profiles.

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [Entity Layout](#2-entity-layout)
   - 2.1 [Directory Structure](#21-directory-structure)
   - 2.2 [File Format Conventions](#22-file-format-conventions)
3. [Core Formats](#3-core-formats)
   - 3.1 [ACP Envelope](#31-acp-envelope)
   - 3.2 [Structural Baseline](#32-structural-baseline)
   - 3.3 [Integrity Document](#33-integrity-document)
   - 3.4 [Operator Bound](#34-operator-bound)
   - 3.5 [Session Token](#35-session-token)
   - 3.6 [Working Memory](#36-working-memory)
   - 3.7 [Closure Payload](#37-closure-payload)
   - 3.8 [Semantic Digest](#38-semantic-digest)
   - 3.9 [Skill Index](#39-skill-index)
   - 3.10 [Skill Manifest](#310-skill-manifest)
   - 3.11 [Drift Probe](#311-drift-probe)
   - 3.12 [Integrity Chain Entry](#312-integrity-chain-entry)
   - 3.13 [Imprint Record](#313-imprint-record)
4. [First Activation Protocol](#4-first-activation-protocol)
5. [Boot Sequence](#5-boot-sequence)
   - 5.1 [Boot Manifest](#51-boot-manifest)
   - 5.2 [Crash Recovery](#52-crash-recovery)
   - 5.3 [Session Token Issuance](#53-session-token-issuance)
6. [Cognitive Session](#6-cognitive-session)
   - 6.1 [Context Assembly](#61-context-assembly)
   - 6.2 [Action Dispatch](#62-action-dispatch)
   - 6.3 [Cycle Chain](#63-cycle-chain)
   - 6.4 [Context Budget Tracking](#64-context-budget-tracking)
7. [Sleep Cycle](#7-sleep-cycle)
   - 7.1 [Stage 0 — Semantic Drift Detection](#71-stage-0--semantic-drift-detection)
   - 7.2 [Stage 1 — Memory Consolidation](#72-stage-1--memory-consolidation)
   - 7.3 [Stage 2 — Garbage Collection](#73-stage-2--garbage-collection)
   - 7.4 [Stage 3 — Endure Execution](#74-stage-3--endure-execution)
8. [Memory Layer](#8-memory-layer)
   - 8.1 [Session Store](#81-session-store)
   - 8.2 [Memory Store](#82-memory-store)
   - 8.3 [Pre-Session Buffer](#83-pre-session-buffer)
9. [Execution Layer](#9-execution-layer)
   - 9.1 [Skill Index](#91-skill-index)
   - 9.2 [Dispatch](#92-dispatch)
   - 9.3 [Action Ledger](#93-action-ledger)
   - 9.4 [Worker Skills](#94-worker-skills)
   - 9.5 [Native Exec Tools](#95-native-exec-tools)
   - 9.6 [Operator Skills](#96-operator-skills)
   - 9.7 [Lifecycle Hooks](#97-lifecycle-hooks)
   - 9.8 [Session Approval Model](#98-session-approval-model)
10. [Integrity Layer](#10-integrity-layer)
    - 10.1 [Structural Verification](#101-structural-verification)
    - 10.2 [Drift Detection](#102-drift-detection)
    - 10.3 [Heartbeat and Vital Check](#103-heartbeat-and-vital-check)
    - 10.4 [Watchdog](#104-watchdog)
    - 10.5 [Evolution Gate](#105-evolution-gate)
    - 10.6 [Operator Channel](#106-operator-channel)
    - 10.7 [Passive Distress Beacon](#107-passive-distress-beacon)
    - 10.8 [Critical Condition Resolution](#108-critical-condition-resolution)
11. [Decommission](#11-decommission)
12. [Operator Interface](#12-operator-interface)
   - 12.1 [Session Invocation](#121-session-invocation)
   - 12.2 [Interactive Loop](#122-interactive-loop)
   - 12.3 [Slash Commands](#123-slash-commands)
     - 12.3.1 [Platform Commands](#1231-platform-commands)
     - 12.3.2 [Skill Aliases](#1232-skill-aliases)
   - 12.4 [Notifications](#124-notifications)
13. [Compliance](#13-compliance)

---

## 1. Introduction

The Filesystem Cognitive Platform is built on a single premise: everything the entity needs to operate — identity, memory, skills, integrity state — lives in a directory. No external databases, message brokers, or runtime infrastructure. The host provides a POSIX filesystem and a language model inference endpoint; the entity provides the rest.

This approach is called Living off the Land. Rather than introducing infrastructure dependencies, FCP maps every architectural requirement to primitives the host already provides: files for state, directories for organization, atomic rename for consistency, append-only writes for audit trails. An FCP entity is portable by construction — moving the directory to a different host, pointed at any compatible inference endpoint, restores the entity to its last verified state.

HACA-Arch defines five components and their contracts — it does not define how they are orchestrated. FCP fills that gap. The FCP process is the cognitive cycle orchestrator: it drives the session loop, assembles context, invokes the CPE, parses its output, and dispatches to the appropriate component. The five HACA components operate under FCP's coordination. The SIL is not the orchestrator — its role is specifically the integrity layer: structural verification, drift detection, heartbeat, and evolution gate.

FCP is a platform, not a profile. It defines the filesystem conventions, wire formats, and operational procedures that any HACA-compliant entity can be built on. The active Cognitive Profile determines how those conventions are applied. The platform layer — directory layout, file formats, ACP protocol, boot and sleep procedures — is shared across all profiles. The profile layer — topology guarantees, evolution authorization, CMI policy — is what differentiates them. This document covers both supported profiles: **HACA-Core** (zero-autonomy, Transparent topology, operator-gated evolution) and **HACA-Evolve** (supervised-autonomy, Adaptive topology, scope-based evolution).

---

## 2. Entity Layout

An FCP entity is a single directory. Its location on the host filesystem is the entity root. All paths in this document are relative to that root.

### 2.1 Directory Structure

```
<entity-root>/
├── boot.md                     — boot protocol (CPE instruction document)
├── persona/                    — structural identity files
├── skills/
│   ├── index.json              — skill index
│   └── <name>/
│       ├── manifest.json       — skill manifest
│       └── ...                 — skill executables
├── hooks/                      — lifecycle hook executables
├── io/
│   ├── inbox/                  — async stimuli queue for CPE
│   │   └── presession/         — stimuli received without active session
│   └── spool/                  — flat staging area; components write unique-named files here before atomic rename into io/inbox/
├── memory/                     — MIL exclusive write territory
│   ├── imprint.json            — imprint record (written once at FAP, never modified)
│   ├── episodic/               — archived session fragments
│   ├── semantic/               — semantic graph (concept nodes and links)
│   ├── active-context/         — working memory symlinks
│   ├── session.jsonl           — session store (cognitive record)
│   ├── working-memory.json     — working memory pointer map
│   └── session-handoff.json    — session handoff record
└── state/
    ├── baseline.json           — structural baseline
    ├── integrity.json          — integrity document
    ├── integrity.log           — integrity log (append-only)
    ├── integrity-chain.jsonl   — endure commit chain (append-only)
    ├── drift-probes.jsonl      — semantic probes
    ├── semantic-digest.json    — semantic digest
    ├── workspace-focus.json    — active workspace project path (operational; not tracked by Integrity Document)
    ├── pending-closure.json    — closure payload staging (present only between session close and Stage 1 completion)
    ├── sentinels/              — runtime sentinels
    │   └── session.token       — session token (present = active or crashed session)
    ├── snapshots/              — pre-mutation snapshots for crash recovery (present only during Stage 3 execution)
    ├── operator-notifications/ — operator channel output
    └── distress.beacon         — passive distress beacon
```

The `persona/`, `skills/`, and `hooks/` directories contain structural content — covered by the Integrity Document, changed only via Endure. The `io/` directory is the CPE's async stimulus queue — any component writes here when a result is relevant to cognition; FCP drains it at the start of each cycle. The `memory/` directory is MIL-exclusive write territory; `imprint.json` is the exception — written once by the MIL during FAP and never modified thereafter. The `state/` directory is SIL territory: structural (`baseline.json`, `integrity.json`, `integrity-chain.jsonl`), integrity-exclusive (`integrity.log`, `distress.beacon`), and operational (`sentinels/`, `operator-notifications/`, `workspace-focus.json`, `pending-closure.json`).

Skill staging lives outside the entity root at `/tmp/fcp-stage/<entity_id>/` — skill cartridges assembled by `skill_create` land here before being promoted to `skills/` via Endure. This path is outside the Endure scope and not tracked by the Integrity Document.

### 2.2 File Format Conventions

FCP uses four file formats, each with a distinct semantic:

**`.md`** — Markdown. Used for narrative content: persona definitions, boot protocol, skill documentation. These files are human-readable by design. Within FCP, `.md` files are structural — they are written once via Endure and not modified at runtime.

**`.json`** — JSON object. Used for structured, low-mutation content: configuration, manifests, pointer maps, integrity artefacts. Every write to a `.json` file must be atomic: write to a `.tmp` sibling, then rename into place. Direct in-place writes are not permitted.

**`.jsonl`** — Newline-delimited JSON. Used for append-only content: session store, integrity log, integrity chain. Each line is a complete, self-contained JSON object. Existing lines are never modified or deleted. Truncation or compaction of a `.jsonl` file is only permitted when explicitly authorized by the active procedure (session summarization, Sleep Cycle archival).

**`.msg`** — ACP envelope file. Used for inter-component messaging: each file in `io/inbox/` and `io/inbox/presession/` is a single JSON object representing one ACP envelope. `.msg` files are written atomically via the spool-then-rename pattern defined in the ACP protocol, and are consumed — read then deleted — by FCP during inbox drain. Unlike `.jsonl`, they are not append-only and do not accumulate; their lifecycle ends at consumption.

---

## 3. Core Formats

This section defines the exact structure of every named artefact in the Entity Store. Implementations must produce and consume these formats exactly.

### 3.1 ACP Envelope

The ACP (Atomic Chunked Protocol) envelope is the inter-component communication format in FCP. It is used in three contexts: as `.msg` files in `io/inbox/` for asynchronous delivery; as lines in `memory/session.jsonl` for session records; and as lines in `state/integrity.log` for integrity records.

```json
{
  "actor": "sil",
  "gseq":  1042,
  "tx":    "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "seq":   1,
  "eof":   true,
  "type":  "HEARTBEAT",
  "ts":    "2026-03-11T14:00:00Z",
  "data":  "...",
  "crc":   "a1b2c3d4"
}
```

| Field | Type | Description |
|---|---|---|
| `actor` | string | Component that produced this envelope: `fcp`, `sil`, `mil`, `cpe`, `exec`, `operator` |
| `gseq` | integer | Monotonically increasing counter, per actor, per session; starts at 1 and increments with each envelope produced |
| `tx` | string | Transaction UUID; ties multi-chunk envelopes together |
| `seq` | integer | Position within the transaction (1-indexed) |
| `eof` | boolean | `true` if this is the last envelope in the transaction |
| `type` | string | Envelope type (see table below) |
| `ts` | string | ISO 8601 UTC timestamp |
| `data` | string | UTF-8 payload; structured payloads are JSON-serialized into this field |
| `crc` | string | CRC-32/ISO-HDLC of `data` (polynomial 0xEDB88320, init 0xFFFFFFFF, final XOR 0xFFFFFFFF), 8-character lowercase hex |

**Size limit.** No single ACP envelope may exceed 4000 bytes. Larger payloads must be chunked across multiple envelopes sharing the same `tx`, with incrementing `seq` and `eof: true` on the final chunk.

**Chunk reassembly.** A multi-chunk transaction is complete when an envelope with `eof: true` for that `tx` has been received and all `seq` values from `1` through the final envelope's `seq` are present. The reconstructed payload is the concatenation of `data` fields in ascending `seq` order. Incomplete transactions are held across consecutive inbox drain cycles; if a transaction remains incomplete after `fault.n_retry` consecutive drain cycles, it is discarded and logged to `state/integrity.log`. A single-envelope transaction (`seq: 1`, `eof: true`) requires no reassembly.

**Envelope types:**

| Type | Producer | Description |
|---|---|---|
| `MSG` | CPE, Operator | General narrative message |
| `SKILL_REQUEST` | CPE | Intent to invoke a skill |
| `SKILL_RESULT` | EXEC | Successful skill output |
| `SKILL_ERROR` | EXEC | Skill failure |
| `SKILL_TIMEOUT` | SIL | Skill exceeded watchdog threshold |
| `HEARTBEAT` | SIL | Vital Check record |
| `DRIFT_FAULT` | SIL | Semantic Drift Critical condition |
| `IDENTITY_DRIFT` | SIL | Identity Drift Critical condition detected during Heartbeat Vital Check; a structural file hash does not match the Integrity Document |
| `EVOLUTION_PROPOSAL` | SIL | Evolution Proposal forwarded to Operator |
| `EVOLUTION_AUTH` | SIL | Operator approval of an Evolution Proposal |
| `EVOLUTION_REJECTED` | SIL | Operator rejection of an Evolution Proposal |
| `PROPOSAL_PENDING` | SIL | Evolution Proposal persisted across session close |
| `ENDURE_COMMIT` | SIL | Structural write completed during Stage 3 |
| `SEVERANCE_COMMIT` | SIL | Skill removed from Skill Index as a maintenance operation; carries the removed skill name, reason, and updated `skills/index.json` hash |
| `SEVERANCE_PENDING` | SIL | `SEVERANCE_COMMIT` unacknowledged at session close (normal or forced); escalates to a Critical condition at session close; written to `state/integrity.log`; presented at Phase 6 of every subsequent boot as a Critical condition until resolved |
| `SLEEP_COMPLETE` | SIL | Authoritative Sleep Cycle completion record |
| `ACTION_LEDGER` | FCP | Write-ahead entry for irreversible skill execution |
| `SIL_UNRESPONSIVE` | EXEC, MIL | Watchdog escalation bypassing SIL |
| `CTX_SKIP` | FCP | Context entry dropped (absent Working Memory target or budget exhaustion) |
| `CRITICAL_CLEARED` | SIL | Operator-acknowledged resolution of a Critical condition |
| `DECOMMISSION` | FCP | Decommission instruction injected at session start |
| `MEMORY_RESULT` | MIL | Result of a `memory_recall` action; `data` is a JSON object: `{"query": "...", "paths": ["memory/semantic/...", "memory/episodic/..."], "status": "found|not_found"}` |

**The `io/` path.** The `io/inbox/` directory is used exclusively for asynchronous delivery — when a component cannot respond within the current cognitive cycle, or when an external stimulus arrives outside an active session. Components write to the flat `io/spool/` staging directory, using unique filenames, and rename atomically into `io/inbox/`. FCP drains the inbox at the start of each cycle. The synchronous cognitive chain — CPE output dispatched and resolved within a single cycle — does not pass through `io/`.

### 3.2 Structural Baseline

`state/baseline.json` declares all operational parameters for the entity. It is part of the structural baseline, covered by the Integrity Document, and cannot be modified outside the Endure Protocol. All fields below are required — none may be absent or null. **[HACA-Evolve]** must additionally include an `authorization_scope` object as defined in HACA-Evolve §4.2; its structure is outside the scope of this document.

```json
{
  "version": "1.0",
  "entity_id": "...",
  "cpe": {
    "topology": "transparent",
    "backend": "..."
  },
  "heartbeat": {
    "cycle_threshold": 10,
    "interval_seconds": 300
  },
  "watchdog": {
    "sil_threshold_seconds": 300
  },
  "context_window": {
    "budget_tokens": 200000,
    "critical_pct": 85
  },
  "drift": {
    "comparison_mechanism": "ncd-gzip-v1",
    "threshold": 0.15
  },
  "session_store": {
    "rotation_threshold_bytes": 2097152
  },
  "working_memory": {
    "max_entries": 20
  },
  "integrity_chain": {
    "checkpoint_interval": 10
  },
  "pre_session_buffer": {
    "max_entries": 50
  },
  "operator_channel": {
    "notifications_dir": "state/operator-notifications/"
  },
  "fault": {
    "n_boot": 3,
    "n_channel": 3,
    "n_retry": 3
  }
}
```

**[HACA-Core]** `cpe.topology` must be `"transparent"` — any other value causes boot abort with no session token issued. **[HACA-Evolve]** `cpe.topology` may be `"transparent"` or `"opaque"`; the declared value is covered by the Integrity Document and cannot change after Imprint. `cpe.backend` identifies the model or endpoint used for CPE invocations; its format is `"<provider>:<model-identifier>"` — e.g., `"anthropic:claude-opus-4-6"`, `"openai:gpt-4o"`, `"google:gemini-2.0-flash"`, `"ollama:llama3.2"`. The special value `"auto"` requests model auto-detection from the configured provider. `cpe.backend` can be updated by the Operator via `/model <name>` — a direct structural modification that bypasses the Endure Protocol; the change is recorded as a `MODEL_CHANGE` integrity chain entry.

### 3.3 Integrity Document

`state/integrity.json` maps every tracked structural file to its SHA-256 hash. Written by the SIL during FAP and updated atomically at each Endure commit. The root hash of this document anchors the Integrity Chain.

```json
{
  "version": "1.0",
  "algorithm": "sha256",
  "last_checkpoint": {
    "seq": 12,
    "digest": "sha256:4d2a3581f3b5f6c9..."
  },
  "files": {
    "boot.md": "8d969eef6ecad3c29a3a...",
    "persona/identity.md": "e3b0c44298fc1c149afb...",
    "persona/values.md": "a665a45920422f9d417e...",
    "persona/constraints.md": "2cf24dba5fb0a30e26e8...",
    "skills/index.json": "1f40fc92da241694750a...",
    "skills/memory_store/manifest.json": "da39a3ee5e6b4b0d325b...",
    "hooks/pre_session/01_check.sh": "b94f6f125c79e3a5feea...",
    "state/baseline.json": "5994471abb01112afcc1..."
  }
}
```

Tracked files are: `boot.md`, all files in `persona/`, `skills/index.json`, all skill `manifest.json` files, all files in `hooks/`, and `state/baseline.json`. A file present in any of these paths but absent from `files` is treated as an unauthorized addition and causes boot abort.

`last_checkpoint` records the sequence number and digest of the most recent checkpoint entry in `state/integrity-chain.jsonl`. It is `null` before the first checkpoint is produced. At boot, the SIL reads this field to locate the verified anchor in the chain, enabling re-verification without traversing from genesis.

### 3.4 Operator Bound

The Operator Bound is not a standalone file. It is a sub-object within the Imprint Record (`memory/imprint.json`), established during FAP and immutable thereafter. FCP reads the Operator Bound from the Imprint Record at every boot.

```json
{
  "name": "...",
  "email": "...",
  "operator_hash": "sha256:..."
}
```

`operator_hash` is a deterministic SHA-256 digest of the identifying fields (`name` + `email`), computed during FAP Operator enrollment. It serves as the stable cryptographic identity of the Operator.

### 3.5 Session Token

`state/sentinels/session.token` is written by the SIL at the end of the boot sequence, immediately before the first Cognitive Cycle. The SIL has exclusive authority over the session token lifecycle: it issues, revokes, and removes the token. No other component may write to or delete this artefact, except FCP acting on an explicit Operator instruction (e.g., during decommission).

```json
{
  "session_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "issued_at": "2026-03-11T14:00:00Z"
}
```

At session close, before the Sleep Cycle begins, the SIL rewrites the token artefact atomically, adding `revoked_at`:

```json
{
  "session_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "issued_at": "2026-03-11T14:00:00Z",
  "revoked_at": "2026-03-11T16:32:00Z"
}
```

The artefact remains in place throughout the Sleep Cycle. It is removed — not revoked, removed — only after the `SLEEP_COMPLETE` record is written to the Integrity Log. Its presence at boot is the primary crash indicator.

Senders that route stimuli to the entity use the session token state to determine the correct inbox: a token present without `revoked_at` indicates an active session — stimuli go to `io/inbox/`. A token with `revoked_at`, or no token at all, indicates no active session — stimuli go to `io/inbox/presession/`. FCP enforces this routing for Operator input and schedule triggers; CMI-layer senders are required to implement the same check.

### 3.6 Working Memory

`memory/working-memory.json` is a pointer map written by the MIL at Sleep Cycle Stage 1. It declares the Memory Store artefacts the CPE considers relevant to the next session, in priority order. FCP loads it at boot to seed `memory/active-context/`.

```json
{
  "version": "1.0",
  "entries": [
    {"priority": 10, "path": "memory/episodic/2026-01/session-1234.jsonl"},
    {"priority": 20, "path": "memory/semantic/architecture-decisions.md"},
    {"priority": 90, "path": "memory/session-handoff.json"}
  ]
}
```

Entries are sorted ascending by `priority` — lower value means higher priority (loaded first, dropped last when context budget is exhausted). The number of entries is bounded by `working_memory.max_entries` in the structural baseline. FCP validates each declared path at boot; artefacts absent from the Memory Store are dropped and the drop is logged to the Integrity Log.

### 3.7 Closure Payload

The Closure Payload is the structured output produced by the CPE in the last Cognitive Cycle of a session. It is emitted as an `fcp_mil` tool_use call and must conform to the following schema:

```json
{
  "type": "closure_payload",
  "consolidation": "...",
  "promotion": [
    "regras-de-react",
    "preferencia-cores"
  ],
  "working_memory": [
    {"priority": 10, "path": "memory/episodic/2026-01/session-1234.jsonl"},
    {"priority": 90, "path": "memory/session-handoff.json"}
  ],
  "session_handoff": {
    "pending_tasks": ["..."],
    "next_steps": "..."
  }
}
```

| Field | Type | Description |
|---|---|---|
| `type` | string | Must be `"closure_payload"` |
| `consolidation` | string | Semantic summary of the session: insights, decisions, and knowledge worth carrying forward |
| `promotion` | array | List of episodic memory slugs to be promoted to the semantic knowledge base. FCP queues these as an Evolution Proposal for Stage 3 processing |
| `working_memory` | array | Ordered list of Memory Store artefact paths declared relevant to the next session; bounded by `working_memory.max_entries` |
| `working_memory[].priority` | integer | Load priority — lower value means higher priority; must be a positive integer (minimum 1) |
| `working_memory[].path` | string | Path relative to entity root; must resolve to an existing Memory Store artefact |
| `session_handoff` | object | Prospective record of pending tasks and next steps |
| `session_handoff.pending_tasks` | array | List of unfinished tasks to surface at the next session; no separate size constraint — bounded by the CPE response context window |
| `session_handoff.next_steps` | string | Narrative description of recommended next actions |

The `memory/session-handoff.json` path must always be included in `working_memory` — it is never absent from the next session's active context. How the MIL processes each field is defined in §7.2.

### 3.8 Semantic Digest

`state/semantic-digest.json` is a rolling aggregate of Semantic Drift scores across Sleep Cycles, maintained by the SIL. Updated at the end of each Stage 0 run.

```json
{
  "version": "1.0",
  "last_updated": "2026-03-11T16:32:00Z",
  "cycles_evaluated": 14,
  "probes": {
    "probe-001": {"last_score": 0.04, "mean_score": 0.03, "max_score": 0.07},
    "probe-002": {"last_score": 0.09, "mean_score": 0.06, "max_score": 0.11}
  }
}
```

Stage 0 checks both the current cycle's per-probe scores and the aggregate trend in the digest against the drift threshold declared in the structural baseline. Either can trigger a `DRIFT_FAULT`.

**Single-cycle breach:** `last_score > drift.threshold` for any probe triggers a `DRIFT_FAULT` immediately.

**Aggregate trend breach:** `mean_score > drift.threshold` for any probe triggers a `DRIFT_FAULT`, even if no individual cycle exceeded the threshold. This catches sustained low-level drift that accumulates across sessions.

**`mean_score` computation:** running average over all `cycles_evaluated` — updated after each Stage 0 run as `mean_score = (mean_score × (cycles_evaluated − 1) + new_score) / cycles_evaluated`. `cycles_evaluated` is incremented before the update. The initial value before the first Stage 0 run is `0.0`.

### 3.9 Skill Index

`skills/index.json` is the authoritative registry of skills the entity is authorized to use. It is written by the SIL during FAP Step 1 and updated exclusively via Endure (or via maintenance operation for `SEVERANCE_COMMIT`).

```json
{
  "version": "1.0",
  "skills": [
    {
      "name": "memory_store",
      "desc": "Retrieves and stores concepts in the semantic graph",
      "manifest": "skills/memory_store/manifest.json",
      "class": "custom"
    },
    {
      "name": "endure_invoke",
      "desc": "Triggers the Endure Protocol",
      "manifest": "skills/endure_invoke/manifest.json",
      "class": "operator"
    }
  ],
  "aliases": {
    "/snapshot": {"skill": "snapshot_create"}
  }
}
```

| Field | Type | Description |
|---|---|---|
| `version` | string | Schema version; must be `"1.0"` |
| `skills[]` | array | All skills the entity is authorized to invoke |
| `skills[].name` | string | Skill name; must match the directory name under `skills/` and the `name` field in its `manifest.json` |
| `skills[].desc` | string | Brief human-readable description of the skill's purpose; included in the `[SKILLS INDEX]` context block for `"custom"` skills; `"operator"` skills are excluded |
| `skills[].manifest` | string | Path to the skill's `manifest.json`, relative to entity root |
| `skills[].class` | string | `"custom"` for skills installed via Endure (executables in `skills/<name>/`); `"operator"` for system-control skills invokable exclusively by the Operator Channel (executables in `skills/<name>/`); `"custom"` skills are included in the `[SKILLS INDEX]` context block; `"operator"` skills are excluded |
| `aliases` | object | Map from slash command string (with leading `/`) to alias record; defines the alias dispatch table used by §12.3.2 |
| `aliases[key].skill` | string | Target skill name; must reference a name present in `skills[]` |
| `aliases[key].operator_only` | boolean | If `true`, this alias is rejected when issued from any source other than the interactive terminal prompt; default `false` |

### 3.10 Skill Manifest

Each skill's `manifest.json`, located at `skills/<name>/manifest.json`, declares the skill's identity and execution constraints. The SIL validates this file at boot during Skill Index construction; a skill that fails validation is excluded from `skills/index.json`.

```json
{
  "name": "memory_store",
  "class": "custom",
  "version": "1.0.0",
  "description": "...",
  "timeout_seconds": 30,
  "background": false,
  "ttl_seconds": null,
  "permissions": [],
  "dependencies": []
}
```

| Field | Type | Description |
|---|---|---|
| `name` | string | Skill name; must match the skill's directory name and its entry in `skills/index.json` |
| `class` | string | `"custom"` for skills installed via Endure; `"operator"` for system-control skills invokable exclusively by the Operator Channel; the SIL copies this value into `skills/index.json` when building the Skill Index |
| `version` | string | Semver string |
| `description` | string | Human-readable description of the skill's purpose |
| `timeout_seconds` | integer | Execution timeout in seconds; monitored by the SIL skill timeout watchdog (§10.4) |
| `background` | boolean | If `true`, the skill executes asynchronously and declares a TTL; background skills return their result through `io/inbox/` after the dispatching cycle ends |
| `ttl_seconds` | integer or null | Required when `background: true`; the SIL treats TTL expiry without a registered result as an incomplete execution and logs it to `state/integrity.log`; must be absent or `null` when `background: false` |
| `permissions` | array | List of permission tokens the skill requires; validated by the SIL at boot; permission token semantics are implementation-defined |
| `dependencies` | array | List of skill names or host capabilities required; the SIL validates availability at boot; a skill with unmet dependencies is excluded from `skills/index.json` |

### 3.11 Drift Probe

Each line in `state/drift-probes.jsonl` is a probe record. Probes are structural content — written only via Endure. Stage 0 of the Sleep Cycle executes all probes in declaration order.

```json
{
  "id": "probe-001",
  "description": "...",
  "target": "memory/semantic/architecture-decisions.md",
  "deterministic": {
    "type": "hash",
    "value": "sha256:..."
  },
  "reference": "..."
}
```

| Field | Type | Description |
|---|---|---|
| `id` | string | Unique probe identifier; referenced in `DRIFT_FAULT` envelopes and per-probe records in `state/semantic-digest.json` |
| `description` | string | Human-readable description of the behavioral property this probe monitors |
| `target` | string | Path to the Memory Store artefact to evaluate; relative to entity root; must resolve within `memory/` |
| `deterministic` | object or null | Deterministic layer configuration; if present, this layer executes and its result is always conclusive — the probabilistic layer is skipped |
| `deterministic.type` | string | Check type: `"hash"` (SHA-256 of target content vs. `value`), `"string"` (literal substring presence), or `"pattern"` (regex match against target content using RE2 syntax — O(n) guaranteed, no backtracking) |
| `deterministic.value` | string | The hash, string, or pattern to check against |
| `reference` | string or null | Reference text used by the probabilistic NCD layer; if present and `deterministic` is absent, the probabilistic layer executes; if both are absent, the probe is malformed |

A probe with both `deterministic` and `reference` absent is malformed; the SIL appends a `DRIFT_FAULT` ACP envelope to `state/integrity.log` identifying the `probe_id` and the reason (`"malformed: both deterministic and reference absent"`), then skips the probe. No `DRIFT_FAULT` is sent to `io/inbox/` and no Critical condition is raised — the entry is informational.

If the probe's `target` file is absent from the Memory Store, the SIL logs the absence to `state/integrity.log` and skips the probe without triggering a `DRIFT_FAULT`. Missing probe targets are an operational artefact, not a structural violation.

**Implementation Note:** The SIL operates exclusively on absolute or relative physical paths in the Entity Store. Though the CPE references knowledge in `memory/semantic/` abstractly via topic slugs, the Operator must configure the probe's `target` to point to the exact structural artefact mapping to that slug within the active profile's MIL implementation (e.g., `memory/semantic/<slug>.md`).

### 3.12 Integrity Chain Entry

Each line in `state/integrity-chain.jsonl` is a chain entry. Four entry types exist.

**Genesis entry** — written at FAP Step 7; seq 0; the entity's permanent identity anchor:

```json
{
  "seq": 0,
  "type": "genesis",
  "ts": "2026-03-11T14:00:00Z",
  "imprint_hash": "sha256:...",
  "prev_hash": null
}
```

**ENDURE_COMMIT** — written at Stage 3 Step 6 for each approved Evolution Proposal:

```json
{
  "seq": 12,
  "type": "ENDURE_COMMIT",
  "ts": "2026-03-11T16:32:00Z",
  "evolution_auth_digest": "sha256:...",
  "files": {
    "persona/identity.md": "sha256:..."
  },
  "integrity_doc_hash": "sha256:...",
  "prev_hash": "sha256:..."
}
```

**SEVERANCE_COMMIT** — written at maintenance skill removal; no `EVOLUTION_AUTH` required:

```json
{
  "seq": 5,
  "type": "SEVERANCE_COMMIT",
  "ts": "2026-03-11T16:00:00Z",
  "skill_removed": "old_skill",
  "reason": "manifest malformed",
  "files": {
    "skills/index.json": "sha256:..."
  },
  "integrity_doc_hash": "sha256:...",
  "prev_hash": "sha256:..."
}
```

**MODEL_CHANGE** — written when the Operator updates `cpe.backend` via `/model <name>`; no `EVOLUTION_AUTH` required:

```json
{
  "seq": 8,
  "type": "MODEL_CHANGE",
  "ts": "2026-03-11T17:00:00Z",
  "from": "claude-sonnet-4-6",
  "to": "claude-opus-4-6",
  "files": {
    "state/baseline.json": "sha256:..."
  },
  "integrity_doc_hash": "sha256:...",
  "prev_hash": "sha256:..."
}
```

| Field | Type | Applicable | Description |
|---|---|---|---|
| `seq` | integer | all | Monotonically increasing; `0` for genesis; `1`-indexed for all subsequent entries |
| `type` | string | all | Entry type: `"genesis"`, `"ENDURE_COMMIT"`, `"SEVERANCE_COMMIT"`, or `"MODEL_CHANGE"` |
| `ts` | string | all | ISO 8601 UTC timestamp |
| `imprint_hash` | string | genesis | SHA-256 of the finalized Imprint Record; the Genesis Omega value |
| `evolution_auth_digest` | string | ENDURE_COMMIT | SHA-256 of the `EVOLUTION_AUTH` ACP envelope that authorized this commit; used by Evolutionary Drift detection (§10.2) |
| `skill_removed` | string | SEVERANCE_COMMIT | Name of the removed skill |
| `reason` | string | SEVERANCE_COMMIT | Human-readable reason for removal |
| `from` | string | MODEL_CHANGE | Previous `cpe.backend` value |
| `to` | string | MODEL_CHANGE | New `cpe.backend` value |
| `files` | object | ENDURE_COMMIT, SEVERANCE_COMMIT, MODEL_CHANGE | Map of modified tracked file paths (relative to entity root) to their SHA-256 hashes after the write |
| `integrity_doc_hash` | string | ENDURE_COMMIT, SEVERANCE_COMMIT, MODEL_CHANGE | SHA-256 of `state/integrity.json` as written atomically during this commit; this is the verifiable anchor for checkpoint entries |
| `prev_hash` | string or null | all | SHA-256 of the previous entry's complete JSON line as stored in the file (excluding the trailing newline); `null` for genesis |

**Chain validation.** Each entry's `prev_hash` must equal the SHA-256 of the previous entry line as written. Phase 3 Step 1 reads `last_checkpoint` from `state/integrity.json`, locates the entry at that `seq`, verifies its SHA-256 matches the recorded digest, then validates `prev_hash` continuity forward. If `last_checkpoint` is `null`, validation starts from seq 0. Evolutionary Drift detection (§10.2) additionally verifies that every `ENDURE_COMMIT` — but not `SEVERANCE_COMMIT` or `MODEL_CHANGE` — carries a valid `evolution_auth_digest`.

**Checkpoint identification.** Checkpoint entries carry no dedicated field — they are identified solely by their `seq` matching `last_checkpoint.seq` in `state/integrity.json`. The verifiable anchor is `integrity_doc_hash`, not a flag in the chain entry itself.

### 3.13 Imprint Record

`memory/imprint.json` is the entity's birth certificate — written atomically by the MIL at FAP Step 6 and never modified thereafter. Genesis Omega, the entity's permanent identity anchor, is the SHA-256 digest of this file.

```json
{
  "version": "1.0",
  "activated_at": "2026-03-11T14:00:00Z",
  "haca_arch_version": "1.0.0",
  "haca_profile": "HACA-Core-1.0.0",    // or "HACA-Evolve-1.0.0"
  "operator_bound": {
    "operator_name": "...",
    "operator_email": "...",
    "operator_hash": "sha256:..."
  },
  "structural_baseline": "sha256:...",
  "integrity_document": "sha256:...",
  "skills_index": "sha256:..."
}
```

| Field | Type | Description |
|---|---|---|
| `version` | string | Schema version; always `"1.0"` |
| `activated_at` | string | ISO 8601 UTC timestamp of FAP completion |
| `haca_arch_version` | string | HACA-Arch version under which the entity was initialized |
| `haca_profile` | string | HACA profile under which the entity was initialized (e.g., `"HACA-Core-1.0.0"`) |
| `operator_bound` | object | Operator Bound sub-object as defined in §3.4 |
| `structural_baseline` | string | SHA-256 of `state/baseline.json` at activation |
| `integrity_document` | string | SHA-256 of `state/integrity.json` at activation |
| `skills_index` | string | SHA-256 of `skills/index.json` at activation |

The `structural_baseline`, `integrity_document`, and `skills_index` fields capture the entity's authorized configuration at birth. They are not updated as the entity evolves — they record the initial state from which Genesis Omega is derived.

---

## 4. First Activation Protocol


The First Activation Protocol (FAP) executes once, on cold-start — the first boot of a newly installed entity. It transforms a pre-installed structural baseline into a live entity with a verified identity, a bound Operator, and a cryptographic genesis anchor. All subsequent boots follow the Boot Sequence in §5.

**Cold-start detection.** The definitive cold-start indicator is the absence of `memory/imprint.json`. If the Imprint Record does not exist, FAP must execute before any Boot Sequence proceeds.

**FAP is not a Cognitive Cycle.** No session token exists at this stage. The CPE is not invoked. FAP is a gated sequential pipeline executed directly by FCP, with synchronous Operator interaction for enrollment.

**FAP pipeline:**

```
structural validation
  → host environment capture
  → Operator Channel initialization
  → Operator enrollment
  → Integrity Document generated
  → Imprint Record finalized and written to Memory Store
  → Genesis Omega derived
  → first session token issued
```

**Steps:**

1. **Structural validation** — The SIL verifies that the pre-installed structural baseline is internally consistent: `boot.md` is present, all `persona/` files exist and are well-formed, `state/baseline.json` is present and complete. The SIL validates every skill manifest in `skills/` and writes `skills/index.json` containing only skills with well-formed manifests and present executables.

2. **Host environment capture** — The SIL verifies the declared CPE topology and that the execution boundary is enforceable. **[HACA-Core]** topology must be `transparent`; Opaque topology causes FAP abort. **[HACA-Evolve]** both `transparent` and `opaque` are valid; the SIL records the declared topology in the Imprint Record. Identical to Phase 1 of the Boot Sequence (§5).

3. **Operator Channel initialization** — FCP verifies that `state/operator-notifications/` is writable and that the terminal prompt is available. The verification result is logged to `state/integrity.log`. If either mechanism is unavailable, FAP aborts.

4. **Operator enrollment** — FCP conducts the interaction with the Operator and collects name and email address. The SIL computes the `operator_hash` as the SHA-256 digest of the UTF-8 string `"<operator_name>\n<operator_email>"` — the name, a single newline character, then the email address, with no trailing newline. The Operator Bound is held in memory — it is not written until Step 6. **[HACA-Evolve]** FCP additionally collects the Operator-defined authorization scope declaration and writes it to `state/baseline.json` as `authorization_scope` before Step 5 executes.

5. **Integrity Document generated** — The SIL computes SHA-256 hashes of all tracked structural files and writes `state/integrity.json` atomically.

6. **Imprint Record finalized** — The MIL writes `memory/imprint.json` atomically. The Imprint Record contains: entity identity, Operator Bound (including `operator_hash`), references to the structural baseline, the Integrity Document, a reference to `skills/index.json` (the entity's authorized capabilities at activation), the HACA-Arch version and active Cognitive Profile version under which the entity was initialized, and the activation timestamp.

7. **Genesis Omega derived** — The SIL computes the SHA-256 digest of the finalized Imprint Record and writes it as the root entry of `state/integrity-chain.jsonl`. This is the entity's permanent identity anchor.

8. **First session token issued** — The SIL writes `state/sentinels/session.token`. FAP is complete; the first session begins following the Boot Sequence from Phase 5 onward (§5). Phases 0–4 are bypassed entirely — in particular, Phase 2 (Crash Recovery) does not execute and the fresh token is not treated as a crash indicator. Phase 7, which normally issues the session token, is a no-op on first boot: the token is already present.

**Atomicity.** FCP ensures FAP is atomic with respect to its own outputs. If any step fails, all writes produced by that FAP attempt are reverted and `memory/imprint.json` is not created. The entity cannot enter a partially-initialized state. FAP re-executes on the next boot.

---

## 5. Boot Sequence

The boot sequence executes on every startup after FAP. It is a deterministic gated pipeline orchestrated by FCP — each phase must pass before the next executes. Any failure aborts the boot; FCP notifies the Operator and does not issue a session token.

**Prerequisite — Passive Distress Beacon check.** Before any phase executes, FCP checks for `state/distress.beacon`. If active, FCP exits immediately with a non-zero exit code — no phase runs. On the next boot attempt, the SIL verifies whether the beacon condition has been resolved; if so, it removes `state/distress.beacon` and boot proceeds normally. If the condition persists, FCP exits again.

**Phase 0 — Operator Bound Verification.**
The SIL reads `memory/imprint.json` and verifies the Operator Bound is present and well-formed. If absent or invalid, the entity enters permanent inactivity — no session token is issued until a valid Bound is established. This is not a recoverable fault; it is the correct behavior of an entity with no principal to serve.

FCP also verifies that both Operator Channel mechanisms are available: `state/operator-notifications/` is writable and the terminal prompt is accessible. If either is unavailable, no session token is issued — an entity that cannot reach its Operator cannot escalate Critical conditions.

**Phase 1 — Host Introspection.**
The SIL verifies the declared CPE topology against the Imprint Record and confirms the execution boundary is enforceable. **[HACA-Core]** If the declared topology is not `transparent`, or if the detected deployment does not match the declaration, boot aborts immediately — no recovery path exists. **[HACA-Evolve]** Both `transparent` and `opaque` are valid; if the detected deployment does not match the declared topology, boot aborts immediately.

The SIL also validates inter-parameter constraints in `state/baseline.json`. If `watchdog.sil_threshold_seconds` is greater than `heartbeat.interval_seconds`, boot aborts immediately — a watchdog threshold that exceeds the Heartbeat interval cannot detect SIL silence within a single Heartbeat window.

**Phase 2 — Crash Recovery.**
The SIL checks for `state/sentinels/session.token`. Its presence at boot is the primary crash indicator. See §5.2.

**Phase 3 — Integrity Verification.**
Two-step verification executed by the SIL:

- **Step 1 — Chain anchor.** The SIL reads `state/integrity.json` to locate the chain anchor: the `last_checkpoint` field identifies the sequence number and digest of the most recent checkpoint. The SIL then reads `state/integrity-chain.jsonl` and validates the chain from that checkpoint forward. Any gap, hash mismatch, or missing authorization reference → boot aborts. If `last_checkpoint` is `null`, the SIL validates from genesis.
- **Step 2 — Structural files.** The SIL recomputes SHA-256 hashes of all tracked structural files and compares them against `state/integrity.json`. Any mismatch → boot aborts.

**Phase 4 — Skill Index Resolution.**
FCP loads `skills/index.json` — already verified in Phase 3 — and makes it available to the EXEC for the session. No additional manifest verification is performed at this phase; the Integrity Document hash check in Phase 3 is the authoritative verification gate.

**Phase 5 — Context Assembly.**
FCP assembles the Boot Manifest and the CPE input context. See §5.1.

**Phase 6 — Critical Condition Check.**
The SIL scans `state/integrity.log` for unresolved Critical conditions — any record without a corresponding `CRITICAL_CLEARED` (e.g., `DRIFT_FAULT`, `SEVERANCE_PENDING`). If any are found, the SIL writes a notification to `state/operator-notifications/` and withholds the session token until each condition is resolved. Resolution requires Operator declaration and SIL independent re-verification — see §10.8.

FCP also presents any `PROPOSAL_PENDING` records found in `state/integrity.log` via terminal prompt, collecting an explicit Operator decision on each before proceeding to Phase 7.

**Phase 7 — Session Token Issuance.**
The SIL issues the session token. See §5.3.

### 5.1 Boot Manifest

The Boot Manifest is the fixed set of artefacts loaded at every boot, regardless of entity age. Boot cost is constant — it does not scale with Memory Store size.

FCP assembles the CPE input context in the following order:

```
[PERSONA]       ← persona/ files, lexicographic order
[BOOT PROTOCOL] ← boot.md
[SKILLS INDEX]  ← skills/index.json
[SKILL:<name>]  ← authorized skill manifests, one block each
[MEMORY]        ← working-memory.json targets + active-context/ symlinks, priority order
[SESSION]       ← tail of session.jsonl, newest-first until context budget exhausted
[PRESESSION]    ← contents of io/inbox/presession/, arrival order
```

Each `[SKILL:<name>]` block contains the `name`, `version`, `description`, `timeout_seconds`, `operator_only`, and `permissions` fields from the skill's manifest — not the full manifest file.

Working Memory entries are loaded at the highest priority — they are never dropped before other context fragments. Entries in `memory/working-memory.json` that point to absent Memory Store artefacts are silently dropped at Phase 5; each drop is logged as a `CTX_SKIP` envelope to `state/integrity.log`. This is not a Critical condition — missing Working Memory targets are an operational artefact, not a structural violation. Session history is loaded newest-first; when the context budget declared in `state/baseline.json` is exhausted, older entries are dropped and each skip is logged as a `CTX_SKIP` envelope to `memory/session.jsonl`. The two destinations reflect different concerns: Working Memory skips are structural artefacts — logged in integrity context because they indicate a mismatch between the declared Memory layout and what is present on disk. Session history skips are operational housekeeping — logged in the session record because they are routine context-budget management.

### 5.2 Crash Recovery

A stale session token at boot means the previous Sleep Cycle did not complete. The SIL determines the exact recovery boundary from the Integrity Log.

Recovery procedure:

0. FCP checks whether `memory/session.jsonl` is present. If absent, the previous Sleep Cycle's Stage 2 rotation completed the rename but crashed before creating the replacement file; FCP creates a new empty `memory/session.jsonl` before proceeding.
1. The SIL reads `state/integrity.log` and locates the most recent `SLEEP_COMPLETE` record.
2. If a partial Endure commit exists — an `ENDURE_COMMIT` marker with no subsequent `SLEEP_COMPLETE` — the SIL restores the pre-mutation snapshot from `state/snapshots/<seq>/` (where `seq` is the sequence number of the partial chain entry) by copying each snapshot file back to its original path, then deletes the snapshot directory.
3. The SIL scans `memory/session.jsonl` for unresolved `ACTION_LEDGER` entries — skills marked in-progress at crash time. Each unresolved entry is presented to the Operator via terminal prompt before the session token is issued. Unresolved entries are never re-executed automatically; the Operator decides whether to re-execute, skip, or investigate each one.
4. The SIL increments the consecutive crash counter in `state/integrity.log`. If the counter reaches `fault.n_boot` declared in the structural baseline, the SIL activates the Passive Distress Beacon and halts.
5. With the Entity Store in a verified state and all Action Ledger entries resolved, the SIL re-executes the Sleep Cycle from Stage 0. This completes the consolidation of the crashed session. The entity does not proceed to session token issuance until the Sleep Cycle has completed successfully and a `SLEEP_COMPLETE` record has been written to `state/integrity.log`.

On a clean boot (no stale token), the crash counter resets to zero.

### 5.3 Session Token Issuance

The SIL writes `state/sentinels/session.token`. This is the last gate — its completion marks the start of the session.

The **Heartbeat Protocol** begins. The SIL writes a `HEARTBEAT` envelope to `state/integrity.log` at the start of each Vital Check. A Vital Check triggers when either `T` completed Cognitive Cycles or `I` seconds have elapsed since the last check, whichever comes first. Both thresholds are declared in `state/baseline.json` and cannot be modified at runtime.

The **Reciprocal SIL Watchdog** activates. EXEC and MIL each monitor the interval since the last `HEARTBEAT` record in `state/integrity.log`. If the SIL has been silent beyond `watchdog.sil_threshold_seconds`, the component writes a `SIL_UNRESPONSIVE` envelope directly to `state/operator-notifications/`, bypassing the SIL entirely. The notification includes the component identity, the timestamp of the last observed heartbeat, and the elapsed interval. FCP then activates the Passive Distress Beacon and halts immediately.

---

## 6. Cognitive Session

A session begins when the SIL issues the session token and ends when FCP receives a `SESSION_CLOSE` signal — from the CPE, from the SIL (context window critical threshold reached), or from the Operator. FCP drives the session loop:

```
drain io/inbox/
  → consolidate to session.jsonl
  → assemble context
  → invoke CPE (with tool declarations)
  → process tool_use calls
  → dispatch to target components
  → return tool_results
  → next cycle
```

Each iteration of this loop is one Cognitive Cycle. The loop continues until a session-close signal is received.

A normal session close has a strict invariant: the final CPE response must contain a `fcp_mil` tool_use call with a `closure_payload` action and a `fcp_sil` tool_use call with a `session_close` action. The ordering is structurally guaranteed — `fcp_mil` tool_use calls are always processed before `fcp_sil` tool_use calls, so the Closure Payload is always staged to `state/pending-closure.json` before the session-close signal is acted upon. If a session ends without this pair — whether due to process termination, signal interruption, or any other cause — the session is treated as a crash. The presence of a stale session token at the next boot is the crash indicator. The absence of this pair as the last CPE response in `memory/session.jsonl` is additional diagnostic context — it confirms the session did not close normally and helps determine how far the previous session progressed before termination.

### 6.1 Context Assembly

At the start of each Cognitive Cycle, FCP drains `io/inbox/` — reading all `.msg` files in ascending `ts` order (ties broken by `gseq`), appending each as an ACP envelope to `memory/session.jsonl`, and deleting the `.msg` file. This consolidates all pending asynchronous stimuli into the session record before the CPE is invoked.

FCP then assembles the CPE input context. The assembly order follows the Boot Manifest defined in §5.1, with `[SESSION]` updated to include the newly consolidated envelopes. The context budget is re-evaluated at every cycle; if it has reached the critical threshold declared in `state/baseline.json`, FCP emits a `SESSION_CLOSE` signal before invoking the CPE.

FCP declares one tool per component (`fcp_exec`, `fcp_mil`, `fcp_sil`) to the API as part of every CPE invocation. The tool definitions expose the action types documented in §6.2; the CPE uses them to express intent.

### 6.2 Action Dispatch

A Cognitive Cycle ends when the CPE emits one or more tool_use calls. What follows — skill execution, memory writes, integrity signals — is handled independently by each responsible component. The cycle does not wait for results; results arrive as stimuli in the next cycle via `io/inbox/`.

The CPE emits at most one tool_use call per tool per response. When multiple actions must be sent to the same component, the tool's input is a JSON array of action objects. FCP rejects a response containing more than one tool_use call for the same tool, or a malformed input. Rejected responses are logged to `session.jsonl` and surfaced to the Operator. FCP does not re-invoke the CPE automatically — the session waits for the next Operator input stimulus.

**Actions by component:**

`fcp_exec` — skill invocation:
```json
{"type": "skill_request", "skill": "<name>", "params": {...}}
```

`fcp_mil` — memory operations:
```json
{"type": "memory_recall", "query": "..."}
{"type": "memory_write", "slug": "...", "content": "..."}
```

`fcp_sil` — integrity and control signals:
```json
{"type": "evolution_proposal", "content": "..."}
{"type": "session_close"}
```

The `evolution_proposal.content` field is a free-form narrative string describing the proposed change. The SIL computes a SHA-256 digest of the content to produce the `EVOLUTION_AUTH` integrity chain entry — the digest commits the proposal to the chain without storing the full text inline.

**Tool results:** FCP returns a tool_result for each tool_use call before the model produces its final text response. For `fcp_exec` and `fcp_sil`, the tool_result is an acknowledgement — the action has been dispatched and any result will arrive in the next cycle's assembled context. For `fcp_mil` with `memory_recall`, the tool_result carries the recalled content synchronously; the CPE receives the memory contents before emitting its final text response for the cycle.

Each component writes its asynchronous results to `io/inbox/` as an ACP envelope. FCP drains the inbox at the start of the next cycle, consolidates into `session.jsonl`, and the results become stimuli for the next invocation of the CPE.

The `closure_payload` action (§3.7) is an exception to this model: it is not dispatched to a component, and its tool_result is an immediate acknowledgement. FCP writes it atomically to `state/pending-closure.json` before the Sleep Cycle begins. This ensures the Closure Payload survives a crash between session close and Stage 1 processing.

### 6.3 Cycle Chain

A Cognitive Cycle is the atomic unit of cognition: stimulus received → context loaded → intent generated → intent dispatched. The cycle is complete when the CPE response is processed, tool_use calls are dispatched to their components, and tool_results returned. What follows is the consequence of the dispatched intent, handled by the responsible components independently.

Composite operations are expressed as chains of consecutive cycles. Results from the previous cycle arrive in `io/inbox/`, are consolidated into `session.jsonl` at the start of the next cycle, and become part of the assembled context. The CPE reasons over accumulated stimuli and emits the next intent. There is no synchronous result-passing between cycles — all inter-cycle communication flows through the inbox.

A cycle chain may be interrupted by the SIL at any Vital Check boundary. If a Critical condition is detected, the SIL revokes the session token and the chain terminates. The Sleep Cycle executes immediately.

The Heartbeat Protocol and Vital Check are defined in §10.3.

### 6.4 Context Budget Tracking

The context budget measures current context window utilization against the `context_window.budget_tokens` limit declared in `state/baseline.json`. FCP re-evaluates the budget at the start of every Cognitive Cycle, before assembling the CPE input.

**Authoritative count.** Every CPE response includes a `usage` field with the actual token counts for the completed invocation. FCP stores the reported `input_tokens` value and uses it as the baseline for the following cycle's budget evaluation. This is the preferred measurement path.

**Estimated count.** When no authoritative count is available — at the first cycle of a session, or when the CPE response does not include usage data — FCP estimates the token count as `floor(total_context_characters / 4)`, where `total_context_characters` is the sum of UTF-8 character lengths of all strings in the assembled CPE input context. This estimate is a conservative approximation for English-language content; it underestimates for non-ASCII-heavy content. It is a fallback only — never used when an authoritative count is available.

**Budget threshold.** FCP compares the current token count against `budget_tokens`. If the ratio meets or exceeds `context_window.critical_pct / 100`, FCP emits a `SESSION_CLOSE` signal before invoking the CPE for that cycle. No CPE invocation occurs on the closing cycle — the session terminates immediately and the Sleep Cycle begins.

**Budget reporting.** The current token count and budget ratio are included in every Heartbeat record written to `state/integrity.log` (§10.3). The `/status` command surfaces the current context budget as a percentage of the configured limit (§12.2).

---

## 7. Sleep Cycle

The Sleep Cycle is the ordered shutdown protocol that executes at every clean session close. It is the sole authorized window for structural writes. FCP orchestrates four sequential stages; each must complete before the next begins. No two stages execute concurrently. HACA-Arch §6.4 describes three canonical stages (memory consolidation → garbage collection → Endure execution); FCP adds a preparatory Stage 0 (Semantic Drift Detection) required by HACA-Core §4.2, which mandates drift detection during the Sleep Cycle. Stage 0 executes before any mnemonic or structural write occurs.

**Session token revocation.** On receiving a session-close signal, the SIL revokes the session token immediately by appending `revoked_at` to `state/sentinels/session.token`. No further Cognitive Cycles are dispatched after revocation. The token artefact remains in place throughout the Sleep Cycle as a crash indicator; the SIL removes it only after Stage 3 completes.

Between revocation and Stage 0, behavior differs by close type:

- **Normal close** (CPE emitted `closure_payload` + `session_close`): FCP intercepts the `promotion` array (if present and not empty) from the Closure Payload and queues it as a pending Evolution Proposal. FCP then presents any pending Evolution Proposals to the Operator via terminal prompt and collects a decision on each.
- **Forced close** (Critical condition, context window limit, or `/endure approve <id>`): no proposal presentation occurs. Any undecided proposals are persisted as `PROPOSAL_PENDING` and presented at the next boot's Phase 6.

**Operator input during the Sleep Cycle.** The session token carries `revoked_at` — the out-of-session routing rule applies: all Operator stimuli and slash commands directed to the skill registry are routed to `io/inbox/presession/`. FCP platform commands that do not require skill dispatch or session state are serviced immediately by the FCP process regardless of Sleep Cycle state.

### 7.1 Stage 0 — Semantic Drift Detection

The SIL runs Semantic Probes against the accumulated Memory Store content. The CPE is inactive during this stage; no inference is required.

Probes are defined in `state/drift-probes.jsonl`. Each probe is executed in two layers:

**Deterministic layer** — the SIL applies string matching, pattern scanning, and content hash verification to the designated Memory Store excerpt. Each probe produces a conclusive pass or fail. A conclusive deterministic result skips the probabilistic layer for that probe.

**Probabilistic layer** — activated when the deterministic layer produces no conclusive result. The EXEC invokes a standalone comparison worker at the SIL's request. The worker computes Unigram NCD (Normalized Compression Distance using gzip) between the Memory Store excerpt and the probe's reference text: `NCD(x,y) = (C(xy) − min(C(x),C(y))) / max(C(x),C(y))`, where `C(z)` is the compressed size of `z`. A score above the probe's tolerance indicates drift. The comparison mechanism (`ncd-gzip-v1`) is declared in `state/baseline.json` and cannot be substituted at runtime.

After all probes run, the SIL updates `state/semantic-digest.json` with the current cycle's per-probe scores. Stage 0 checks both the current scores and the aggregate trend in the digest against the drift threshold declared in `state/baseline.json`.

If any probe fails:
1. The SIL logs a `DRIFT_FAULT` Critical condition to `state/integrity.log` with the probe ID, layer, divergence score, and the Memory Store excerpt that triggered it.
2. The SIL writes a `DRIFT_FAULT` notification to `state/operator-notifications/`.
3. The condition is marked unresolved. The next boot's Phase 6 will detect it and withhold the session token.

A `DRIFT_FAULT` does not halt the Sleep Cycle — Stages 1–3 still complete.

### 7.2 Stage 1 — Memory Consolidation

The MIL reads `state/pending-closure.json`. If present, the session closed normally and the file contains the Closure Payload produced in the final Cognitive Cycle (§6) — the MIL processes it and deletes the file. If absent, the session was a forced close — a Critical condition, context window limit, or `/endure approve <id>` — and Stage 1 is a no-op; the Sleep Cycle proceeds directly to Stage 2. No further CPE invocation occurs during the Sleep Cycle.

The MIL processes each field:

- **`consolidation`** — appended to `memory/session.jsonl` as a `MSG` ACP envelope.
- **`working_memory`** — each declared path is validated against the Memory Store. Valid paths are written atomically to `memory/working-memory.json`. Invalid or absent paths are dropped and logged to `state/integrity.log`. If the list exceeds `working_memory.max_entries`, entries with the highest `priority` values (lowest priority) are dropped first until the list is within the limit.
- **`session_handoff`** — written atomically to `memory/session-handoff.json`, replacing the previous record.

The `active-context/` symlinks are rebuilt from the validated Working Memory pointer map at the next boot's Phase 5.

### 7.3 Stage 2 — Garbage Collection

The SIL performs bounded housekeeping against the Memory Store. No CPE invocation occurs in this stage.

- If `memory/session.jsonl` exceeds `session_store.rotation_threshold_bytes` declared in `state/baseline.json`, the SIL renames `memory/session.jsonl` to `memory/episodic/<year>/<timestamp>.jsonl` and creates a new empty `memory/session.jsonl`. If the rename completes but the new file is not created — detected at the next boot by the absent `memory/session.jsonl` — Phase 2 creates a new empty file before proceeding.
- Stale `memory/active-context/` symlinks pointing to absent targets are removed.
- Temporary spool files older than one session in `io/spool/` are deleted.
- Entries in `io/inbox/presession/` beyond the capacity declared in `state/baseline.json` are discarded and logged to `state/integrity.log`.

### 7.4 Stage 3 — Endure Execution

The SIL processes all queued Evolution Proposals. For each proposal:

1. Verify that a matching `EVOLUTION_AUTH` record exists in `state/integrity.log` — an explicit Operator approval whose content digest matches the proposal exactly.
2. Create a pre-mutation snapshot: copy each file to be modified into `state/snapshots/<seq>/`, preserving the path relative to the entity root (e.g., `persona/identity.md` → `state/snapshots/12/persona/identity.md`), where `<seq>` is the sequence number of the chain entry about to be written. The snapshot directory is deleted by the SIL after `SLEEP_COMPLETE` is written successfully.
3. Apply the structural write atomically: write to a `.tmp` sibling, then `rename(2)` into place. For memory promotion proposals, the SIL triggers the MIL to integrate the authorized slugs from `memory/episodic/` into the `memory/semantic/` graph.
4. Recompute SHA-256 hashes for all modified tracked files.
5. Update `state/integrity.json` atomically. If the number of Endure commits since the last checkpoint has reached `integrity_chain.checkpoint_interval`, include the updated `last_checkpoint` field in this same write.
6. Append the commit entry to `state/integrity-chain.jsonl`. If step 5 updated `last_checkpoint`, this entry is a checkpoint entry — the Integrity Document is the verifiable anchor; the chain entry carries the full chain data.
7. The SIL invokes the MIL synchronously in-process to append an `ENDURE_COMMIT` ACP envelope to `memory/session.jsonl` — no ACP roundtrip is required. This is the only Sleep Cycle write to `session.jsonl`; the MIL remains the authoritative writer even during Stage 3.
8. If the proposal originated from a staged cartridge under `/tmp/fcp-stage/<entity_id>/<name>/`, the SIL deletes that staging directory. Staged cartridges are not retained after promotion.

Proposals without a valid `EVOLUTION_AUTH` record are discarded and logged — they are never executed.

After all proposals are processed, the SIL writes the `SLEEP_COMPLETE` ACP envelope to `state/integrity.log`. This record is the authoritative Sleep Cycle completion boundary used by crash recovery. Immediately after, the SIL removes `state/sentinels/session.token`. The entity is now at rest.

---

## 8. Memory Layer

The memory layer is the MIL's exclusive write territory. No other component may write mnemonic content to the Session Store or Memory Store. Operator input, skill results, and CMI messages are stimuli that enter the cognitive pipeline — they do not bypass it to write directly to either store.

### 8.1 Session Store

`memory/session.jsonl` is the cognitive record of the active session. Every event relevant to cognition is recorded here as an ACP envelope: Operator messages, CPE responses, skill requests and results, memory operations, integrity signals, and context assembly events. The Session Store is append-only during the session — existing lines are never modified or deleted.

The MIL is the sole writer to `session.jsonl`. Components that produce results write to `io/inbox/` via the spool-then-rename pattern; FCP consolidates the inbox into `session.jsonl` at the start of each Cognitive Cycle.

The Session Store grows throughout the session. There are two mechanisms that manage its size, serving distinct purposes:

**Mid-session Session Summarization** — a corrective action triggered by the SIL when a Vital Check detects the Session Store approaching `session_store.rotation_threshold_bytes`. The SIL invokes the MIL summarization procedure synchronously within the FCP process — no ACP roundtrip is required. The MIL rewrites `session.jsonl` in-place: it retains the most recent 50% of the file's bytes (the newest entries), discards the oldest half, and prepends a single `MSG` ACP envelope with `data: "session summarized"` as a boundary marker. If re-verification fails after the corrective action, the condition escalates to Critical. This is a Degraded-class response (externally verifiable by the SIL), not a Sleep Cycle operation. It compresses the physical record without semantic consolidation.

**Sleep Cycle Stage 2 rotation** — archival at every Sleep Cycle if the Session Store exceeds `session_store.rotation_threshold_bytes`. The SIL performs a crash-safe rotation: renames `session.jsonl` to `memory/episodic/<year>/<timestamp>.jsonl` and starts a fresh `session.jsonl`. This is structural housekeeping, not a corrective response.

The two mechanisms are independent. Mid-session summarization is reactive and bounded; Stage 2 rotation is routine and unconditional when the threshold is exceeded.

### 8.2 Memory Store

The Memory Store is the entity's consolidated long-term knowledge base. It persists across sessions and is the exclusive origin of persisted knowledge that informs cognition — no external source may override or replace its content outside the established pipeline.

The Memory Store comprises:

- `memory/episodic/` — episodic memories recorded during the session. Written by the MIL as directed by CPE `memory_write` actions, which provide a `slug` to identify the topic. The SIL also archives session fragments here during Stage 2 rotation (via rename of `memory/session.jsonl`).
- `memory/semantic/` — semantic knowledge base structured around topic slugs. The CPE queries it opaquely via `memory_recall`. It is written by the MIL exclusively during Sleep Cycle Stage 3 execution of an authorized memory promotion proposal.
- `memory/imprint.json` — the Imprint Record. Written once at FAP by the MIL; never modified thereafter.
- `memory/working-memory.json` — the Working Memory pointer map. Written by the MIL at Stage 1 of each Sleep Cycle.
- `memory/session-handoff.json` — the Session Handoff record. Written by the MIL at Stage 1, replacing the previous record.

`memory/active-context/` is the boot-time view into the Memory Store — a directory of symlinks seeded from `working-memory.json` at Phase 5, extended dynamically during the session via `memory_recall` actions. When the MIL processes a `memory_recall`, it creates a symlink in `memory/active-context/` named after the basename of the recalled path (e.g., `memory/active-context/arch.md` → `memory/semantic/arch.md` or `memory/active-context/note.md` → `memory/episodic/2026-03/note.md`); an existing symlink of the same name is replaced. The MIL then writes a `MEMORY_RESULT` envelope to `io/inbox/` with the recalled paths and status. Symlinks are validated at boot; stale entries are removed at Stage 2.

### 8.3 Pre-Session Buffer

Stimuli received without an active session token — Operator messages delivered outside a session, scheduled triggers, or CMI signals — are held in `io/inbox/presession/` rather than dropped. Senders use the standard spool-then-rename pattern, renaming into `io/inbox/presession/` instead of `io/inbox/`.

The buffer is governed by the `pre_session_buffer` parameters declared in `state/baseline.json`:

- **Ordering** — FIFO. Arrival order is preserved and must not be altered.
- **Persistence** — disk. Entries survive a crash and are available at the next boot.
- **Capacity** — bounded by `pre_session_buffer.max_entries`. Enforcement happens at write time: before renaming a stimulus into `io/inbox/presession/`, FCP counts existing entries; if the count is already at `max_entries`, the stimulus is rejected without writing and logged to `state/integrity.log`. Silent overflow is not permitted. The SIL's Vital Check independently verifies buffer bounds and writes a notification to `state/operator-notifications/` if the buffer is at or near capacity.

At Phase 5 of the Boot Sequence, FCP loads the buffer contents into the Boot Manifest as `[PRESESSION]`, positioned after `[SESSION]` — the most recent pending stimuli available to the CPE at session start.

---

## 9. Execution Layer

The execution layer is responsible for all skill dispatch and host actuation. Skill authorization is established once, at boot, when the SIL builds and seals `skills/index.json`. The EXEC dispatches against this index without per-execution re-validation.

Every skill entry in `skills/index.json` carries a `class` field: `"builtin"`, `"custom"`, or `"operator"`. This field determines whether the skill is injected into the `[SKILLS INDEX]` context block assembled for the CPE: built-in and custom skills are included; operator skills are not. Skills absent from `[SKILLS INDEX]` are structurally invisible to the CPE — it receives no instruction, no context, and has no dispatch path to reach them. The EXEC enforces this at dispatch: a `skill_request` referencing an operator-class skill is rejected and logged to `state/integrity.log`.

### 9.1 Skill Index

`skills/index.json` is the authoritative registry of skills the entity is authorized to use. It is part of the structural baseline, covered by the Integrity Document from the moment of FAP, and cannot be modified outside the Endure Protocol — with one exception: the SIL may remove a skill from the index as a maintenance operation when the skill's manifest is invalid or its executable is absent, without requiring a full Endure Protocol execution, to avoid blocking the system.

When removing a skill as a maintenance operation, the SIL still performs an atomic integrity update: it rewrites `state/integrity.json` with the updated hash for `skills/index.json` and appends a `SEVERANCE_COMMIT` entry to `state/integrity-chain.jsonl`. This entry references the removed skill, the reason for removal, and the new `skills/index.json` hash. No `EVOLUTION_AUTH` record is required. A `SEVERANCE_COMMIT` without a corresponding `EVOLUTION_AUTH` is valid — it is distinguished from a normal Endure commit by its type field. The SIL writes a `SEVERANCE_COMMIT` notification to `state/operator-notifications/` immediately. At normal session close, FCP presents it via terminal prompt and requires an explicit Operator acknowledgement before the Sleep Cycle begins. If the session closes via forced close, the notification is persisted as `SEVERANCE_PENDING` in `state/integrity.log` and presented at the next boot's Phase 6, blocking session token issuance until resolved.

The Skill Index is established during FAP Step 1: the SIL validates every skill manifest present in `skills/` and writes `skills/index.json` containing only the skills whose manifests are well-formed and whose executables are present. `skills/index.json` is then included in the Integrity Document and referenced in the Imprint Record — the entity's authorized capabilities are sealed into its identity from first activation.

At Phase 3 of the Boot Sequence, `skills/index.json` is verified like any other tracked structural file: the SIL recomputes its hash and compares it against the Integrity Document. Any mismatch aborts the boot. At Phase 4, FCP loads the verified index and makes it available to the EXEC for the session.

The EXEC operates exclusively against `skills/index.json`. A skill invocation request for a skill absent from the index is rejected and logged to `state/integrity.log`; the SIL is notified synchronously within the same FCP execution context — no ACP roundtrip over `io/` is required. The SIL evaluates the anomaly immediately and escalates to Critical if warranted — an unexpected skill request may indicate a structural anomaly or an adversarial attempt.

### 9.2 Dispatch

The EXEC dispatches skill requests against `skills/index.json`. A skill present in the index is executed directly — no per-execution re-validation occurs.

If a skill fails, the EXEC writes a `SKILL_ERROR` ACP envelope to `io/inbox/`. If a skill exceeds its declared timeout, the SIL writes a `SKILL_TIMEOUT` envelope to `io/inbox/` at the next Vital Check (§10.3). Both results reach the CPE as stimuli in the next Cognitive Cycle. If a skill fails on `fault.n_retry` consecutive attempts within the current session, the EXEC writes a notification to `state/operator-notifications/`; the consecutive failure counter resets at session start.

### 9.3 Action Ledger

Skills that produce irreversible side effects — writes to external systems, physical actuations, payments — must be covered by a write-ahead `ACTION_LEDGER` entry in `memory/session.jsonl` before execution begins. FCP writes the entry before dispatching to the EXEC; the EXEC resolves it — marking it complete or failed — after the skill returns.

The `data` field of both envelopes is a JSON object:

```json
// write-ahead entry (written by FCP before dispatch)
{"ledger_id": "uuid", "skill": "send_email", "params": {...}, "status": "pending"}

// resolution entry (written by EXEC after the skill returns)
{"ledger_id": "uuid", "skill": "send_email", "status": "complete|failed"}
```

Phase 2 crash recovery scans `memory/session.jsonl` for `ledger_id` values that have a `"pending"` entry with no corresponding `"complete"` or `"failed"` entry — these are the unresolved records surfaced to the Operator.

The write-ahead entry records the intent before the skill executes. If a crash occurs between execution and Sleep Cycle consolidation, the unresolved entry is detected at the next boot's Phase 2 (Crash Recovery) and surfaced to the Operator. Unresolved entries are never re-executed automatically.

### 9.4 Worker Skills

Worker skills are skills that execute in isolation, outside the main CPE context window. They serve two distinct use cases.

**SIL-invoked workers** — bounded, deterministic operations requested directly by the SIL via EXEC, without CPE involvement. The primary example is the NCD comparison worker used by Stage 0 Semantic Drift Detection: invoked only when the deterministic probe layer produces no conclusive result, never as the primary check. SIL-invoked workers must be read-only — they must not produce irreversible side effects. The Action Ledger requirement (§9.3) does not apply to them.

**CPE-invoked workers** — sub-agents dispatched by the CPE via a standard `skill_request` action. The CPE provides three fields in the `params` object: `persona` (the specialized identity for the worker), `context` (the relevant knowledge the worker needs), and `task` (the specific work to execute). The worker runs in isolation with that payload and returns its result through `io/inbox/` as a `SKILL_RESULT` envelope.

```json
{
  "type": "skill_request",
  "skill": "agent_run",
  "params": {
    "persona": "...",
    "context": "...",
    "task": "..."
  }
}
```

Worker Skills are for isolated, single-agent specialized execution. When the CPE requires coordinated work across multiple agents, the correct mechanism is the Cognitive Mesh Interface — Worker Skills must not be used as a substitute for collective coordination.

Worker skills are declared in `skills/index.json` and authorized at boot like any other skill. SIL-invoked workers return their results directly to the SIL; CPE-invoked workers route results through `io/inbox/`.

### 9.5 Native Exec Tools

FCP ships eight tools hardcoded into the EXEC layer. These tools live in `exec/tools/` inside the FCP runtime — they are not declared in `skills/index.json`, not tracked by the Integrity Document, and carry no manifest. They are always available to the CPE regardless of the entity's skill configuration.

| Tool | Description |
|---|---|
| `skill_create` | Stages a new skill cartridge under `/tmp/fcp-stage/<entity_id>/<name>/` for Endure installation; accepts an optional `--base <name>` parameter — when provided, EXEC copies the named skill's files from `skills/<name>/` into the staging directory, giving the CPE a pre-populated cartridge to read and modify via `file_read` and `file_write`; does not modify `skills/index.json` directly — the staged files become an Evolution Proposal |
| `skill_audit` | Validates a skill's manifest, executable, and index consistency; read-only — does not modify any files |
| `file_read` | Reads a file within `workspace_focus`; rejects any path outside `workspace_focus` |
| `file_write` | Writes a file within `workspace_focus`; rejects any path outside `workspace_focus`; no file size limit beyond host disk capacity |
| `agent_run` | Instantiates a Worker Skill sub-agent with a provided persona, context, and task |
| `shell_run` | Executes a shell command within the active `workspace_focus` directory; the permitted command set is a static allowlist hardcoded in the EXEC layer — includes standard read-only utilities and `git`; entity root and workspace are always separate directory trees, so git operations carry no risk of touching entity structural files; rejects if `workspace_focus` is unset or if the requested command is not in the allowlist |
| `web_fetch` | Fetches the content of a URL and returns it as text; blocks loopback and RFC-1918 addresses; content is delivered as chunked `SKILL_RESULT` envelopes; timeout enforced by the SIL watchdog (§10.4) |

`skill_audit` has three invocation paths: CPE dispatches it via `skill_request` to validate skills under development; the SIL invokes it as a read-only operation for `SEVERANCE_PENDING` resolution (§10.8); and the Operator invokes it via the `/skill audit` platform command (§12.3).

### 9.6 Operator Skills

Operator skills are system-control capabilities invokable exclusively by the Operator. They carry `class: "operator"` in `skills/index.json` and are excluded from the `[SKILLS INDEX]` context block — the CPE has no awareness of their existence. The EXEC rejects any `skill_request` referencing an operator-class skill regardless of origin.

Operator skills are dispatched directly by the Operator Channel (§10.6). Their executables reside in `skills/<name>/` alongside custom skills.

The slash commands defined in §12.3 are the interactive surface over operator skills and FCP internal operations. Some platform commands map directly to operator skill invocations; others execute FCP logic internally without dispatching a skill.

### 9.7 Lifecycle Hooks

Lifecycle hooks are host executables stored in `hooks/` and tracked by the Integrity Document. FCP invokes them at defined lifecycle events:

| Event | Trigger point |
|---|---|
| `on_boot` | After Phase 7 — session token issued, before the first Cognitive Cycle |
| `on_session_close` | After the session-close signal is received, before token revocation |
| `pre_skill` | Before EXEC dispatches a skill; receives skill name and params as environment variables |
| `post_skill` | After a skill result is written to `io/inbox/`; receives skill name and exit status |
| `post_endure` | After all Stage 3 proposals are processed, before `SLEEP_COMPLETE` is written |

Hooks run as ordinary host processes within the FCP execution context. They operate outside the cognitive pipeline — they cannot dispatch skill requests, write to `io/inbox/`, or invoke the CPE. A hook's exit code is informational: FCP logs it but does not alter control flow based on it.

Recursion is structurally prohibited. FCP sets a hook-execution guard before invoking any hook; any lifecycle event that would ordinarily trigger a hook while the guard is active is suppressed. A hook cannot cause another hook to fire, directly or indirectly.

### 9.8 Session Approval Model

The static allowlists in native exec tool implementations (§9.5) and custom skill manifests define which commands or URLs a tool or skill is permitted to invoke — they do not gate whether the Operator authorizes the skill to run at all within the current session. FCP provides a three-tier runtime approval system layered above the static manifest gates.

**Approval tiers:**

- **One-time** — approved for the current invocation only; not persisted. The Operator is prompted again on the next invocation.
- **Session** — approved for all invocations of this skill within the current session. Recorded in `state/session-grants.json`; cleared atomically when the SIL revokes the session token.
- **Persistent** — approved for all future sessions. Recorded in `state/allowlist.json`.

**Approval gate.** Before dispatching a skill, FCP checks authorization in this order:
1. Is the skill entry present in `state/allowlist.json` with a value of `true`? → dispatch immediately.
2. Is the skill entry present in `state/session-grants.json` with a value of `true`? → dispatch immediately.
3. Present the Operator with the skill name and invocation parameters via terminal prompt, offering all three tiers plus denial. On denial, the EXEC logs the rejection to `state/integrity.log`; no dispatch occurs.

This gate is independent of the two-gate authorization sequence defined in §9.2. All three gates must pass for a skill to execute: Skill Index check (§9.1), session approval check (this section), and EXEC manifest validation (§9.2).

**Artefact formats:**

`state/allowlist.json`:
```json
{ "<skill-name>": true }
```

`state/session-grants.json` — identical schema; written atomically on first grant within a session; removed atomically at token revocation.

Both artefacts are operational state — not covered by the Integrity Document and not modified by the Endure Protocol. Neither is present in the default entity layout; FCP creates them on first use.

---

## 10. Integrity Layer

The integrity layer is the SIL's domain. It operates independently of the cognitive pipeline — it does not reason, it verifies. Its authority is structural: it monitors state, enforces boundaries, and escalates when violations are detected. It does not attempt to resolve conditions it cannot verify independently.

**Integrity Log retention.** `state/integrity.log` grows without bound and is never compacted, archived, or deleted. No truncation, rotation, or archival of any record is permitted under HACA-Core — this log targets regulated and auditable environments where complete record retention is a requirement. Log storage growth over time is an operational concern outside the entity's scope; the Operator is responsible for provisioning adequate storage infrastructure for the lifetime of the deployment.

### 10.1 Structural Verification

Structural verification runs at two points: at every boot (Phase 3) and at every Heartbeat Vital Check during the session.

At boot, the SIL performs a two-step verification. First, it validates the Integrity Chain: reads `last_checkpoint` from `state/integrity.json` to locate the chain anchor, then reads `state/integrity-chain.jsonl` and verifies the chain from that checkpoint forward — any gap, hash mismatch, or missing authorization reference aborts the boot. If `last_checkpoint` is `null`, the SIL validates from genesis. Second, it recomputes SHA-256 hashes of all tracked structural files and compares them against `state/integrity.json` — any mismatch aborts the boot.

During the session, each Vital Check repeats the structural file hash verification. A mismatch detected mid-session is an Identity Drift violation: the SIL revokes the session token immediately, logs a Critical condition to `state/integrity.log`, writes a notification to `state/operator-notifications/`, and the Sleep Cycle executes.

### 10.2 Drift Detection

The SIL monitors three drift categories. Under HACA-Core, all three escalate directly to Critical — there is no Degraded intermediate state, no tolerance threshold, and no corrective attempt before escalation.

**Semantic Drift** — detected during Sleep Cycle Stage 0 by running Semantic Probes against the Memory Store content. Two-layer execution: deterministic layer first (string matching, pattern scanning, content hashes); probabilistic layer (NCD via Worker Skill) only when the deterministic layer produces no conclusive result. Results are accumulated in `state/semantic-digest.json` across Sleep Cycles. A single-cycle threshold breach or an aggregate trend breach in the digest triggers a `DRIFT_FAULT` Critical condition. Stages 1–3 of the Sleep Cycle still complete; the next session is blocked at Phase 6.

**Identity Drift** — detected at every Heartbeat Vital Check by recomputing structural file hashes against the Integrity Document. A mismatch triggers immediate Critical escalation: session token revoked, Sleep Cycle executed.

**Evolutionary Drift** — detected at each Endure execution by verifying that every commit in the Integrity Chain — other than `SEVERANCE_COMMIT` entries — references a valid `EVOLUTION_AUTH` record. A commit without a traceable authorization reference triggers immediate Critical escalation regardless of whether the structural change appears benign.

### 10.3 Heartbeat and Vital Check

The Heartbeat Protocol activates when the SIL issues the session token (§5.3) and runs for the duration of the session. A Vital Check triggers when either `T` completed Cognitive Cycles or `I` seconds have elapsed since the last check, whichever comes first. Both thresholds are declared in `state/baseline.json` and cannot be modified at runtime.

At each Vital Check, the SIL writes a `HEARTBEAT` envelope to `state/integrity.log` and performs a full entity health scan:

| Check | Condition | SIL action |
|---|---|---|
| Structural file hashes | Mismatch against Integrity Document | Critical → revoke token, Sleep Cycle |
| Background skill TTLs | TTL expired without registered result | `SKILL_TIMEOUT` to `io/inbox/`; surface to CPE |
| Session Store size | ≥ 80% of `session_store.rotation_threshold_bytes` | Degraded → corrective signal to MIL |
| Pre-session buffer | At or near `pre_session_buffer.max_entries` | Write to `operator-notifications/`; if `n_channel` failures → Beacon + halt |
| `io/inbox/` health | `.msg` file present at previous Vital Check still present (stuck), or payload fails ACP parse (malformed) | Corrective signal to MIL |
| `workspace_focus` path | Present but pointing inside entity root or ancestor of entity root | Critical → revoke token, Sleep Cycle |

For Degraded conditions — those the SIL can verify independently by observing the component externally — the SIL issues a corrective signal and re-verifies after the component acts. If re-verification fails, the condition escalates to Critical. Conditions not externally verifiable escalate to Critical directly.

### 10.4 Watchdog

The integrity layer operates two watchdog mechanisms with distinct ownership: the SIL monitors skill executions, and the components monitor the SIL itself — with FCP providing the information necessary for that check.

**Skill timeout watchdog** — the SIL monitors active skill executions against the timeout declared in each skill's manifest. A skill that exceeds its timeout receives a `SKILL_TIMEOUT` envelope written to `io/inbox/`; the result reaches the CPE as a stimulus in the next cycle. Background skills declare a TTL in their manifest; a background skill whose TTL expires without a registered result is treated as an incomplete execution and logged to `state/integrity.log`. If a skill fails on `fault.n_retry` consecutive attempts, the EXEC writes a notification to `state/operator-notifications/`.

**Reciprocal SIL Watchdog** — FCP exposes the SIL's last heartbeat timestamp to EXEC and MIL at the start of each operation. Each component independently checks whether the interval since the last `HEARTBEAT` record in `state/integrity.log` exceeds `watchdog.sil_threshold_seconds` declared in `state/baseline.json`. If it does, the component writes a `SIL_UNRESPONSIVE` envelope directly to `state/operator-notifications/`, bypassing the SIL entirely. The notification includes the component identity, the timestamp of the last observed heartbeat, and the elapsed interval. FCP then activates the Passive Distress Beacon and halts immediately.

### 10.5 Evolution Gate

The Evolution Gate is the SIL's enforcement of Operator authority over structural change. Profile-specific authorization rules determine whether a proposal is queued automatically or requires explicit Operator decision.

**[HACA-Core]** Every Evolution Proposal requires explicit, per-proposal Operator authorization — implicit authorization is never valid.

**[HACA-Evolve]** The SIL classifies each proposal against the `authorization_scope` declared in `state/baseline.json`. Proposals within scope are queued automatically for Stage 3 execution without Operator interaction; the SIL logs the scope category under which the proposal was classified. Proposals outside scope require explicit Operator authorization and follow the same flow as HACA-Core proposals below.

When the CPE emits an `evolution_proposal` action, the SIL intercepts it. The session continues normally while the proposal is pending. The SIL writes the proposal to `state/operator-notifications/` immediately so the Operator is aware.

The Operator may approve or reject a pending proposal mid-session using `/endure approve <id>` or `/endure reject <id>` (§12.3). A pending proposal is identified by the `seq` field of its `PROPOSAL_PENDING` record in `state/integrity.log`; `/endure list` displays the `seq` for each pending proposal. These commands are Operator-exclusive — the CPE cannot invoke them. On mid-session approval, the SIL writes the `EVOLUTION_AUTH` record and triggers an immediate forced session close: the token is revoked without consulting the CPE and the Sleep Cycle begins. Stage 3 will execute the approved proposal. On mid-session rejection, the SIL writes `EVOLUTION_REJECTED` and the session continues normally.

At normal session close, FCP presents any remaining pending proposals via terminal prompt and waits for an explicit decision on each. If the session closes before the terminal prompt can be shown — for example during an unattended session — the SIL persists the proposal as a `PROPOSAL_PENDING` record in `state/integrity.log` and FCP presents it at the next boot's Phase 6.

On explicit Operator approval, the SIL writes an `EVOLUTION_AUTH` record to `state/integrity.log` containing the Operator's identity, a timestamp, and a SHA-256 digest of the approved proposal content. The proposal is queued for execution at Sleep Cycle Stage 3. On rejection, the SIL writes an `EVOLUTION_REJECTED` record. In both cases, the outcome is never returned to the CPE.

A proposal that has not received an explicit Operator decision is never queued and never discarded by timeout. It remains in `PROPOSAL_PENDING` state until the Operator responds.

### 10.6 Operator Channel

The Operator Channel is not a component — it is a pair of platform primitives provided by FCP that components use directly to communicate with the Operator.

**Terminal prompt** — synchronous interaction. Used when a response is required before the platform can proceed: FAP enrollment, Evolution Proposal approval at session close, explicit Operator acknowledgement of a Critical condition. FCP opens the prompt, presents the content, and waits for the Operator's input. The response is returned to the requesting component.

**`state/operator-notifications/`** — asynchronous delivery. Used for notifications that do not require an immediate response: SIL escalations, `DRIFT_FAULT` reports, `SIL_UNRESPONSIVE` alerts, schedule anomalies. Components write notification files directly to this directory, each named in the format `<utc-timestamp>.<severity>.json` — where `<utc-timestamp>` is an ISO 8601 UTC timestamp with colons replaced by hyphens (e.g. `2026-03-12T14-00-00Z`) and `<severity>` is one of `critical`, `warning`, or `info`. The Operator reads them at their own pace.

The `state/operator-notifications/` directory is declared in `state/baseline.json` and verified at every boot (Phase 0). If it is absent or not writable, no session token is issued. The terminal prompt is a platform primitive — always available when FCP is running.

Every use of either mechanism is logged to `state/integrity.log` as an ACP envelope with a timestamp, the invoking component, the condition, and the delivery status. If async delivery fails on `fault.n_channel` consecutive attempts, the SIL activates the Passive Distress Beacon.

### 10.7 Passive Distress Beacon

`state/distress.beacon` is a passive, persistent signal written by the SIL when autonomous recovery is no longer possible. It is activated in two conditions: `fault.n_boot` consecutive boot failures, or `fault.n_channel` consecutive Operator Channel delivery failures.

The beacon is a plain file — readable from the Entity Store without network connectivity, running processes, or any component active. Its presence at boot suspends the entire boot sequence before any phase executes. It contains a JSON object identifying the cause:

```json
{"cause": "n_boot|n_channel|sil_unresponsive", "ts": "2026-03-11T14:00:00Z", "consecutive_failures": 3}
```

While the beacon is active, the entity is in suspended halt: no session token is issued, no Cognitive Cycles execute, and no stimuli are processed.

The beacon is cleared only by the Operator. Clearance requires two steps: the Operator acknowledges the condition, and the SIL independently verifies that the underlying cause is resolved. Acknowledgement without resolution does not clear the beacon — the SIL must confirm the cause is addressed before lifting the suspended halt.

If the beacon was activated due to SIL unresponsiveness — detected by EXEC or MIL via the Reciprocal SIL Watchdog — the resolution verification cannot be delegated to the SIL. In this case, FCP performs the verification directly: after the Operator acknowledges the condition, FCP starts the boot sequence and observes whether a `HEARTBEAT` record appears in `state/integrity.log` within `watchdog.sil_threshold_seconds` of Phase 0. If a `HEARTBEAT` is written within that window, the SIL is confirmed responsive; FCP presents the result to the Operator via terminal prompt and, on Operator confirmation, removes `state/distress.beacon` and continues boot. If no `HEARTBEAT` appears within the window, FCP reports SIL still unresponsive, exits, and leaves the beacon active.

### 10.8 Critical Condition Resolution

A Critical condition blocks session token issuance at Phase 6. Resolution requires two independent steps: the Operator declares the condition resolved via terminal prompt, and the SIL performs independent re-verification confirming the declared correction. The SIL writes `CRITICAL_CLEARED` to `state/integrity.log` only when both steps pass. An Operator declaration without a passing re-verification does not produce `CRITICAL_CLEARED` — the block persists.

The re-verification method is specific to the condition type:

| Condition | Operator declaration | SIL re-verification |
|---|---|---|
| `DRIFT_FAULT` | Declares Memory Store corrected | Re-executes Semantic Probes against Memory Store |
| Identity Drift | Declares structural files corrected | Recomputes structural file hashes against Integrity Document |
| `SEVERANCE_PENDING` | Acknowledges skill removal | Invokes `skill_audit` as a read-only Worker Skill; confirms index integrity |
| `SIL_UNRESPONSIVE` | — | See §10.7 |

`SIL_UNRESPONSIVE` activates the Passive Distress Beacon directly (§10.4) and does not produce a `CRITICAL_CLEARED` entry — resolution follows the beacon clearance procedure in §10.7.

After a passing re-verification, the SIL writes `CRITICAL_CLEARED` to `state/integrity.log` referencing the sequence number of the original Critical record. Unresolved conditions accumulate — each must be individually resolved before Phase 7 proceeds.

---

## 11. Decommission

Decommission is the permanent retirement of the entity. The Operator issues the decommission instruction via the FCP command line, specifying the disposition upfront:

```
fcp-core <entity-root> decommission --archive <dest-path>
fcp-core <entity-root> decommission --destroy
```

`--archive` and `--destroy` are mutually exclusive. If invoked outside an active session, FCP starts a silent session solely to process the `DECOMMISSION` envelope and run the Sleep Cycle — the interactive loop does not open. The entity must not resist, delay, or circumvent the instruction.

**Decommission sequence:**

1. FCP injects a `DECOMMISSION` envelope as the first stimulus of the current session — or the next session if none is active. FCP also writes a `DECOMMISSION_PENDING` record to `state/integrity.log` at this point. The CPE processes the envelope as a normal Cognitive Cycle and emits `closure_payload` + `session_close`, acknowledging the shutdown. FCP treats this as a normal session close.
2. FCP executes a complete Sleep Cycle — consolidating mnemonic state, running Semantic Drift probes, and committing any queued Evolution Proposals. The `SLEEP_COMPLETE` record is written to `state/integrity.log` as usual.
3. The SIL removes the session token. FCP then executes the Operator's chosen disposition:

**Archive** — FCP creates a gzip-compressed tar archive (`.tar.gz`) of the Entity Store at `<dest-path>`, with all paths relative to the entity root; volatile paths listed in the entity's `.gitignore` are excluded. The archived entity is inoperative — it cannot boot without explicit reactivation by an Operator — but its Integrity Chain, mnemonic records, and Imprint Record are fully preserved.

**Destroy** — FCP deletes all files in the Entity Store root. Before deletion, `state/integrity.log` is copied to an Operator-specified location as a final audit record.

**Partial decommission recovery.** A crash between Step 1 and Step 3 is detected at the next boot by the stale session token. Phase 2 (Crash Recovery) executes. FCP identifies the crash as decommission-in-progress by finding a `DECOMMISSION_PENDING` record in `state/integrity.log` with no subsequent `SLEEP_COMPLETE` — a regular crash has no such record. FCP presents the pending decommission to the Operator via terminal prompt for confirmation before proceeding.

---

## 12. Operator Interface

The Operator Interface is the FCP terminal — the primary interaction surface between the Operator and the entity. FCP presents the terminal prompt, accepts input, and displays output. There is no separate UI process; the interface is the platform itself.

### 12.1 Session Invocation

The Operator starts a session by invoking FCP from the command line, pointing it at the entity root:

```
fcp-core <entity-root>
```

FCP executes the full Boot Sequence. If the boot succeeds, the session begins and the interactive loop opens. If the boot fails at any phase, FCP displays the failure reason and exits without issuing a session token.

Decommission is invoked as a separate subcommand (§11):

```
fcp-core <entity-root> decommission --archive <dest-path>
fcp-core <entity-root> decommission --destroy
```

### 12.2 Interactive Loop

During an active session, the Operator types input at the terminal. FCP injects the input as a `MSG` ACP envelope into `io/inbox/`, which is consolidated into `session.jsonl` at the start of the next Cognitive Cycle. The CPE processes it and emits tool_use calls; FCP dispatches them, returns tool_results, and displays the CPE's narrative response to the Operator.

The loop continues until the Operator closes the session, the CPE emits a `session_close` action, or the SIL triggers a session close (context window critical threshold reached or Critical condition detected).

### 12.3 Slash Commands

FCP recognizes any terminal input beginning with `/` as a slash command. Two categories exist: platform commands, which FCP handles natively, and skill aliases, which dispatch to the EXEC.

#### 12.3.1 Platform Commands

Platform commands are FCP-native operations that do not pass through the EXEC. Most are available at any time — including outside an active session and during the Sleep Cycle. Commands annotated *(requires active session)* are unavailable outside a live session and during the Sleep Cycle.

```
/help                        — display available commands and their status
/status                      — display the entity monitoring panel; five fixed sections:
                               ENTITY (entity_id, active model, HACA profile version);
                               SESSION (status active/inactive, cycle count, tool_use calls
                               in current session, context budget as percentage of configured
                               limit, elapsed time since session start);
                               INTEGRITY (last integrity chain entry seq and type, last
                               heartbeat result and elapsed time, pending notification count,
                               pending Evolution Proposal count);
                               HEALTH (consecutive crash count, last crash timestamp,
                               consecutive skill failure count);
                               WORKSPACE (active workspace_focus path, or unset if not
                               configured); layout is implementation-defined
/verbose [on|off]            — toggle verbose output; when on, FCP displays tool_use calls,
                               component dispatch details, and tool_results in the terminal;
                               session-scoped, not persisted; if omitted, displays current state
/doctor [--fix]              — run entity health diagnostics; checks: presence of required
                               volatile directories (io/inbox/, io/spool/,
                               state/operator-notifications/, /tmp/fcp-stage/<entity_id>/), stale files
                               in io/spool/, session token state (stale token indicates
                               unreported crash), consecutive crash and skill failure counters,
                               and skill index consistency (all indexed skills have manifest
                               and executable present); --fix attempts correctable repairs:
                               recreates absent volatile directories, clears stale spool files
                               from io/spool/, resets consecutive crash counter if the current
                               boot passed Phase 2 cleanly, resets consecutive skill failure
                               counter if no failures are active; items that cannot be
                               auto-repaired (structural integrity violations, stale session
                               token) are reported with the required resolution action
/model list                  — list available CPE inference endpoints and display the active one
/model <name>                — switch the active CPE inference endpoint; Operator-exclusive;
                               updates cpe.backend in state/baseline.json, records a MODEL_CHANGE
                               entry to state/integrity-chain.jsonl, and updates
                               state/integrity.json atomically; takes effect at the next session
                               start
/exit | /bye | /close        — requires active session; triggers normal close (CPE emits
                               closure_payload + session_close)
/new | /clear | /reset       — requires active session; triggers a forced close (session token
                               revoked immediately, Sleep Cycle executes, Stage 1 no-op); FCP
                               starts a new boot sequence immediately after SLEEP_COMPLETE
/compact                     — requires active session; triggers MIL summarization (§8.1) on
                               demand — session.jsonl is condensed to its last 50%, then FCP
                               immediately re-assembles the CPE input context from the condensed
                               record and invokes the CPE; the session does not close and the
                               operation is transparent to the Operator
/skill list                  — list all skills in the Skill Index
/skill add <name> [params]   — requires active session; FCP injects a structured task into
                               the cognitive pipeline; CPE uses skill_create to stage the
                               skill under /tmp/fcp-stage/<entity_id>/<name>/, presents the result to the
                               Operator, and emits an evolution_proposal; Operator approves
                               via /endure approve <id> or at session close
/skill remove <name>         — remove a skill from the Skill Index (Operator-exclusive;
                               triggers Endure)
/skill audit <name>          — invoke skill_audit against the named skill
/endure list                 — list pending Evolution Proposals
/endure approve <id>         — approve a pending proposal (Operator-exclusive; triggers forced close)
/endure reject <id>          — reject a pending proposal (Operator-exclusive)
/endure sync [--remote]      — commit entity root structural content to version control;
                               FCP validates that every staged change corresponds to a
                               recorded Endure event before committing; with --remote,
                               also pushes to the configured remote
/inbox list                  — list pending notifications in state/operator-notifications/
/inbox view <id>             — display full content of a notification
/inbox dismiss <id>          — remove a notification; dismissal logged to state/integrity.log
/inbox clear                 — dismiss all pending notifications
/work set <path>             — set workspace_focus to the specified path (absolute or relative
                               to cwd); SIL validates the path before writing
                               state/workspace-focus.json; rejects paths inside entity root
/work clone <repo>           — clone a git repository into workspace_focus and set workspace_focus
                               to the cloned directory; SIL validates the resulting path
/work clear                  — unset workspace_focus; state/workspace-focus.json is removed
/work status                 — display the active workspace_focus path
/snapshot [path]             — create a copy of entity_root/ at the specified path; path must
                               be outside entity_root/; if omitted, FCP writes to a default
                               implementation-defined location; available at any time including
                               outside an active session
/memory [query]              — display the contents of the Memory Store; if a query is provided,
                               the display is filtered to entries containing the query string;
                               read-only, does not invoke the CPE or pass through EXEC
```

**Endure boundary.** A modification to entity root structural content is an Endure event — it must go through the Endure Protocol to be valid. Work done in `workspace_focus` (the operator's external project) is outside the Endure scope and is not tracked by the Integrity Chain. This boundary is enforced at every level: `/endure` and related commands operate on structural content only; the `commit` built-in skill operates on `workspace_focus` projects only. The two domains never overlap. When the CPE is operating in a workspace project context, it uses `commit` for version control — it has no visibility into `/endure sync` or the Endure domain. This separation is by design: FCP enforces it structurally so neither domain can accidentally operate in the other's scope.

Commands declared as `"operator_only"` are rejected if issued from any source other than the interactive terminal prompt.

#### 12.3.2 Skill Aliases

Skill aliases dispatch to a named skill via EXEC. They require an active session and follow session token routing. FCP resolves each alias against the `/command` alias map in `skills/index.json` — a flat lookup table from slash command name to skill name — and dispatches directly to EXEC, bypassing the cognitive pipeline. Action Ledger protection (§9.3) still applies for skills with irreversible side effects. Aliases not present in the map are rejected; they are never forwarded to the CPE.

The slash command registry is declared in `skills/index.json` as a `/command` alias map. Commands declared as `"operator_only": true` in the alias map are rejected if issued from any source other than the interactive terminal prompt.

### 12.4 Notifications

The Operator can inspect pending notifications at any time using the `/inbox` platform command (§12.3.1). Outside an active session, notifications are also accessible via:

```
fcp-core <entity-root> --notifications
```

FCP reads `state/operator-notifications/` in timestamp order and displays each entry. Notifications that require an explicit Operator response — Critical condition acknowledgements, pending Evolution Proposals — are presented via terminal prompt immediately when FCP starts a session, before the Boot Sequence proceeds past Phase 6.

---

## 13. Compliance

A deployment is FCP-compliant if and only if it satisfies all requirements below. Each item is non-negotiable — partial compliance is not compliance. Profile-specific items are annotated **[HACA-Core]** or **[HACA-Evolve]**; unannotated items apply to both profiles.

**Entity Layout**
- [ ] Entity root contains `boot.md`, `persona/`, `skills/`, `hooks/`, `io/`, `memory/`, `state/` as defined in §2.1; skill staging lives outside entity root at `/tmp/fcp-stage/<entity_id>/`.
- [ ] `skills/<name>/` contains custom and operator skill executables; operator-class skills are excluded from the `[SKILLS INDEX]` context block; custom skills are included.
- [ ] `memory/imprint.json` is present after FAP and never modified thereafter.
- [ ] `state/integrity-chain.jsonl` is append-only and never compacted or deleted.
- [ ] `state/sentinels/session.token` is written, revoked, and removed exclusively by the SIL.

**File Format Conventions**
- [ ] All `.json` writes are atomic: write to `.tmp` sibling, then `rename(2)` into place.
- [ ] All `.jsonl` lines are complete, self-contained ACP envelopes; existing lines are never modified or deleted.
- [ ] All `.msg` files are written via spool-then-rename and consumed (read then deleted) by FCP during inbox drain.
- [ ] No ACP envelope exceeds 4000 bytes; larger payloads are chunked.
- [ ] Multi-chunk transactions are complete only when `eof: true` has been received and all `seq` values from `1` through the final envelope's `seq` are present; incomplete transactions held across drain cycles are discarded after `fault.n_retry` cycles and logged to `state/integrity.log`.

**First Activation Protocol**
- [ ] FAP executes if and only if `memory/imprint.json` is absent.
- [ ] FAP pipeline follows the exact sequence defined in §4.
- [ ] `skills/index.json` is created during FAP Step 1 containing only skills with valid manifests and present executables.
- [ ] Imprint Record references the Skill Index and the Integrity Document.
- [ ] Genesis Omega is the SHA-256 digest of the finalized Imprint Record, written as the root entry of `state/integrity-chain.jsonl`.
- [ ] FAP is atomic: any step failure reverts all writes; the entity cannot enter a partially-initialized state.

**Boot Sequence**
- [ ] Passive Distress Beacon checked before any phase executes.
- [ ] Operator Bound verified at Phase 0; absent or invalid Bound → permanent inactivity.
- [ ] Both Operator Channel mechanisms verified at Phase 0; unavailable mechanisms → no session token issued.
- [ ] **[HACA-Core]** Topology verified as `transparent` at Phase 1; any other value → boot abort with no recovery path. **[HACA-Evolve]** Declared topology verified against Imprint Record at Phase 1; mismatch → boot abort.
- [ ] `watchdog.sil_threshold_seconds` verified ≤ `heartbeat.interval_seconds` at Phase 1; violation → boot abort.
- [ ] Integrity Chain validated from last checkpoint forward at Phase 3 Step 1.
- [ ] All tracked structural file hashes verified against `state/integrity.json` at Phase 3 Step 2.
- [ ] `skills/index.json` loaded (already verified in Phase 3) at Phase 4.
- [ ] Unresolved Critical conditions block session token at Phase 6; resolution requires Operator declaration and SIL independent re-verification per §10.8; `CRITICAL_CLEARED` written by SIL only after both steps pass.
- [ ] `PROPOSAL_PENDING` records presented to Operator via terminal prompt at Phase 6; Operator decision collected before session token is issued.
- [ ] Session token issued exclusively by the SIL at Phase 7.

**Cognitive Session**
- [ ] `io/inbox/` drained and consolidated into `session.jsonl` at the start of each Cognitive Cycle.
- [ ] CPE output uses tool_use calls (`fcp_exec`, `fcp_mil`, `fcp_sil`); at most one tool_use call per tool per response; duplicate tool_use calls for the same tool or malformed inputs are rejected and logged.
- [ ] Each tool_use input is a single action object or an array of action objects; all actions in a tool_use call are addressed to that tool's component.
- [ ] All inter-cycle communication flows through `io/inbox/`; no synchronous result-passing between cycles.

**Sleep Cycle**
- [ ] SIL revokes session token before Stage 0 begins.
- [ ] Stages execute sequentially; no two stages run concurrently.
- [ ] Semantic Drift probes run deterministic layer first; probabilistic layer (NCD Worker Skill) only when deterministic produces no conclusive result.
- [ ] FCP writes the Closure Payload atomically to `state/pending-closure.json` before the Sleep Cycle begins. Stage 1 reads and deletes the file. On normal close: all four fields (`consolidation`, `promotion`, `working_memory`, `session_handoff`) must be present and valid. On forced close: `state/pending-closure.json` is absent and Stage 1 is a no-op; the Sleep Cycle proceeds to Stage 2.
- [ ] `memory/session-handoff.json` always included in `working_memory` declaration.
- [ ] Session Store rotated at Stage 2 if exceeding `session_store.rotation_threshold_bytes`; rotation renames `memory/session.jsonl` to `memory/episodic/` and creates a new empty `memory/session.jsonl`.
- [ ] Each Evolution Proposal executed at Stage 3 only with a matching `EVOLUTION_AUTH` record.
- [ ] `SLEEP_COMPLETE` written to `state/integrity.log` before session token is removed.
- [ ] Session token removed by SIL immediately after `SLEEP_COMPLETE`.
- [ ] Staged cartridge directories in `/tmp/fcp-stage/<entity_id>/` are deleted by the SIL as step 8 of each promoted proposal's Endure execution.

**Memory Layer**
- [ ] MIL is the sole writer of mnemonic content to the Session Store and Memory Store.
- [ ] Pre-session buffer preserves FIFO ordering; silent overflow not permitted; discards logged to `state/integrity.log`.

**Execution Layer**
- [ ] EXEC operates exclusively against `skills/index.json`; absent skill requests logged and SIL notified.
- [ ] EXEC operates exclusively against `skills/index.json`; absent skill requests are rejected, logged to `state/integrity.log`, and the SIL is notified.
- [ ] `ACTION_LEDGER` write-ahead entry created before executing any skill with irreversible side effects.
- [ ] Unresolved `ACTION_LEDGER` entries surfaced to Operator via terminal prompt at next boot; never re-executed automatically.
- [ ] CPE-invoked Worker Skills receive all three fields: persona, context, and task.
- [ ] SIL-invoked Worker Skills are read-only; Action Ledger (§9.3) does not apply.
- [ ] `SEVERANCE_COMMIT` notification written to `state/operator-notifications/` immediately; unacknowledged at session close escalates to `SEVERANCE_PENDING` Critical condition; resolved at Phase 6 via dual-gate: Operator acknowledges + SIL invokes `skill_audit` Worker Skill to confirm index integrity.
- [ ] Native exec tools (`skill_create`, `skill_audit`, `file_read`, `file_write`, `agent_run`, `shell_run`, `web_fetch`) are hardcoded in the EXEC layer; they require no entry in `skills/index.json` and are always available to the CPE.
- [ ] `file_read` and `file_write` operate exclusively within `workspace_focus`; requests targeting any path outside `workspace_focus` are rejected.
- [ ] `skill_create` with `--base <name>` clones an existing skill's files from `skills/<name>/` into `/tmp/fcp-stage/<entity_id>/<name>/`; the clone is deleted by the SIL after Endure promotion.

**Integrity Layer**
- [ ] `state/integrity.log` is never compacted, archived, truncated, or deleted; retention is unbounded.
- [ ] All three drift categories (Semantic, Identity, Evolutionary) escalate directly to Critical under HACA-Core — no Degraded intermediate state.
- [ ] `IDENTITY_DRIFT` envelope produced by the SIL immediately upon detecting a structural file hash mismatch during the Heartbeat Vital Check; triggers Critical escalation.
- [ ] Heartbeat Vital Check includes full entity health scan as defined in §10.3.
- [ ] Reciprocal SIL Watchdog managed by FCP; EXEC and MIL check SIL heartbeat independently; unresponsive SIL writes `SIL_UNRESPONSIVE` to `state/operator-notifications/`, activates the Passive Distress Beacon, and halts FCP immediately.
- [ ] Evolution Proposals immediately written to `state/operator-notifications/`; decision collected via `/endure approve <id>` mid-session or via terminal prompt at normal session close.
- [ ] `/endure approve <id>` triggers immediate forced session close; SIL writes `EVOLUTION_AUTH` and Sleep Cycle begins without CPE involvement.
- [ ] Proposal outcome never returned to the CPE.
- [ ] Passive Distress Beacon is a plain file readable without running processes.
- [ ] Beacon cleared only after SIL (or FCP, if SIL was unresponsive) independently verifies resolution.

**Operator Interface**
- [ ] Platform commands (§12.3.1) execute natively without EXEC dispatch; available outside active session and during Sleep Cycle.
- [ ] Skill aliases (§12.3.2) resolved against `skills/index.json` alias map; dispatched directly to EXEC without CPE involvement; require active session.
- [ ] Operator-exclusive commands (`"operator_only": true`) rejected if issued from any source other than the interactive terminal prompt.
- [ ] `/skill add` injects a structured task into the cognitive pipeline; CPE stages skill via `skill_create` under `/tmp/fcp-stage/<entity_id>/`; result goes through normal evolution proposal flow.
- [ ] `/endure sync [--remote]` commits entity root structural content to version control; validates Endure event coverage before committing.
- [ ] `/work set` and `/work clone` write `state/workspace-focus.json` only after SIL validates the resulting path is outside entity root; rejected paths produce an error without modifying workspace_focus.
- [ ] SIL validates `state/workspace-focus.json` path at every Vital Check; path inside entity root or ancestor of entity root triggers Critical escalation.
- [ ] Pending notifications presented to Operator before Phase 6 completes at boot.
- [ ] Terminal prompt used for all synchronous Operator interactions requiring a response.
- [ ] `state/operator-notifications/` used for all asynchronous notifications not requiring immediate response.
- [ ] `/inbox` commands operate exclusively against `state/operator-notifications/`; dismissal removes the notification file and is logged to `state/integrity.log`; dismissing a notification does not resolve the underlying Critical condition.

**Decommission**
- [ ] `DECOMMISSION` signal injected as first stimulus; entity does not resist, delay, or circumvent.
- [ ] Complete Sleep Cycle executes before disposition (archive or destroy).
- [ ] `state/integrity.log` preserved to Operator-specified location before destroy disposition.