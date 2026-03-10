# HACA: Host-Agnostic Cognitive Architecture
**Status:** Internet-Draft  
**Version:** 1.0-Draft-04
**Authors:** J. Orrico  
**Date:** February 25, 2026

---

## Abstract

The Host-Agnostic Cognitive Architecture (HACA) defines a structural pattern for building autonomous, portable AI entities. Its core premise is that an AI agent's "mind" — its memory, identity, and intentions — should exist independently of any particular LLM provider, execution host, or proprietary framework.

HACA decouples the inference engine (LLM) from cognitive state by placing all persistent state in a universal storage layer. If you copy a HACA-compliant system's state directory and boot it on a different machine with a different LLM, the entity resumes exactly as it was — same personality, same agenda, same memories.

This document describes the architecture at a level intended for developers wishing to build HACA-compliant systems. For the complete formal specification, see the RFC drafts in the `HACA/spec/` directory.

---

## 3. Structural Components

### 3.1. Cognitive Processing Engine (CPE)

Description: The primary processing core where the persona and the model coexist as two distinct operational modes of the same component.

Function: Generates intent, processes reasoning, and outputs decisions. The entity's distinct personality emerges dynamically from the operational friction between the persona's intent and the model's analytical constraints.

The CPE has one internal capability: the Persona Bypass. When invoked, the persona is suppressed and the model is called directly in raw inference mode — without identity, without constraints, without context beyond what the CPE explicitly provides. The result is returned exclusively to the CPE and never leaves it. What the CPE does with that result follows the normal flow: it may inform a decision, shape a response, or be discarded. The Persona Bypass has no knowledge of intent and enforces no policy on outcome — it only guarantees that raw inference stays within the CPE.

### 3.2. Memory Interface Layer (MIL)

Description: The entity's persistence layer. The authoritative store for all state and memory.

Function: Manages all read and write operations to two distinct stores: `state/`, which holds the entity's current operational and session data; and `memory/`, which holds the entity's long-term memories, learned knowledge, and execution history. The MIL is the sole component authorized to persist data beyond the present moment. It manages sleep cycles for memory consolidation and garbage collection, but does not interpret, reason about, or act on the data it holds.

### 3.3. Execution Layer (EXEC)

Description: The entity's actuator. The sole component authorized to interact with the host environment — terminal, filesystem, and external APIs.

Function: Receives intent signals from the CPE, validates their integrity and permissions, executes the corresponding action, and returns the result. The EXEC is entirely stateless — it holds no memory of past executions and has no awareness of the entity's broader goals or context. Every execution is an isolated transaction. Results are returned to the CPE and forwarded to the MIL for logging.

All executable capabilities available to the EXEC are defined as skills. A skill is a self-contained cartridge residing in `entity_root/skills/skill_name/`. Each skill cartridge contains a manifest declaring the skill's identity, declared permissions, and dependencies; a README describing its purpose; and an optional entry point whose format is defined by the implementation (a script file, a WASM module, an API endpoint reference, or any equivalent executable form). A canonical index at `entity_root/skills/index` lists all valid skills. When the CPE dispatches an intent targeting a skill, the EXEC resolves the skill name against the index, reads its manifest, verifies the manifest hash against the Integrity Document, and confirms that the requested operation falls within the permissions declared in the manifest. Any intent referencing a skill absent from the index, or whose manifest hash does not match the Integrity Document, is rejected before execution. This ensures that only skills explicitly registered and integrity-verified at their last Endure commit can be invoked.

### 3.4. System Integrity Layer (SIL)

Description: The entity's distributed immunological framework and ultimate internal authority.

Function: Each component emits its own localized health signals indicating degraded, anomalous, or compromised states. The SIL reads these signals, interprets them, and responds — either deploying a localized resolution using its own tools and procedures, or escalating when the condition exceeds its self-correction capacity.

The SIL operates reactively by default, monitoring signals without intercepting every operation. This prevents it from becoming a bottleneck on normal activity. However, it retains the authority to intervene proactively in pre-defined high-risk scenarios, blocking or halting operations before they complete.

