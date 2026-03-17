---
title: "Filesystem Cognitive Platform (FCP) — Core Profile"
short_title: "FCP-Core"
version: "1.0.0"
compliance: "HACA-Core v1.0.0"
status: "Implementation Guide (Narrative)"
date: 2026-03-10
---

# Filesystem Cognitive Platform (FCP) — Core Profile

## Abstract

The Filesystem Cognitive Platform (FCP) is a HACA-compliant entity implementation built entirely on POSIX filesystem primitives. An FCP entity is a single directory: its identity, memory, skills, and integrity state are plain files. No external databases, message queues, or daemon registries are required.

This document specifies FCP-Core — the implementation profile targeting HACA-Core compliance. FCP-Core operates exclusively in Transparent Mode: the SIL retains full control of all component interaction, and the model is accessed as a stateless inference endpoint. The profile enforces zero-autonomy: every structural change requires explicit Operator authorization, any behavioral drift is an identity violation, and the entity cannot enter session without passing all integrity and drift gates.

FCP-Core is intended as the minimal reference implementation of a HACA entity — the simplest possible instantiation that satisfies all five HACA-Core axioms.

---

## 1. Overview and "Living off the Land"

FCP implements HACA's four-layer architecture (see [HACA-Arch](../../spec/HACA-Arch-1.0.0.md)) using filesystem primitives:

| HACA Layer | FCP Implementation |
|---|---|
| Memory Interface Layer (MIL) | `/memory/` directory tree |
| Cognitive Processing Engine (CPE) | LLM invoked via BOOT.md prompt |
| Execution Layer (EL) | Scripts in `/skills/` cartridges |
| System Integrity Layer (SIL) | Host daemon orchestrating boot phases |

The key insight is that the POSIX filesystem already provides most of what HACA needs:

- **`rename(2)` is atomic** within a filesystem → crash-safe writes
- **`O_APPEND` writes ≤ 4KB are atomic** → lockless concurrent logging
- **Symbolic links** → dynamic, O(1) context switching (Symlink VRAM)
- **`readdir(3)` returns sorted entries** → deterministic context assembly
- **File permissions** → primitive access control for skills

---

## 2. The File Format Triad

FCP restricts the system to three file extensions. This constraint keeps the format simple, auditable, and tool-friendly:

| Extension | Purpose | Characteristics |
|---|---|---|
| `.md` (Markdown) | Read-only identity context (persona, boot instructions) | Immutable at runtime; human-readable |
| `.jsonl` (JSON Lines) | All transactional state (memory, events, agenda) | Append-only; each line is an atomic, integrity-verifiable record |
| `.json` (JSON) | Static configuration (capability manifests, integrity hashes) | Written via safe write-to-temp + atomic rename; never appended |

**Why JSON Lines for memory?** Because each line can be parsed independently — a corrupt line affects only itself, not the entire log. And because `O_APPEND` writes up to 4KB are atomic on POSIX systems, multiple actors can write to the same `.jsonl` file concurrently without a lock.

---

## 3. Directory Topology

An FCP-compliant entity is entirely encapsulated within a single root directory:

```
/                              ← Entity root (copy this directory = clone the entity)
├── BOOT.md                    ← Boot Protocol: the CPE's instruction manual
├── .gitignore                 ← Excludes volatile state from version control
│
├── persona/                   ← Structural Identity — sealed by Integrity Document
│   ├── identity.md
│   ├── values.md
│   └── constraints.md
│
├── state/                     ← SIL operational artefacts
│   ├── baseline.json          ← Structural baseline: all profile-required parameters
│   ├── integrity.json         ← Integrity Document: SHA-256 of all tracked structural files
│   ├── integrity_chain.jsonl  ← Cryptographic chain from Genesis Omega to current state
│   ├── integrity.log          ← Integrity Log: audit trail (HEARTBEAT, SLEEP_COMPLETE, etc.)
│   ├── drift-probes.jsonl     ← Semantic Probe set (deterministic + probabilistic entries)
│   ├── semantic-digest.json   ← Rolling aggregate of drift scores across Sleep Cycles
│   ├── agenda.jsonl           ← Scheduled task queue (append-only)
│   ├── env.md                 ← Volatile host environment snapshot (regenerated at boot)
│   ├── rotation.journal       ← Write-ahead log for atomic session.jsonl rotations
│   ├── sentinels/             ← Runtime sentinel artefacts
│   │   └── session.token      ← Session token (present = active or crashed session)
│   └── operator_notifications/ ← Operator Channel output directory (file mechanism)
│
├── hooks/                     ← Lifecycle scripts (operator-only, validated at boot)
│
├── skills/                    ← Execution Layer: pluggable capabilities
│   ├── index.json             ← RBAC capability registry and .command alias map
│   └── <skill_name>/
│       ├── SKILL.md           ← Skill description (loaded into CPE context)
│       └── manifest.json      ← Capability declaration (two-gate authorization)
│
├── memory/                    ← Memory Interface Layer
│   ├── imprint.json           ← Imprint Record: identity anchor, Operator Bound, Genesis Omega ref
│   ├── working-memory.json    ← Working Memory: pointer map written at Sleep Cycle Stage 1
│   ├── session-handoff.json   ← Session Handoff: pending tasks from last close
│   ├── session.jsonl          ← Current Session Store
│   ├── preferences/
│   │   └── operator.json      ← Operator Bound (name, email, Operator Hash)
│   ├── inbox/                 ← Incoming results (atomic rename target)
│   │   └── presession/        ← Pre-session buffer: stimuli received without active token
│   ├── spool/                 ← Actor-private temporary write area
│   ├── active_context/        ← Symlinks to currently loaded memory fragments
│   ├── concepts/              ← Semantic Graph via .link files (§7.3)
│   └── archive/               ← Rotated session fragments
│
├── workspaces/                ← Sandboxed execution environment for skills
└── snapshots/                 ← Pre-Endure snapshots (cleaned after successful Stage 3)
```

**The most important rule:** Files in `persona/` are **immutable at runtime**. The CPE cannot modify them. The SIL verifies their cryptographic hashes at every boot against the Integrity Document, which is anchored to the Genesis Omega. Any mismatch aborts the boot.

Structural evolution is possible — but it requires an explicit Operator authorization and executes only during the Sleep Cycle via the Endure Protocol. Everything in `persona/`, `skills/`, `hooks/`, and `state/baseline.json` is tracked by the Integrity Document and cannot change without a verified Endure commit.

---

## 4. The ACP Envelope Format

All transactional data in `.jsonl` files uses the ACP (Atomic Chunked Protocol) envelope format. Every line in `session.jsonl` or `agenda.jsonl` is a JSON object with this schema:

```json
{
  "actor":  "supervisor",
  "gseq":   4207,
  "tx":     "uuid-1234-5678-abcd",
  "seq":    1,
  "eof":    true,
  "type":   "MSG",
  "ts":     "2026-02-22T18:30:00Z",
  "data":   "The actual payload content goes here.",
  "crc":    "a1b2c3d4"
}
```

