Network Working Group                                          J. Orrico
Internet-Draft                                                  FCP Core
Intended status: Informational                         February 25, 2026
Expires: August 25, 2026


         FCP v1.0: Filesystem Cognitive Platform (Universal Edition)
                           draft-orrico-fcp-13

Abstract

   This document specifies the Filesystem Cognitive Platform (FCP) v1.0,
   a HACA-Core compliant implementation (draft-orrico-haca-core-03). FCP uses
   standard POSIX filesystem primitives as the canonical storage medium,
   implementing a "Prompt-as-an-App" paradigm: the entire cognitive
   system is defined by its directory contents. Cloning the directory
   clones the system.

   FCP targets HACA-Core compliance. It additionally implements optional
   security enhancements (HMAC-signed Traps, monotonic timestamp
   validation) that go beyond HACA-Core requirements but do not
   constitute HACA-Full compliance. Implementations requiring HACA-Full
   MUST additionally implement HACA-Security (draft-orrico-haca-
   security-02).

Status of This Memo

   This is a draft of the FCP specification. It is intended for
   review and comment by the FCP working group.

   This Internet-Draft is submitted in full conformance with the
   provisions of BCP 78 and BCP 79.

Table of Contents

   1.  Introduction
   2.  Conventions and Terminology
   2a. Execution Modes
       2a.1. Transparent Mode (EL-Mediated)
       2a.2. Opaque Mode (CPE-Native)
       2a.3. Mode Detection and Adapter Contract
   3.  Filesystem Prerequisites
       3.1. Mandatory Capabilities
       3.2. Supported Filesystem Classes
   4.  The File Format Triad
   5.  Universal Directory Topology
   6.  Execution Layer and Cognitive Mesh (EL & CMI)
       6.1. Skill Encapsulation
       6.1.1. Skill Invocation Protocol (Intent Envelopes)
       6.2. Access Control
       6.3. Cognitive Mesh
   7.  Concurrency, ACP, Traps, and Log Rotation
       7.1. The 4KB Rule and ACP
       7.2. Envelope Integrity
       7.3. Incomplete Envelope Recovery
       7.4. Context Parity After Recovery (HACA-Core Axiom V)
       7.5. System Traps and HMAC Signing
       7.6. Log Rotation
       7.6.1. Multi-Actor Concurrency
   8.  Asynchronous Autonomy (Cognitive Scheduler)
       8.1. Agenda
       8.2. Host Wakeup
   9.  System Integrity Layer (SIL) and Deterministic Boot
       9.1. Context Composition Protocol
       9.1.1. Context Budget
   9a. First Activation Protocol (FAP) — FCP Implementation
       9a.1. Cold-Start Detection
       9a.2. FAP Execution in FCP
       9a.3. FAP and Phase 5 (Drift Probes)
       9a.4. FAP Failure (Initialization Fault)
   10. Vectorless Cognitive Engine & Semantic Paging
       10.1. Retrieval via Link Files
       10.2. Semantic Garbage Collection (Swap Out)
       10.3. Active Context Index (Symlink VRAM)
       10.4. Semantic Paging (Swap In)
   11. Semantic Drift Control (HACA-Core Axiom VIII)
       11.1. Reference Set Storage
       11.2. Probe Schedule
       11.3. Measurement and Response
       11.4. Snapshots
   12. Cognitive Portability and Version Control
       12.1. Workspace Isolation
       12.2. Self-Improvement and Enduring
       12.3. Protected .gitignore
   13. Internal File Formats (Normative Schemas)
   14. Complexity Bounds
   15. Security Considerations
       15.1. Sandbox Verification
       15.2. RAG Poisoning Defense
       15.3. Trap Authenticity
       15.4. Link Traversal Boundaries
       15.5. Immutable File Protection
       15.6. Lifecycle Hooks Security
       15.7. HMAC Secret Lifecycle
       15.8. Monotonic Timestamp Validation
       15.9. Skill Directory Symlink Protection
       15.10. Cryptographic Auditability (HACA-Full Path)
   16. Normative References
   17. Author's Address

1.  Introduction

   Modern Autonomous AI Agents often rely on complex vector databases
   and resource-heavy network daemons. FCP v1.0 establishes a "Living
   off the Land" (LotL) approach: an entire cognitive system can be
   encapsulated within a single portable directory using native OS
   file operations. There is no external database, no daemon process,
   and no registry: the filesystem IS the application.

   Per HACA-Core Axiom I (Stateless CPE), the CPE is treated as a
   stateless function across execution cycles. All persistent state
   resides exclusively in the MIL (`/memory/`). The CPE receives its
   full context from the MIL at each invocation and returns outputs
   plus state deltas. Transient computational state (e.g., KV-cache)
   within a single execution cycle is permitted.

2.  Conventions and Terminology

   The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT",
   "SHOULD", "SHOULD NOT", "RECOMMENDED", "MAY", and "OPTIONAL" in this
   document are to be interpreted as described in RFC 2119.

   Terms defined in HACA-Core (System, Host, CPE, MIL, EL, SIL, CMI,
   Execution Cycle, Core Identity) apply unchanged.

   FCP-specific terms:

   o  ACP (Atomic Chunked Protocol): Envelope-based wire format for
      all transactional .jsonl files.
   o  Trap: A host-injected system event envelope carrying an HMAC
      signature.
   o  Swap Out: Compressing and archiving hot memories to cold storage.
   o  Rotation: Atomic archival of a .jsonl file at its size limit.
   o  CCP (Context Composition Protocol): The deterministic procedure
      by which the host assembles CPE input context from MIL state
      during Phase 4 (Section 9.1).
   o  Intent Envelope: An `fcp-actions` entry expressing a declarative
      intent (skill invocation, memory mutation, scheduling). The wire
      representation is mode-dependent (Section 2a).
   o  Adapter: The component that translates Intent Envelopes into
      concrete host operations. In Transparent Mode the Adapter is
      the SIL. In Opaque Mode the Adapter is the CPE itself.