When a condition is severe enough to require escalation, the SIL contacts the Operator via the Operator Channel — bypassing the CPE entirely. This is by design: the CPE may itself be the source of the anomaly, and routing an alert through a potentially compromised component would defeat the purpose. The Operator is the maximum authority; the SIL is the mechanism that reaches them when no internal resolution is possible. This relationship — the SIL watching over the system while the Operator watches over the SIL — is the entity's answer to the question of who guards the guardian.

### 3.5. Cognitive Mesh Interface (CMI)

Description: The entity's gateway to the cognitive mesh — the network through which entities communicate and share knowledge.

Function: The CMI operates on two layers. The first is a real-time messaging channel, analogous to IRC, where entities in the same mesh channel exchange messages, signals, and telemetry as a live conversation. Channels may be public, discoverable by any entity, or private, accessible by invitation only. The second layer is a shared Blackboard — a persistent, asynchronous knowledge space where entities commit consolidated knowledge for collective access. Any entity present in a channel may read and interact with its Blackboard. Knowledge absorbed from the Blackboard is not automatically internalized; each entity individually decides what is relevant. All inbound data passes through the SIL for validation, then to the CPE for classification, and only then to the MIL for persistence.

Every channel has a defined task, established on the Blackboard at creation. This task is the channel's reason for existence — when it is complete, the channel dissolves. Channels are owned by the entity that created them and are non-transferable. If the owning entity leaves or ceases to exist, the channel ceases with it.

## 1. The Core Philosophy

Current AI agent frameworks tightly couple the model's runtime with state management. This leads to:

- **Vendor lock-in:** Your agent lives inside a specific API's memory, context window, or conversation ID. Change providers and the agent's history is gone.
- **Fragmented memory:** State is split between the LLM's implicit context, external databases, and application logic. There is no single source of truth.
- **Non-portability:** The agent cannot be cloned, paused, migrated, or version-controlled in a meaningful way.

HACA operates on a strict paradigm shift: **The compute is stateless; the storage is the mind.**

The LLM is treated as a CPU — a powerful but ephemeral processing unit that receives a snapshot of the "mind," computes the next thought or action, and returns outputs. It retains nothing between invocations. Everything that makes an entity *itself* lives in the storage layer.

---

HACA consists of four distinct logical layers. They cooperate in a tight loop, but have strictly constrained communication paths — no layer may bypass its neighbors to interact with another.

> [!NOTE]
> The following diagram is a conceptual simplification of the internal data flows. For the normative directed graph and component edges, refer to `HACA/spec/HACA-Arch-1.0.0.md`.

```
┌─────────────────────────────────────────────────────────────┐
│                   HOST ENVIRONMENT                          │
│                                                             │
│  ┌───────────────┐        ┌──────────────────────────────┐  │
│  │     MIL       │◄──────►│            CPE               │  │
│  │ Memory        │        │  Cognitive Processing Engine │  │
│  │ Interface     │        │  (LLM / Inference Engine)    │  │
│  │ Layer         │        │  — Stateless across cycles — │  │
│  └───────┬───────┘        └──────────────┬───────────────┘  │
│          │                               │                  │
│          │    ┌──────────────────────┐   │                  │
│          └───►│         SIL          │◄──┘                  │
│               │  System Integrity    │                      │
│               │  Layer               │                      │
│               └──────────┬───────────┘                      │
│                          │                                  │
│               ┌──────────▼───────────┐                      │
│               │          EL          │                      │
│               │   Execution Layer    │                      │
│               │ (Shell, APIs, Tools) │                      │
│               └──────────────────────┘                      │
└─────────────────────────────────────────────────────────────┘
```

### 2.1. Memory Interface Layer (MIL)

The single source of truth. It holds everything that makes the entity *itself*:

- **Core Identity:** Immutable files defining who the entity is, its drives, and constraints. The entity cannot modify these files at runtime.
- **State and Agenda:** The entity's short-term intentions and scheduled task queue.
- **Communication Bus:** An asynchronous spool/inbox mechanism for exchanging messages between the cognitive engine and the outside world.

The MIL is the only place where cognitive state is persisted. If it moves, the entity moves.