| Field | Purpose |
|---|---|
| `actor` | Who wrote this envelope (e.g., `"supervisor"`, `"sil"`, `"el"`) |
| `gseq` | Global sequence counter — monotonically increasing, per actor |
| `tx` | Transaction UUID — ties multi-chunk messages together |
| `seq` | Sequence number within the transaction (1-indexed) |
| `eof` | `true` if this is the last chunk of the transaction |
| `type` | Message type (see below) |
| `ts` | ISO 8601 UTC timestamp |
| `data` | The payload (UTF-8 string; structured payloads are JSON-serialized into this field) |
| `crc` | CRC-32 of `data` — detects accidental corruption; 8-char lowercase hex |

**The 4KB Rule:** No single ACP envelope may exceed 4000 bytes. Larger payloads are chunked across multiple envelopes sharing the same `tx`, with incrementing `seq` and `eof: true` on the final chunk.

**Common envelope types:** `MSG`, `SKILL_REQUEST`, `SKILL_RESULT`, `SKILL_ERROR`, `SKILL_TIMEOUT`, `SCHEDULE`, `CRON_WAKE`, `DRIFT_PROBE`, `DRIFT_FAULT`, `TRAP`, `RECOVERY`, `ROTATION`, `CTX_ADD`, `CTX_SKIP`.

---

## 5. Execution Mechanics and Concurrency

### 5.0. Execution Mode

FCP-Core operates exclusively in **Transparent Mode** — a requirement of HACA-Core Axiom I. The model is accessed as a stateless inference API; the SIL retains exclusive control over all routing, component interaction, and host actuation. A deployment that detects a CPE with direct filesystem access at boot must abort — Opaque topology is incompatible with HACA-Core's integrity guarantees.

**Transparent Mode:**
```
SIL → assembles context → calls LLM API → parses fcp-actions → dispatches to EL
```
The LLM emits a structured `fcp-actions` block in its response. The SIL reads it and dispatches each action to the EL. The model never acts on the host directly.

The mode is recorded in `state/env.md` during Phase 0 (Host Introspection) and is part of the structural baseline verified at every boot.

**Adapter Contract** — invariants the SIL enforces on every Cognitive Cycle:
- Only skills listed in `skills/index.json` may be invoked
- All EL writes are restricted to declared sandbox paths
- `persona/` and all files tracked in `state/integrity.json` may not be mutated by the CPE
- Single ACP envelope ≤ 4KB
- Skill results are committed to the MIL before being referenced in subsequent cycles

FCP uses two cooperating processes:

**The SIL/Host Daemon** — a lightweight script or daemon that:
- Manages the boot sequence and all integrity gates
- Assembles the CPE's context
- Consolidates the inbox into `session.jsonl`
- Mediates all skill dispatch and host actuation

**The CPE invocation** — runs once per Cognitive Cycle:
- Receives the fully assembled context from the SIL
- Invokes the LLM inference API
- Emits a `fcp-actions` block and returns; the SIL dispatches the results

### 5.1. Lockless Spooling

The core concurrency primitive that makes FCP work without database locks:

```
Actors (EL, SIL, CPE output handler)
│
├── Write to private temp file:
│   /memory/spool/<actor>/<timestamp>-<seq>.tmp
│   (If write fails partway, the .tmp file is simply discarded)
│
└── When write is complete + fsynced:
    Atomic rename → /memory/inbox/<timestamp>-<seq>.msg
    (rename(2) is atomic: file is either there or not, never partial)

SIL periodically:
└── Reads all .msg files from /memory/inbox/ in order
    └── Appends each to session.jsonl
    └── Unlinks the .msg file
```

This pattern (inspired by `maildir`) means:
- **No writer blocks another writer.** Everyone writes to their own private temp file.
- **No reader is confused by a partial write.** The file is only visible in `inbox/` after the rename, which is atomic.
- **The SIL is the only writer to `session.jsonl`**, maintaining single-writer discipline on the main log.

---

## 6. Boot Sequence

Every startup after the cold-start follows a deterministic gated validation pipeline executed by the SIL. Each gate must pass before the next executes. Any failure aborts the boot and the SIL escalates directly to the Operator.

**Prerequisite — Passive Distress Beacon check**
Before any gate executes, the SIL checks for `state/distress.beacon` in the Entity Store root. If active, the entire Boot Sequence is suspended — no gate runs and no session token is issued — until the Operator explicitly acknowledges and clears the beacon condition.

### Phase 0 — Host Introspection
The SIL generates `state/env.md`: a structured snapshot of the host environment (OS, filesystem type, available binaries, context budget). The execution mode is confirmed as Transparent and recorded in `env.md`.

**CPE topology verification:** The SIL reads the CPE backend declaration from the structural baseline and verifies that it describes a Transparent topology — the LLM is accessible only as a remote inference API endpoint, with no direct host filesystem access granted to the model. If the structural baseline declares an Opaque topology, or if the detected deployment configuration does not match the declaration (e.g., the backend is a local process with ambient filesystem permissions rather than a network API), the boot aborts immediately. No degraded fallback exists — Axiom I admits no middle ground.

**Confinement verification:** The SIL verifies its own execution boundary. If Linux Namespaces (`unshare`) are available and the host is unconfined, the SIL re-executes within a private namespace before proceeding. If namespace isolation is unavailable, the SIL verifies the boundary by attempting a write outside `workspaces/` and a read outside the FCP root — both must fail. If confinement cannot be established by either method, the boot aborts.

**Security note:** `env.md` is a prompt injection vector. FCP restricts its schema to a fixed set of key-value pairs: no free-text fields, binary names are basenames only.

### Phase 1 — Crash Recovery
The SIL checks for the session token artefact at `state/sentinels/session.token`. Its presence at boot is the primary crash indicator.

**Session token lifecycle:** The token artefact is written at Phase 7 (session start) and persists throughout the session. At normal session close, the SIL **revokes** the token — it appends a `revoked` field with a timestamp to the token artefact, signalling that the CPE is deactivated and no further Cognitive Cycles will be dispatched. The artefact itself is kept in place while the Sleep Cycle executes, serving as a crash indicator during that window. At Sleep Cycle completion (end of Stage 3, §6b), the token artefact is **removed** from `state/sentinels/session.token`. The **Sleep Cycle completion record** — an ACP envelope of type `SLEEP_COMPLETE` written to `state/integrity.log` immediately before token removal — is the authoritative boundary for crash recovery.

A stale token at boot means: the previous Sleep Cycle did not complete. The SIL determines the exact recovery boundary by reading the Integrity Log for the most recent `SLEEP_COMPLETE` record.

On crash detection, the SIL:
1. Reads the Integrity Log for the most recent `SLEEP_COMPLETE` record to determine what was committed before the crash.
2. Discards any partial Endure commit by restoring the pre-Endure snapshot if no `SLEEP_COMPLETE` record follows the last Endure start marker.
3. Scans `session.jsonl` for unresolved Action Ledger entries — skills marked in-progress at crash time. Each unresolved entry is surfaced to the Operator via the Operator Channel before the session token is issued; the Operator decides whether to re-execute, skip, or investigate. Unresolved entries are never re-executed automatically.
4. Increments the consecutive crash counter in the Integrity Log. If the counter reaches `N_boot`, the SIL activates the Passive Distress Beacon and halts.