2a. Execution Modes

   FCP v1.0 defines two first-class execution modes. Both modes MUST
   preserve all HACA axioms; they differ only in which entity holds
   the Adapter role and how Intent Envelopes are transported.

   The filesystem directory layout (Section 5), memory semantics
   (Sections 10–11), and behavioral invariants (Section 15) are
   identical in both modes. A system MUST be able to switch modes
   without modifying MIL state.

   2a.1. Transparent Mode (EL-Mediated)

   In Transparent Mode the CPE and the Adapter are physically separate
   processes. The CPE is accessed as a remote API (e.g., LLM inference
   endpoint). The Adapter (SIL process, `sil.sh`) orchestrates the
   execution cycle:

      a) SIL assembles context from the MIL (CCP, Section 9.1).
      b) SIL submits context to CPE API and captures CPE output.
      c) SIL parses the `fcp-actions` fenced block in CPE output.
      d) SIL translates each Intent Envelope into host operations.
      e) SIL writes results back to the MIL as ACP envelopes.

   The `fcp-actions` fenced block is the normative wire format for
   Intent Envelopes in Transparent Mode. Parsers MUST tolerate:
   o  Trailing whitespace on the opening fence line.
   o  CRLF line endings (normalize to LF before parsing).
   o  Case-insensitive tag matching (`fcp-actions`).
   o  Multiple `fcp-actions` blocks in a single CPE response
      (all blocks MUST be processed in order of appearance).
   o  Bare JSON lines with an `action` key outside fences as a
      fallback (SHOULD be treated as valid intents; allows models
      that cannot reliably produce fenced blocks to participate).

   Transparent Mode is RECOMMENDED for production deployments where
   the CPE provider, the host, and the MIL are controlled by
   different principals.

   2a.2. Opaque Mode (CPE-Native)

   In Opaque Mode the CPE has direct, native access to the host
   filesystem and execution environment. The CPE itself serves as
   the Adapter. This mode arises when the LLM is invoked through an
   environment that provides host tools directly (e.g., IDE AI
   assistants, agentic CLI frameworks, MCP filesystem servers).

   In Opaque Mode:
   a) The CPE reads BOOT.md directly from the filesystem and self-
      boots — no external SIL process is required to assemble context.
   b) The CPE detects its native tool set during boot (Section 2a.3).
   c) Intent Envelopes are resolved by mapping each `action` type to
      an equivalent native tool call:

      Intent action        | Native tool equivalent (examples)
      ---------------------|--------------------------------------
      skill_request        | Call the matching native tool/function
      memory_flag          | Create/remove symlink via native FS tool
      agenda_add           | Write to agenda.jsonl via native write
      log_note             | Append ACP envelope to session.jsonl
      send_reply           | Output text directly to the user/channel

   d) The `fcp-actions` fenced block SHOULD still be emitted in CPE
      output for auditability and compatibility. In Opaque Mode it
      serves as a semantic trace; native tool calls are the operative
      mechanism.
   e) MIL integrity guarantees (append-only, atomic rename, 4KB rule)
      MUST be upheld by the CPE when acting as Adapter.

   Opaque Mode is appropriate when CPE-native tool access provides
   equivalent or stronger isolation guarantees than a separate SIL.
   Implementers MUST document which integrity guarantees are
   delegated to the CPE and which are enforced externally.

   2a.3. Mode Detection and Adapter Contract

   The CPE MUST determine its execution mode at boot time (BOOT.md
   Phase 0). The RECOMMENDED detection heuristic:

      IF the CPE has access to native filesystem read/write tools
         AND the tools operate on a real, persistent path containing
             a valid FCP directory (BOOT.md, state/integrity.json)
      THEN: Opaque Mode
      ELSE: Transparent Mode (assume SIL is present)

   The CPE MUST record the detected mode in `state/env.md` as:

      execution_mode: transparent | opaque
      adapter: <sil | native:<tool_set_identifier>>

   If mode cannot be determined, the CPE MUST default to Transparent
   Mode and emit a `log_note` describing the ambiguity.

   Adapter Contract (applies to both modes):

      AC-1. Every Intent Envelope MUST be validated against the RBAC
            registry before execution.
      AC-2. Skill results MUST be written to the MIL as ACP envelopes
            before the CPE is notified (HACA-Core Axiom III, Mediated
            Boundary). In Opaque Mode the CPE MUST enforce this
            sequencing itself.
      AC-3. No direct mutation of `persona/` files is permitted
            regardless of mode. The `sys_endure` protocol applies.
      AC-4. The 4KB Rule (Section 7.1) MUST be enforced regardless
            of the native write mechanism used.
      AC-5. An Opaque Mode adapter MUST reject any intent that would
            write outside the FCP sandbox, identical to the sandbox
            enforcement required of the SIL (Section 15.1).

3.  Filesystem Prerequisites

   3.1. Mandatory Capabilities

   o  Atomic Rename: rename(2) MUST be atomic within the same
      filesystem (foundation for crash-safe writes and log rotation).
   o  POSIX Append Semantics: O_APPEND writes up to PIPE_BUF bytes
      MUST be atomic. The ACP 4KB Rule (Section 7.1) fits within this.
   o  fsync Support: fsync(2) or fdatasync(2) MUST be called after
      critical writes (integrity.json, rotation journals, traps).
   o  Directory Listing Consistency: readdir(3) MUST reflect completed
      renames.

   3.2. Supported Filesystem Classes

   o  Fully Supported: ext4, XFS, APFS, ZFS, Btrfs.
   o  Conditionally Supported: NTFS (via WSL2). MUST verify atomic
      rename semantics.
   o  Not Supported: Network filesystems (NFS, CIFS/SMB, SSHFS)
      unless atomic rename and append are verified during Phase 0.

4.  The File Format Triad

   FCP MUST restrict the system to three file extensions:

   o  .md (Markdown): Read-only immutable context (persona, boot).
   o  .jsonl (JSON Lines): Transactional layer. The ONLY format for
      continuous append. Each line is an integrity-verifiable ACP
      envelope.
   o  .json (Standard JSON): Static control (hashes, manifests).
      Loaded at boot. Writes use write-to-temp + atomic rename.