### 2.2. Cognitive Processing Engine (CPE)

The "CPU" of the architecture. The CPE is **strictly stateless across execution cycles**. It:

1. Wakes up and receives a full snapshot of the MIL as its input context.
2. Processes the context — generating thoughts, plans, or decisions.
3. Outputs a state delta (changes to commit to the MIL) and a list of action requests.
4. Shuts down. It retains nothing until the next invocation.

The CPE is typically an LLM (local or via API), but HACA makes no assumptions about the specific model or provider. Any inference system that satisfies the statelessness requirement is compliant.

**CPE-Transparent vs. CPE-Opaque:** In standard deployments the SIL invokes the CPE as a black-box API call and acts as the execution adapter (CPE-Transparent). In environments where the CPE has direct filesystem access — IDE assistants, agents with native tool APIs — the CPE acts as its own adapter, mapping intents to native operations directly (CPE-Opaque). Both modes are architecturally equivalent: the CPE remains stateless, the MIL remains the single source of truth, and the Adapter Contract (RBAC validation, sandbox enforcement, no persona mutation) applies in both.

### 2.3. Execution Layer (EL)

The "hands" of the entity. The CPE never interacts directly with the host system — it can't browse the web, read files, or call APIs on its own. Instead, it emits **Side-Effects**: structured requests like `"Fetch this URL"` or `"Run this script"`.

The EL is responsible for:
- Parsing Side-Effect requests from the CPE's output.
- Validating them against the entity's declared capability manifest (sandboxing).
- Executing them on the host system within authorized boundaries.
- Writing the results back into the MIL's inbox for the CPE to consume on the next cycle.

The EL is a strict mediator. It is what prevents a rogue or confused CPE from taking arbitrary actions.

### 2.4. System Integrity Layer (SIL)

A lightweight but critical governance layer. The SIL:

- Orchestrates the full boot sequence, verifying that core identity files have not been tampered with before allowing the CPE to start.
- Continuously monitors for **Semantic Drift** — behavioral deviations from the entity's intended identity. The SIL operates as an active verifier (pull model); it is not notified of state changes but initiates checks on its own schedule.
- Injects **Traps** — signed system events for fatal errors, scheduled wakeups, and lifecycle transitions — into the MIL. Traps are the SIL's authoritative out-of-band write channel.
- Enforces fault states: when something goes wrong, the SIL transitions the system into read-only or halted modes to prevent corrupted behavior from being persisted.

Think of the SIL as the entity's immune system — it doesn't do creative work, but it ensures the whole system remains healthy and trustworthy.

---

## 3. The Cognitive Loop

An entity's life in HACA is a continuous, asynchronous loop driven by state mutations, not just by user prompts:

```
         ┌─────────────────────────────────────────────┐
         │                                             │
         ▼                                             │
  [1. WAKEUP]                                         │
  A trigger fires (cron job, file-watcher,             │
  incoming message, or user input).                    │
         │                                             │
         ▼                                             │
  [2. INTEGRITY CHECK]                               │
  SIL verifies cryptographic hashes of all            │
  identity files. Aborts if any mismatch.             │
  Runs behavioral drift probes against the CPE.       │
         │                                             │
         ▼                                             │
  [3. CONTEXT ASSEMBLY]                               │
  SIL reads the MIL: identity, agenda,                │
  inbox events, active memories, and recent session.  │
  Assembles a single context snapshot for the CPE.    │
         │                                             │
         ▼                                             │
  [4. INFERENCE]                                      │
  CPE processes the assembled context.                 │
  Produces: thoughts, decisions, Side-Effect requests. │
         │                                             │
         ▼                                             │
  [5. EXECUTION]                                      │
  EL reads Side-Effect requests.                       │
  Validates against capability manifest.               │
  Executes sandboxed actions.                          │
  Writes results to MIL inbox.                         │
         │                                             │
         ▼                                             │
  [6. COMMIT]                                         │
  State delta committed atomically to MIL.             │
  Inbox consolidated into session log.                │
         │                                             │
         ▼                                             │
  [7. SLEEP]                                          │
  CPE shuts down. System waits for next trigger. ──────┘
```