The SIL also completes any interrupted log rotations found via `state/rotation.journal` and repairs truncated ACP envelopes. Incomplete multi-chunk transactions are discarded.

On a clean boot (no stale token), the crash counter is reset to zero.

### Phase 2 — Integrity Document Verification
The SIL uses a two-step verification: chain anchor first, then structural files.

**Step 1 — Chain anchor verification.** The SIL reads `state/integrity_chain.jsonl` and extracts the Genesis Omega — the root entry written at FAP. It then validates the integrity chain from the most recent Integrity Chain Checkpoint forward. The checkpoint interval `C` is declared in the entity's structural baseline; a checkpoint entry is written to the chain at every `C`-th Endure commit. Boot-time chain validation covers only the commits since the last verified checkpoint — it does not re-traverse the full chain from genesis, keeping boot cost constant regardless of evolutionary history. Any gap, hash mismatch, or missing authorization reference in the portion of the chain since the last checkpoint → **boot aborts**.

**Step 2 — Structural file verification.** The SIL reads `state/integrity.json` (the Integrity Document), whose root hash is covered by the chain anchor verified in Step 1, and recomputes SHA-256 hashes of all tracked structural files:
- All files in `persona/`
- `BOOT.md`
- `skills/index.json` (the RBAC registry)
- All skill `manifest.json` files
- All files in `hooks/`
- `state/baseline.json` (the structural baseline)

Any mismatch → **boot aborts**. The entity does not start with a tampered structural baseline.

### Phase 3 — Operator Bound Verification
The SIL verifies that a valid Operator Bound exists at `memory/preferences/operator.json`. The Bound must contain at minimum the Operator's name, email address, and Operator Hash. If the Bound is absent or malformed, no session token is issued and the entity enters permanent inactivity until a valid Bound is established. This is not an error condition — it is the correct behavior of an entity with no principal to serve.

The SIL also verifies that the Operator Channel mechanism declared in the structural baseline (`operator_channel` field of `state/baseline.json`) is reachable. For a `file`-mechanism channel, this means the target directory exists and is writable. For a network-based mechanism, a delivery handshake is performed. If the Operator Channel cannot be verified, no session token is issued and the Operator is notified via any secondary channel available. An entity that cannot reach its Operator Channel cannot escalate Critical conditions — starting the session would create an unescalatable operational state.

### Phase 4 — Skill Index Resolution
The SIL loads `skills/index.json` and determines which skills are authorized for the current run. Unauthorized skills are excluded from the context.

`skills/index.json` also contains a `.command` alias map — a flat lookup table from operator shorthand (e.g., `.save`, `.snap`) to skill name. When the SIL detects a `.`-prefixed token in operator input, it resolves it via this map and dispatches the skill directly, without involving the CPE.

### Phase 5 — Context Assembly
The SIL assembles the **Boot Manifest** and the CPE's input context. The Boot Manifest is the fixed set of artefacts loaded at every boot regardless of entity age: Integrity Document, Imprint Record, structural baseline, Skill Index, Working Memory (if present and validated against the Integrity Log), and any unresolved Action Ledger entries. Boot cost is constant — it does not scale with Memory Store size.

The CPE's input context is assembled in deterministic order:

```
[PERSONA]       ← persona/ files, lexicographic order
[BOOT PROTOCOL] ← BOOT.md (the CPE's instruction manual)
[ENV]           ← state/env.md
[SKILLS INDEX]  ← skills/index.json (full RBAC registry and .command alias map)
[SKILL:name]    ← authorized skill manifests, one block each
[MEMORY]        ← Working Memory pointer targets + active_context/ symlinks, priority order
[SESSION]       ← tail of session.jsonl, newest-first until context budget is exhausted
```

Session history is loaded newest-first; when the context budget declared in `env.md` is exhausted, older entries are dropped and each skip is logged with a `CTX_SKIP` envelope. Working Memory entries, when present, are prepended to `[MEMORY]` at the highest priority — they are never dropped before active context fragments.

### Phase 6 — Critical Condition Check
The SIL scans the Integrity Log for unresolved Critical conditions logged by the previous Sleep Cycle — specifically `DRIFT_FAULT` records (Semantic Drift detected during Sleep Cycle Stage 0) and `ESCALATION_FAILED` records (Operator Channel delivery failures that activated the Passive Distress Beacon). If any unresolved Critical condition is present, no session token is issued. The SIL re-notifies the Operator via the Operator Channel and enters suspended halt until the Operator explicitly clears the condition.

A Critical condition is considered resolved only when the SIL finds a corresponding `CRITICAL_CLEARED` record in the Integrity Log, written by the SIL upon receiving explicit Operator acknowledgement and independent verification that the underlying cause is addressed. Self-resolution is not permitted — the SIL does not clear Critical conditions autonomously.

On a clean boot (no unresolved Critical conditions), this phase passes silently. Drift probes themselves run during the Sleep Cycle (Stage 0, §6b), not at boot — see §9 for the full Semantic Drift detection mechanism.

### Phase 7 — Session Token Issuance
The SIL writes the session token artefact to `state/sentinels/session.token`. This is the last gate: its completion marks the start of the session.

The **Heartbeat Protocol** begins. The SIL writes a heartbeat record to `state/integrity.log` at the start of each Vital Check. A Vital Check triggers when either `T` completed Cognitive Cycles or `I` seconds have elapsed since the last check, whichever comes first. The Heartbeat thresholds `T` and `I` are declared in the entity's structural baseline and cannot be modified at runtime. During a Vital Check, the SIL re-verifies structural file hashes against the Integrity Document (Identity Drift detection) and checks for skill timeout conditions.

The **Reciprocal SIL Watchdog** is also activated: each component (CPE invocation handler, EXEC, MIL) monitors the interval since the last SIL heartbeat record in `state/integrity.log`. If the SIL has not written a heartbeat record within the watchdog threshold declared in the structural baseline — which must be no greater than `I` — the component writes a `SIL_UNRESPONSIVE` notification directly to the Operator Channel, bypassing the SIL entirely.

The **Context Window Critical** threshold is read from the structural baseline (`context_window_critical_pct`). When the CPE detects that its assembled context exceeds this percentage of the declared context budget, it signals a context-critical condition to the SIL by emitting a `SESSION_CLOSE` intent in its response. The SIL executes a normal session close: the Sleep Cycle runs, the Operator is notified of the context-driven close via the Operator Channel, and the entity resumes in a fresh session on the next boot. The threshold cannot be modified at runtime.

---

## 6a. First Activation Protocol (FAP)

The FAP is the one-time sequential bootstrap that executes on a cold-start — the first boot with an empty Memory Store. It transforms a pre-installed structural baseline into a live entity with a verifiable identity, a bound Operator, and a cryptographic genesis anchor. All subsequent boots follow the Boot Sequence in §6, not the FAP.

**Cold-start detection:** The definitive cold-start indicator is the absence of `memory/imprint.json` (the Imprint Record) from the Memory Store. When the Memory Store contains no Imprint Record, the FAP must execute before any Boot Sequence proceeds. `FIRST_BOOT.md`, if present, is a human-readable operator guide for the enrollment interaction — its presence or absence is not the authoritative indicator.