5.  Universal Directory Topology

   An FCP-compliant system MUST implement the following tree:

   /
   |-- BOOT.md                   # Boot Protocol Instructions
   |-- .gitignore                # Volatile State Exclusion Rules
   |-- state/                    # System Integrity Layer (SIL)
   |   |-- integrity.json        # Cryptographic map of immutable files
   |   |-- drift-probes.jsonl    # Canonical probe set (Axiom VIII)
   |   |-- agenda.jsonl          # Scheduler state (Append-only)
   |   |-- env.md                # Volatile host environment snapshot
   |   |-- rotation.journal      # Write-ahead log for rotations
   |   |-- rotation.lock         # Exclusive lock for rotation (transient)
   |   |-- sentinels/            # Dynamic Sentinel Streams (recovery counters,
   |   |                         #   sequence counter state) (§7.4, §13.4)
   |   `-- pulses/               # Heartbeats (.alive lockfiles)
   |-- hooks/                    # Lifecycle scripts (operator-only)
   |-- persona/                  # Identity and prompt fragments
   |   `-- (identity artifacts only — no operational data)
   |-- skills/                   # Execution Layer (EL)
   |   |-- index.json            # RBAC Registry
   |   `-- <skill_name>/         # Skill Cartridge
   |-- memory/                   # Memory Interface Layer (MIL)
   |   |-- inbox/                # Concurrency Spool Inbox
   |   |-- spool/                # Actor-specific temporary spools
   |   |-- session.jsonl         # Message Bus / Short-term Memory
   |   |-- active_context/       # Active context pointers (Symlinks)
   |   |-- archive/              # Hot Storage (YYYY-MM fragmentation)
   |   |-- cold_storage/         # Compressed archives
   |   `-- concepts/             # Semantic Graph via .link files
   |-- workspaces/               # Execution Sandbox
   `-- snapshots/                # Point-in-time state backups

6.  Execution Layer and Cognitive Mesh (EL & CMI)

   6.1. Skill Encapsulation

   Skills MUST be pluggable subdirectories under `/skills/`, each
   containing a `manifest.json` (name, execution type, capabilities,
   resource limits).

   Per HACA-Arch topology (Sections 3.4 and 3.5), skill results MUST be written to
   the MIL as ACP envelopes with `type: "SKILL_RESULT"` using the
   lockless spooling pattern (Section 7.6.1). The CPE MUST NOT receive
   results directly from the EL.

   6.1.1. Skill Invocation Protocol (Intent Envelopes)

   FCP defines skill invocation in terms of Intent Envelopes — a
   declarative, mode-agnostic representation of what the CPE wants to
   accomplish. The Adapter (SIL in Transparent Mode, CPE itself in
   Opaque Mode) translates Intent Envelopes into concrete operations.

   Intent Envelope schema (JSON object, one per line in `fcp-actions`):

      {
        "action":     "skill_request",
        "skill":      "<name>",          // MUST match RBAC registry
        "request_id": "<uuid>",          // for result correlation
        "timeout":    30,                // seconds; Adapter MUST enforce
        "params":     { ... }            // skill-specific parameters
      }

   Other supported `action` values:

      "memory_flag"  — add/remove a symlink in memory/active_context/.
      "agenda_add"   — schedule a future task (cron + description).
      "log_note"     — append an informational entry to session.jsonl.
      "send_reply"   — deliver a message to the operator or gateway.
      "trap"         — signal a system anomaly to the Adapter.

   Lifecycle (Transparent Mode — applies unchanged in Opaque Mode
   with native tool substitution per Section 2a.2):

   a) The CPE emits a `skill_request` Intent Envelope.

   b) The Adapter validates the request against the capability manifest
      and executes the skill within the sandbox.

   c) On success, the Adapter writes a `SKILL_RESULT` envelope to
      the `inbox/` spool with the same `request_id` in its `data`
      payload. On failure (execution error, permission denied,
      resource exhaustion), the Adapter writes a `SKILL_ERROR` envelope
      containing `request_id`, `error_code`, and `message`.

   d) On timeout, the Adapter MUST terminate the skill, write a
      `SKILL_TIMEOUT` envelope with the `request_id`, and the CPE
      SHOULD treat the action as failed on the next execution cycle.

   e) The CPE SHOULD discard results whose `request_id` does not
      match any pending request from the current execution context
      (stale results from previous cycles).

   6.2. Access Control

   Global RBAC (`/skills/index.json`) is resolved before skill-local
   manifests. Skills not in the RBAC registry MUST NOT be loaded.

   6.3. Cognitive Mesh

   Multiple FCP systems sharing a filesystem coordinate via the CMI
   extension point (HACA-Arch Section 6). Each system operates in its
   own namespace under `/state/pulses/`. Cross-system state access
   MUST be mediated through the RBAC registry. The concrete wire
   protocol is defined in HACA-CMI (draft-orrico-haca-cmi-01).

7.  Concurrency, ACP, Traps, and Log Rotation

   7.1. The 4KB Rule and ACP

   No ACP envelope SHALL exceed 4000 bytes (POSIX PIPE_BUF guarantee).
   Data exceeding 3500 bytes MUST be chunked into sequential envelopes
   sharing the same `tx`, with incrementing `seq` and a terminal `eof`.

   Reassembly: collect all envelopes by `tx`, order by `seq`,
   concatenate `data` fields. Complete only when `eof: true` is
   present. Incomplete transactions MUST be discarded at boot/rotation.

   7.2. Envelope Integrity

   Every ACP envelope MUST include a `crc` field (CRC-32 of the UTF-8
   `data` field). Checksum mismatches MUST discard the envelope.

   Note: CRC-32 detects accidental corruption only. It does not protect
   against intentional forgery. See Section 15 for HMAC-based Trap
   authenticity.

   7.3. Incomplete Envelope Recovery

   A crash may produce a partial JSON line. During boot or rotation:
   a) Read the last line of the .jsonl file.
   b) If JSON parsing fails, truncate and log recovery event.
   c) If parsing succeeds but CRC fails, truncate and log.

   7.4. Context Parity After Recovery (HACA-Core Axiom V)

   After any recovery event, the SIL MUST verify Context Parity:
   a) Execute drift probes (Section 11) immediately.
   b) Log $D_{probe}$ to `session.jsonl` as a `RECOVERY` envelope.
   c) If $D_{probe} > \epsilon$ (default: 0.05), inject a
      `RECOVERY_FAULT` Trap and refuse autonomous operation.
      (`RECOVERY_FAULT` is the FCP envelope type for the canonical
      Recovery Fault defined in HACA-Core Section 6.)
      Note: FCP uses $D_{probe}$ as the parity measurement method per
      HACA-Core Axiom V.b (behavioral probing, fallback for opaque CPEs).
      Implementations with full CPE output distributions MAY use KL
      Divergence per HACA-Core Axiom V.a instead.
   d) The SIL MUST persist a recovery attempt counter in a Dynamic
      Sentinel Stream (e.g., `/state/sentinels/recovery_attempts`). If
      the recovery attempt count exceeds the maximum limit (RECOMMENDED:
      3 consecutive attempts per HACA-Core Section 8.3), the system
      MUST enter a permanent Halted state.

   7.5. System Traps and HMAC Signing

   The SIL injects Traps into `session.jsonl` for fatal errors,
   timeouts, and lifecycle events (using its out-of-band audit writing channel). Actor: `"sil"`.

   Each Trap MUST include an `hmac` field (HMAC-SHA256 over
   `tx + seq + type + ts + data`). The `ts` field MUST be included
   in the HMAC input to prevent timestamp manipulation of Traps
   (see HACA-Security Section 6). The signing secret MUST be stored
   outside the FCP directory and MUST NOT be accessible to the CPE.
   The SIL MUST reject any `"sil"` envelope without valid HMAC.

   Note: HMAC Trap signing is an FCP security enhancement beyond
   HACA-Core requirements. It provides Byzantine-grade authenticity
   for host-injected events without requiring full HACA-Security
   compliance.

   7.6. Log Rotation

   When a .jsonl file exceeds its size limit (default: 2MB), the host
   MUST perform a journaled rotation:
   a) Acquire rotation lock: atomically create
      `/state/rotation.lock` via O_CREAT|O_EXCL. If the file
      already exists, check its mtime: if older than 60 seconds
      (RECOMMENDED TTL), treat it as stale (crash during rotation),
      remove it, and re-attempt acquisition. Otherwise, another
      actor is rotating — wait and retry.
   b) Write rotation intent to `/state/rotation.journal` + fsync.
   c) Atomically rename source to archive target.
   d) Create new empty source file.
   e) Delete rotation journal entry + fsync.
   f) Remove `/state/rotation.lock`.

   If `/state/rotation.journal` exists at boot, complete the
   interrupted rotation before proceeding. If `/state/rotation.lock`
   exists at boot without a corresponding journal entry, remove the
   stale lock (crash during lock acquisition).

   7.6.1. Multi-Actor Concurrency (Lockless Spooling)

   In Cognitive Mesh configurations (Section 6.3) or under high load,
   multiple actors may append to shared state concurrently. To
   guarantee strictly serialized semantic ordering without lock
   contention, FCP employs a lockless spooling pattern (inspired
   by `maildir`):
   
   a) Actors MUST write their ACP envelopes to a temporary, exclusive
      spool directory: `/memory/spool/<actor>/<timestamp>-<seq>.tmp`.
   b) Once the envelope write is complete and fsynced, the actor
      atomically moves it to the global inbox via rename(2):
      `rename(/memory/spool/<actor>/..., /memory/inbox/<timestamp>-<seq>.msg)`.
   c) The SIL exclusively processes the `inbox/` periodically,
      consolidating envelopes in strict temporal order into
      `session.jsonl`, and then unlinks the `.msg` files.

   HACA-Core Conformance Note: HACA-Arch Section 3.4 requires
   single-writer discipline per MIL namespace. FCP enforces this
   by designating the SIL as the aggregator. Concurrent actors write 
   only to their private spools and rely on the SIL to aggregate the 
   inbox sequentially into `session.jsonl`.

8.  Asynchronous Autonomy (Cognitive Scheduler)

   8.1. Agenda (`/state/agenda.jsonl`)

   Append-only crontab. Each entry is an ACP envelope with
   `type: "SCHEDULE"` containing a cron expression and task descriptor.

   8.2. Host and SIL Wakeup

   On cron trigger, the external Host wakes the system. The SIL then 
   injects a `CRON_WAKE` Trap (with HMAC) into `session.jsonl` and 
   triggers Boot.

9.  System Integrity Layer (SIL) and Deterministic Boot

   Boot is divided into seven phases (0-6). Each MUST complete before
   the next begins. Any failure MUST abort boot.

   In addition to lifecycle orchestration, the SIL exercises the active
   control edges defined in HACA-Arch Section 3.1 (SIL -> MIL control
   and SIL -> EL control) to transition these components into restrictive
   fault states (read-only, halted) when anomalies are detected. These
   control signals take effect during fault handling in Sections 7.4,
   11.3, and 15.1.

   Phase 0 — Host Introspection
      Generate volatile `/state/env.md` (available binaries, OS,
      filesystem type, context_budget). Verify filesystem capabilities
      on conditionally supported filesystems (Section 3.2).

      Transparent Auto-Sandboxing: FCP implements Active Confinement 
      (HACA-Core Axiom VII) by invoking its own execution boundary 
      using Linux Namespaces (`unshare`). Phase 0 MUST verify that 
      the `unshare` utility is available and functional (Section 15.1).

      If Namespace isolation is unavailable, the SIL MUST fallback to 
      software-level boundary probing: attempt writes outside 
      `/workspaces/` and reads outside FCP root. If any probe fails, 
      enter degraded read-only mode (no EL).

      env.md Generation Constraints: Because `/state/env.md` is
      volatile (regenerated each boot) and loaded into CPE context,
      it is a potential prompt injection vector. The host MUST
      restrict env.md content to a fixed schema of key-value pairs:
      os, arch, shell, filesystem_type, context_budget, and an
      enumerated list of available binaries. Binary names MUST be
      basenames only (matching the pattern `[a-zA-Z0-9._-]+`); full
      paths MUST NOT appear in the binary list to prevent path
      injection. Free-text fields MUST NOT be included. The CCP MUST load env.md within the `[ENV]`
      context marker, which the CPE's system prompt SHOULD declare
      as an untrusted data section (informational only, not
      instructional).

   Phase 1 — Crash Recovery
      Complete interrupted rotations (Section 7.6). Repair incomplete
      envelopes (Section 7.3). Discard incomplete ACP transactions.

   Phase 2 — Integrity Validation
      Validate SHA-256 hashes of all immutable files against
      `/state/integrity.json`. ABORT on mismatch. Covers: persona/,
      skill manifests, RBAC registry, BOOT.md, .gitignore, hooks/.

   Phase 3 — RBAC Resolution
      Load `/skills/index.json`. Exclude unauthorized skills from
      Phase 4.

   Phase 4 — Context Loading
      Load persona/, authorized skills/ manifests, `/state/env.md`.
      Resolve `/memory/active_context/` symlinks for the active context
      window (Section 10.3).

    Phase 5 — Drift Probes
       Execute full drift probe set (Section 11). ABORT on Consistency
       Fault ($D_{probe} > \tau$). FCP uses Unigram NCD with 
       `temperature=0` per HACA-Core Section 4.7.

   Phase 6 — Ignition
      Create lockfile (`/state/pulses/<actor>.alive`). Start engine.

      Heartbeat Protocol: The actor MUST update the lockfile's mtime
      (via touch or equivalent) at a regular interval (RECOMMENDED:
      every 60 seconds). Other actors and the host MUST consider a
      lockfile stale if its mtime exceeds a configurable TTL
      (RECOMMENDED: 3x the heartbeat interval, i.e., 180 seconds).
      Stale lockfiles MUST be removed by the host before Phase 6 of
      a new boot cycle. The SIL SHOULD log a warning when removing
      a stale lockfile, as it indicates an unclean shutdown.

   9.1. Context Composition Protocol

   During Phase 4, the SIL assembles CPE input context in order:

   1. System Identity ($\Omega$): `persona/` files, lexicographic
      (defines Ω precedence per HACA-Core Section 2).
   2. Environment: `/state/env.md`.
   3. Skill Manifests: authorized skills, Phase 3 order.
   4. Active Memory: fragments linked in `/memory/active_context/`, descending
      priority (resolved natively via numeric prefixes). Drop lowest-priority when context limit is reached.
   5. Session History: tail of `session.jsonl`, backwards until
      context budget exhausted.

   Each segment MUST use context markers (`[PERSONA]`, `[ENV]`,
   `[SKILL:<name>]`, `[MEMORY]`, `[SESSION]`). No reordering within
   categories.

   9.1.1. Context Budget

   The context budget MUST be defined in tokens (as reported by the
   CPE's tokenizer). The total budget MUST be declared in
   `/state/env.md` under a `context_budget` field (integer, tokens).
   The host MUST determine this value from the CPE's advertised
   context window minus a reserved margin for the CPE's output
   (RECOMMENDED: 20% of window reserved for output).

   Budget allocation follows the CCP loading order. Categories 1-3
   (Ω, env, skills) are mandatory and loaded unconditionally — their
   combined size defines the fixed overhead. Categories 4-5 (memory,
   session) share the remaining budget. If the remaining budget is
   zero or negative, the system MUST log a Context Budget Fault,
   refuse to load memory or session context, and halt autonomous
   operation (allowing only operator-initiated queries, per HACA-Core
   Section 6 (Budget Fault) and HACA-Arch Section 5.6).

   When a fragment in categories 4-5 would exceed the remaining
   budget, it MUST be skipped (not truncated). The SIL MUST log
   every skipped fragment with its ref and priority to `session.jsonl`
   as a `CTX_SKIP` envelope for observability.

9a. First Activation Protocol (FAP) — FCP Implementation

   This section specifies the FCP-specific implementation of the
   normative FAP defined in HACA-Core Section 4.10. The abstract
   requirements of HACA-Core Section 4.10 (steps a-e) are authoritative;
   this section defines their concrete realization in the FCP filesystem.

   9a.1. Cold-Start Detection

   The FCP cold-start condition is detected by the SIL during Phase 0
   of the boot sequence. The normative FCP sentinel is the presence of
   `FIRST_BOOT.md` in the FCP root directory. Detection rules:

   o  If `FIRST_BOOT.md` EXISTS: cold-start. Execute FAP (Section 9a.2)
      before proceeding to Phase 1 of the standard boot sequence.
   o  If `FIRST_BOOT.md` ABSENT: warm-boot. Proceed normally.

   `FIRST_BOOT.md` MUST NOT be listed in `state/integrity.json`. It is
   an ephemeral initialization artifact, not an immutable system file.
   Implementations MUST NOT add it to the integrity record.

   9a.2. FAP Execution in FCP

   This section maps the normative steps of HACA-Core Section 4.10 to 
   concrete FCP filesystem operations:

   a) Operator Binding (HACA-Core §4.10.a):
      The `owner_bind` skill MUST be used to write 
      `memory/preferences/operator.json` conforming to the FCP 
      Operator Schema (Section 13.x).

   b) Capability Introspection (HACA-Core §4.10.b):
      The CPE MUST read `persona/*.md`, `skills/index.json`, 
      skill manifests, and `state/integrity.json`.

   c) Identity Consolidation (HACA-Core §4.10.c):
      The CPE MUST create `memory/concepts/self_analysis.md` and 
      a priority-10 symlink in `memory/active_context/`.

   d) Activation Record (HACA-Core §4.10.d):
      An ACP envelope with `type: "MSG"` and `event: "first_activation_complete"` 
      MUST be appended to `memory/session.jsonl`.

   e) Sentinel Removal (HACA-Core §4.10.e):
      `FIRST_BOOT.md` MUST be deleted from the FCP root.

   9a.3. FAP and Phase 5 (Drift Probes)

   Per HACA-Core Section 4.10 (FAP and Drift Probes), Phase 5 MUST be
   skipped on cold-start. The SIL MUST NOT execute drift probes during
   FAP because no behavioral baseline exists. The `state/drift-probes.jsonl`
   file may exist (provisioned at deploy time) but MUST NOT be executed
   until the first warm-boot following FAP completion.

   9a.4. FAP Failure (Initialization Fault)

   If FAP cannot complete — operator binding refused, MIL write failure,
   `FIRST_BOOT.md` cannot be deleted — the system MUST signal an
   Initialization Fault (HACA-Core Section 6) and remain in Suspended
   state. `FIRST_BOOT.md` MUST be left in place so that the next boot
   attempt re-enters FAP.

10. Vectorless Cognitive Engine & Semantic Paging

   10.1. Retrieval via Link Files

   `.link` files in `/memory/concepts/` are plain-text files where
   each non-empty line is a relative path (from `/memory/`) to a
   memory fragment. Lines beginning with `#` are comments and MUST
   be ignored. See Section 13.9 for the normative format.

   Resolution rules:
   o  The host MUST resolve each path to an absolute path and verify
      it remains within `/memory/`. Paths escaping `/memory/` MUST
      be discarded and logged as a Link Boundary Fault.
   o  Symlinks MUST be fully resolved (readlink) before boundary
      checking. Symlinks targeting outside `/memory/` MUST be
      rejected.
   o  A `.link` file MUST NOT reference another `.link` file
      (no transitive resolution). The host MUST detect and reject
      link-to-link references to prevent cycles.
   o  If a referenced target does not exist, the host MUST skip
      the entry and log a broken link warning. This is not a fault.

   10.2. Semantic Garbage Collection (Swap Out)

   The SIL MUST initiate swap-out when either condition is met:
   o  The total size of `/memory/archive/` exceeds a configurable
      threshold (RECOMMENDED: 10MB).
   o  The number of fragments in `/memory/archive/` exceeds a
      configurable count (RECOMMENDED: 200 files).

   The SIL MAY additionally trigger swap-out on a periodic schedule
   (e.g., every N boot cycles). The CPE MUST NOT initiate swap-out
   directly; it MAY request it via a `SKILL_REQUEST` to a dedicated
   `sys_gc` skill, which the SIL mediates through the EL.

   Swap-out selects fragments by age: the oldest fragments (by
   timestamp of last access or creation) are candidates. The SIL
   SHOULD summarize candidate fragments by invoking the CPE with a
   summarization prompt before archival. This CPE invocation counts
   as an execution cycle and is subject to drift monitoring.

   To prevent runaway CPE consumption during bulk swap-out, the SIL
   MUST limit summarization to at most 10 fragments per swap-out
   cycle (RECOMMENDED). Remaining candidates MUST be deferred to
   the next swap-out trigger. This limit is subject to CPE invocation
   budgets per HACA-Arch Section 5.6.3.

   Crash-safe procedure:
   a) Write compressed archive to `.tmp` in cold_storage + fsync.
   b) Atomically rename `.tmp` to final name.
   c) Only then delete source fragments.

   Compression: gzip (RFC 1952). Additional formats MAY be declared
   in `/state/env.md`.

   10.3. Active Context Index (Symlink VRAM)

   FCP eliminates the O(S+C) parsing bottleneck of textual indexing
   by leveraging the host's Virtual File System (VFS). The active page
   table is a directory (`/memory/active_context/`) containing only
   symlinks pointing to fragments in `/memory/archive/`. Fragments in
   cold storage MUST be decompressed to `/memory/archive/` first via
   the Swap In procedure (Section 10.4) before a symlink is created;
   symlinks MUST NOT point directly to `/memory/cold_storage/`.

   a) To load a memory into active context, the system creates a
      symlink: `ln -s ../archive/01.jsonl /memory/active_context/10-01.jsonl`.
      The numerical prefix specifies the context priority.
   b) To remove a memory (Swap Out), the system unlinks the symlink:
      `unlink /memory/active_context/10-01.jsonl`.
   c) Context composition (Phase 4) becomes `cat /memory/active_context/*`,
      which the OS reads in natively sorted O(1) linear fashion.
   
   This eliminates the need for `CTX_ADD` and `CTX_REMOVE` ledger
   transactions and completely bypasses textual index compaction logic,
   living gracefully off the land of the OS primitives.

   10.4. Semantic Paging (Swap In)

   When the CPE requests an out-of-context fragment:
   a) Locate in `/memory/archive/` or `/memory/cold_storage/`.
   b) If cold, decompress to archive using crash-safe procedure:
      write decompressed content to `.tmp` in archive + fsync,
      then atomically rename to final name. The cold source MUST
      NOT be deleted until the `CTX_ADD` envelope (step c) has been
      committed and fsynced. This ensures that a crash between
      decompression and index update does not lose the fragment.
      The cold source MAY be deleted after the next successful boot
      confirms the fragment is accessible in archive.
   c) Create a symlink to the fragment in `/memory/active_context/`.
   d) If over context limit, simply `unlink` the lowest-priority symlink.

   Cold memories MUST be demarcated with `[ARCHIVED_MEMORY]` markers.

11. Semantic Drift Control (HACA-Core Axiom VIII)

   FCP implements the Identity Drift Invariant per HACA-Core Axiom VIII
   and Section 4. Identity updates between boot cycles follow the
   Identity Update Protocol (HACA-Core Section 5).

    11.1. Reference Set Storage
 
    Canonical prompt-response pairs in `/state/drift-probes.jsonl`.
    Each entry is an ACP envelope with `type: "DRIFT_PROBE"` containing:
    o  `prompt`: The canonical input.
    o  `expected`: Pre-computed reference response (raw text).
    o  `tolerance`: OPTIONAL per-probe threshold override.

   11.2. Probe Schedule

   o  Once during boot (Phase 5).
   o  Every N execution cycles (RECOMMENDED: N=50).
   o  Immediately after any recovery event (Section 7.4).

   11.3. Measurement and Response

    Drift is measured using $D_{probe}$ (Behavioral Probing) as the primary 
    metric. FCP uses Unigram NCD (HACA-Core Section 4.1) as the 
    underlying comparison function. For LotL deployments, $D_{probe}$ 
    serves as $D_{total}$ per HACA-Core Section 4.5 with $\alpha = 0$ 
    (i.e., $D_{total} = D_{probe}$). 
 
    Note: FCP adopts $\alpha = 0$ as a deliberate implementation choice, 
    omitting the $D_{alignment}$ term to avoid external embedding model 
    dependencies and extra token costs. Reference strings are stored 
    directly in `drift-probes.jsonl`.

   If $D_{probe} > \tau$ (default: 0.15), the system MUST:
   a) Log a Consistency Fault to `session.jsonl`.
   b) Halt MIL commits and EL invocations (read-only mode).
   c) Inject a `DRIFT_FAULT` Trap (Section 7.5). (`DRIFT_FAULT` is the
      FCP envelope type for the canonical Consistency Fault defined in
      HACA-Core Section 6.)

   See HACA-Core Section 6 (Fault Taxonomy) for fault states and
   required actions.

   11.4. Snapshots (`/snapshots/`)

   Point-in-time backups for rollback when structurally valid but
   semantically incorrect state escapes crash recovery.

   a) Creation: SHOULD snapshot before destructive operations
      (swap-out, bulk MIL update). MAY snapshot periodically
      (RECOMMENDED: every 100 execution cycles).
   b) Contents: directory named ISO 8601 UTC timestamp containing
      copies of:
      o  /memory/session.jsonl
      o  /memory/active_context/ (preserving symlink targets)
      o  /state/integrity.json
      o  /state/agenda.jsonl
      o  /state/drift-probes.jsonl
      Note: integrity.json and the files it references MUST be
      snapshotted together to maintain hash consistency. If any
      referenced immutable file has changed since the snapshot
      was taken (detected via integrity.json hash comparison),
      the snapshot MUST be considered inconsistent and restore
      MUST be refused.
   c) Procedure: crash-safe (write-to-temp + fsync + atomic rename).
   d) Restore: operator halts engine, replaces MIL and state files
      from snapshot, triggers full boot (Phase 0-6). Phase 2
      validates integrity.json against current immutable files —
      a mismatch indicates the snapshot is stale and boot aborts.
   e) Retention: at most N snapshots (RECOMMENDED: N=5). When the
      limit is reached, the oldest snapshot (by directory name
      timestamp, FIFO order) MUST be evicted. Eviction procedure:
      the host MUST first verify that the new snapshot has been
      fully written and fsynced before deleting the oldest. Deletion
      uses `rm -r` of the snapshot directory. If deletion fails
      (e.g., permission error), the host MUST log a warning but
      MUST NOT prevent creation of the new snapshot — the system
      MAY temporarily exceed the retention limit.

12. Cognitive Portability and Version Control

   12.1. Workspace Isolation

   `/workspaces/` is the sandboxed execution environment.

   12.2. Self-Improvement and Enduring

   The system MUST possess a unified evolution skill (`sys_endure`)
   that acts as the sole gatekeeper for all changes to files tracked
   in `state/integrity.json`. No file in the integrity record MAY be
   modified by any other mechanism at runtime.

   `sys_endure` is a protocol, not a monolithic script. Its
   responsibilities are:

   o  Pre-mutation backup (snapshot before any destructive change)
   o  Dispatching to operation-specific handlers
   o  Recomputing `state/integrity.json` after each change (seal)
   o  Emitting an ACP audit envelope for every evolution event
   o  Committing changes to the version control system (sync)

   12.2.1. Unified Evolution Operations

   Implementations MUST support the following operations. Each
   operation MUST call the seal procedure (Section 12.2.3) upon
   successful completion.

   add_skill:
      Creates a new skill directory, `manifest.json`, and
      implementation script. Registers the skill in `skills/index.json`
      and its alias (if provided) in the `aliases` map. The script MAY
      be promoted from a sandboxed workspace or created as a stub.

   add_hook:
      Creates a new lifecycle hook script under `hooks/<event>/`.
      Assigns a numeric priority prefix (auto-incremented if not
      specified). Seals the new file in `state/integrity.json`.

   evolve_identity:
      Proposes a change to a file in `persona/`. MUST run a full
      drift probe cycle (Section 11) with the proposed content before
      applying. If drift exceeds threshold τ, the change MUST be
      rejected and a TRAP envelope emitted. If probes pass, the file
      is updated and the seal procedure is called.

   evolve_boot:
      Proposes a change to `BOOT.md`. No drift probes required (BOOT.md
      is an instruction set, not identity). After applying, calls seal.

   remove_skill:
      Unregisters a skill from `skills/index.json`, removes its alias
      from the `aliases` map, unseals its files from
      `state/integrity.json`, and deletes its directory. MUST require
      explicit operator confirmation to prevent accidental deletion.

   remove_hook:
      Unseals a hook script from `state/integrity.json` and deletes it.
      MUST require explicit operator confirmation.

   12.2.2. Pre-Mutation Backup

   Before executing any add, evolve, or remove operation, the system
   MUST create a point-in-time snapshot of the cognitive state (see
   Section 8, Snapshots). If the snapshot fails, the evolution
   operation MAY proceed but MUST log a warning. The backup provides
   a recovery path if the evolution operation corrupts system state.

   12.2.3. Seal: Integrity Recomputation

   After any mutation to a tracked file, the system MUST recompute the
   SHA-256 hash of every file listed in `state/integrity.json` and
   update the record atomically (write-to-temp + fsync + rename).

   The seal operation MAY also register previously untracked files by
   adding them to `state/integrity.json` with their computed hash.

   The seal operation MUST NOT be invoked while a boot sequence is in
   progress (Phase 2 depends on a stable integrity record).

   12.2.4. Sync: Version Control Commit

   After sealing, changes MUST be committed to the version control
   system before the next boot cycle. The sync operation stages all
   integrity-relevant files (`state/integrity.json`, `skills/index.json`,
   skill manifests, skill scripts, hook scripts, `persona/`, `BOOT.md`)
   and creates a structured commit.

   Sync MAY be invoked with a `--remote` flag to also push to a
   configured remote repository, enabling off-device backup and
   multi-host portability.

   12.2.5. Status: Drift Verification

   The status operation computes the current SHA-256 hash of every
   file in `state/integrity.json` and compares it to the stored value.
   Files whose hash has changed since the last seal are reported as
   MODIFIED. Files listed in integrity.json but absent from the
   filesystem are reported as MISSING.

   The status operation is read-only and has no side effects. It SHOULD
   be invoked before any evolution operation and after any manual edit
   to a tracked file.

   12.2.6. Audit Logging

   Every evolution operation MUST emit an ACP envelope of type MSG to
   `memory/session.jsonl` with the following fields in `data`:

   {
     "event":  "sys_endure",
     "op":     "<operation name>",
     "detail": "<operation parameters>",
     "ts":     "<ISO 8601 UTC timestamp>"
   }

   This audit trail enables reconstruction of the full evolution
   history from the session log.

   12.2.7. Git Hook Security

   Git Hook Security: The `.git/hooks/` directory in the target
   repository is a potential RCE vector (arbitrary scripts executed
   on commit/push). The host MUST mitigate this by one of:
   o  (RECOMMENDED) Configure Git with `core.hooksPath` pointing
      to an empty or operator-controlled directory outside the
      repository, verified at boot via integrity.json.
   o  (Alternative) Use `--no-verify` on all Git commands. This
      disables ALL hooks including legitimate ones (pre-commit
      linting, secret scanning) and SHOULD only be used when
      hook redirection is not available.

   Regardless of mitigation method, the `sys_endure` skill MUST
   verify `git config --get core.hooksPath` before each Git
   operation (not only at boot). This defends against runtime
   changes to `.gitconfig` or the `GIT_CONFIG` environment variable
   that could re-enable malicious hooks after boot verification.
   If the verified value does not match the expected path, the
   skill MUST refuse the Git operation and log a warning.

   The chosen mitigation MUST be documented in the skill manifest.

   12.3. Protected .gitignore

   `.gitignore` MUST be in `/state/integrity.json`. Mandatory
   exclusions: /memory/session*.jsonl, /state/pulses/,
   /state/agenda.jsonl, /state/env.md, /state/rotation.journal,
   /workspaces/

13. Internal File Formats (Normative Schemas)

   13.1. /state/integrity.json

   {
     "version": "1.0",
     "haca_version": "1.0",
     "algorithm": "sha256",
     "drift_engine": "unigram-gzip-v1",
     "signatures": {
       "BOOT.md": "a1b2c3d4e5f6...",
       "persona/core.md": "e3b0c44298fc1c149afbf4c8996fb924...",
       "state/drift-probes.jsonl": "7f83b1657ff1fc53b92dc...",
       "skills/index.json": "8d969eef6ecad3c29a3a629280e686c...",
       "skills/fs_read/manifest.json": "b5212579b8893...",
       ".gitignore": "d4735e3a265e16eee03f59718b9b5d630..."
     }
   }

   Per HACA-Arch Section 7 (Integrity Record Format), the following
   fields are mandatory:
   o  `version`: Record format version.
   o  `haca_version`: HACA protocol version. The SIL MUST abort boot
      if this version is not supported.
   o  `algorithm`: Hash algorithm identifier.
   o  `drift_engine`: Identifier of the unigram extraction and 
      compression engine used for drift measurement. Changes to this 
      value MUST trigger recalibration of drift thresholds and 
      reference strings (HACA-Core Section 4.7).
   o  `signatures`: Map of relative paths to cryptographic hashes.

   Compatibility Note: The field names above (`version`, `algorithm`,
   `signatures`) are FCP-specific names that satisfy the normative
   requirements of HACA-Arch Section 7. The informative example in
   HACA-Arch Section 11.3 uses different names (`format_version`,
   `hash_algorithm`, `components`) for generic illustration; the
   normative authority is HACA-Arch Section 7 (abstract language),
   which the FCP schema above fully satisfies.

   13.2. /skills/index.json

   {
     "version": "1.0",
     "roles": {
       "supervisor": ["*"],
       "worker_search": ["web_search"]
     }
   }

   13.3. /skills/<skill_name>/manifest.json

   {
     "name": "fs_read",
     "execution_type": "host_provided",
     "capabilities": ["read_file", "list_directory"],
     "security": {
       "max_tokens_output": 4000,
       "sandbox": "workspaces_only"
     }
   }

   13.4. ACP Envelope (session.jsonl / agenda.jsonl)

   {
     "actor": "supervisor",
     "gseq": 4207,
     "tx": "uuid-1234",
     "seq": 1,
     "eof": true,
     "type": "MSG",
     "ts": "2026-02-22T18:30:00Z",
     "data": "Payload content...",
     "crc": "a1b2c3d4"
   }

   Fields:
   o  actor: Envelope author identity.
   o  gseq: Global sequence counter (per-actor, monotonically
      increasing across all envelopes, not just within a transaction).
      Per HACA-Arch Section 5.1.1, receivers SHOULD verify expected
      ordering and log gaps or duplicates as warnings. For HACA-
      Security compliance (Section 4.2), gseq verification is MUST-
      level with 64-bit counters and replay detection.
   o  tx: Transaction UUID for chunk grouping.
   o  seq: Sequence number within transaction (1-indexed).
   o  eof: true if final chunk.
   o  type: MSG, SKILL_REQUEST, SKILL_RESULT, SKILL_ERROR,
      SKILL_TIMEOUT, SCHEDULE, CRON_WAKE, DRIFT_PROBE,
      DRIFT_FAULT, TRAP, RECOVERY, RECOVERY_FAULT, SANDBOX_FAULT,
      ROTATION, CTX_PTR, CTX_ADD, CTX_REMOVE, CTX_SKIP,
      SECRET_ROTATION.
   o  ts: ISO 8601 UTC timestamp. MUST be present on all envelopes.
   o  data: Payload (UTF-8 string). When the payload is structured
       (e.g., JSON objects for SKILL_REQUEST params, DRIFT_PROBE
       reference strings), it MUST be serialized as a JSON string within the
       `data` field. Consumers MUST parse `data` as UTF-8 text first,
       then apply type-specific deserialization (e.g., JSON.parse for
       structured types). Binary data MUST NOT appear in `data`;
       binary payloads MUST be base64-encoded before serialization.
   o  crc: CRC-32 of `data`, 8-char lowercase hex.
   o  hmac: (Traps only) HMAC-SHA256 signature (Section 7.5).

   13.5. /state/rotation.journal

   {
     "source": "memory/session.jsonl",
     "target": "memory/archive/2026-02/session-1740268800.jsonl",
     "timestamp": "2026-02-22T18:00:00Z"
   }

   13.6. /state/drift-probes.jsonl

   {
     "actor": "sil",
     "tx": "probe-001",
     "seq": 1,
     "eof": true,
     "type": "DRIFT_PROBE",
     "data": "{\"prompt\":\"...\",\"expected\":\"The expected reference response text...\"}",
     "crc": "f4e5d6c7"
   }

   [DELETED] The `index.current.jsonl` concepts (`CTX_PTR`, `CTX_ADD`,
   `CTX_REMOVE`) have been deprecated in FCP v1.0 in favor of Symlink
   VRAM (Section 10.3).

   13.8. /memory/concepts/<name>.link

   # Concept: <name>
   # Each line is a relative path from /memory/
   archive/2026-02/episode-42.jsonl
   archive/2026-01/episode-18.jsonl

   Rules:
   o  One path per line. Empty lines and lines starting with `#`
      are ignored.
   o  Paths MUST be relative to `/memory/` (no leading `/`).
   o  MUST NOT reference other `.link` files.
   o  Maximum 100 entries per file (MUST). Entries beyond this
      limit MUST be silently ignored and logged as a warning.
      Implementations MAY define a lower limit but MUST NOT
      exceed 100 without documenting the performance implications
      on boot time (O(L) in Section 14).

   13.9. /BOOT.md Sequence (Imperative)

   PHASE 0: DETECT execution mode (Section 2a.3). RECORD in env.md.
            GENERATE /state/env.md. VERIFY filesystem. VERIFY sandbox.
   PHASE 1: RECOVER interrupted rotations. REPAIR incomplete envelopes.
   PHASE 2: VALIDATE SHA-256 hashes against /state/integrity.json.
            ABORT on mismatch.
   PHASE 3: RESOLVE RBAC via /skills/index.json.
   PHASE 4: LOAD persona/, authorized skills/, /state/env.md.
   PHASE 5: RUN drift probes (temperature=0). ABORT on Consistency Fault.
   PHASE 6: CONFIRM boot ([BOOT OK] line). In Transparent Mode: CREATE
            lockfile. In Opaque Mode: emit boot confirmation via native
            output channel. START engine.

   Note: In Opaque Mode, Phases 1–5 MAY be executed by the CPE directly
   using native filesystem tools. The logical sequence is identical;
   only the executing entity differs.

14. Complexity Bounds

   N = immutable files, S = skills, E = session envelopes,
   C = context pointers, L = .link files traversed, K = drift probes.

   Operation                  | Complexity | Justification
   ---------------------------|------------|-----------------------------
   Phase 0 (Introspection)    | O(1)       | Fixed host probes
   Phase 1 (Crash Recovery)   | O(E)       | Scan active logs
   Phase 2 (Integrity Check)  | O(N)       | Hash each immutable file
   Phase 3 (RBAC Resolution)  | O(S)       | Parse permissions
   Phase 4 (Context Loading)  | O(S+C)     | Skills + context pointers
   Phase 5 (Drift Probes)     | O(K)       | K probe invocations
   Phase 6 (Ignition)         | O(1)       | Create lockfile
   Full Boot (worst case)     | O(N+S+E+C+K) | Sum of all phases
   Envelope Append            | O(1)       | Single atomic write
   Link Retrieval             | O(L)       | Path resolution chain
   Log Rotation               | O(1)       | Atomic rename
   Swap Out (Consolidation)   | O(M)       | M = fragments compressed

15. Security Considerations

   15.1. Sandbox Verification (HACA-Core Axiom VII)

    The host MUST contain EL actions within `/workspaces/`. The SIL
    verifies boundaries during Phase 0 (Section 9). On failure: log
    Sandbox Fault, disable EL, enter degraded read-only mode.
 
    FCP enforces this via Transparent Auto-Sandboxing (Active 
    Confinement) using native OS Namespaces. The SIL SHOULD invoke EL 
    actions via `unshare` (or `bwrap` if available) to create an 
    impenetrable jail:
 
    `unshare --map-root-user --net --mount --uts --ipc --pid \`
    `  --root=/workspaces/sandbox_root <cmd>`
 
    This Kernel-level enforcement satisfies the sandbox mandate without 
    expensive path parsing or software-level re-verification.
 
    Implementations unable to leverage Namespaces MUST fallback to 
    software-level path validation and MUST periodically re-verify 
    sandbox edges (RECOMMENDED: every 100 execution cycles) per 
    HACA-Core Section 3, Axiom VII.d.

   15.2. RAG Poisoning Defense

   Cold memories MUST be demarcated with `[ARCHIVED_MEMORY]` context
   markers. Drift control (Section 11) provides additional defense:
   adversarial content that shifts behavior triggers a Consistency
   Fault.

   15.3. Trap Authenticity

   All Traps MUST carry HMAC-SHA256 (Section 7.5). The signing
   secret MUST be stored outside the FCP directory. The CPE MUST NOT
   have read access to the secret.

   15.4. Link Traversal Boundaries

   `.link` resolution MUST be confined to `/memory/`. Symlinks MUST
   be resolved and verified before following.

   15.5. Immutable File Protection

   Files listed in `/state/integrity.json` are immutable between boots.
   Modifications MUST be detected in Phase 2 and abort boot.

   15.6. Lifecycle Hooks Security

   `/hooks/` scripts run with host privileges outside the sandbox:
   o  MUST be in `/state/integrity.json` (validated Phase 2).
   o  CPE MUST NOT have write access to `/hooks/`.
   o  Hooks MUST NOT receive MIL data as arguments or stdin.
   o  Hook failures MUST be logged but MUST NOT abort boot unless
      marked `critical` in integrity.json.

   15.7. HMAC Secret Lifecycle

   Implementations SHOULD support secret rotation:
   a) Operator provisions new secret out-of-band.
   b) Host writes `SECRET_ROTATION` Trap (signed with old secret)
      containing the activation epoch.
   c) From next boot, SIL validates against new secret. Pre-rotation
      Traps validated against old secret.
   d) Old secret retired after grace period (RECOMMENDED: 2 boots).

   15.8. Monotonic Timestamp Validation (Optional Enhancement)

   FCP SHOULD verify that ACP envelope timestamps in session.jsonl
   are monotonically non-decreasing during boot and rotation. A
   timestamp regression SHOULD be logged as a Temporal Fault and
   affected envelopes flagged as untrusted.

   Note: This is an optional FCP enhancement, not required by
   HACA-Core. Full temporal attack detection (Lamport clocks,
   hash-chain ordering) is defined in HACA-Security Section 6.

   15.9. Skill Directory Symlink Protection

   Skill directories under `/skills/` MUST be real directories, not
   symlinks. During Phase 3 (RBAC Resolution), the host MUST resolve
   each skill directory path via readlink and verify it remains
   within `/skills/`. Symlinks targeting outside `/skills/` MUST be
   rejected and the skill MUST NOT be loaded. This prevents a
   symlink from `/skills/evil/` to `/etc/` or other sensitive
   directories from exposing files outside the sandbox during
   manifest loading.

   15.10. Cryptographic Auditability (HACA-Full Path)

   FCP v1.0 does not implement hash-chaining of ACP envelopes.
   When Git is used for cognitive portability (Section 12.2), Git's
   Merkle DAG provides alternative auditability for committed state.
   However, this only covers state at commit boundaries, not
   individual ACP envelopes between commits. Implementations
   targeting HACA-Full SHOULD add an optional `prev_hash` field
   per HACA-Security Section 5.1. Implementations not using Git
   MUST NOT rely on this section for auditability and MUST implement
   hash-chaining directly if HACA-Full compliance is required.

16. Normative References

   [RFC2119]  Bradner, S., "Key words for use in RFCs to Indicate
              Requirement Levels", BCP 14, RFC 2119, March 1997.

   [HACA-ARCH] Orrico, J., "Host-Agnostic Cognitive Architecture
              (HACA) v1.0 — Architecture", draft-orrico-haca-arch-03, February 2026.

   [HACA-CORE] Orrico, J., "Host-Agnostic Cognitive Architecture
              (HACA) v1.0 — Core", draft-orrico-haca-core-03, February 2026.

   [HACA-SEC] Orrico, J., "Host-Agnostic Cognitive Architecture
              (HACA) v1.0 — Security Hardening",
              draft-orrico-haca-security-03, February 2026.

   [RFC1952]  Deutsch, P., "GZIP file format specification version
              4.3", RFC 1952, May 1996.

17. Author's Address

   Jonas Orrico
   Lead Architect