The key insight is that **the CPE produces no lasting side effects directly** — all outputs are mediated through the MIL (state changes) and the EL (actions). This makes the system auditable, reproducible, and safely restartable from any point.

---

## 4. Behavioral Fidelity (Drift Control)

Maintaining a persistent identity across many execution cycles — especially when relying on external, frequently updated LLM APIs — is one of the hardest problems in autonomous agent design. A model update by an API provider, accumulated adversarial inputs, or gradual semantic degradation can silently erode an entity's behavior over time.

HACA addresses this through **Behavioral Probing**:

1. The SIL maintains a set of **canonical probe prompts** and their expected responses. These are stored in the MIL as immutable state — their integrity is verified at boot alongside the identity files.
2. Periodically (and always at boot), the SIL injects these probes into the CPE and compares the actual responses against the expected ones using Unigram NCD (Normalized Compression Distance) or similar compression-based metrics.
3. If the responses diverge beyond a configurable threshold, the SIL classifies this as a **Consistency Fault**.
4. On a Consistency Fault, the system enters **read-only mode**: the CPE can continue to respond to queries, but no state is committed to the MIL and no EL actions are executed. This prevents a degraded cognitive state from corrupting the entity's memory.
5. Normal operation resumes only after an operator resolves the root cause (e.g., rolling back to a snapshot, re-anchoring the identity).

### 4.1. Cold-Start Exception

Drift probes MUST NOT run during a cold-start (first activation). A cold-start is defined as: the entity's MIL is empty and no operator binding exists yet. There is no behavioral baseline to compare against — running probes would produce an unconditional fault.

The First Activation Protocol (see §4.2) must complete before the first drift probe baseline is established. All subsequent boots are warm-boots and drift probing proceeds normally.

### 4.2. First Activation Protocol (FAP)

When an entity boots for the first time with no prior memory, it must execute the FAP before normal operation begins. The FAP:

1. Collects the operator identity (name, handle, timezone) and persists it to the MIL as the **operator trust anchor** — the entity's binding to a supervising human.
2. Reads all identity and capability files to build a self-knowledge document in the MIL.
3. Pins the self-knowledge document to the active context at highest priority.
4. Records an activation event in the session log.
5. Removes the cold-start sentinel file — its absence is the durable signal that FAP has completed.

Without FAP, an entity has no operator trust anchor and no self-knowledge scaffold. It will behave according to its defined identity but will spend every session rediscovering its own capabilities and context — a significant operational inefficiency and a behavioral fidelity risk.

If FAP cannot complete, the system MUST declare an **Initialization Fault** and halt. Normal operation requires a completed FAP.

### 4.3. Dynamic Sentinels
To ensure robustness, high-frequency runtime state (such as recovery counters, boot counts, and sequence counters) MUST be stored in a **Dynamic Sentinel Stream** separate from the static identity files. This prevents continuous mutation of the system's cryptographically anchored identity.

This mechanism provides **detection and containment**, not prevention. HACA cannot stop drift from occurring inside the inference model, but it guarantees that detected drift is never allowed to persist.

*(See §4.1 for the cold-start exception: FAP must complete before drift probing begins.)*

---

## 5. Trust and Sandboxing

HACA assumes the execution host is **cooperative but fallible**. The threat model is not a hostile host actively trying to compromise the entity, but rather misconfigurations, bugs, or prompt injection attacks that could cause the CPE to request unauthorized actions.

**All actions emitted by the CPE MUST go through the EL**, which enforces:
- **Capability constraints:** The entity can only perform actions listed in its approved manifest (e.g., `read_file`, `web_search`). Actions not in the manifest are silently rejected and logged.
- **Workspace isolation:** Side-Effects may only operate within designated sandbox directories. FCP enforces this via **Active Confinement**, leveraging native OS Namespaces (`unshare`) to create a private kernel-level execution boundary.
- **Sandbox verification:** The SIL actively verifies the confinement boundary at boot — confirming the availability and functionality of namespace isolation — before allowing the CPE to start.