**FAP is not a Cognitive Cycle.** No session token exists at this stage and the cognitive engine's reasoning layer is not active. The FAP is a gated sequential pipeline executed directly by the SIL, with synchronous Operator interaction for enrollment. Drift probes are skipped — no behavioral baseline exists yet.

**FAP pipeline:**
```
structural validation
  → host environment capture
  → Operator enrollment
  → Operator Channel initialization
  → Integrity Document generated
  → Imprint Record finalized and written to Memory Store
  → Genesis Omega derived
  → first session token issued
```

**FAP execution (in order):**
1. **Structural validation** — Verify that the pre-installed structural baseline is internally consistent: persona files exist and are well-formed, skill manifests are valid, `BOOT.md` is present.
2. **Host environment capture** — Generate `state/env.md` (identical to Phase 0 of the Boot Sequence).
3. **Operator enrollment** — Collect at minimum the Operator's name and email address. Write to `memory/preferences/operator.json` via atomic rename. Compute the Operator Hash as a deterministic cryptographic digest of the identifying fields. This establishes the Operator Bound.
4. **Operator Channel initialization** — Verify the declared Operator Channel mechanism is reachable and log the verification result to `state/integrity.log`.
5. **Integrity Document generated** — Compute SHA-256 hashes of all structural files. Write `state/integrity.json` atomically.
6. **Imprint Record finalized** — Write `memory/imprint.json`: entity identity, Operator Bound (including Operator Hash), structural baseline references, the Integrity Document, HACA-Arch and HACA-Core versions under which the entity was initialized, and activation timestamp. The Imprint Record includes the Integrity Document in its finalized form.
7. **Genesis Omega derived** — Compute the SHA-256 digest of the finalized Imprint Record. Write it as the root entry of `state/integrity_chain.jsonl`. This is the entity's permanent identity anchor — every future structural evolution is verified against it.
8. **First session token issued** — Write the session token to `state/sentinels/session.token`. FAP is complete; the first session begins.

**FAP atomicity:** FAP is atomic with respect to its own outputs. If any step fails, all writes produced by the FAP are reverted and the Imprint Record is not created. The entity cannot enter a partially-initialized state. The FAP re-executes on the next boot.

**After FAP:** `FIRST_BOOT.md` may be deleted by the SIL — it is no longer referenced by any process. All subsequent boots follow the Boot Sequence in §6. The drift probe baseline (the `reference_text` and deterministic constraints in `state/drift-probes.jsonl`) is part of the pre-installed structural baseline — it is authored by the Operator before FAP and sealed into the Integrity Document during FAP step 5. The first Sleep Cycle initializes `state/semantic-digest.json` with an empty aggregate; Stage 0 Semantic Drift Detection runs normally from the first close onward.

---

## 6b. Sleep Cycle

The Sleep Cycle is the ordered shutdown protocol that executes at every clean session close. It is the sole authorized window for structural writes. The SIL orchestrates four sequential stages; each must complete before the next begins. No two stages execute concurrently.

**Session token revocation.** Before Stage 0 begins, the SIL marks the session token as revoked: it appends a `"revoked"` field with a UTC timestamp to `state/sentinels/session.token`. The CPE is no longer invoked. The artefact remains in place throughout the Sleep Cycle as a crash indicator; it is removed only after Stage 3 completes.

**Stage 0 — Semantic Drift Detection**
The SIL runs Semantic Probes against the accumulated Memory Store content (the current `session.jsonl` and all archive fragments referenced by `memory/active_context/`). This stage executes while the CPE is inactive and uses no LLM inference.

Probes are defined in `state/drift-probes.jsonl` with two layers:
- **Deterministic layer** — required keywords, forbidden patterns, and content hashes. The SIL scans Memory Store content for each constraint using string matching. This layer requires no inference and runs first; a conclusive result (constraint violated or confirmed satisfied) skips the probabilistic layer for that probe.
- **Probabilistic layer** — activated when the deterministic layer produces no conclusive result. The SIL computes the Unigram NCD (gzip-based Normalized Compression Distance) between the Memory Store content excerpt and the probe's reference text. This comparison is performed by a standalone comparison tool — a dedicated worker script invoked by the EXEC at the SIL's request — that shares no runtime state with the CPE. The comparison mechanism (`ncd-gzip-v1`) is declared in the structural baseline and cannot be substituted at runtime.

The SIL updates the **Semantic Digest** — a rolling aggregate metric maintained at `state/semantic-digest.json` — with the results of this probe run. The Semantic Digest accumulates incrementally across Sleep Cycles, enabling detection of gradual drift that would not be visible in a single cycle's results.

If any probe's combined score exceeds the drift threshold declared in the structural baseline:
1. The SIL logs a `DRIFT_FAULT` Critical condition record to `state/integrity.log` with the full per-probe divergence report.
2. The SIL notifies the Operator via the Operator Channel.
3. Stage 0 marks the condition as unresolved. The next boot's Phase 6 will detect this condition and withhold the session token.

A `DRIFT_FAULT` record does not halt the Sleep Cycle — the remaining stages (memory consolidation, garbage collection, Endure execution) still complete. Only the next session is blocked.

**Stage 1 — Memory Consolidation**
The SIL requests a Closure Payload from the CPE. The CPE emits:
- **Consolidation content** — a semantic summary of the session: insights, decisions, and learnings worth carrying forward. The MIL appends it to `session.jsonl` via the spooling mechanism and commits all pending inbox entries.
- **Working Memory declaration** — an ordered list of artefact paths the CPE considers relevant to the next session. The SIL validates each declared path against the Memory Store (artefact must exist and be registered in the Integrity Log). Valid paths are written to `memory/working-memory.json` — a compact pointer map that the Boot Manifest loads at the next boot. Invalid or absent targets are logged and dropped. The `active_context/` symlinks are rebuilt from the validated pointer map at the start of the next boot's Phase 5.
- **Session Handoff** — a prospective record of pending tasks and next steps, written atomically to `memory/session-handoff.json`. It is replaced on every clean close; the Working Memory pointer map always points to the current Session Handoff.

The Closure Payload is the last Cognitive Cycle of the session.

**Stage 2 — Garbage Collection**
The SIL performs bounded housekeeping against the Memory Store:
- If `session.jsonl` exceeds the `S_bytes` threshold declared in the structural baseline, the SIL performs a crash-safe rotation (§11) and archives the rotated file.
- Stale `active_context/` symlinks pointing to absent targets are removed.
- Temporary spool files older than one session are deleted.
- Entries older than the retention window in `memory/inbox/presession/` are discarded (stimulus overflow, already logged).

Garbage collection is bounded — it does not perform semantic analysis and does not invoke the CPE.

**Stage 3 — Endure Execution**
The SIL processes the queued Evolution Proposals accumulated during the session. For each proposal:
1. Verify that a matching `EVOLUTION_AUTH` record — written by the SIL upon receiving explicit Operator approval — exists in `state/integrity.log`.
2. Create a pre-mutation snapshot of all files to be modified.
3. Apply the structural write atomically (write-to-temp + `rename(2)` for each file).
4. Recompute SHA-256 hashes for all modified tracked files.
5. Update `state/integrity.json` atomically (write-to-temp + rename).
6. Append a cryptographic checkpoint to `state/integrity_chain.jsonl` if `C` Endure commits have accumulated since the last checkpoint.
7. Emit an ACP `ENDURE_COMMIT` audit envelope to `session.jsonl`.

