---
title: "Filesystem Cognitive Platform (FCP) — Core Profile"
short_title: "FCP-Core"
version: "1.0.0"
compliance: "HACA-Core v1.0.0"
status: "Draft"
date: 2026-03-11
---

# Filesystem Cognitive Platform (FCP) — Core Profile

## Abstract

The Filesystem Cognitive Platform (FCP) is a concrete implementation specification for HACA-compliant entities. Where HACA-Arch and HACA-Core define architecture and behavioral contracts, FCP defines exact implementation: directory layout, file formats, protocol envelopes, boot sequence, and operational procedures — all built exclusively on POSIX filesystem primitives, requiring no external databases, message brokers, or runtime daemons.

FCP-Core is the FCP profile targeting HACA-Core compliance. It is the reference implementation for the zero-autonomy profile: Transparent topology, sealed identity, operator-gated evolution. Every architectural requirement of HACA-Core has a direct, unambiguous mapping to a filesystem artifact or procedure defined in this document.

This document assumes familiarity with HACA-Arch and HACA-Core. It does not restate their concepts — it operationalizes them. A reader who knows what a Sleep Cycle is will find here exactly how it runs: which files are written, in what order, under what conditions, and what constitutes a valid completion. The level of detail is intentional — FCP-Core is meant to be implemented, not interpreted.

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
4. [First Activation Protocol](#4-first-activation-protocol)
5. [Boot Sequence](#5-boot-sequence)
   - 5.1 [Boot Manifest](#51-boot-manifest)
   - 5.2 [Crash Recovery](#52-crash-recovery)
   - 5.3 [Session Token Issuance](#53-session-token-issuance)
6. [Cognitive Session](#6-cognitive-session)
   - 6.1 [Context Assembly](#61-context-assembly)
   - 6.2 [Action Dispatch](#62-action-dispatch)
   - 6.3 [Cycle Chain](#63-cycle-chain)
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
10. [Integrity Layer](#10-integrity-layer)
    - 10.1 [Structural Verification](#101-structural-verification)
    - 10.2 [Drift Detection](#102-drift-detection)
    - 10.3 [Heartbeat and Vital Check](#103-heartbeat-and-vital-check)
    - 10.4 [Watchdog](#104-watchdog)
    - 10.5 [Evolution Gate](#105-evolution-gate)
    - 10.6 [Operator Channel](#106-operator-channel)
    - 10.7 [Passive Distress Beacon](#107-passive-distress-beacon)
11. [Decommission](#11-decommission)
12. [Operator Interface](#12-operator-interface)
13. [Compliance](#13-compliance)

---

## 1. Introduction

The Filesystem Cognitive Platform is built on a single premise: everything the entity needs to operate — identity, memory, skills, integrity state — lives in a directory. No external databases, message brokers, or runtime infrastructure. The host provides a POSIX filesystem and a language model inference endpoint; the entity provides the rest.

This approach is called Living off the Land. Rather than introducing infrastructure dependencies, FCP maps every architectural requirement to primitives the host already provides: files for state, directories for organization, atomic rename for consistency, append-only writes for audit trails. An FCP entity is portable by construction — moving the directory to a different host, pointed at any compatible inference endpoint, restores the entity to its last verified state.

HACA-Arch defines five components and their contracts — it does not define how they are orchestrated. FCP fills that gap. The FCP process is the cognitive cycle orchestrator: it drives the session loop, assembles context, invokes the CPE, parses its output, and dispatches to the appropriate component. The five HACA components operate under FCP's coordination. The SIL is not the orchestrator — its role is specifically the integrity layer: structural verification, drift detection, heartbeat, and evolution gate.

FCP is a platform, not a profile. It defines the filesystem conventions, wire formats, and operational procedures that any HACA-compliant entity can be built on. The active Cognitive Profile determines how those conventions are applied. FCP-Core implements HACA-Core: zero-autonomy, Transparent topology, sealed identity, operator-gated evolution. A future FCP-Evolve profile would build on the same platform with different operational rules. The platform layer — directory layout, file formats, ACP protocol, boot and sleep procedures — is shared. The profile layer — drift response, evolution authorization, channel policy — is what differentiates them.

This document specifies FCP-Core, the FCP implementation targeting HACA-Core compliance.

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
│   └── spool/                  — staging area for atomic writes
├── memory/                     — MIL exclusive write territory
│   ├── imprint.json            — imprint record (written once at FAP, never modified)
│   ├── episodic/               — archived session fragments
│   ├── semantic/               — semantic graph (concept nodes and links)
│   ├── active_context/         — working memory symlinks
│   ├── session.jsonl           — session store (cognitive record)
│   ├── working-memory.json     — working memory pointer map
│   └── session-handoff.json    — session handoff record
└── state/
    ├── baseline.json           — structural baseline
    ├── integrity.json          — integrity document
    ├── integrity.log           — integrity log (append-only)
    ├── integrity_chain.jsonl   — endure commit chain (append-only)
    ├── drift-probes.jsonl      — semantic probes
    ├── semantic-digest.json    — semantic digest
    ├── sentinels/              — runtime sentinels
    │   └── session.token       — session token (present = active or crashed session)
    ├── operator_notifications/ — operator channel output
    └── distress.beacon         — passive distress beacon
```

The `persona/`, `skills/`, and `hooks/` directories contain structural content — covered by the Integrity Document, changed only via Endure. The `io/` directory is the CPE's async stimulus queue — any component writes here when a result is relevant to cognition; the MIL drains it at the start of each cycle. The `memory/` directory is MIL-exclusive write territory; `imprint.json` is the exception — written once by the MIL during FAP and never modified thereafter. The `state/` directory is SIL territory: structural (`baseline.json`, `integrity.json`, `integrity_chain.jsonl`), integrity-exclusive (`integrity.log`, `distress.beacon`), and operational (`sentinels/`, `operator_notifications/`).

### 2.2 File Format Conventions

FCP uses four file formats, each with a distinct semantic:

**`.md`** — Markdown. Used for narrative content: persona definitions, boot protocol, skill documentation. These files are human-readable by design. Within FCP, `.md` files are structural — they are written once via Endure and not modified at runtime.

**`.json`** — JSON object. Used for structured, low-mutation content: configuration, manifests, pointer maps, integrity artifacts. Every write to a `.json` file must be atomic: write to a `.tmp` sibling, then rename into place. Direct in-place writes are not permitted.

**`.jsonl`** — Newline-delimited JSON. Used for append-only content: session store, integrity log, agenda. Each line is a complete, self-contained JSON object. Existing lines are never modified or deleted. Truncation or compaction of a `.jsonl` file is only permitted when explicitly authorized by the active procedure (session summarization, Sleep Cycle archival).

**`.msg`** — ACP envelope file. Used for inter-component messaging: each file in `io/inbox/` and `io/inbox/presession/` is a single JSON object representing one ACP envelope. `.msg` files are written atomically via the spool-then-rename pattern defined in the ACP protocol, and are consumed — read then deleted — by the MIL during inbox drain. Unlike `.jsonl`, they are not append-only and do not accumulate; their lifecycle ends at consumption.

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
| `actor` | string | Component that produced this envelope: `fcp`, `sil`, `mil`, `cpe`, `exec` |
| `gseq` | integer | Monotonically increasing counter, per actor, per session |
| `tx` | string | Transaction UUID; ties multi-chunk envelopes together |
| `seq` | integer | Position within the transaction (1-indexed) |
| `eof` | boolean | `true` if this is the last envelope in the transaction |
| `type` | string | Envelope type (see table below) |
| `ts` | string | ISO 8601 UTC timestamp |
| `data` | string | UTF-8 payload; structured payloads are JSON-serialized into this field |
| `crc` | string | CRC-32 of `data`, 8-character lowercase hex |

**Size limit.** No single ACP envelope may exceed 4000 bytes. Larger payloads must be chunked across multiple envelopes sharing the same `tx`, with incrementing `seq` and `eof: true` on the final chunk.

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
| `EVOLUTION_PROPOSAL` | SIL | Evolution Proposal forwarded to Operator |
| `EVOLUTION_AUTH` | SIL | Operator approval of an Evolution Proposal |
| `EVOLUTION_REJECTED` | SIL | Operator rejection of an Evolution Proposal |
| `PROPOSAL_PENDING` | SIL | Evolution Proposal persisted across session close |
| `ENDURE_COMMIT` | SIL | Structural write completed during Stage 3 |
| `SLEEP_COMPLETE` | SIL | Authoritative Sleep Cycle completion record |
| `ACTION_LEDGER` | FCP | Write-ahead entry for irreversible skill execution |
| `SIL_UNRESPONSIVE` | EXEC, MIL | Watchdog escalation bypassing SIL |
| `CTX_SKIP` | FCP | Context entry dropped due to budget exhaustion |
| `CRITICAL_CLEARED` | SIL | Operator-acknowledged resolution of a Critical condition |
| `CRON_WAKE` | FCP | Scheduled trigger injected at session start |
| `DECOMMISSION` | FCP | Decommission instruction injected at session start |

**The `io/` path.** The `io/inbox/` directory is used exclusively for asynchronous delivery — when a component cannot respond within the current cognitive cycle, or when an external stimulus arrives outside an active session. Components write to their private spool under `io/spool/` and rename atomically into `io/inbox/`. FCP drains the inbox at the start of each cycle. The synchronous cognitive chain — CPE output dispatched and resolved within a single cycle — does not pass through `io/`.

### 3.2 Structural Baseline

`state/baseline.json` declares all operational parameters for the entity. It is part of the structural baseline, covered by the Integrity Document, and cannot be modified outside the Endure Protocol. Under HACA-Core, all fields below are required — none may be absent or null.

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
    "max_entries": 50,
    "ordering": "fifo",
    "persistence": "disk"
  },
  "operator_channel": {
    "notifications_dir": "state/operator_notifications/"
  },
  "fault": {
    "n_boot": 3,
    "n_channel": 3,
    "n_retry": 3
  }
}
```

`cpe.topology` must be `"transparent"` — any other value causes boot abort with no session token issued.

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

`last_checkpoint` records the sequence number and digest of the most recent checkpoint entry in `state/integrity_chain.jsonl`. It is `null` before the first checkpoint is produced. At boot, the SIL reads this field to locate the verified anchor in the chain, enabling re-verification without traversing from genesis.

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

`memory/working-memory.json` is a pointer map written by the MIL at Sleep Cycle Stage 1. It declares the Memory Store artefacts the CPE considers relevant to the next session, in priority order. FCP loads it at boot to seed `memory/active_context/`.

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

The Closure Payload is the structured output produced by the CPE in the last Cognitive Cycle of a session. It is emitted as an `fcp-actions` block addressed to the MIL and must conform to the following schema:

```json
{
  "type": "closure_payload",
  "consolidation": "...",
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
| `working_memory` | array | Ordered list of Memory Store artefact paths declared relevant to the next session; bounded by `working_memory.max_entries` |
| `working_memory[].priority` | integer | Load priority — lower value means higher priority |
| `working_memory[].path` | string | Path relative to entity root; must resolve to an existing Memory Store artefact |
| `session_handoff` | object | Prospective record of pending tasks and next steps |
| `session_handoff.pending_tasks` | array | List of unfinished tasks to surface at the next session |
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

2. **Host environment capture** — The SIL verifies the declared CPE topology is `transparent` and that the execution boundary is enforceable. Identical to Phase 0 of the Boot Sequence (§5).

3. **Operator Channel initialization** — FCP verifies that `state/operator_notifications/` is writable and that the terminal prompt is available. The verification result is logged to `state/integrity.log`. If either mechanism is unavailable, FAP aborts.

4. **Operator enrollment** — FCP conducts the interaction with the Operator and collects name and email address. The SIL computes the `operator_hash` as a SHA-256 digest of these fields. The Operator Bound is held in memory — it is not written until Step 6.

5. **Integrity Document generated** — The SIL computes SHA-256 hashes of all tracked structural files and writes `state/integrity.json` atomically.

6. **Imprint Record finalized** — The MIL writes `memory/imprint.json` atomically. The Imprint Record contains: entity identity, Operator Bound (including `operator_hash`), references to the structural baseline, the Integrity Document, a reference to `skills/index.json` (the entity's authorized capabilities at activation), the HACA-Arch and HACA-Core versions under which the entity was initialized, and the activation timestamp.

7. **Genesis Omega derived** — The SIL computes the SHA-256 digest of the finalized Imprint Record and writes it as the root entry of `state/integrity_chain.jsonl`. This is the entity's permanent identity anchor.

8. **First session token issued** — The SIL writes `state/sentinels/session.token`. FAP is complete; the first session begins following the Boot Sequence from Phase 5 onward (§5).

**Atomicity.** FCP ensures FAP is atomic with respect to its own outputs. If any step fails, all writes produced by that FAP attempt are reverted and `memory/imprint.json` is not created. The entity cannot enter a partially-initialized state. FAP re-executes on the next boot.

---

## 5. Boot Sequence

The boot sequence executes on every startup after FAP. It is a deterministic gated pipeline orchestrated by FCP — each phase must pass before the next executes. Any failure aborts the boot; FCP notifies the Operator and does not issue a session token.

**Prerequisite — Passive Distress Beacon check.** Before any phase executes, FCP checks for `state/distress.beacon`. If active, the entire boot is suspended and no phase runs until the Operator explicitly clears the beacon condition.

**Phase 0 — Operator Bound Verification.**
The SIL reads `memory/imprint.json` and verifies the Operator Bound is present and well-formed. If absent or invalid, the entity enters permanent inactivity — no session token is issued until a valid Bound is established. This is not a recoverable fault; it is the correct behavior of an entity with no principal to serve.

FCP also verifies that both Operator Channel mechanisms are available: `state/operator_notifications/` is writable and the terminal prompt is accessible. If either is unavailable, no session token is issued — an entity that cannot reach its Operator cannot escalate Critical conditions.

**Phase 1 — Host Introspection.**
The SIL verifies the declared CPE topology is `transparent` and that the execution boundary is enforceable. If the topology is Opaque, or if the detected deployment does not match the declaration, boot aborts immediately — no recovery path exists and no session token is issued for this boot attempt.

The SIL also validates inter-parameter constraints in `state/baseline.json`. If `watchdog.sil_threshold_seconds` is greater than `heartbeat.interval_seconds`, boot aborts immediately — a watchdog threshold that exceeds the Heartbeat interval cannot detect SIL silence within a single Heartbeat window, violating HACA-Core §4.2.

**Phase 2 — Crash Recovery.**
The SIL checks for `state/sentinels/session.token`. Its presence at boot is the primary crash indicator. See §5.2.

**Phase 3 — Integrity Verification.**
Two-step verification executed by the SIL:

- **Step 1 — Chain anchor.** The SIL reads `state/integrity.json` to locate the chain anchor: the `last_checkpoint` field identifies the sequence number and digest of the most recent checkpoint. The SIL then reads `state/integrity_chain.jsonl` and validates the chain from that checkpoint forward. Any gap, hash mismatch, or missing authorization reference → boot aborts. If `last_checkpoint` is `null`, the SIL validates from genesis.
- **Step 2 — Structural files.** The SIL recomputes SHA-256 hashes of all tracked structural files and compares them against `state/integrity.json`. Any mismatch → boot aborts.

**Phase 4 — Skill Index Resolution.**
FCP loads `skills/index.json` — already verified in Phase 3 — and makes it available to the EXEC for the session. No additional manifest verification is performed at this phase; the Integrity Document hash check in Phase 3 is the authoritative verification gate.

**Phase 5 — Context Assembly.**
FCP assembles the Boot Manifest and the CPE input context. See §5.1.

**Phase 6 — Critical Condition Check.**
The SIL scans `state/integrity.log` for unresolved Critical conditions — `DRIFT_FAULT` and `ESCALATION_FAILED` records without a corresponding `CRITICAL_CLEARED`. If any are found, the SIL writes a notification to `state/operator_notifications/` and withholds the session token until the Operator explicitly acknowledges and resolves the condition via terminal prompt.

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
[MEMORY]        ← working-memory.json targets + active_context/ symlinks, priority order
[SESSION]       ← tail of session.jsonl, newest-first until context budget exhausted
[PRESESSION]    ← contents of io/inbox/presession/, arrival order
```

Working Memory entries are loaded at the highest priority — they are never dropped before other context fragments. Entries in `memory/working-memory.json` that point to absent Memory Store artefacts are silently dropped at Phase 5; each drop is logged as a `CTX_SKIP` envelope to `state/integrity.log`. This is not a Critical condition — missing Working Memory targets are an operational artifact, not a structural violation. Session history is loaded newest-first; when the context budget declared in `state/baseline.json` is exhausted, older entries are dropped and each skip is logged as a `CTX_SKIP` envelope to `memory/session.jsonl`.

### 5.2 Crash Recovery

A stale session token at boot means the previous Sleep Cycle did not complete. The SIL determines the exact recovery boundary from the Integrity Log.

Recovery procedure:

1. The SIL reads `state/integrity.log` and locates the most recent `SLEEP_COMPLETE` record.
2. If a partial Endure commit exists — an `ENDURE_COMMIT` marker with no subsequent `SLEEP_COMPLETE` — the SIL restores the pre-mutation snapshot created at Stage 3 entry.
3. The SIL scans `memory/session.jsonl` for unresolved `ACTION_LEDGER` entries — skills marked in-progress at crash time. Each unresolved entry is presented to the Operator via terminal prompt before the session token is issued. Unresolved entries are never re-executed automatically; the Operator decides whether to re-execute, skip, or investigate each one.
4. The SIL increments the consecutive crash counter in `state/integrity.log`. If the counter reaches `fault.n_boot` declared in the structural baseline, the SIL activates the Passive Distress Beacon and halts.
5. With the Entity Store in a verified state and all Action Ledger entries resolved, the SIL re-executes the Sleep Cycle from Stage 0. This completes the consolidation of the crashed session. The entity does not proceed to session token issuance until the Sleep Cycle has completed successfully and a `SLEEP_COMPLETE` record has been written to `state/integrity.log`.

On a clean boot (no stale token), the crash counter resets to zero.

### 5.3 Session Token Issuance

The SIL writes `state/sentinels/session.token`. This is the last gate — its completion marks the start of the session.

The **Heartbeat Protocol** begins. The SIL writes a `HEARTBEAT` envelope to `state/integrity.log` at the start of each Vital Check. A Vital Check triggers when either `T` completed Cognitive Cycles or `I` seconds have elapsed since the last check, whichever comes first. Both thresholds are declared in `state/baseline.json` and cannot be modified at runtime.

The **Reciprocal SIL Watchdog** activates. EXEC and MIL each monitor the interval since the last `HEARTBEAT` record in `state/integrity.log`. If the SIL has been silent beyond `watchdog.sil_threshold_seconds`, the component writes a `SIL_UNRESPONSIVE` envelope directly to `state/operator_notifications/`, bypassing the SIL entirely. The notification includes the component identity, the timestamp of the last observed heartbeat, and the elapsed interval.

---

## 6. Cognitive Session

A session begins when the SIL issues the session token and ends when FCP receives a `SESSION_CLOSE` signal — from the CPE, from the SIL (context window critical threshold reached), or from the Operator. FCP drives the session loop:

```
drain io/inbox/
  → consolidate to session.jsonl
  → assemble context
  → invoke CPE
  → parse fcp-actions block
  → dispatch to target component
  → collect result
  → next cycle
```

Each iteration of this loop is one Cognitive Cycle. The loop continues until a session-close signal is received.

A normal session close has a strict invariant: the final CPE response must contain exactly one Closure Payload followed by one `SESSION_CLOSE` signal, in that order, within the same `fcp-actions` block. If a session ends without this pair — whether due to process termination, signal interruption, or any other cause — the session is treated as a crash. The presence of a stale session token at the next boot is the crash indicator. The absence of this pair as the last CPE response in `memory/session.jsonl` is additional diagnostic context — it confirms the session did not close normally and helps determine how far the previous session progressed before termination.

### 6.1 Context Assembly

At the start of each Cognitive Cycle, FCP drains `io/inbox/` — reading all `.msg` files in arrival order, appending each as an ACP envelope to `memory/session.jsonl`, and deleting the `.msg` file. This consolidates all pending asynchronous stimuli into the session record before the CPE is invoked.

FCP then assembles the CPE input context. The assembly order follows the Boot Manifest defined in §5.1, with `[SESSION]` updated to include the newly consolidated envelopes. The context budget is re-evaluated at every cycle; if it has reached the critical threshold declared in `state/baseline.json`, FCP emits a `SESSION_CLOSE` signal before invoking the CPE.

### 6.2 Action Dispatch

A Cognitive Cycle ends when the CPE emits an `fcp-actions` block. What follows — skill execution, memory writes, integrity signals — is handled independently by each responsible component. The cycle does not wait for results; results arrive as stimuli in the next cycle via `io/inbox/`.

The `fcp-actions` block is a fenced code block with the `fcp-actions` tag, containing a JSON object with an `actions` array. Each entry addresses one component; multiple components may be addressed in a single block:

````
```fcp-actions
{
  "actions": [
    {"target": "exec", "type": "skill_request", "skill": "<name>", "params": {...}},
    {"target": "mil", "type": "memory_write", "content": "..."}
  ]
}
```
````

FCP rejects any response containing more than one `fcp-actions` block or a malformed payload. Rejected responses are logged to `session.jsonl` and surfaced to the Operator.

**Actions by target:**

`exec` — skill invocation:
```json
{"target": "exec", "type": "skill_request", "skill": "<name>", "params": {...}}
```

`mil` — memory operations:
```json
{"target": "mil", "type": "memory_recall", "query": "..."}
{"target": "mil", "type": "memory_write", "content": "..."}
```

`sil` — integrity and control signals:
```json
{"target": "sil", "type": "evolution_proposal", "content": "..."}
{"target": "sil", "type": "session_close"}
```

Each component writes its result to `io/inbox/` as an ACP envelope. FCP drains the inbox at the start of the next cycle, consolidates into `session.jsonl`, and the results become stimuli for the next invocation of the CPE.

### 6.3 Cycle Chain

A Cognitive Cycle is the atomic unit of cognition: stimulus received → context loaded → intent generated → intent dispatched. The cycle is complete when the `fcp-actions` block is emitted. What follows is the consequence of the dispatched intent, handled by the responsible components independently.

Composite operations are expressed as chains of consecutive cycles. Results from the previous cycle arrive in `io/inbox/`, are consolidated into `session.jsonl` at the start of the next cycle, and become part of the assembled context. The CPE reasons over accumulated stimuli and emits the next intent. There is no synchronous result-passing between cycles — all inter-cycle communication flows through the inbox.

A cycle chain may be interrupted by the SIL at any Vital Check boundary. If a Critical condition is detected, the SIL revokes the session token and the chain terminates. The Sleep Cycle executes immediately.

The Heartbeat Protocol and Vital Check are defined in §10.3.

---

## 7. Sleep Cycle

The Sleep Cycle is the ordered shutdown protocol that executes at every clean session close. It is the sole authorized window for structural writes. FCP orchestrates four sequential stages; each must complete before the next begins. No two stages execute concurrently. HACA-Arch §6.4 describes three canonical stages (memory consolidation → garbage collection → Endure execution); FCP adds a preparatory Stage 0 (Semantic Drift Detection) required by HACA-Core §4.2, which mandates drift detection during the Sleep Cycle. Stage 0 executes before any mnemonic or structural write occurs.

**Session token revocation.** Before Stage 0 begins, the SIL revokes the session token by appending `revoked_at` to `state/sentinels/session.token`. No further Operator-initiated Cognitive Cycles are dispatched after revocation. The token artefact remains in place throughout the Sleep Cycle as a crash indicator; the SIL removes it only after Stage 3 completes.

### 7.1 Stage 0 — Semantic Drift Detection

The SIL runs Semantic Probes against the accumulated Memory Store content. The CPE is inactive during this stage; no inference is required.

Probes are defined in `state/drift-probes.jsonl`. Each probe is executed in two layers:

**Deterministic layer** — the SIL applies string matching, pattern scanning, and content hash verification to the designated Memory Store excerpt. Each probe produces a conclusive pass or fail. A conclusive deterministic result skips the probabilistic layer for that probe.

**Probabilistic layer** — activated when the deterministic layer produces no conclusive result. The EXEC invokes a standalone comparison worker at the SIL's request. The worker computes Unigram NCD (Normalized Compression Distance using gzip) between the Memory Store excerpt and the probe's reference text: `NCD(x,y) = (C(xy) − min(C(x),C(y))) / max(C(x),C(y))`, where `C(z)` is the compressed size of `z`. A score above the probe's tolerance indicates drift. The comparison mechanism (`ncd-gzip-v1`) is declared in `state/baseline.json` and cannot be substituted at runtime.

After all probes run, the SIL updates `state/semantic-digest.json` with the current cycle's per-probe scores. Stage 0 checks both the current scores and the aggregate trend in the digest against the drift threshold declared in `state/baseline.json`.

If any probe fails:
1. The SIL logs a `DRIFT_FAULT` Critical condition to `state/integrity.log` with the probe ID, layer, divergence score, and the Memory Store excerpt that triggered it.
2. The SIL writes a `DRIFT_FAULT` notification to `state/operator_notifications/`.
3. The condition is marked unresolved. The next boot's Phase 6 will detect it and withhold the session token.

A `DRIFT_FAULT` does not halt the Sleep Cycle — Stages 1–3 still complete.

### 7.2 Stage 1 — Memory Consolidation

The MIL processes the Closure Payload produced in the final Cognitive Cycle of the session (§6). No further CPE invocation occurs during the Sleep Cycle.

The MIL processes each field:

- **`consolidation`** — appended to `memory/session.jsonl` as a `MSG` ACP envelope.
- **`working_memory`** — each declared path is validated against the Memory Store. Valid paths are written atomically to `memory/working-memory.json`. Invalid or absent paths are dropped and logged to `state/integrity.log`. The list is truncated to `working_memory.max_entries` if necessary.
- **`session_handoff`** — written atomically to `memory/session-handoff.json`, replacing the previous record.

The `active_context/` symlinks are rebuilt from the validated Working Memory pointer map at the next boot's Phase 5.

### 7.3 Stage 2 — Garbage Collection

The SIL performs bounded housekeeping against the Memory Store. No CPE invocation occurs in this stage.

- If `memory/session.jsonl` exceeds `session_store.rotation_threshold_bytes` declared in `state/baseline.json`, the SIL performs a crash-safe rotation: it writes the rotation intent to a temporary journal, renames `session.jsonl` to `memory/episodic/<year>/<timestamp>.jsonl`, creates a new empty `session.jsonl`, and removes the journal. If interrupted, the next boot detects the incomplete rotation via the journal and completes it before Phase 2.
- Stale `memory/active_context/` symlinks pointing to absent targets are removed.
- Temporary spool files older than one session in `io/spool/` are deleted.
- Entries in `io/inbox/presession/` beyond the capacity declared in `state/baseline.json` are discarded and logged to `state/integrity.log`.

### 7.4 Stage 3 — Endure Execution

The SIL processes all queued Evolution Proposals. For each proposal:

1. Verify that a matching `EVOLUTION_AUTH` record exists in `state/integrity.log` — an explicit Operator approval whose content digest matches the proposal exactly.
2. Create a pre-mutation snapshot of all files to be modified.
3. Apply the structural write atomically: write to a `.tmp` sibling, then `rename(2)` into place.
4. Recompute SHA-256 hashes for all modified tracked files.
5. Update `state/integrity.json` atomically.
6. If the number of Endure commits since the last checkpoint has reached `integrity_chain.checkpoint_interval`, produce the checkpoint atomically: extend the `state/integrity.json` write in step 5 to include the updated `last_checkpoint` field, and append the checkpoint entry to `state/integrity_chain.jsonl`. Both writes are part of the same Endure commit — the Integrity Document is the verifiable anchor; the chain entry carries the full chain data.
7. Log an `ENDURE_COMMIT` ACP envelope to `memory/session.jsonl`.

Proposals without a valid `EVOLUTION_AUTH` record are discarded and logged — they are never executed.

After all proposals are processed, the SIL writes the `SLEEP_COMPLETE` ACP envelope to `state/integrity.log`. This record is the authoritative Sleep Cycle completion boundary used by crash recovery. Immediately after, the SIL removes `state/sentinels/session.token`. The entity is now at rest.

---

## 8. Memory Layer

The memory layer is the MIL's exclusive write territory. No other component may write mnemonic content to the Session Store or Memory Store. Operator input, skill results, and CMI messages are stimuli that enter the cognitive pipeline — they do not bypass it to write directly to either store.

### 8.1 Session Store

`memory/session.jsonl` is the cognitive record of the active session. Every event relevant to cognition is recorded here as an ACP envelope: Operator messages, CPE responses, skill requests and results, memory operations, integrity signals, and context assembly events. The Session Store is append-only during the session — existing lines are never modified or deleted.

The MIL is the sole writer to `session.jsonl`. Components that produce results write to `io/inbox/` via the spool-then-rename pattern; FCP consolidates the inbox into `session.jsonl` at the start of each Cognitive Cycle.

The Session Store grows throughout the session. There are two mechanisms that manage its size, serving distinct purposes:

**Mid-session Session Summarization** — a corrective action triggered by the SIL when a Vital Check detects the Session Store approaching `session_store.rotation_threshold_bytes`. The SIL issues a corrective signal to the MIL; if re-verification fails after the corrective action, the condition escalates to Critical. This is a Degraded-class response (externally verifiable by the SIL), not a Sleep Cycle operation. It compresses or summarizes the physical content without semantic consolidation.

**Sleep Cycle Stage 2 rotation** — archival at every Sleep Cycle if the Session Store exceeds `session_store.rotation_threshold_bytes`. The SIL performs a crash-safe rotation: renames `session.jsonl` to `memory/episodic/<year>/<timestamp>.jsonl` and starts a fresh `session.jsonl`. This is structural housekeeping, not a corrective response.

The two mechanisms are independent. Mid-session summarization is reactive and bounded; Stage 2 rotation is routine and unconditional when the threshold is exceeded.

### 8.2 Memory Store

The Memory Store is the entity's consolidated long-term knowledge base. It persists across sessions and is the exclusive origin of persisted knowledge that informs cognition — no external source may override or replace its content outside the established pipeline.

The Memory Store comprises:

- `memory/episodic/` — archived session fragments, organized by date. Written by the MIL during Stage 2 rotation.
- `memory/semantic/` — semantic graph: concept nodes and links representing structured knowledge accumulated across sessions. Written by the MIL as directed by CPE `memory_write` actions.
- `memory/imprint.json` — the Imprint Record. Written once at FAP by the MIL; never modified thereafter.
- `memory/working-memory.json` — the Working Memory pointer map. Written by the MIL at Stage 1 of each Sleep Cycle.
- `memory/session-handoff.json` — the Session Handoff record. Written by the MIL at Stage 1, replacing the previous record.

`memory/active_context/` is the boot-time view into the Memory Store — a directory of symlinks seeded from `working-memory.json` at Phase 5, extended dynamically during the session via `memory_recall` actions. Symlinks are validated at boot; stale entries are removed at Stage 2.

### 8.3 Pre-Session Buffer

Stimuli received without an active session token — Operator messages delivered outside a session, scheduled triggers, or CMI signals — are held in `io/inbox/presession/` rather than dropped. Senders use the standard spool-then-rename pattern, renaming into `io/inbox/presession/` instead of `io/inbox/`.

The buffer is governed by the `pre_session_buffer` parameters declared in `state/baseline.json`:

- **Ordering** — FIFO. Arrival order is preserved and must not be altered.
- **Persistence** — disk. Entries survive a crash and are available at the next boot.
- **Capacity** — bounded by `pre_session_buffer.max_entries`. Silent overflow is not permitted: if the buffer is full, new stimuli are rejected and the SIL writes a notification to `state/operator_notifications/`. Any discarded stimulus is logged to `state/integrity.log`.

At Phase 5 of the Boot Sequence, FCP injects the buffer contents as the first stimuli of the new session, in arrival order, before any other context fragment.

---

## 9. Execution Layer

The execution layer is responsible for all skill dispatch and host actuation. The EXEC enforces the two-gate authorization model: no skill executes unless it passed both gates.

### 9.1 Skill Index

`skills/index.json` is the authoritative registry of skills the entity is authorized to use. It is part of the structural baseline, covered by the Integrity Document from the moment of FAP, and cannot be modified outside the Endure Protocol — with one exception: the SIL may remove a skill from the index as a maintenance operation when the skill's manifest is invalid or its executable is absent, without requiring a full Endure cycle, to avoid blocking the system.

When removing a skill as a maintenance operation, the SIL still performs an atomic integrity update: it rewrites `state/integrity.json` with the updated hash for `skills/index.json` and appends a `SEVERANCE_COMMIT` entry to `state/integrity_chain.jsonl`. This entry references the removed skill, the reason for removal, and the new `skills/index.json` hash. No `EVOLUTION_AUTH` record is required. A `SEVERANCE_COMMIT` without a corresponding `EVOLUTION_AUTH` is valid — it is distinguished from a normal Endure commit by its type field.

The Skill Index is established during FAP Step 1: the SIL validates every skill manifest present in `skills/` and writes `skills/index.json` containing only the skills whose manifests are well-formed and whose executables are present. `skills/index.json` is then included in the Integrity Document and referenced in the Imprint Record — the entity's authorized capabilities are sealed into its identity from first activation.

At Phase 3 of the Boot Sequence, `skills/index.json` is verified like any other tracked structural file: the SIL recomputes its hash and compares it against the Integrity Document. Any mismatch aborts the boot. At Phase 4, FCP loads the verified index and makes it available to the EXEC for the session.

The EXEC operates exclusively against `skills/index.json`. A skill invocation request for a skill absent from the index is rejected, logged to `state/integrity.log`, and the SIL is notified — an unexpected skill request may indicate a structural anomaly or an adversarial attempt.

### 9.2 Dispatch

Skill dispatch follows a two-gate model:

**Gate 1 — Skill Index.** Established at boot by the SIL. A skill not present in the runtime index never reaches Gate 2.

**Gate 2 — Manifest validation.** At dispatch time, the EXEC validates the request against the skill's `manifest.json`: declared permissions, required dependencies, and execution context constraints. A request that violates the manifest is rejected and logged. There is no SIL roundtrip per execution — Gate 1 provides the pre-authorization established at boot.

If a skill fails or times out, the EXEC writes a `SKILL_ERROR` or `SKILL_TIMEOUT` ACP envelope to `io/inbox/`. The result reaches the CPE as a stimulus in the next Cognitive Cycle. If a skill fails on `fault.n_retry` consecutive attempts, the EXEC writes a notification to `state/operator_notifications/`.

### 9.3 Action Ledger

Skills that produce irreversible side effects — writes to external systems, physical actuations, payments — must be covered by a write-ahead `ACTION_LEDGER` entry in `memory/session.jsonl` before execution begins. FCP writes the entry before dispatching to the EXEC; the EXEC resolves it — marking it complete or failed — after the skill returns.

The write-ahead entry records the intent before the skill executes. If a crash occurs between execution and Sleep Cycle consolidation, the unresolved entry is detected at the next boot's Phase 2 (Crash Recovery) and surfaced to the Operator. Unresolved entries are never re-executed automatically.

### 9.4 Worker Skills

Worker skills are skills that execute in isolation, outside the main CPE context window. They serve two distinct use cases.

**SIL-invoked workers** — bounded, deterministic operations requested directly by the SIL via EXEC, without CPE involvement. The primary example is the NCD comparison worker used by Stage 0 Semantic Drift Detection: invoked only when the deterministic probe layer produces no conclusive result, never as the primary check.

**CPE-invoked workers** — sub-agents dispatched by the CPE via a standard `skill_request` action. The CPE provides three fields in the request: a persona injection (the specialized identity for the worker), a context (the relevant knowledge the worker needs), and a task (the specific work to execute). The worker runs in isolation with that payload and returns its result through `io/inbox/` as a `SKILL_RESULT` envelope.

Worker Skills are for isolated, single-agent specialized execution. When the CPE requires coordinated work across multiple agents, the correct mechanism is the Cognitive Mesh Interface — Worker Skills must not be used as a substitute for collective coordination.

Worker skills are declared in `skills/index.json` and subject to the same two-gate authorization as any other skill. SIL-invoked workers return their results directly to the SIL; CPE-invoked workers route results through `io/inbox/`.

---

## 10. Integrity Layer

The integrity layer is the SIL's domain. It operates independently of the cognitive pipeline — it does not reason, it verifies. Its authority is structural: it monitors state, enforces boundaries, and escalates when violations are detected. It does not attempt to resolve conditions it cannot verify independently.

**Integrity Log retention.** `state/integrity.log` grows without bound and is never compacted, archived, or deleted. No truncation, rotation, or archival of any record is permitted under HACA-Core — this log targets regulated and auditable environments where complete record retention is a requirement. Log storage growth over time is an operational concern outside the entity's scope; the Operator is responsible for provisioning adequate storage infrastructure for the lifetime of the deployment.

### 10.1 Structural Verification

Structural verification runs at two points: at every boot (Phase 3) and at every Heartbeat Vital Check during the session.

At boot, the SIL performs a two-step verification. First, it validates the Integrity Chain: reads `last_checkpoint` from `state/integrity.json` to locate the chain anchor, then reads `state/integrity_chain.jsonl` and verifies the chain from that checkpoint forward — any gap, hash mismatch, or missing authorization reference aborts the boot. If `last_checkpoint` is `null`, the SIL validates from genesis. Second, it recomputes SHA-256 hashes of all tracked structural files and compares them against `state/integrity.json` — any mismatch aborts the boot.

During the session, each Vital Check repeats the structural file hash verification. A mismatch detected mid-session is an Identity Drift violation: the SIL revokes the session token immediately, logs a Critical condition to `state/integrity.log`, writes a notification to `state/operator_notifications/`, and the Sleep Cycle executes.

### 10.2 Drift Detection

The SIL monitors three drift categories. Under HACA-Core, all three escalate directly to Critical — there is no Degraded intermediate state, no tolerance threshold, and no corrective attempt before escalation.

**Semantic Drift** — detected during Sleep Cycle Stage 0 by running Semantic Probes against the Memory Store content. Two-layer execution: deterministic layer first (string matching, pattern scanning, content hashes); probabilistic layer (NCD via Worker Skill) only when the deterministic layer produces no conclusive result. Results are accumulated in `state/semantic-digest.json` across Sleep Cycles. A single-cycle threshold breach or an aggregate trend breach in the digest triggers a `DRIFT_FAULT` Critical condition. Stages 1–3 of the Sleep Cycle still complete; the next session is blocked at Phase 6.

**Identity Drift** — detected at every Heartbeat Vital Check by recomputing structural file hashes against the Integrity Document. A mismatch triggers immediate Critical escalation: session token revoked, Sleep Cycle executed.

**Evolutionary Drift** — detected at each Endure execution by verifying that every commit in the Integrity Chain references a valid `EVOLUTION_AUTH` record. A commit without a traceable authorization reference triggers immediate Critical escalation regardless of whether the structural change appears benign.

### 10.3 Heartbeat and Vital Check

The Heartbeat Protocol activates when the SIL issues the session token (§5.3) and runs for the duration of the session. A Vital Check triggers when either `T` completed Cognitive Cycles or `I` seconds have elapsed since the last check, whichever comes first. Both thresholds are declared in `state/baseline.json` and cannot be modified at runtime.

At each Vital Check, the SIL writes a `HEARTBEAT` envelope to `state/integrity.log` and performs a full entity health scan:

| Check | Condition | SIL action |
|---|---|---|
| Structural file hashes | Mismatch against Integrity Document | Critical → revoke token, Sleep Cycle |
| Background skill TTLs | TTL expired without registered result | `SKILL_TIMEOUT` to `io/inbox/`; surface to CPE |
| Session Store size | Approaching `session_store.rotation_threshold_bytes` | Degraded → corrective signal to MIL |
| Pre-session buffer | At or near `pre_session_buffer.max_entries` | Write to `operator_notifications/`; if `n_channel` failures → Beacon + halt |
| `io/inbox/` health | Stuck or malformed `.msg` files | Corrective signal to MIL |
| Pending schedules | Trigger overdue without execution | Write to `operator_notifications/`; if `n_channel` failures → Beacon + halt |

For Degraded conditions — those the SIL can verify independently by observing the component externally — the SIL issues a corrective signal and re-verifies after the component acts. If re-verification fails, the condition escalates to Critical. Conditions not externally verifiable escalate to Critical directly.

### 10.4 Watchdog

The integrity layer operates two watchdog mechanisms with distinct ownership: the SIL monitors skill executions, and the components monitor the SIL itself — with FCP providing the information necessary for that check.

**Skill timeout watchdog** — the SIL monitors active skill executions against the timeout declared in each skill's manifest. A skill that exceeds its timeout receives a `SKILL_TIMEOUT` envelope written to `io/inbox/`; the result reaches the CPE as a stimulus in the next cycle. Background skills declare a TTL in their manifest; a background skill whose TTL expires without a registered result is treated as an incomplete execution and logged to `state/integrity.log`. If a skill fails on `fault.n_retry` consecutive attempts, the EXEC writes a notification to `state/operator_notifications/`.

**Reciprocal SIL Watchdog** — FCP exposes the SIL's last heartbeat timestamp to EXEC and MIL at the start of each operation. Each component independently checks whether the interval since the last `HEARTBEAT` record in `state/integrity.log` exceeds `watchdog.sil_threshold_seconds` declared in `state/baseline.json`. If it does, the component escalates directly to the Operator via terminal prompt — bypassing both the SIL and `state/operator_notifications/`. The notification includes the component identity, the timestamp of the last observed heartbeat, and the elapsed interval. The watchdog threshold must not exceed the Heartbeat maximum interval `I`.

### 10.5 Evolution Gate

The Evolution Gate is the SIL's enforcement of Operator Primacy over structural change. Under HACA-Core, every Evolution Proposal requires explicit, per-proposal Operator authorization — implicit authorization is never valid.

When the CPE emits an `evolution_proposal` action, the SIL intercepts it. The session continues normally while the proposal is pending. The SIL writes the proposal to `state/operator_notifications/` immediately so the Operator is aware. At session close, FCP presents any pending proposals via terminal prompt and waits for an explicit decision on each. If the session closes before the terminal prompt can be shown — for example during an unattended session — the SIL persists the proposal as a `PROPOSAL_PENDING` record in `state/integrity.log` and FCP presents it at the start of the next session.

On explicit Operator approval, the SIL writes an `EVOLUTION_AUTH` record to `state/integrity.log` containing the Operator's identity, a timestamp, and a SHA-256 digest of the approved proposal content. The proposal is queued for execution at Sleep Cycle Stage 3. On rejection, the SIL writes an `EVOLUTION_REJECTED` record. In both cases, the outcome is never returned to the CPE.

A proposal that has not received an explicit Operator decision is never queued and never discarded by timeout. It remains in `PROPOSAL_PENDING` state until the Operator responds.

### 10.6 Operator Channel

The Operator Channel is not a component — it is a pair of platform primitives provided by FCP that components use directly to communicate with the Operator.

**Terminal prompt** — synchronous interaction. Used when a response is required before the platform can proceed: FAP enrollment, Evolution Proposal approval at session close, explicit Operator acknowledgement of a Critical condition. FCP opens the prompt, presents the content, and waits for the Operator's input. The response is returned to the requesting component.

**`state/operator_notifications/`** — asynchronous delivery. Used for notifications that do not require an immediate response: SIL escalations, `DRIFT_FAULT` reports, `SIL_UNRESPONSIVE` alerts, schedule anomalies. Components write notification files directly to this directory, each named with a UTC timestamp and a severity label. The Operator reads them at their own pace.

The `state/operator_notifications/` directory is declared in `state/baseline.json` and verified at every boot (Phase 0). If it is absent or not writable, no session token is issued. The terminal prompt is a platform primitive — always available when FCP is running.

Every use of either mechanism is logged to `state/integrity.log` as an ACP envelope with a timestamp, the invoking component, the condition, and the delivery status. If async delivery fails on `fault.n_channel` consecutive attempts, the SIL activates the Passive Distress Beacon.

### 10.7 Passive Distress Beacon

`state/distress.beacon` is a passive, persistent signal written by the SIL when autonomous recovery is no longer possible. It is activated in two conditions: `fault.n_boot` consecutive boot failures, or `fault.n_channel` consecutive Operator Channel delivery failures.

The beacon is a plain file — readable from the Entity Store without network connectivity, running processes, or any component active. Its presence at boot suspends the entire boot sequence before any phase executes.

While the beacon is active, the entity is in suspended halt: no session token is issued, no Cognitive Cycles execute, and no stimuli are processed.

The beacon is cleared only by the Operator. Clearance requires two steps: the Operator acknowledges the condition, and the SIL independently verifies that the underlying cause is resolved. Acknowledgement without resolution does not clear the beacon — the SIL must confirm the cause is addressed before lifting the suspended halt.

If the beacon was activated due to SIL unresponsiveness — detected by EXEC or MIL via the Reciprocal SIL Watchdog — the resolution verification cannot be delegated to the SIL. In this case, FCP performs the verification directly before lifting the suspended halt, presenting the result to the Operator via terminal prompt.

---

## 11. Decommission

Decommission is the permanent retirement of the entity. The Operator issues a decommission instruction; the entity must not resist, delay, or circumvent it.

**Decommission sequence:**

1. FCP injects a `DECOMMISSION` envelope as the first stimulus of the current session — or the next session if none is active. The CPE processes it as a normal Cognitive Cycle and produces a Closure Payload acknowledging the shutdown.
2. FCP executes a complete Sleep Cycle — consolidating mnemonic state, running Semantic Drift probes, and committing any queued Evolution Proposals. The `SLEEP_COMPLETE` record is written to `state/integrity.log` as usual.
3. The SIL removes the session token. FCP then executes the Operator's chosen disposition:

**Archive** — FCP creates a `tar` archive of the Entity Store, excluding all volatile paths listed in `.gitignore`. The archive is written to an Operator-specified path. The archived entity is inoperative — it cannot boot without explicit reactivation by an Operator — but its Integrity Chain, mnemonic records, and Imprint Record are fully preserved.

**Destroy** — FCP deletes all files in the Entity Store root. Before deletion, `state/integrity.log` is copied to an Operator-specified location as a final audit record.

**Partial decommission recovery.** A crash between Step 1 and Step 3 is detected at the next boot by the stale session token. Phase 2 (Crash Recovery) executes, and FCP presents the pending decommission instruction to the Operator via terminal prompt for confirmation before proceeding.

---

## 12. Operator Interface

The Operator Interface is the FCP terminal — the primary interaction surface between the Operator and the entity. FCP presents the terminal prompt, accepts input, and displays output. There is no separate UI process; the interface is the platform itself.

### 12.1 Session Invocation

The Operator starts a session by invoking FCP from the command line, pointing it at the entity root:

```
fcp <entity-root>
```

FCP executes the full Boot Sequence. If the boot succeeds, the session begins and the interactive loop opens. If the boot fails at any phase, FCP displays the failure reason and exits without issuing a session token.

### 12.2 Interactive Loop

During an active session, the Operator types input at the terminal. FCP injects the input as a `MSG` ACP envelope into `io/inbox/`, which is consolidated into `session.jsonl` at the start of the next Cognitive Cycle. The CPE processes it and emits an `fcp-actions` block; FCP dispatches the actions and displays the CPE's narrative response to the Operator.

The loop continues until the Operator closes the session, the CPE emits a `session_close` action, or the SIL triggers a session close (context window critical threshold reached or Critical condition detected).

### 12.3 Slash Commands

Slash commands allow the Operator to invoke skills directly without involving the CPE. FCP recognizes any input beginning with `/` as a slash command, resolves it against the skill registry in `skills/index.json`, and dispatches directly to EXEC — bypassing the cognitive pipeline entirely. Action Ledger protection (§9.3) still applies: FCP writes the write-ahead entry to `memory/session.jsonl` before dispatching any skill that declares irreversible side effects, regardless of dispatch origin.

```
/snapshot          — invoke the snapshot_create skill
/endure            — invoke the sys_endure skill
/memory            — invoke the memory_retrieve skill
```

The slash command registry is declared in `skills/index.json` as a `/command` alias map — a flat lookup table from slash command name to skill name. Commands not present in the map are rejected with an error message; they are never forwarded to the CPE.

### 12.4 Notifications

The Operator can inspect pending notifications at any time:

```
fcp <entity-root> --notifications
```

FCP reads `state/operator_notifications/` in timestamp order and displays each entry. Notifications that require an explicit Operator response — Critical condition acknowledgements, pending Evolution Proposals — are presented via terminal prompt immediately when FCP starts a session, before the Boot Sequence proceeds past Phase 6.

---

## 13. Compliance

A deployment is FCP-Core compliant if and only if it satisfies all requirements below. Each item is non-negotiable — partial compliance is not compliance.

**Entity Layout**
- [ ] Entity root contains `boot.md`, `persona/`, `skills/`, `hooks/`, `io/`, `memory/`, `state/` as defined in §2.1.
- [ ] `memory/imprint.json` is present after FAP and never modified thereafter.
- [ ] `state/integrity_chain.jsonl` is append-only and never compacted or deleted.
- [ ] `state/sentinels/session.token` is written, revoked, and removed exclusively by the SIL.

**File Format Conventions**
- [ ] All `.json` writes are atomic: write to `.tmp` sibling, then `rename(2)` into place.
- [ ] All `.jsonl` lines are complete, self-contained ACP envelopes; existing lines are never modified or deleted.
- [ ] All `.msg` files are written via spool-then-rename and consumed (read then deleted) by FCP during inbox drain.
- [ ] No ACP envelope exceeds 4000 bytes; larger payloads are chunked.

**First Activation Protocol**
- [ ] FAP executes if and only if `memory/imprint.json` is absent.
- [ ] FAP pipeline follows the exact sequence defined in §4.
- [ ] `skills/index.json` is created during FAP Step 1 containing only skills with valid manifests and present executables.
- [ ] Imprint Record references the Skill Index and the Integrity Document.
- [ ] Genesis Omega is the SHA-256 digest of the finalized Imprint Record, written as the root entry of `state/integrity_chain.jsonl`.
- [ ] FAP is atomic: any step failure reverts all writes; the entity cannot enter a partially-initialized state.

**Boot Sequence**
- [ ] Passive Distress Beacon checked before any phase executes.
- [ ] Operator Bound verified at Phase 0; absent or invalid Bound → permanent inactivity.
- [ ] Both Operator Channel mechanisms verified at Phase 0; unavailable mechanisms → no session token issued.
- [ ] Topology verified as `transparent` at Phase 1; Opaque topology → boot abort with no recovery path.
- [ ] `watchdog.sil_threshold_seconds` verified ≤ `heartbeat.interval_seconds` at Phase 1; violation → boot abort.
- [ ] Integrity Chain validated from last checkpoint forward at Phase 3 Step 1.
- [ ] All tracked structural file hashes verified against `state/integrity.json` at Phase 3 Step 2.
- [ ] `skills/index.json` loaded (already verified in Phase 3) at Phase 4.
- [ ] Unresolved Critical conditions block session token at Phase 6; Operator presented via terminal prompt.
- [ ] Session token issued exclusively by the SIL at Phase 7.

**Cognitive Session**
- [ ] `io/inbox/` drained and consolidated into `session.jsonl` at the start of each Cognitive Cycle.
- [ ] CPE output contains exactly one `fcp-actions` block; multiple blocks or malformed payloads are rejected and logged.
- [ ] Each `fcp-actions` action addresses exactly one target component per action entry.
- [ ] All inter-cycle communication flows through `io/inbox/`; no synchronous result-passing between cycles.

**Sleep Cycle**
- [ ] SIL revokes session token before Stage 0 begins.
- [ ] Stages execute sequentially; no two stages run concurrently.
- [ ] Semantic Drift probes run deterministic layer first; probabilistic layer (NCD Worker Skill) only when deterministic produces no conclusive result.
- [ ] Closure Payload requested from CPE at Stage 1; all three fields (`consolidation`, `working_memory`, `session_handoff`) processed by the MIL.
- [ ] `memory/session-handoff.json` always included in `working_memory` declaration.
- [ ] Session Store rotated at Stage 2 if exceeding `session_store.rotation_threshold_bytes`; rotation uses write-ahead journal.
- [ ] Each Evolution Proposal executed at Stage 3 only with a matching `EVOLUTION_AUTH` record.
- [ ] `SLEEP_COMPLETE` written to `state/integrity.log` before session token is removed.
- [ ] Session token removed by SIL immediately after `SLEEP_COMPLETE`.

**Memory Layer**
- [ ] MIL is the sole writer of mnemonic content to the Session Store and Memory Store.
- [ ] Pre-session buffer preserves FIFO ordering; silent overflow not permitted; discards logged to `state/integrity.log`.

**Execution Layer**
- [ ] EXEC operates exclusively against `skills/index.json`; absent skill requests logged and SIL notified.
- [ ] Two-gate dispatch enforced: Gate 1 (Skill Index), Gate 2 (manifest validation at dispatch time).
- [ ] `ACTION_LEDGER` write-ahead entry created before executing any skill with irreversible side effects.
- [ ] Unresolved `ACTION_LEDGER` entries surfaced to Operator via terminal prompt at next boot; never re-executed automatically.
- [ ] CPE-invoked Worker Skills receive all three fields: persona, context, and task.

**Integrity Layer**
- [ ] `state/integrity.log` is never compacted, archived, truncated, or deleted; retention is unbounded.
- [ ] All three drift categories (Semantic, Identity, Evolutionary) escalate directly to Critical under HACA-Core — no Degraded intermediate state.
- [ ] Heartbeat Vital Check includes full entity health scan as defined in §10.3.
- [ ] Reciprocal SIL Watchdog managed by FCP; EXEC and MIL check SIL heartbeat independently; unresponsive SIL escalates via terminal prompt.
- [ ] Evolution Proposals immediately written to `state/operator_notifications/`; decision collected via terminal prompt at session close.
- [ ] Proposal outcome never returned to the CPE.
- [ ] Passive Distress Beacon is a plain file readable without running processes.
- [ ] Beacon cleared only after SIL (or FCP, if SIL was unresponsive) independently verifies resolution.

**Operator Interface**
- [ ] Slash commands resolved against `skills/index.json` alias map; dispatched directly to EXEC without CPE involvement.
- [ ] Pending notifications presented to Operator before Phase 6 completes at boot.
- [ ] Terminal prompt used for all synchronous Operator interactions requiring a response.
- [ ] `state/operator_notifications/` used for all asynchronous notifications not requiring immediate response.

**Decommission**
- [ ] `DECOMMISSION` signal injected as first stimulus; entity does not resist, delay, or circumvent.
- [ ] Complete Sleep Cycle executes before disposition (archive or destroy).
- [ ] `state/integrity.log` preserved to Operator-specified location before destroy disposition.