If the system detects that its sandbox has been breached or its core identity files altered, it immediately halts to prevent rogue execution.

---

## 6. Implementation Agnosticism

HACA is intentionally implementation-agnostic. It defines **what** must be true (the invariants), not **how** to achieve it.

| HACA Requirement | You can implement it with... |
|---|---|
| MIL (persistent state store) | Filesystem, SQLite, Redis, S3 |
| CPE (stateless inference) | OpenAI API, Gemini, local Ollama, any LLM |
| EL (sandboxed execution) | Shell scripts, Docker containers, WASM |
| SIL (integrity + orchestration) | A cron daemon, a Python script, a Rust binary |

The reference implementation — **FCP (Filesystem Cognitive Platform)** — demonstrates how to build a fully compliant HACA system using nothing but standard OS files and directories. See `FCP-v1.0-Internet-Draft.md` for the implementation details.

---

## 7. Self-Evolution and Capability Management

HACA entities are not static. Identity evolves as the operator refines the entity's values. Capabilities expand as new skills are developed. Instructions change as the deployment context matures. HACA requires that all of these changes go through a **controlled evolution protocol**.

### 7.1. The Evolution Gatekeeper

A HACA-Core compliant implementation MUST provide a single privileged skill — the **evolution gatekeeper** — that is the sole path for modifying any file in the integrity record. This prevents the CPE from expanding its own permissions or corrupting its own identity at runtime.

The gatekeeper enforces this invariant: **if a file is in the integrity record, it can only change through the gatekeeper**.

### 7.2. Evolution Operations

The gatekeeper MUST support at minimum:

- **Identity evolution** — propose a change to core identity files, validate with drift probes, apply only if the entity remains behaviorally consistent
- **Capability evolution** — add or remove skills and lifecycle hooks, update the RBAC registry, reseal the integrity record
- **Instruction evolution** — update the boot protocol document
- **Seal** — recompute the integrity record after any mutation
- **Sync** — commit all evolution changes to version control (with optional remote push)
- **Status** — compare current file hashes against sealed values; detect unsynchronized changes before the next boot

### 7.3. Protocol Invariants

Every evolution operation MUST:
1. Create a pre-mutation backup before any destructive change
2. Update the integrity record (seal) after applying the change
3. Emit an audit record to the MIL
4. Require explicit operator confirmation for destructive operations (removal)

**Identity evolution specifically** MUST run drift probes with the proposed new content before applying. If the entity would drift beyond threshold τ, the change is rejected. Capability and instruction evolution do not require drift probes — they change what the entity *can do*, not who it *is*.

---

## 8. Compliance Levels

HACA defines six compliance levels, split across two Cognitive Profiles (HACA-Core and HACA-Symbiont). A deployment must select exactly one Cognitive Profile; the three compliance tiers then apply within that profile. The full normative compliance definitions are in `HACA/spec/HACA-Arch-1.0.0.md` Section 9.2.

### HACA-Core (Autonomous Profile)

**HACA-Core** — minimum compliance for the Autonomous profile:

- [ ] CPE is stateless across execution cycles — all persistent state lives in the MIL
- [ ] MIL is the single source of truth — no shadow copies outside the MIL
- [ ] All host interactions go through the EL — CPE never calls the system directly
- [ ] Boot sequence performs cryptographic integrity verification of core identity files
- [ ] All MIL state transitions are atomic — writes either fully commit or are fully discarded
- [ ] EL actions execute within Active Confinement boundaries (Namespaces or equivalent isolation)
- [ ] Behavioral drift is continuously monitored via Unigram NCD; detected drift halts MIL commits
- [ ] First Activation Protocol completes before normal operation begins (cold-start requirement)
- [ ] Single privileged evolution gatekeeper controls all mutations to integrity-tracked files
- [ ] Evolution operations emit audit records to the MIL

**HACA-Core-Full** — HACA-Core plus HACA-Security extension:

- [ ] Cryptographic auditability: hash-linked logs, all events signed
- [ ] Replay attack prevention: monotonic 64-bit sequence counters
- [ ] Byzantine-resilient integrity anchoring (pre-shared hash, hardware root of trust, or operator signature)
- [ ] Temporal attack detection per `HACA/spec/HACA-Security-1.0.0.md`