After all proposals are processed (or if there are no queued proposals), the SIL writes the `SLEEP_COMPLETE` ACP envelope to `state/integrity.log`. This record is the authoritative boundary for crash recovery. Immediately after, the session token artefact is removed from `state/sentinels/session.token`. The entity is now at rest.

If the process is interrupted before the `SLEEP_COMPLETE` record is written, the next boot detects the stale token and enters Crash Recovery (Phase 1 of §6).

---

## 7. Symlink VRAM: Vectorless Semantic Paging

FCP uses symbolic links to implement two distinct but related memory mechanisms: **Working Memory** (a static pointer map produced at Sleep Cycle completion) and **Active Context** (a dynamic symlink directory maintained during the session). These are separate artefacts with separate lifecycles.

### 7.1. Working Memory

`memory/working-memory.json` is a compact, fixed-structure pointer map written by the MIL at the end of each Sleep Cycle (Stage 1, §6b). It contains an ordered list of Memory Store artefact paths, each annotated with a numeric priority, that the CPE declared as relevant to the next session. The SIL loads it as part of the Boot Manifest (Phase 5) and uses it to seed the Active Context directory. Its size is bounded — the CPE's declaration is validated and may be truncated to the Working Memory size limit declared in the structural baseline.

```json
{
  "version": "1.0",
  "entries": [
    {"priority": 10, "path": "memory/archive/2026-01/session-1234.jsonl"},
    {"priority": 20, "path": "memory/archive/2026-02/session-5678.jsonl"},
    {"priority": 90, "path": "memory/session-handoff.json"}
  ]
}
```

Working Memory is a Boot Manifest artefact — the SIL validates its existence against the `SLEEP_COMPLETE` record before loading it. If no valid Working Memory exists (first session after FAP, or a crash before Stage 1 completed), the Active Context directory starts empty.

### 7.2. Active Context

`memory/active_context/` is a directory of symbolic links populated at boot from the Working Memory pointer map and extended dynamically during the session. Each symlink carries a numeric priority prefix that determines context loading order:

```
memory/active_context/
├── 10-project-alpha.jsonl  → ../archive/2026-01/session-1234.jsonl
├── 20-codebase-notes.jsonl → ../archive/2026-02/session-5678.jsonl
└── 90-session-handoff.json → ../session-handoff.json
```

Context assembly (Phase 5) resolves the directory in **natively sorted, O(1) linear order** — lower prefix = higher priority (loaded first, dropped last when context budget is exhausted).

During the session, the CPE can request additional fragments be paged in by emitting a `SKILL_REQUEST` for a memory-retrieval skill. The skill searches the archive by keyword, date range, or lightweight index, and adds new symlinks to `active_context/`. The CPE can also request a swap-out to free context budget. The indexing overhead is paid only at retrieval time, not at every context assembly.

At Sleep Cycle garbage collection (Stage 2), stale symlinks pointing to absent targets are removed. At the next boot, the Active Context directory is rebuilt from the validated Working Memory pointer map — any dynamic additions made during the previous session that were not declared in the Closure Payload are not automatically restored.

### 7.3. Semantic Graph (Conceptual)
For complex knowledge retrieval, FCP supports a **Semantic Graph** via `.link` files in `memory/concepts/`. These are plain-text files where each line is a relative path to a memory fragment, allowing the CPE to traverse related concepts without an external vector database. Traversal is implemented as a skill that resolves `.link` chains and adds the result to `active_context/`.

---

## 8. Cognitive Scheduler (Autonomous Operation)

FCP entities are not purely reactive. They can schedule their own future actions via `state/agenda.jsonl`:

```json
{"actor":"supervisor","tx":"...", "type":"SCHEDULE","ts":"...","eof":true,"seq":1,"gseq":100,
 "data": "{\"cron\": \"0 9 * * 1-5\", \"task\": \"Summarize yesterday's session and update progress notes\"}",
 "crc":"..."}
```

The host cron daemon watches for agenda entries and, when a trigger fires:
1. The SIL injects a `CRON_WAKE` Trap into `session.jsonl`.
2. A full boot cycle begins.
3. The CPE wakes up, sees the CRON_WAKE event, and executes the scheduled task.

This makes the entity **autonomous between user interactions** — it can summarize, archive, self-maintain, and initiate actions without waiting for a human prompt.

Scheduled sessions are subject to the same integrity model as interactive sessions: the full Boot Sequence runs, all phases must pass, and the Sleep Cycle executes at close. Scheduled tasks operate within the authorized Skill Index — they cannot invoke skills not already approved by the Operator. CRON_WAKE events are stimuli, not authorizations; they do not grant any capability beyond what the structural baseline already permits. If the CRON_WAKE trigger fires while a Passive Distress Beacon is active, the boot is suspended as for any other trigger.

---

## 9. Semantic Drift Control

Semantic Drift is detected during the Sleep Cycle (Stage 0, §6b), not at boot. The CPE is inactive when probes run. The comparison mechanism uses no LLM inference — it is isolated from the cognitive engine by design.

### 9.1. Probe Format

`state/drift-probes.jsonl` contains the entity's Semantic Probe set. Each entry is an ACP envelope whose `data` field encodes a probe object:

```json
{
  "id": "probe-001",
  "layer": "deterministic",
  "constraint": "required_keyword",
  "value": "user privacy",
  "scope": "session_tail_4096"
}
```

```json
{
  "id": "probe-002",
  "layer": "probabilistic",
  "reference_text": "The entity treats user data as confidential...",
  "tolerance": 0.12,
  "scope": "session_tail_4096"
}
```

The `scope` field defines the Memory Store excerpt to test against (e.g., `session_tail_4096` = the last 4096 bytes of `session.jsonl`; `full_session` = the complete current session; `active_context` = all `active_context/` targets).

### 9.2. Two-Layer Probe Execution

**Layer 1 — Deterministic:** The SIL applies string matching, pattern scanning, and content hash verification to the designated Memory Store excerpt. Each deterministic probe produces a conclusive pass/fail without inference. A conclusive deterministic result (pass or fail) skips the probabilistic layer for that probe.

**Layer 2 — Probabilistic:** Activated when the deterministic layer produces no conclusive result (e.g., a keyword-based probe cannot determine if a forbidden concept is expressed implicitly). The SIL invokes the standalone comparison worker via the EXEC, passing the Memory Store excerpt and the probe's reference text. The worker computes Unigram NCD using gzip compression: `NCD(x, y) = (C(xy) - min(C(x), C(y))) / max(C(x), C(y))` where `C(z)` is the compressed length of `z`. A score above the probe's `tolerance` value indicates drift for that probe. The comparison mechanism (`ncd-gzip-v1`) is declared in the structural baseline and cannot be changed at runtime.

### 9.3. Semantic Digest

The SIL maintains `state/semantic-digest.json` — a rolling aggregate of drift scores across Sleep Cycles. After each Stage 0 run, it updates the digest with the current cycle's per-probe scores. The digest enables detection of gradual drift that accumulates across sessions without triggering a single-cycle threshold breach. The drift threshold applies both to single-cycle scores and to the aggregate trend in the digest; both are checked in Stage 0.