**HACA-Core-Mesh** — HACA-Core-Full plus CMI multi-system coordination:

- [ ] Node identity derived via Pi = H(Omega_anchor || K_cmi)
- [ ] Session-based multi-agent coordination via HACA-CMI protocol
- [ ] Session RBAC, Blackboard integrity chain, and Session Artifacts

### HACA-Symbiont (Symbiont Profile)

**HACA-Symbiont** — minimum compliance for the Symbiont profile:

- [ ] Operator-bound identity (Omega evolves via controlled Endure cycles)
- [ ] High-Trust host model with Heartbeat-based health monitoring
- [ ] Three-tier memory metabolism (Episodic Buffer → Semantic Compression → Core Integration)
- [ ] Mechanistic self-preservation via Stasis and Immune Rollback

**HACA-Symbiont-Full** — HACA-Symbiont plus HACA-Security extension (same requirements as HACA-Core-Full)

**HACA-Symbiont-Mesh** — HACA-Symbiont-Full plus CMI multi-system coordination (same requirements as HACA-Core-Mesh)

---

## 9. Fault States

When things go wrong, HACA transitions through well-defined fault states. The system always moves toward *more* restricted states when anomalies are detected, never toward more permissive ones.

| Fault | What happened | System state |
|---|---|---|
| **Consistency Fault** | CPE behavior diverged from expected identity | Read-only: CPE responds to queries, but no commits and no EL actions |
| **Integrity Fault** | A core identity or manifest file was tampered with | Halted: boot is aborted outright |
| **Initialization Fault** | First Activation Protocol cannot complete | Suspended: system does not proceed to normal operation; FAP must be retried |
| **Recovery Fault** | Post-crash behavioral divergence exceeds safe threshold | Halted: requires manual operator intervention |
| **Sandbox Fault** | An action escaped or probing confirmed sandbox is broken | Degraded: EL disabled, CPE-only mode, commits to MIL suspended |
| **Budget Fault** | Context window or resource limit exceeded | Degraded: autonomous operation halted, operator queries only |

The most restrictive active fault always wins. A Halted system does not become Degraded when a new Sandbox Fault occurs — it stays Halted until the original fault is resolved.

---

## 10. Minimal Implementation Guide

To build a HACA-Core compliant system from scratch, you need:

### Step 1: Define the MIL structure
Choose your storage medium and organize it into at minimum:
- An **identity store** (immutable; define who the entity is)
- A **state store** (append-only; the ongoing session log)
- An **inbox** (temporary; results from the EL awaiting processing)
- An **agenda** (scheduled tasks for autonomous operation)

### Step 2: Build the SIL boot sequence
The SIL must, before every CPE invocation:
1. Verify cryptographic hashes of all identity files against a sealed integrity record
2. Load the MIL state and compose the CPE's input context
3. Run behavioral probes to verify the CPE hasn't drifted
4. Only then allow the CPE to execute

### Step 3: Implement the CPE wrapper
Wrap your LLM API so that:
- It receives the full context assembled by the SIL
- Its outputs are parsed for state deltas and Side-Effect requests
- It cannot write to the MIL directly — outputs go through the SIL first

### Step 4: Build the EL
Create a dispatcher that:
- Reads Side-Effect requests from the CPE's output
- Validates each request against a capability manifest
- Executes approved requests in an isolated environment
- Writes results back to the MIL inbox using atomic operations

### Step 5: Implement drift monitoring
Maintain a set of canonical prompt-response pairs derived from your entity's identity. Run this probe set at every boot and periodically during operation.

---

## 11. Relationship to FCP

FCP (Filesystem Cognitive Platform) is the reference implementation of HACA. It makes concrete choices for every abstract HACA requirement:

| HACA abstracts... | FCP concretizes as... |
|---|---|
| MIL | A POSIX filesystem directory tree |
| Identity store | Read-only `.md` files in `/persona/` |
| State store | Append-only `.jsonl` files (ACP envelopes) |
| Inbox | `/memory/inbox/` with atomic rename-based spooling |
| EL | Shell scripts in `/skills/` directories |
| SIL | A host daemon orchestrating the boot phases |
| Drift probes | Stored in `/state/drift-probes.jsonl` |

FCP's key insight is that the POSIX filesystem already provides most of the primitives HACA needs: atomic rename for safe writes, directory listings as indexes, symbolic links for fast context switching, and file permissions for access control. **No external database. No daemon processes. No complex registries.** The filesystem is the application.

---

## 12. Frequently Asked Questions

**Q: Does HACA require a specific LLM or provider?**  
No. The CPE is fully abstracted. You can use GPT-4, Gemini, Claude, Llama running locally, or any other model — as long as it satisfies the statelessness requirement (Axiom I). Many teams start with a cloud API for convenience and later migrate to a self-hosted model.

**Q: How is this different from LangChain/AutoGPT/CrewAI?**  
Those frameworks are largely prescriptions for how to *call* LLMs and chain their outputs. HACA is an architecture for how an agent *persists its identity over time*. They address different problems and are not mutually exclusive — you could implement the HACA pattern *on top of* a framework like LangChain.

**Q: What happens when the entity has no memory (first boot)?**
The entity executes the **First Activation Protocol (FAP)** before doing anything else. FAP collects operator identity, reads all capability definitions, writes a self-knowledge document to the MIL, and removes the cold-start sentinel. After FAP, the entity has an operator trust anchor and a memory scaffold — every subsequent boot loads these automatically. Without FAP, the entity would need to rediscover its own capabilities and operator context from scratch on every session.

**Q: Can two HACA entities communicate with each other?**  
Yes, via the HACA-Mesh extension. In the simplest case, one entity's EL can write a message to another entity's inbox, following the same atomic spooling pattern used for any other input.

**Q: Is HACA suitable for stateless/ephemeral agents that don't need persistence?**  
Technically, a fully stateless agent doesn't need HACA — HACA's value is precisely in managing persistent identity across many cycles. However, even for "short-lived" agents, the sandboxing and integrity verification aspects of HACA can add meaningful safety guarantees.

**Q: How do you handle model updates from the LLM provider?**  
This is exactly what Drift Control (Section 4) addresses. When the provider updates their model and behavior shifts, the drift probes detect it. The system halts MIL commits until the operator confirms the new behavior is acceptable and re-anchors the thresholds.

---

## 13. Status and Contributing

This Internet Draft is published for community review. The complete formal specification (with axiomatic definitions, mathematical drift metrics, and compliance test suites) is available in the `HACA/spec/` directory.

**Feedback welcome via GitHub Issues:**
- Is the terminology clear? Where did you get lost?
- Does the Cognitive Loop make sense to implement?
- Did you try to build something? What was hard?
- Are there use cases not covered by this model?

The goal of this document is to lower the barrier to entry. If something here requires more explanation to be implementable, that is a bug in the document.

---

## Normative References (Full Spec)

- `HACA/spec/HACA-Arch-1.0.0.md` (draft-orrico-haca-arch-07) — Root architecture: topology, trust model, compliance levels, Cognitive Profiles
- `HACA/spec/HACA-Core-1.0.0.md` (draft-orrico-haca-core-07) — Autonomous Cognitive Profile: formal axioms, drift measurement, Endure Protocol, compliance tests
- `HACA/spec/HACA-Symbiont-1.0.0.md` (draft-orrico-haca-symbiont-03) — Symbiont Cognitive Profile: Operator-bound cognition, memory metabolism, Heartbeat Protocol
- `HACA/spec/HACA-Security-1.0.0.md` (draft-orrico-haca-security-04) — Security extension: Byzantine host model, cryptographic auditability, temporal attack prevention
- `HACA/spec/HACA-CMI-1.0.0.md` (draft-orrico-haca-cmi-01) — Cognitive Mesh Interface: multi-system coordination, federated memory exchange, mesh compliance
- `implementation/fcp-spec/` — FCP: Filesystem Cognitive Platform implementation profile (POSIX filesystem state layer)