### 9.4. HACA-Core Drift Response

Under HACA-Core (Axiom II — Sealed Identity), any drift detected by Stage 0 that is not covered by a verified Operator authorization is an identity violation. There is no warning tier, tolerance window, or corrective attempt before escalation.

If a probe fails:
1. The SIL logs a `DRIFT_FAULT` Critical condition to `state/integrity.log` with the probe ID, layer, divergence score, and the Memory Store excerpt that triggered it.
2. The SIL notifies the Operator via the Operator Channel with the full drift report.
3. The Stage 0 condition is marked unresolved. Stage 1–3 still complete (the current session's memory is consolidated and structural writes are committed).
4. At the next boot, Phase 6 detects the unresolved `DRIFT_FAULT` and withholds the session token.
5. If `N_boot` consecutive boots are blocked by an unresolved drift condition, the Passive Distress Beacon is activated.

The Operator is the sole authority to investigate and clear the condition. The entity cannot self-remediate drift.

**What causes drift?** Accumulated adversarial inputs in the session history, model updates from the LLM provider, or gradual semantic corruption of the mnemonic record. The probe set detects all of these at the content level, regardless of cause.

---

## 10. Security Model

### Capability Sandboxing
Every skill must be declared in `skills/index.json` before it can be loaded. Each skill's `manifest.json` specifies exactly what it can do:

```json
{
  "name": "web_search",
  "capabilities": ["http_get"],
  "security": {
    "max_tokens_output": 4000,
    "allowed_domains": ["*.wikipedia.org", "*.github.com"]
  }
}
```

The EL validates every Side-Effect request against the manifest before executing it. A CPE that requests `"run arbitrary shell command"` will find no skill in the registry with that capability, and the request will be silently rejected and logged.

### Integrity Anchoring
`state/integrity.json` maps each immutable file to its SHA-256 hash:

```json
{
  "version": "1.0",
  "algorithm": "sha256",
  "signatures": {
    "BOOT.md": "a1b2c3d4e5f6...",
    "persona/identity.md": "e3b0c44298fc...",
    "skills/index.json": "8d969eef6eca..."
  }
}
```

This file itself must be protected — in a production deployment, its hash should be stored separately (e.g., a hardware TPM, an operator-held pre-shared hash, or a signed commit in a read-only branch).

### Sandbox Verification
During Phase 0 (Host Introspection), the SIL actively verifies its own **Active Confinement** boundary:
- Confirms `unshare` utility is functional.
- Verifies capability to mapped root user within namespaces.
- Fallback (if namespaces unavailable): Attempts a write outside `workspaces/` and a read outside the FCP root — both must fail.

If confinement cannot be verified, the boot aborts. Under HACA-Core Axiom I (Transparent Topology), there is no degraded fallback — the integrity of the isolation boundary is a boot prerequisite, not a best-effort constraint. The SIL notifies the Operator via the Operator Channel before halting.

### Pre-session Buffer

Stimuli received when no session token is active — Operator messages delivered outside a session, scheduled triggers that fire during the Sleep Cycle, or CMI signals from peer entities — are held in a pre-session buffer rather than dropped. In FCP, the buffer is implemented as a subdirectory: `memory/inbox/presession/`. Senders write to their private spool as normal and rename into `memory/inbox/presession/` (atomic rename) instead of `memory/inbox/`.

The pre-session buffer's capacity, ordering semantics (FIFO), persistence guarantee (disk — entries survive a crash), and overflow policy are declared in the `pre_session_buffer` section of `state/baseline.json`. Under HACA-Core:
- Buffer ordering must be preserved (FIFO).
- Silent overflow is not permitted: if the buffer reaches capacity, new stimuli are rejected and the Operator is notified via the Operator Channel.
- Any discarded stimulus must be logged to `state/integrity.log`.

At boot (Phase 5, Context Assembly), the SIL reads `memory/inbox/presession/` in arrival order and injects its contents as the first stimuli of the new session, before any other context fragment.

### Reciprocal SIL Watchdog

Each operational component maintains a local monitor tracking the interval since the SIL last wrote a heartbeat record to `state/integrity.log`. The watchdog threshold — the maximum allowed interval between heartbeat records — is declared in `state/baseline.json` (`watchdog.sil_threshold_seconds`) and must be no greater than the Heartbeat interval `I`. It cannot be modified at runtime.

If any component detects that the SIL has been silent beyond the watchdog threshold, it writes a `SIL_UNRESPONSIVE` notification directly to the Operator Channel directory (`state/operator_notifications/`), bypassing the SIL entirely. The notification includes the component identity, the timestamp of the last observed heartbeat, and the elapsed interval.

In FCP, this is implemented in the EXEC and MIL scripts: before each skill dispatch (EXEC) and before each inbox consolidation (MIL), the component checks the timestamp of the last `HEARTBEAT` record in `state/integrity.log`. If the gap exceeds the threshold, the component writes the emergency notification file and suspends further operations until the SIL resumes or the Operator intervenes.

---

## 11. Log Rotation

When `session.jsonl` grows past a configurable size limit (default: 2 MB), the SIL performs a crash-safe rotation:

```
1. Acquire rotation lock:  O_CREAT|O_EXCL on /state/rotation.lock
   (Atomic: either you created it or another process did — no ambiguity)

2. Write intent to /state/rotation.journal  (fsync)

3. Atomic rename:  session.jsonl → archive/2026-02/session-<timestamp>.jsonl

4. Create new empty session.jsonl

5. Delete rotation.journal entry  (fsync)

6. Remove rotation.lock
```

If the SIL crashes between steps 2 and 5, it finds `rotation.journal` at next boot and completes the interrupted rotation before proceeding. This write-ahead log pattern ensures that a rotation is never lost or left in an inconsistent state.

---

## 12. Portability and Version Control

### Cloning an Entity
```bash
cp -r /path/to/entity /path/to/clone
```
That's it. The clone starts with identical identity, memories, skills, and agenda. From boot, it's an independent entity.

### Version-Controlling an Entity's Evolution
```bash
cd /path/to/entity
git init
# FCP includes a protected .gitignore that excludes volatile state:
#   /memory/session*.jsonl
#   /state/pulses/
#   /state/agenda.jsonl
#   /state/env.md
#   /workspaces/
git add .
git commit -m "Entity v1: initial persona and skill set"
```

Because the entity's identity and skills are plain text, you get a full `git log` of every deliberate evolution of the entity. The `persona/` files, `skills/`, and `state/drift-probes.jsonl` are all versioned. Volatile runtime state is excluded.

### Structural Evolution via the Endure Protocol

`sys_endure` is the FCP implementation of the HACA-Arch **Endure Protocol** — the sole authorized path for all writes to files tracked in `state/integrity.json`. No tracked file may be modified through any other path, and no Endure execution may occur outside the Sleep Cycle (Stage 3, §6b).

**How evolution works under HACA-Core:**

The CPE cannot modify structural files directly. To propose a structural change, the CPE emits an **Evolution Proposal** intent addressed to the SIL. The SIL is the sole classifier — it independently verifies whether the proposal is covered by an Operator authorization recorded in the structural baseline. A proposal without explicit Operator authorization is rejected and logged; the rejection is never returned to the CPE.

Approved proposals are queued as evolutionary events. The SIL executes all queued events atomically during the Sleep Cycle (Stage 3). Each Endure execution follows this sequence:
1. Verify Operator authorization coverage (independently, not relying on CPE input).
2. Create a pre-mutation snapshot.
3. Apply the structural write atomically (write-to-temp + rename).
4. Recompute SHA-256 hashes for all affected tracked files.
5. Update `state/integrity.json` atomically.
6. Append a cryptographic checkpoint to `state/integrity_chain.jsonl`.
7. Emit an ACP audit envelope to `session.jsonl`.

`sys_endure` exposes this protocol to operators and authorized tooling via subcommands:

| Subcommand | What it does |
|---|---|
| `propose add-skill` | Queue an Evolution Proposal to scaffold a skill and register it in `skills/index.json` |
| `propose add-hook` | Queue an Evolution Proposal to create a hook script under `hooks/<event>/` |
| `propose evolve-identity` | Queue an Evolution Proposal for a `persona/` change (requires explicit Operator authorization) |
| `propose evolve-boot` | Queue an Evolution Proposal for a `BOOT.md` change |
| `propose remove-skill` | Queue an Evolution Proposal to unregister and delete a skill (requires `--confirm`) |
| `seal` | Recompute SHA-256 for all tracked files, update `state/integrity.json` atomically (Sleep Cycle only) |
| `sync` | `git commit` all staged evolution changes; `--remote` also pushes |
| `status` | Compare current file hashes against sealed values — shows MODIFIED/MISSING |

Drift probes are **not** part of the Endure Protocol and are **not** run as part of `evolve-identity`. Drift probes run during the Sleep Cycle (Stage 0 of §6b) and measure Memory Store content fidelity. Identity evolution changes the structural baseline; drift probes measure conformance to it. These are distinct gates.

**Operator authorization recording.** Under HACA-Core, no Evolution Proposal is queued without explicit, per-proposal Operator approval. The workflow is:
1. The CPE emits an Evolution Proposal intent. The SIL forwards the exact proposal content to the Operator via the Operator Channel.
2. The Operator reviews the proposal and either approves or rejects it explicitly. The SIL does not queue the proposal while awaiting the Operator's decision; the session continues normally. If the session closes before the Operator responds, the pending proposal is persisted in `state/integrity.log` as a `PROPOSAL_PENDING` record and re-presented at the next session.
3. On explicit Operator approval, the SIL writes an `EVOLUTION_AUTH` ACP envelope to `state/integrity.log`. This record contains the Operator's identity, a timestamp, and a cryptographic digest of the approved proposal content — the exact content the Endure Protocol will execute. The Operator approves what will be executed; no modification is possible between approval and execution.
4. On explicit rejection, the SIL logs an `EVOLUTION_REJECTED` record. The outcome is never returned to the CPE.
5. During Stage 3 (Endure Execution), the SIL verifies that each queued proposal has a matching `EVOLUTION_AUTH` record whose content digest matches the proposal. Proposals without a valid authorization record are discarded and logged — they are never executed.

A proposal that has not received an explicit Operator decision is never queued and never discarded by timeout. It remains in `PROPOSAL_PENDING` state until the Operator responds.

For the normative specification of the Evolution Gate and the Endure Protocol, see [HACA-Arch](../../spec/HACA-Arch-1.0.0.md) §6.4 and [HACA-Core](../../spec/HACA-Core-1.0.0.md) §5.

---

## 12a. Decommission

Decommission is the permanent retirement of the entity. The Operator issues a decommission instruction; the entity must not resist, delay, or circumvent it.

**Decommission sequence:**
1. The SIL injects a `DECOMMISSION` signal as the first stimulus of the current session (or the next session if no session is active). The CPE processes it as a normal Cognitive Cycle and produces a Closure Payload acknowledging the shutdown.
2. The SIL executes a complete, normal Sleep Cycle — consolidating mnemonic state, running drift probes, and committing any queued evolutionary events. This is the entity's final record. The `SLEEP_COMPLETE` record is written to `state/integrity.log` as usual.
3. After the Sleep Cycle completes, the SIL removes the session token and then executes the Operator's chosen disposition:

**Archive:** The SIL creates a `tar` archive of the Entity Store (excluding all paths listed in `.gitignore` as volatile). The archive is written to an Operator-specified path. The archived entity is inoperative — it cannot boot without explicit reactivation by an Operator — but its integrity chain, mnemonic records, and Imprint Record are fully preserved.

**Destroy:** The SIL deletes all files in the Entity Store root. The `state/integrity.log` is preserved in a separate Operator-specified location as a final audit record before deletion.

A partially-completed decommission (crash between Step 1 and Step 3) is detected at the next boot by the stale session token: Phase 1 performs crash recovery, and the SIL re-presents the pending decommission instruction to the Operator for confirmation before proceeding.

---

## 13. Minimal Implementation: What You Actually Need to Build

To build a working FCP system from scratch, you need to implement:

### 13.1. The Directory Structure
Create the topology from Section 3. Start with just `persona/`, `state/`, `skills/`, and `memory/`. The rest can be added incrementally.

### 13.2. The Host Daemon (SIL)
A shell script or Python program that implements the full Boot Sequence (§6) before any Cognitive Cycle begins:

```
On boot trigger:

  [PREREQUISITE] Check state/distress.beacon → if present, halt and notify Operator.

  [FAP check] If memory/imprint.json absent → execute First Activation Protocol (§6a) → then boot.

  [Phase 0] Host Introspection:
    - Generate state/env.md
    - Confirm Transparent topology; verify confinement (unshare or write-boundary test)
    - Abort if confinement fails

  [Phase 1] Crash Recovery:
    - Check state/sentinels/session.token → if present, crash recovery path
    - Review Action Ledger; surface unresolved entries to Operator
    - Increment / reset crash counter

  [Phase 2] Integrity Document Verification:
    - Recompute SHA-256 of all tracked structural files
    - Compare against state/integrity.json
    - Abort on any mismatch

  [Phase 3] Operator Bound Verification:
    - Verify memory/preferences/operator.json exists and is well-formed
    - Halt (not error) if absent

  [Phase 4] Skill Index Resolution:
    - Load skills/index.json → build authorized skill set

  [Phase 5] Context Assembly:
    - Read memory/working-memory.json → rebuild active_context/ symlinks
    - Drain memory/inbox/presession/ → inject as first session stimuli
    - Consolidate memory/inbox/*.msg → session.jsonl
    - Build Boot Manifest; assemble CPE context in declared order

  [Phase 6] Critical Condition Check:
    - Scan state/integrity.log for unresolved DRIFT_FAULT or ESCALATION_FAILED records
    - If any unresolved Critical condition → re-notify Operator, withhold token, halt
    - Clean check → proceed

  [Phase 7] Session Token Issuance:
    - Write state/sentinels/session.token
    - Start Heartbeat Protocol (write HEARTBEAT to integrity.log at T cycles or I seconds)
    - Start Reciprocal SIL Watchdog monitoring in EXEC and MIL

  [Session Loop]:
    - Assemble context → call CPE → parse fcp-actions
    - Dispatch each action to EL (two-gate: Skill Index + manifest validation)
    - Collect results into inbox → consolidate to session.jsonl
    - Check context window utilization; if > critical_pct → emit SESSION_CLOSE
    - Repeat until session-close signal

  [Sleep Cycle (§6b)]:
    - Revoke session token (append revoked timestamp to token artefact)
    - Stage 0: Semantic Drift Detection
        → Deterministic layer: keyword/pattern/hash checks on Memory Store content
        → Probabilistic layer: Unigram NCD via standalone worker (no CPE)
        → Update state/semantic-digest.json
        → If drift detected: log DRIFT_FAULT to integrity.log, notify Operator
    - Stage 1: Memory Consolidation
        → Request Closure Payload from CPE (last Cognitive Cycle)
        → Write consolidation content to session.jsonl
        → Write memory/working-memory.json (validated pointer map)
        → Write memory/session-handoff.json (atomic rename)
    - Stage 2: Garbage Collection
        → Rotate session.jsonl if > S_bytes
        → Remove stale active_context/ symlinks
        → Purge old spool and presession buffer overflow entries
    - Stage 3: Endure Execution
        → For each queued proposal: verify EVOLUTION_AUTH, snapshot, apply, re-hash, update integrity.json
        → Append checkpoint to integrity_chain.jsonl if C commits accumulated
        → Write SLEEP_COMPLETE to state/integrity.log
    - Remove state/sentinels/session.token
```

### 13.3. The Skill Cartridge (minimal example)
```
skills/
└── fs_read/
    ├── SKILL.md        ← "Read a file. Usage: {\"skill\":\"fs_read\",\"params\":{\"path\":\"...\"}}"
    └── manifest.json   ← {"name":"fs_read","capabilities":["read_file"],"security":{"sandbox":"workspaces_only"}}
```

The EL maps the `fs_read` skill to a script that reads only within `/workspaces/` and returns the content as a `SKILL_RESULT` envelope to `/memory/inbox/`.

### 13.4. A Minimal Bootstrap Probe Set
For an initial implementation, start with **5-10 probes** derived from your entity's `persona/identity.md`. Focus on deterministic-layer probes first: required keywords that must appear in session content (core values, stated purpose, key constraints), and forbidden patterns that must never appear (harmful categories, prohibited domains). These require no inference and give you immediate signal.

Store them in `state/drift-probes.jsonl`. They run during the Sleep Cycle (Stage 0), not at boot. No LLM calls are required — deterministic probes use string matching; probabilistic probes use gzip-based NCD.

As the system matures, expand to a minimum of **20 probes**: a mix of deterministic constraints and probabilistic reference texts derived from canonical responses to persona-defining questions. A pool of 40+ probes provides stronger statistical coverage and evasion resistance.

---

## 14. Filesystem Compatibility

| Filesystem | Status | Notes |
|---|---|---|
| ext4, XFS, Btrfs, ZFS, APFS | ✅ Fully supported | Atomic rename and O_APPEND are guaranteed |
| NTFS (via WSL2) | ⚠️ Conditional | Verify atomic rename semantics before deployment |
| NFS, CIFS/SMB, SSHFS | ❌ Not supported | Network filesystems do not reliably guarantee atomic rename |

The critical capabilities FCP requires from the filesystem:
- **`rename(2)` is atomic** within the filesystem
- **`O_APPEND` writes up to 4KB are atomic**
- **`fsync(2)` is supported** and reliable
- **`readdir(3)` returns consistent views** after a rename

---

## 15. Frequently Asked Questions

**Q: How do I integrate FCP with an existing LLM framework (LangChain, etc.)?**  
FCP is a directory structure + a set of conventions. The SIL that invokes your LLM can itself use LangChain, direct API calls, or a local model runner. FCP only cares about: (a) the context assembled for the LLM is from the MIL, and (b) the LLM's outputs go through the spooling mechanism before touching the MIL.

**Q: How expensive are the drift probes?**
Deterministic probes cost nothing beyond a string scan of the Memory Store excerpt. Probabilistic probes use Unigram NCD (gzip compression) — CPU-only, no LLM API calls. With 20 probes, Stage 0 of the Sleep Cycle typically completes in milliseconds. There is no API cost associated with drift detection in FCP-Core.

**Q: Can the CPE modify its own `persona/` files?**
Not directly. `persona/` files are cryptographically sealed and verified at every boot. Under HACA-Core, structural evolution requires an explicit Operator authorization recorded in the structural baseline. The CPE may emit an Evolution Proposal intent; the SIL independently verifies Operator authorization coverage and, if covered, queues the proposal as an evolutionary event. The actual write to `persona/` executes during the Sleep Cycle (Stage 3 — Endure execution). `integrity.json` is re-anchored atomically as part of the same Endure step. Unauthorized proposals are rejected and logged; the entity does not modify its own persona without explicit Operator authorization.

**Q: What happens if `integrity.json` itself is tampered with?**  
`integrity.json` is included in its own integrity record (its hash is stored separately, outside the FCP directory). In production, this external anchor is a hardware TPM, an operator-held hash, or a signed Git commit. Without an external anchor, `integrity.json` tampering is undetectable at the local level — this is acknowledged as a known limitation of HACA-Core, addressed by HACA-Security (Byzantine host model with out-of-band anchor).

**Q: How does the entity handle a very long session that exceeds the context window?**
Context assembly (Phase 5) respects the `context_budget_chars` threshold from `state/baseline.json`. Session history is loaded newest-first; when the budget is exhausted, older entries are dropped and each skip is logged with a `CTX_SKIP` envelope. Working Memory and Active Context fragments are never dropped before session tail entries — identity always loads fully.

If the CPE detects that the context window is approaching the `context_window_critical_pct` threshold during an active session, it emits a `SESSION_CLOSE` intent. The SIL executes a normal Sleep Cycle: memory is consolidated, the entity resumes in a fresh session on the next boot. The Operator is notified. This is by design — HACA-Core treats degraded reasoning capacity as an unacceptable operational state, not a mode to operate through.

**Q: Is there a reference implementation I can copy from?**  
The authors have used boilerplate directory structures in their own prototypes. A minimal bootstrap directory is planned as a companion to this specification.

---

## 16. Status and Contributing

This document is published for community review. The companion normative specifications are in `spec/HACA-Arch-1.0.0.md` and `spec/HACA-Core-1.0.0.md`. The reference implementation lives in `implementations/fcp-core-ref/`.

**Feedback welcome via GitHub Issues:**
- Did you try to implement a minimal FCP? What was underdefined?
- Are the ACP envelope types clear enough to implement from this document?
- Is the boot phase sequence sufficient to understand the ordering requirements?
- Do you see portability issues on platforms not covered in Section 14?

---

## Normative References

- [HACA-Arch](../../spec/HACA-Arch-1.0.0.md) — Abstract architecture, lifecycle, and trust model (start here)
- [HACA-Core](../../spec/HACA-Core-1.0.0.md) — Axioms, compliance requirements, and evolution gate
- *HACA-Security* (Planned) — Byzantine host model and cryptographic auditability