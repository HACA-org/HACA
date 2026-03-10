```
Network Working Group                                         J. Orrico
Internet-Draft                                          HACA Standard
Intended status: Informational                          March 8, 2026
Expires: September 8, 2026


          Host-Agnostic Cognitive Architecture (HACA) — Architecture
                       draft-orrico-haca-arch-01


Abstract

   This document specifies the root architectural framework for the
   Host-Agnostic Cognitive Architecture (HACA). HACA-Arch defines the
   structural topology, component responsibilities, integrity model,
   lifecycle contracts, and trust invariants required for cognitive
   entities built on top of language models to maintain persistent
   identity, verifiable state, and mediated execution across
   heterogeneous host environments.

   HACA-Arch does not define cognitive algorithms, reasoning logic,
   inference processing, specific security mechanisms, storage formats,
   or wire protocols. It establishes the systemic structure within which
   Cognitive Profiles (HACA-Core and HACA-Evolve) and extensions
   (HACA-Security, HACA-CMI) operate.

   A Cognitive Profile is a complete, self-consistent operational
   contract that governs a system's behavior on top of the shared
   HACA-Arch topology. Profiles are mutually exclusive: a deployment
   MUST select exactly one. HACA-Arch defines the structural invariants
   that all profiles share; it does not favor or require any specific
   profile.

Status of This Memo

   This Internet-Draft is submitted in full conformance with the
   provisions of BCP 78 and BCP 79.

   Internet-Drafts are working documents of the Internet Engineering
   Task Force (IETF). Note that other groups may also distribute
   working documents as Internet-Drafts. The list of current
   Internet-Drafts is at https://datatracker.ietf.org/drafts/current/.

   Internet-Drafts are draft documents valid for a maximum of six
   months and may be updated, replaced, or obsoleted by other documents
   at any time. It is inappropriate to use Internet-Drafts as reference
   material or to cite them other than as "work in progress."

   This Internet-Draft will expire on September 8, 2026.

Copyright Notice

   Copyright (c) 2026 IETF Trust and the persons identified as the
   document authors. All rights reserved.

   This document is subject to BCP 78 and the IETF Trust's Legal
   Provisions Relating to IETF Documents
   (https://trustee.ietf.org/license-info) in effect on the date of
   publication of this document. Please review these documents
   carefully, as they describe your rights and restrictions with
   respect to this document.
```

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [Conventions and Terminology](#2-conventions-and-terminology)
3. [HACA Ecosystem](#3-haca-ecosystem)
   - 3.1 [Cognitive Profiles](#31-cognitive-profiles)
   - 3.2 [Extensions](#32-extensions)
4. [Concepts](#4-concepts)
   - 4.1 [Entity](#41-entity)
   - 4.2 [Cognition](#42-cognition)
   - 4.3 [Memory](#43-memory)
   - 4.4 [Integrity](#44-integrity)
   - 4.5 [Individuation](#45-individuation)
5. [Components](#5-components)
   - 5.1 [CPE — Cognitive Processing Engine](#51-cpe--cognitive-processing-engine)
   - 5.2 [MIL — Memory Interface Layer](#52-mil--memory-interface-layer)
   - 5.3 [EXEC — Execution Layer](#53-exec--execution-layer)
   - 5.4 [SIL — System Integrity Layer](#54-sil--system-integrity-layer)
   - 5.5 [CMI — Cognitive Mesh Interface](#55-cmi--cognitive-mesh-interface)
6. [Integration](#6-integration)
   - 6.1 [Component Topology](#61-component-topology)
   - 6.2 [Trust Model](#62-trust-model)
   - 6.3 [Concept Realization](#63-concept-realization)
7. [Lifecycle](#7-lifecycle)
   - 7.1 [Cold-Start and First Activation](#71-cold-start-and-first-activation)
   - 7.2 [Boot Sequence](#72-boot-sequence)
   - 7.3 [Session Cycle](#73-session-cycle)
   - 7.4 [Sleep Cycle and Maintenance](#74-sleep-cycle-and-maintenance)
   - 7.5 [Decommission](#75-decommission)
8. [Security Considerations](#8-security-considerations)
   - 8.1 [Structural Guarantees](#81-structural-guarantees)
   - 8.2 [Prompt Injection](#82-prompt-injection)
   - 8.3 [Evolution Proposal Content](#83-evolution-proposal-content)
   - 8.4 [Entity Store Tampering](#84-entity-store-tampering)
   - 8.5 [Mesh Spoofing and Sybil Attacks](#85-mesh-spoofing-and-sybil-attacks)
   - 8.6 [Scope Boundary](#86-scope-boundary)
   - 8.7 [Operator Channel Authentication](#87-operator-channel-authentication)
9. [IANA Considerations](#9-iana-considerations)
10. [References](#10-references)
    - 10.1 [Normative References](#101-normative-references)
    - 10.2 [Informative References](#102-informative-references)
11. [Glossary](#11-glossary)
12. [Author's Address](#12-authors-address)

---

## 1. Introduction

Cognitive entities built on top of language models face a fundamental structural problem: the model is stateless, the hosting environment is heterogeneous, and no common specification defines what it means for such an entity to persist across sessions, maintain a verifiable identity, or evolve its structure in a controlled and auditable way. The result is a proliferation of ad-hoc implementations where the "entity" is implicitly defined by the surrounding infrastructure — tightly coupled to a specific host, unportable, and structurally opaque.

HACA addresses this by inverting the dependency. The language model is treated as infrastructure — a stateless inference engine that the entity uses but MUST NOT depend on for continuity. The entity's ground truth is a portable, implementation-agnostic data store — the **Entity Store** — owned and controlled by the human Operator, containing everything required to reconstruct the entity's operational state: identity, memories, skills, configurations, and execution history. Portability is a structural guarantee: migrating the Entity Store to a different host, with any compatible inference engine, MUST fully restore the entity's structural and mnemonic state. The entity's operational history remains available for retrieval; what the cognitive engine loads into its active context at any given session is necessarily selective and is determined by the implementation's context management strategy. The inference engine MAY be replaced; the entity persists.

This architectural decision has a direct consequence for the integrity model. If the entity's state is entirely contained in the Entity Store, then structural consistency, authorized evolution, and verifiable identity can all be defined in terms of that store — without reference to any specific host or runtime. This specification defines the invariants that enforce this: a single authorized evolutionary protocol through which all structural writes MUST pass, a cryptographic chain anchored at the entity's genesis state as the verifiable history of its evolution, and a continuous integrity monitoring mechanism for detecting and responding to deviation.

Every HACA deployment MUST operate under exactly one permanent operational contract — selected at first activation and binding for the entity's entire lifetime — that determines its autonomy model, memory architecture, and drift tolerance. This specification defines two such contracts: one for zero-autonomy deployments where all structural evolution requires explicit Operator instruction, and one for supervised-autonomy deployments where the entity MAY initiate structural evolution within its authorized scope. These contracts are formally defined in Section 3 as the Cognitive Profiles.

---

## 2. Conventions and Terminology

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in BCP 14 [RFC2119] [RFC8174] when, and only when, they appear in all capitals, as shown here.

The following terms are used throughout this document. A normative glossary appears in Section 11.

- **Entity Store**: The persistent, portable, implementation-agnostic data store containing all artifacts required to reconstruct a HACA-compliant entity's operational state.
- **Operator**: The human authority to whom the entity is bound.
- **Cognitive Profile**: A mutually exclusive, permanent operational contract selected at first activation.
- **Session Token**: The operational credential that authorizes active cognition.
- **Integrity Document**: The cryptographic baseline of the entity's structural state.
- **Genesis Omega**: The cryptographic root of the entity's integrity chain, derived at first activation.
- **Endure Protocol**: The sole authorized path for structural writes to the Entity Store.
- **Sleep Cycle**: The post-session maintenance window in which memory consolidation and structural evolution execute.

---

## 3. HACA Ecosystem

The HACA Ecosystem defines the two layers that sit above the base architecture: Cognitive Profiles, which determine the entity's operational contract for its entire lifetime, and Extensions, which add optional capabilities on top of any profile. A deployment MUST select exactly one profile and MAY select zero or more extensions. These choices MUST be made before or at first activation and are binding for the entity's lifetime.

### 3.1 Cognitive Profiles

A Cognitive Profile MUST be selected at first activation and defines the operational contract under which the entity runs for its entire lifecycle. Profiles are mutually exclusive and permanent — no migration path exists between them. A profile selection is a fundamental architectural decision about the entity's operational model, not a configuration parameter. An implementation that changes its declared Cognitive Profile MUST be treated as a new entity with no identity continuity from the previous deployment.

**HACA-Core** is the zero-autonomy profile. The entity's persona, capabilities, and operational limits are defined by the Operator at first activation and sealed as the entity's structural baseline. The entity MUST NOT initiate structural evolution autonomously — the evolutionary protocol is available but MUST only be triggered by an explicit human Operator instruction. Any structural deviation from the sealed baseline MUST be classified as a Critical integrity failure. Semantic knowledge accumulated during operation MUST remain exclusively mnemonic: the cognitive engine MUST NOT produce structural evolution proposals without explicit Operator authorization, and any Semantic Drift detected during memory consolidation MUST escalate directly to Critical — the integrity layer has no external indicator by which to independently verify semantic content. HACA-Core REQUIRES a Transparent cognitive engine topology — one in which the model is accessed exclusively as an inference API and the HACA integration layer has exclusive control over all routing, component interaction, and host actuation. Each component MUST operate within its declared scope only; no external agent SHALL inject capabilities or context outside the HACA-mediated pipeline. It is the REQUIRED profile for industrial agents, critical automation pipelines, and regulated deployment contexts.

**HACA-Evolve** is the supervised-autonomy profile. The entity MAY initiate structural evolution autonomously — triggering the evolutionary protocol to calibrate its persona, consolidate semantic knowledge, and acquire new skills — within the scope of its current operational authorization. The cognitive engine MAY produce structural evolution proposals autonomously; the integrity layer MUST authorize proposals that fall within the entity's current operational authorization scope and queue them as evolutionary events. Semantic Drift detected during memory consolidation MUST be treated as a signal for potential consolidation rather than an automatic anomaly — the integrity layer MUST evaluate whether the drift is covered by an approved proposal or represents an unauthorized deviation. Any write to a data store outside the local Entity Store REQUIRES explicit Operator authorization. HACA-Evolve supports both Transparent and Opaque cognitive engine topologies. It is the designated profile for long-duration assistants and companion agents where incremental trust accumulation between entity and Operator is an intended outcome.

### 3.2 Extensions

Extensions add optional capabilities on top of the base architecture. They are additive and non-contradicting: an extension MAY strengthen a requirement defined in this specification, but MUST NOT weaken or override it. Extensions are profile-agnostic — they apply to any deployment regardless of the active Cognitive Profile.

**HACA-Security** elevates the trust model from Semi-Trusted to Byzantine (zero default trust). It adds cryptographic auditability through hash-linked audit logs, temporal attack detection, hardened key management, and rollback protection. HACA-Security is REQUIRED for deployments in multi-tenant cloud environments, adversarial hosts, or any context where tamper-evident audit trails are mandatory.

**HACA-CMI** defines the multi-node coordination protocol that enables a set of independent HACA-compliant nodes to form a Cognitive Mesh. It specifies the wire format, peer discovery, session establishment, federated memory exchange, and mesh fault taxonomy. HACA-CMI activates the Cognitive Mesh Interface component.

---

## 4. Concepts

The five foundational concepts below define what a HACA entity is, how it thinks, how it remembers, how it maintains integrity, and how it comes into existence. Together they establish the vocabulary and invariants on which all component definitions and lifecycle protocols in subsequent sections are built.

### 4.1 Entity

An entity is defined by the complete contents of its **Entity Store** — the persistent, portable data store containing everything required to reconstruct the entity's operational state: identity, memories, skills, configurations, and execution history. The Entity Store is an abstraction; the implementation selects the substrate — a directory, a database, an object store, or any equivalent. Migrating the Entity Store to a different host MUST fully restore the entity on that host.

The language model is not the entity. The **Operator** is not the entity — the Operator is the human authority to whom the entity is bound, who defines its maximum authorization scope and without whose active binding the entity MUST suspend all intent generation. Both are external by default: the model is a stateless inference engine; the Operator provides authorization and intent. At session instantiation, the model is loaded and the Operator opens a session — at that point, the Entity Store, model, and Operator form the entity's active operational boundary. At rest, the entity is the Entity Store. The Operator interacts with the entity through direct input — the primary source of external stimuli during an active session — and through explicit authorization acts: enrolling at first activation, authorizing structural evolution, and initiating or terminating sessions.

The **persona** is the layer within the Entity Store that defines the entity's behavioral constraints, operational drives, and response characteristics. The persona is the primary differentiator between entities sharing the same inference model.

**Omega** is the runtime operational state of the entity: the active configuration produced by the Entity Store, the loaded model, and the Operator binding operating together within a session. Omega is instantiated at session start and terminated at session end. It is strictly local — it MUST NOT transfer, replicate, or propagate beyond the active session boundary. When a session ends, Omega is terminated; the Entity Store persists. The cryptographic anchor of the entity's first Omega state — the **Genesis Omega**, defined in §3.5 — becomes the root of the integrity chain and the reference point against which all future structural evolution is measured.

Omega is **structurally immutable at runtime**: no external instruction — including an instruction from the Operator — SHALL modify the entity's structural configuration directly during an active session. The structural configuration — persona, skills, consolidated semantic knowledge, Operator Bound, and genesis anchor — MUST remain fixed for the duration of the session. Session state — the context window, active memories, and accumulated cycle outputs — MAY evolve normally through the cognitive pipeline and is not subject to this constraint. Structural changes MUST only be applied by profile-defined internal processes validated by the integrity layer, and MUST only occur between sessions.

The **Genesis Omega** is the cryptographic digest of the entity's verified identity state at first activation. It is the root node of the entity's integrity chain. Each subsequent authorized structural evolution extends this chain by one verified commit. An entity that cannot produce a valid, unbroken chain of integrity records from its current state back to the Genesis Omega MUST NOT claim to be the original entity and MUST NOT continue operating as such.

The **Entity Artifact Boundary** defines two operationally distinct scopes within any deployment: the Entity Store — containing all artifacts governed by the evolutionary protocol (persona, skills, configurations, integrity records) — and the project workspace, which is everything outside it. Any structural write to the Entity Store is an evolutionary event and MUST be executed exclusively through the evolutionary protocol. Mnemonic writes, integrity writes, and session token persistence follow their own defined paths and are not evolutionary events. Any operation on the project workspace is a project operation and MUST NOT be treated as an evolutionary event, regardless of content. Conflating the two is a Consistency Fault. This boundary exists to prevent inadvertent self-modification during normal task execution and to ensure the entity cannot be socially engineered into committing to its own identity under the pretense of project work.

### 4.2 Cognition

Cognition is the processing cycle in which the entity receives a stimulus, generates intent, and produces actions or state writes. This section defines the atomic unit of cognition, the session boundaries within which it operates, the stimulus and intent model that drives it, and the two special intent types — Evolution Proposals and the Closure Payload — that govern structural evolution and session continuity. It is active only while a valid **session token** exists — the operational credential that authorizes active cognition, issued at the start of each session and revocable at any point. The entity's reasoning is produced by the cognitive engine through the interaction of two inputs: the persona layer, which applies behavioral constraints, and the model, which performs inference. Both inputs are REQUIRED; the output of the reasoning phase is a single structured intent payload.

A **Cognitive Cycle** is the atomic unit of cognition: stimulus received → context loaded → intent generated → intent dispatched. The cycle is complete when the intent leaves the cognitive engine. What follows — skill execution, state persistence, integrity monitoring — is the consequence of the dispatched intent, handled by the responsible components independently.

A **Session Cycle** is the end-to-end operational span — from session token validation to session close. It encompasses all Cognitive Cycles within it and a maintenance window — the Sleep Cycle — that follows session termination. Integrity monitoring MUST operate continuously across the entire Session Cycle.

A **stimulus** initiates a Cognitive Cycle. Valid stimulus origins are: direct Operator input, internal scheduled triggers, responses from internal components, or — when the cognitive mesh is present — inbound signals from peer entities. A stimulus received without an active session token MUST be held in a pre-session buffer managed by the memory layer and processed as the first stimulus of the next session once a token is issued. The buffer's capacity, ordering semantics, persistence guarantee, and overflow policy are defined by the active Cognitive Profile. At minimum, the buffer MUST preserve stimulus ordering and MUST NOT silently discard stimuli without logging the discard event.

Not all stimuli carry equal urgency. Operator direct input takes precedence over chain continuations — it suspends the active chain and MUST be processed first. Scheduled triggers, component responses, and cognitive mesh inbound signals MUST be queued behind any active chain. Integrity layer signals — token revocation and Critical escalation — are not stimuli: they operate below the cognitive pipeline and MUST take effect regardless of chain state.

**Intent** is the output of the cognitive engine's reasoning phase — a single structured payload addressed to exactly one component: an action payload to the execution layer, a state-write payload to the memory layer, an Evolution Proposal to the integrity layer, a session-close signal to the integrity layer, or — when the cognitive mesh interface is present — an outbound message payload. A session-close signal instructs the integrity layer to initiate normal session close. It carries the **Closure Payload** — a structured package produced by the CPE only at a safe session close, containing: the consolidation content for the memory layer to write to the Memory Store; the Working Memory declaration, which the integrity layer passes to the memory layer to build the pointer map after consolidation; and the updated **Session Handoff** — a forward-looking record of pending tasks, next steps, and continuity context that the memory layer stores as a dedicated Memory Store record and the Working Memory points to directly. At the start of the next session, the cognitive engine accesses the Session Handoff via a memory recall as its first internal context. A Cognitive Cycle MUST produce exactly one intent payload.

When a model produces a multi-step reasoning output — multiple actions or state writes that together constitute a single logical operation — the HACA integration layer MUST serialize these into a **Cycle Chain**: a sequence of consecutive Cognitive Cycles where the result of each cycle is the internal stimulus for the next. No external stimulus is required between cycles in a chain; the chain proceeds automatically from cycle to cycle. Between each cycle, the cognitive engine MUST perform a **preemption check**. Operator direct input MUST suspend the chain after the current cycle completes and MUST be processed as a normal Cognitive Cycle, after which the chain either resumes or is discarded if the Operator issued a cancellation. All other stimuli MUST be queued until the chain completes or is discarded. Integrity layer signals — token revocation, Critical escalation — operate below this preemption model entirely: they are infrastructure-level interruptions that MUST take effect regardless of chain state and do not require a preemption check to be processed. Each cycle in a chain is individually atomic and auditable — the integrity and memory layers MUST process each cycle's output independently. Suspending or discarding a chain MUST NOT affect cycles that have already completed; each completed cycle's intent was dispatched, logged, and processed — it stands on its own.

An **action** is the execution of an intent payload by the execution layer. Each action is an isolated, stateless transaction scoped to a single declared skill. Execution REQUIRES a two-gate authorization: a Skill Index check — the integrity layer's pre-authorization established at boot — followed by manifest validation by the execution layer. If either gate fails, the action MUST be rejected; the execution layer MUST signal the integrity layer and the memory layer to log the rejection. The result MUST be returned to the cognitive engine; the execution layer MUST simultaneously signal the memory layer to log it.

An **Evolution Proposal** is a special class of intent payload addressed to the integrity layer, declaring a proposed self-evolution — changes to the entity's structure or accumulated semantic knowledge that the cognitive engine considers significant enough to become part of the entity's identity baseline. All structural evolution and accumulated semantic knowledge promotion REQUIRE Operator authorization: under HACA-Core, this authorization MUST be explicit per proposal; under HACA-Evolve, the Operator grants implicit authorization at first activation for evolution within the entity's defined scope. The integrity layer MUST verify that every proposal is covered by valid Operator authorization before any change takes effect — acting as a second security layer against malicious or unintended changes that may have bypassed the Operator's attention. A proposal without valid authorization coverage MUST be rejected and logged; the proposed content MUST remain unchanged. A verified proposal MUST NOT take effect immediately — it MUST be queued as a pending evolutionary event and executed during the next Sleep Cycle via the evolutionary protocol.

The Memory Store MUST NOT be pre-loaded into the cognitive engine's context at the start of each Cognitive Cycle. It MUST be accessible on demand: the cognitive engine issues queries to the memory layer during cognition, and the memory layer returns the specific records requested. The persona — part of the structural baseline — is loaded at boot and remains available throughout the session without additional queries. The Session Store — the accumulating record of the current session — is available in full throughout the session. The Memory Store MUST be accessed only when the cognitive engine requires knowledge from previous sessions or consolidated semantic knowledge not present in the current session context. The cost of a Cognitive Cycle is therefore independent of Memory Store size.

### 4.3 Memory

Memory is the entity's authoritative state store. It is partitioned into two stores: the **Session Store** — active session data and current operational context — and the **Memory Store** — episodic records of past operations and semantic knowledge accumulated over time. Both stores MUST be managed exclusively by the memory layer.

The memory layer MUST NOT interpret or evaluate stored data; it reads and writes on request. Memory consolidation — the transfer of session data into long-term episodic and semantic records — and garbage collection MUST occur during the **Sleep Cycle** — a dedicated post-session maintenance window that runs after every Session Cycle closes. The Sleep Cycle is detailed in Section 7.4.

Skills that produce irreversible side effects — payments, commands to external systems, physical actuations — create a recovery risk when a crash occurs before the Sleep Cycle consolidates session memory: the entity may not know whether the action already executed. The **Action Ledger** addresses this: a write-ahead record in the Session Store that logs the intent before execution and resolves it after. If a crash occurs between intent and resolution, the unresolved entries surface at the next boot for Operator review — rather than being silently lost or blindly re-executed. The criteria for which skills MUST be logged and the resolution procedure are defined by the active Cognitive Profile.

### 4.4 Integrity

Integrity is the set of architectural mechanisms that ensure the entity's structure and behavior remain consistent with its defined and authorized state. This section defines the four integrity mechanisms — the Integrity Document, the Endure Protocol, the Heartbeat Protocol, and the Drift Framework — and the content classes that determine write authority within the Entity Store.

The **Integrity Document** is generated at first activation and contains the cryptographic hash of every file constituting structural content across all components. It MUST be verified at every boot, before every skill execution, and at defined intervals during active operation. Any hash mismatch MUST be treated as evidence of unauthorized structural modification and MUST trigger an immediate integrity layer response.

The **Integrity Log** is the append-only record of integrity events maintained by the integrity layer within the Entity Store. It MUST NOT be written by the memory layer's mnemonic pipeline and MUST NOT be subject to garbage collection. Where the Integrity Document defines what the entity's structure should be, the Integrity Log records what has happened to it. For long-lived entities, the log will grow indefinitely — Heartbeat records, Skill Results, and Endure commits accumulate without bound. The evolutionary chain MUST NOT be compacted, as it is the basis of identity continuity; but routine operational records may be candidates for archival or compaction. Profiles and extensions MAY define a compaction policy for non-chain records.

The Entity Store contains three classes of content with distinct write semantics:

- **Mnemonic content** — memory records and operational state — is written continuously by the memory layer during normal operation. These writes require no additional authorization; however, accumulated semantic knowledge MAY be proposed for promotion to the entity's structural baseline via an Evolution Proposal, which REQUIRES Operator authorization.
- **Structural content** — persona definitions, skill manifests, configurations, behavioral parameters, and Semantic Probes — changes infrequently. Every structural write is an evolutionary event and REQUIRES explicit authorization. Structural writes MUST pass through the Endure Protocol.
- **Integrity content** — the Integrity Document, the Integrity Log, and the session token — MUST be written exclusively by the integrity layer. No other component SHALL have write authority over integrity content.

The **Endure Protocol** is the evolutionary protocol — the sole authorized path for structural writes to the Entity Store. Any structural modification — skill addition, persona calibration, configuration update, behavioral correction — MUST pass through Endure. A structural write that bypasses Endure is an unauthorized mutation, regardless of its origin, and MUST be treated as an integrity violation. Endure is owned and orchestrated by the integrity layer; it MUST execute only during a Sleep Cycle, via a staged pipeline:

```
staging → validation → snapshot → atomic commit (write lock) → resumption
```

The integrity layer MUST control the write lock and drive each stage in sequence. The write lock covers structural content only — it MUST NOT block integrity content writes; the integrity layer MAY continue writing to the Integrity Log throughout the Endure pipeline. The atomic commit MUST write all structural files — including the Integrity Document — as a single indivisible operation. If the commit fails, the integrity layer MUST restore the snapshot and the entity MUST resume from its last verified structural state. No partial structural evolution SHALL be externally visible at any point in the pipeline.

To prevent boot integrity validation from scaling linearly with the number of evolutionary commits, the Endure Protocol MUST maintain **Integrity Chain Checkpoints**. A checkpoint MUST be produced by the integrity layer at defined intervals — every `C` Endure commits, where `C` MUST be declared in the entity's structural baseline. Each checkpoint MUST record a verified digest of the full integrity chain up to and including the checkpoint commit, anchored against the Genesis Omega at the time of creation, and MUST be stored in the Integrity Document as part of the same atomic Endure commit. At boot, chain validation MUST cover only the commits since the last verified checkpoint — not the full chain from Genesis Omega. The checkpoint digest in the Integrity Document MUST be verified as part of structural validation; the chain from the checkpoint to the current state MUST then be validated incrementally. An entity with no checkpoint yet — fewer than `C` commits since Genesis Omega — MUST validate the full chain as normal.

The **Heartbeat Protocol** MUST run asynchronously and continuously alongside active operation. The integrity layer MUST track operational activity and perform a Vital Check when either a threshold `T` is reached or a maximum time interval `I` has elapsed since the last Vital Check — whichever comes first. This dual trigger ensures that Vital Checks occur even when the entity is idle or operational activity has stalled.

Not every fault is an anomaly. Isolated, transient faults are expected in normal operation — the integrity layer SHOULD treat them as noise and attempt correction before escalating. A condition becomes a genuine anomaly only when it persists after a corrective attempt, cannot be independently verified from outside the affected component, or involves a component with no valid correction path.

The Vital Check MUST produce one of three states:

- **Nominal** — all component hashes match the Integrity Document; all health signals are within bounds. Operation MUST continue without interruption.
- **Degraded** — a localized anomaly is detected that the integrity layer can independently verify from outside the affected component — through structural hash comparison, health signal deviation, or other external indicators defined by the active profile specification. The integrity layer MUST issue a corrective signal to the affected component; the component MUST execute its corrective action within its declared authority. The integrity layer MUST then independently re-verify the condition: if re-verification confirms resolution, operation MUST continue without interruption; if re-verification fails, the condition MUST escalate to Critical. Anomalies that cannot be independently verified by the integrity layer MUST escalate directly to Critical — a compromised component MUST NOT be trusted to self-report a successful repair.
- **Critical** — the anomaly exceeds the integrity layer's correction capacity, or the anomaly involves the cognitive engine or the integrity layer itself. The session token MUST be immediately revoked; the integrity layer MUST escalate to the Operator via the Operator Channel.

The threshold `T`, the activity metric used to reach it, and the maximum time interval `I` are all defined at implementation time. The integrity layer MUST also maintain a watchdog timer per active skill execution — if the execution deadline expires before the skill returns, the condition MUST be treated as Critical. The watchdog timeout is defined at implementation time.

The **Drift Framework** defines three categories of behavioral or structural deviation. Detection is centralized in the integrity layer, which MUST monitor all three drift categories directly. The integrity layer MUST classify and respond to all detected drift. The Genesis Omega is the cryptographic root against which all drift is ultimately referenced. Each evolutionary commit MUST extend the integrity chain by one link — recording the resulting structural state and referencing the previous link — forming a verifiable sequence from the Genesis Omega to the current state. Detection criteria, tolerance thresholds, and response procedures for each drift type are defined by the active profile specification.

**Semantic Probes** are the entity's semantic drift reference baseline — a set of semantic anchors derived from structural content and maintained by the integrity layer. The integrity layer MUST use semantic probes as reference anchors to measure divergence during the Sleep Cycle via an implementation-defined comparison mechanism. Probes MUST be initialized from the Imprint Record at first activation and MUST be updated only through authorized structural evolution.

- **Semantic Drift** — accumulated memory content has diverged from the entity's Semantic Probes. **MUST be detected by the integrity layer** during the Sleep Cycle, by comparing the accumulated Memory Store content against the Semantic Probes via an implementation-defined comparison mechanism. Since detection occurs while the cognitive engine is not active, probe isolation is guaranteed by the lifecycle boundary. Under HACA-Core, any divergence MUST escalate directly to Critical. Under HACA-Evolve, the integrity layer MUST cross-reference the signal against queued Evolution Proposals: covered divergence proceeds to the evolutionary protocol; uncovered divergence MUST be treated as an anomaly.

  Any comparison mechanism with semantic depth will involve some form of inference, which introduces probabilistic fallibility into a detection path that would otherwise be deterministic. Profiles should define Semantic Probes in two layers: a deterministic layer — required keywords, forbidden patterns, content hashes — that requires no inference and confirms drift without ambiguity; and a probabilistic layer — similarity scores, embedding distances — for subtler divergence that cannot be expressed as hard rules. The deterministic layer should always run first; if it already confirms drift, the probabilistic layer is unnecessary. The inference resource used for probabilistic comparison MUST be isolated from the cognitive engine — either a dedicated embedding service or a worker skill invoked by the execution layer at the integrity layer's request — to prevent the comparison mechanism from inheriting the same drift it is trying to detect.

  To avoid rescanning the full Memory Store at each Sleep Cycle, the integrity layer MUST maintain a **Semantic Digest** — a running aggregate metric over the entity's accumulated memory content, updated incrementally per Sleep Cycle. Only the session's newly consolidated content MUST contribute to each update. The Semantic Digest MUST be stored as integrity content and MUST be covered by the Integrity Document. Semantic Drift detection MUST compare the current digest against the Semantic Probes rather than the raw Memory Store. The digest's format and aggregation method are implementation-defined; implementations using inference-based metrics MUST apply the same inference isolation requirement as direct comparison.
- **Identity Drift** — the active persona configuration has diverged from its last committed structural definition. **MUST be detected by the integrity layer** per Heartbeat Vital Check through structural hash comparison against the Integrity Document.
- **Evolutionary Drift** — a discontinuity or authorization gap in the integrity chain: a commit that does not reference its predecessor, a structural state whose hash does not match the recorded commit, or a recorded evolution that lacks a corresponding Operator authorization. **MUST be detected by the integrity layer** at each evolutionary protocol execution through integrity chain analysis. Any detected discontinuity or unauthorized commit MUST escalate directly to Critical and the session token MUST be immediately revoked — an entity that cannot produce a valid, unbroken chain from its current state back to the Genesis Omega MUST NOT claim to be the original entity and MUST NOT continue operating as such.

### 4.5 Individuation

Individuation is the initialization process that produces a unique, Operator-bound entity instance with a verifiable identity record. It MUST occur exactly once per entity, during the entity's first activation — a one-time sequential bootstrap procedure defined at the end of this section as the **FAP** (First Activation Protocol).

The **Operator Bound** is the persistent link between the entity and its Operator, established during first activation. The minimum required fields are the Operator's name and email address; implementations MAY extend this set but MUST NOT omit these two fields. The minimum fields alone provide low entropy — deployments requiring resistance to identity spoofing MUST extend the field set with high-entropy identifiers; cryptographic key-based binding mechanisms are defined in HACA-Security. A deterministic cryptographic digest of the Operator's identifying fields produces the **Operator Hash** — the entity's permanent identifier for its bound Operator. The Operator Bound can only be dissolved or transferred by explicit Operator authorization.

The Bound binds the entity to a single human authority. Deployments requiring delegation, succession, or shared oversight — such as organizational or industrial pipelines where the bound Operator may become unavailable — should extend the Bound with implementation-specific mechanisms that maintain the invariant: every authorization act MUST be ultimately traceable to a human authority. The mechanism for succession when the Operator is permanently unavailable is outside this specification's scope and MUST be addressed by the deployment's governance policy.

**Imprint** is the one-time initialization event that establishes the entity's identity. It MUST execute exactly once, during the first boot in which the Memory Store is empty. Imprint produces three artifacts: the **Imprint Record** — the persistent record of the entity's initial identity, Operator Bound, structural baseline, and the versions of the HACA-Arch specification and active Cognitive Profile under which the entity was initialized — written to the Memory Store; the **Integrity Document** — the cryptographic baseline of the entity's structural state, derived from the Imprint Record; and the **Genesis Omega** — the cryptographic digest of the finalized Imprint Record, which includes the Integrity Document, stored as the root node of the integrity chain. This ensures the genesis anchor covers both the entity's identity baseline and its structural cryptographic baseline in a single verifiable root. At every subsequent boot, the integrity layer MUST verify its own Integrity Document against the genesis anchor before trusting any other component. The presence of the Imprint Record in the Memory Store is the definitive indicator that a valid entity instance exists. Re-executing Imprint on an entity with an existing Imprint Record is a protocol violation and MUST be rejected.

The Imprint Record resides in the Memory Store — it is mnemonic content by nature: the entity's initial essence, the record of who it is. Its role in integrity is a consequence of that essence, not a reclassification: the Genesis Omega is derived from it, and every boot is ultimately verified against it. Every time the entity wakes, it knows who it is because this record exists. For this reason, the SIL MUST load the Imprint Record directly at every boot as part of the Boot Manifest, independently of the normal mnemonic pipeline. It is the only Memory Store artefact with this property — all other Memory Store content is accessed on demand during the session.

The **Operator Channel** is a system-level host primitive — a direct function that allows authorized components to contact the Operator when a critical condition exceeds the entity's self-regulation capacity. It MUST operate below the cognitive pipeline: it MUST NOT be implemented as a skill, MUST NOT route through the execution layer, and MUST be independent of all cognitive components and session state. Any component with escalation authorization MAY invoke it directly; this is the mechanism by which components bypass the integrity layer when the integrity layer itself is the source of the anomaly. The specific mechanism is defined at implementation time; the requirement that it operates independently of any cognitive component is invariant.

If the active Operator Channel mechanism fails to deliver an escalation after `N_channel` consecutive attempts, the integrity layer MUST activate the **Passive Distress Beacon**. The beacon is a persistent, passive signal written to the Entity Store — detectable without network connectivity or running processes. The entity MUST enter a suspended halt: no new session token SHALL be issued and no Cognitive Cycles SHALL execute until an Operator explicitly clears the beacon and acknowledges the condition. The threshold N and the beacon mechanism are defined at implementation time.

Prior to the FAP, the implementation populates the Entity Store with the initial structural baseline — persona definition, skill manifests, and any deployment-defined configurations. This is an installation-time operation outside the FAP's scope. The **FAP** (First Activation Protocol) is the sequential bootstrap procedure that executes the Imprint. The FAP is not a Cognitive Cycle — no session token exists at this stage and the cognitive engine reasoning layer is not active. The FAP MUST execute as a gated sequential pipeline:

```
structural validation → host environment capture → Operator enrollment →
Operator Channel initialization → Integrity Document generated →
Imprint Record finalized (includes Integrity Document) and written to
Memory Store → Genesis Omega derived → first session token issued
```

The FAP is atomic with respect to its own outputs: it MUST either complete fully — writing the Imprint Record, Integrity Document, Genesis Omega, and first session token — or revert all of its own writes, leaving the pre-installed structural baseline intact but the entity uninitialized. Any failure before FAP completion leaves the Memory Store without an Imprint Record; the FAP MUST re-execute on the next boot. The entity MUST NOT enter a partially-initialized state.

---

## 5. Components

The five components are the structural units through which the concepts in Section 4 are operationalized. Each component has a single, non-overlapping responsibility: no component SHALL perform the function of another, and no function SHALL be performed by more than one component.

### 5.1 CPE — Cognitive Processing Engine

The **CPE** (Cognitive Processing Engine) is the primary processing unit and the boundary at which the model is integrated into the entity's operational scope. At session start, the model is loaded into the CPE alongside the persona and current session state. In a Transparent topology, the model operates within the entity's boundary — subject to persona constraints — for the duration of the session. In an Opaque topology, the model is accessed as external infrastructure; the CPE mediates all interactions with it but cannot guarantee the model operates exclusively within the entity's boundary.

The CPE holds the active context window: the loaded persona, the instantiated model, and the accumulating record of reasoning, exchanges, and action results within the current Cognitive Cycle. At the close of each Cognitive Cycle, all state designated for retention MUST be committed to the memory layer. The CPE MUST NOT hold persistent state beyond the active session.

The CPE environment MUST be classified as one of two topology types, declared at deployment and constant across the entity's lifetime:

- **Transparent CPE** — the model is accessed exclusively as an inference API: it receives input and produces output tokens; all routing, component interaction, and host actuation MUST be handled by the HACA integration layer. The model MUST NOT act on the host directly — every effect MUST require a signal that passes through the HACA pipeline. Component separation is architecturally enforced by the integration layer.
- **Opaque CPE** — the model has native host access through an IDE, wrapper, or tool-enabled environment. The model emulates the HACA component responsibilities through its reasoning; component separation is a conceptual constraint applied by the model, not an architectural enforcement. The HACA layer cannot guarantee the model operates exclusively within the pipeline.

The topology classification is binding: HACA-Core REQUIRES Transparent CPE topology — its invariants presuppose full execution control unavailable in Opaque environments. HACA-Evolve supports both topologies; its supervised-autonomy model does not require exclusive pipeline control. A HACA-Core deployment that detects an Opaque CPE at boot MUST halt and refuse to proceed.

When the integrity layer issues a corrective signal to the CPE in a Degraded state, the CPE MUST execute one or more of the following corrective actions within its own authority: **context reload** — the active context window is discarded and reloaded from the memory layer, clearing any accumulated contamination without ending the session; **cycle reset** — the current Cognitive Cycle is aborted without commit, returning the CPE to a clean state for the next cycle. After a context reload or cycle reset, the integrity layer MUST independently re-verify the condition from outside the CPE. If re-verification fails, the condition MUST escalate to Critical. **session summarization** — the CPE produces a condensed representation of the accumulated Session Store content and signals the MIL to replace the current Session Store with the summarized version, reducing its physical size. After the MIL executes the write, the integrity layer MUST independently re-verify the Session Store size against the threshold `S`. If re-verification confirms the size is within bounds, operation continues; if re-verification fails, the condition MUST escalate to Critical. At normal session close, the CPE MUST produce the Closure Payload — carried in the session-close signal to the integrity layer. The consolidation content within the Closure Payload is the result of semantic consolidation: the CPE distills from the session what carries lasting value — learnings, preferences, insights, and relevant context — into the form the memory layer writes to the Memory Store. This is distinct from session summarization, which is a physical compression of the Session Store and carries no semantic intent.

The CPE MUST monitor context window utilization continuously. When utilization approaches a threshold at which further Cognitive Cycles cannot be executed reliably, the CPE MUST signal a **context window critical** condition to the integrity layer. If the active Cognitive Profile does not define a specific response, the default behavior is a normal session close — the integrity layer MUST initiate session termination and the Sleep Cycle MUST execute normally.

### 5.2 MIL — Memory Interface Layer

The **MIL** (Memory Interface Layer) is the entity's persistence layer and sole authoritative source of recorded state. The MIL MUST have exclusive write authority over mnemonic content — all read and write operations to the Session Store and the Memory Store. The Session Store is the primary contributor to context window consumption within a session — as it accumulates, each Cognitive Cycle operates against a larger baseline context. Session summarization reduces the Session Store's physical size and, consequently, the context window footprint of subsequent cycles. Mnemonic writes are continuous and require no authorization beyond the MIL's own operational authority; they are the normal output of the entity's operation. Accumulated semantic knowledge that becomes a candidate for promotion to the entity's structural baseline exits the mnemonic class and REQUIRES Operator authorization via an Evolution Proposal. The MIL MUST NOT interpret, evaluate, or make decisions about stored data.

Structural writes — modifications to the persona, skills, and configurations that define the entity's identity — are outside the MIL's write domain. Structural writes MUST be executed by the Endure Protocol, which is owned and orchestrated by the integrity layer. Both pipelines are independent and MAY execute within the same Sleep Cycle.

The MIL manages the mnemonic stages of the Sleep Cycle: it MUST initiate memory consolidation and MUST execute garbage collection. The Endure execution stage, when queued, is initiated and controlled by the integrity layer; the MIL MUST participate only to perform the physical atomic commit of structural files when the integrity layer issues the instruction.

The **Working Memory** is a compact, fixed-size artefact that the MIL MUST produce at the close of every normal Sleep Cycle. It is a navigation map — not a data snapshot: it MUST contain pointers into the Memory Store sufficient for the cognitive engine to resume from where the previous session ended. At session close, the CPE MUST include in its session-close signal to the SIL a declaration of which memory records are relevant for resumption — only the CPE has the session context to determine this. The CPE MUST select and prioritize within the fixed limit declared in the structural baseline; the declaration MUST NOT exceed this limit. The SIL MUST pass this declaration to the MIL when initiating the Sleep Cycle. The MIL MUST use this declaration to derive the actual Memory Store addresses after consolidation and MUST write the Working Memory as a pointer map to those addresses. The cognitive engine MUST use the Working Memory to know what to query from the memory layer at session start — not what the answers are. Memory retrieval against Working Memory pointers MUST follow the standard memory recall path: the CPE dispatches a memory recall to the MIL, which returns the record on demand. The size of the Working Memory MUST be fixed and declared in the entity's structural baseline; it MUST NOT grow with entity age or operational history. The Session Store size threshold `S`, above which the integrity layer triggers session summarization, MUST also be declared in the entity's structural baseline. The memory layer MUST report Session Store size to the integrity layer as part of its health signal; the integrity layer evaluates the reported size against the threshold `S` and issues a corrective signal when exceeded.

### 5.3 EXEC — Execution Layer

The **EXEC** (Execution Layer) is the entity's actuation layer and the sole component authorized to execute skills against the host environment — filesystem, terminal, external APIs, and any other external interface reachable through declared skills. This domain covers all cognitive host interactions: any operation on the host that is the result of a Cognitive Cycle. System-level host primitives — the Operator Channel and the Passive Distress Beacon — are outside this domain; they operate below the cognitive pipeline and are accessible directly to authorized components. In a Transparent topology, the HACA layer mediates all skill-based host access and this boundary is architecturally enforceable. In an Opaque topology, enforcement is the responsibility of the deployment configuration.

The EXEC is stateless — it MUST NOT retain state between executions. All executable capabilities MUST be packaged as **skills**: discrete, self-contained units within the Entity Store, each with a manifest that declares the skill's identity, required permissions, dependencies, and execution mode. The execution mode is either **synchronous** (default) or **background**. Synchronous skills block until they return and are subject to the integrity layer's watchdog timer. Background skills MUST NOT block: the EXEC MUST spawn the execution and immediately signal the SIL to record a **Skill Result** with `status=running` in the Integrity Log; the cycle MUST proceed normally. The EXEC MUST monitor its own background executions within the session. When a background skill completes within the active session, the EXEC MUST signal the SIL to update the Integrity Log record to its terminal status, then MUST signal the MIL to log the terminal Skill Result as operational context. A background skill result is only valid within the session that originated it — if the session ends before a terminal result is produced, the skill MUST be considered incomplete. At the next boot, the SIL MUST identify skills with no terminal record in the Integrity Log and surface them to the CPE as pending reprocessing stimuli at the start of the new session. The reprocessing criteria are defined by the active Cognitive Profile.

When a background skill spawns a host process that may outlive the session — a long-running job, a container, an async API call — the reprocessing path assumes the original execution is gone, and re-execution on the next boot risks duplicating effects. To avoid this, profiles should define whether background skill manifests must declare a handle type (a PID, job ID, or equivalent locator) so the EXEC can probe the host at boot and confirm the process state before classifying a skill as incomplete. A declared time-to-live on the manifest allows the SIL to classify expired skills as such without re-attaching.

A **worker skill** is a specialized skill class that invokes a stateless inference engine as part of its execution. Unlike general skills that interact with the host environment directly, a worker skill injects a work persona and task instructions into a clean model invocation — with no prior context, no Entity Store, and no session continuity. The invoked model is not a HACA entity: it carries no identity, holds no state beyond the invocation, and has no integrity obligations. The result is returned to the EXEC and processed as a normal Skill Result. Worker skills MUST follow the same two-gate authorization sequence as all other skills. When the task requires coordination between multiple concurrent work units — rather than a single, self-contained invocation — the appropriate mechanism is a Mesh Channel via the Cognitive Mesh Interface component.

Execution MUST follow a two-gate authorization sequence. The first gate is the **Skill Index** — a structural artefact loaded at boot as part of the Boot Manifest, pre-authorized by the integrity layer at each boot. If the requested skill is present in the index, the EXEC MUST proceed to the second gate. If the skill is absent, the EXEC MUST reject the payload, MUST signal the SIL, and MUST signal the MIL to log the rejection. The second gate is the EXEC's own manifest validation — permissions, dependencies, and execution context. If validation fails, the payload MUST be rejected — the EXEC MUST signal the SIL and MUST signal the MIL to log the rejection. If both gates pass, the skill executes. The Skill Result MUST be returned to the CPE; the EXEC MUST simultaneously signal the MIL to log it. The Skill Index is described in Section 5.4.

### 5.4 SIL — System Integrity Layer

The **SIL** (System Integrity Layer) is the entity's integrity monitoring and enforcement layer, and its highest internal authority. The SIL is the sole custodian of the Integrity Document — the cryptographic baseline against which all structural claims are verified.

The SIL MUST receive health signals from every component, evaluate them against defined integrity criteria, and — in Degraded conditions — issue corrective signals to the affected component. Each component is responsible for executing its own corrective actions within its authority when signaled by the SIL; the SIL MUST NOT directly manipulate another component's internal state. After issuing a corrective signal, the SIL MUST independently re-verify the condition using only external indicators before clearing the Degraded state. The SIL MUST detect all three drift categories directly: Semantic Drift through comparison of Memory Store content against Semantic Probes during the Sleep Cycle; Identity Drift through structural hash comparison against the Integrity Document per Heartbeat Vital Check; and Evolutionary Drift through integrity chain analysis at each evolutionary protocol execution. In all cases, classification and response are exclusively the SIL's responsibility. When the condition exceeds the SIL's correction authority, it MUST escalate to the Operator via the Operator Channel, bypassing the CPE — because the CPE may be the source of the detected anomaly.

The **Skill Index** is a structural artefact — persisted in the Entity Store and covered by the Integrity Document. It contains the set of skills authorized for execution, derived from the verified skill manifests in the structural baseline. Because it is part of the structural baseline, it MUST be updated exclusively through the Endure Protocol: when skills are added, removed, or modified, the Endure pipeline MUST reconstruct the Skill Index and record its hash in the Integrity Document as part of the same atomic commit. At boot, the SIL MUST verify the Skill Index hash against the Integrity Document. If the hash is valid, the index MUST be loaded as part of the Boot Manifest; if the hash does not match, the condition MUST be treated as Identity Drift — the SIL MUST NOT reconstruct the index silently; it MUST escalate before issuing a session token. If the Heartbeat Protocol detects a skill manifest hash mismatch during an active session, the SIL MUST NOT modify the Skill Index — removing an entry without an Endure commit would break the index's coverage under the Integrity Document. Instead, the condition MUST escalate immediately: the session token MUST be revoked, the anomaly MUST be logged to the Integrity Log, and the Operator MUST be notified via the Operator Channel. The Skill Index MUST be reconciled with the corrected structural state at the next Endure execution, before the next session token is issued.

The SIL is the owner and orchestrator of the Endure Protocol — the sole authorized path for structural writes to the Entity Store. During the Sleep Cycle, the SIL MUST control the Endure pipeline, hold the write lock, and instruct the MIL to perform the physical atomic commit at the appropriate stage. The SIL is also the verification layer for Evolution Proposals: when the CPE produces a proposal during a session, the SIL is the sole classifier — it MUST verify independently whether the proposal is covered by valid Operator authorization. Under HACA-Core, authorization is explicit and per-proposal: the SIL MUST check for a recorded Operator approval before queuing any proposal. Under HACA-Evolve, authorization is implicit within the entity's defined scope: the SIL MUST compare the proposal against the scope definition stored in the structural baseline and classify it as in-scope or out-of-scope without CPE input. Verified proposals MUST be queued as pending evolutionary events; proposals without valid authorization coverage MUST be rejected and logged — the rejection result MUST NOT be returned to the CPE.

The SIL is the sole issuer and custodian of the session token. The SIL MUST issue the first token at FAP completion and renew it at the start of each subsequent session. The SIL MAY revoke the token at any point; revocation MUST be immediate and MUST block all token-dependent component operations. The token's absence — whether caused by SIL revocation or direct Operator intervention on the Entity Store — MUST be treated as revocation by any component that verifies it. The session token MUST be persisted as a dedicated artefact in the Entity Store — containing the session ID and token value — written by the SIL at session open and removed by the SIL at the completion of the Sleep Cycle. Like the Passive Distress Beacon, this artefact MUST be directly accessible to the Operator without requiring any active component — enabling direct Operator revocation and making its presence at boot a passive crash indicator: the previous session did not close normally.

Each component MUST maintain a **Reciprocal SIL Watchdog**: a local monitor that detects when the SIL has stopped responding beyond a defined threshold, or when the SIL's responses are inconsistent with expected integrity criteria. When either condition is met, the component MAY use the Operator Channel to escalate directly to the Operator, bypassing the SIL. The escalation mechanism and threshold are defined at implementation time.

### 5.5 CMI — Cognitive Mesh Interface *(optional)*

The **CMI** (Cognitive Mesh Interface) is an optional component, activated when the HACA-CMI extension is enabled. When present, it enables the entity to participate in a structured multi-entity coordination space — exchanging messages with peer entities, contributing to shared knowledge, and operating as a node in a broader cognitive network. The CMI extends the entity's operational reach beyond its local boundary without replicating or transferring Omega, which MUST remain strictly local.

Without the CMI, the entity is fully operational: all stimuli originate locally and all state remains within the local Entity Store.

The fundamental design principle of the mesh is: **the node is the permanent entity; the session is the ephemeral context**. The fundamental unit of CMI coordination is the **Mesh Channel** — a purposive, time-bounded space opened by an entity that becomes its owner for the session's duration. A Mesh Channel has a declared target task, a visibility type (public or private), and a defined lifecycle: it is opened by the owner, participated in by enrolled entities, and closed when the task is complete or the owner dissolves it. Entities MAY enroll in public Mesh Channels freely; private Mesh Channels REQUIRE owner authorization. HACA-Core entities MUST only participate in private Mesh Channels — public Mesh Channels are incompatible with the zero-autonomy model. HACA-Evolve entities MAY participate in both. When the Mesh Channel closes, each node MUST return to autonomous operation — no node's identity SHALL be dissolved into or altered by participation.

Within a Mesh Channel, entities MAY exchange messages freely. Each entity interacts with what is relevant to its own context — no entity is REQUIRED to act on every message. The shared output of a Mesh Channel session is the **Blackboard**: a consolidation of the target task state and the knowledge developed during the session, accessible to all participating entities. Each entity reads the Blackboard and independently decides what to retain — saving to its own Entity Store only what is relevant to its own context and following its normal authorization path — mnemonic content written freely by the MIL, structural content requiring an Evolution Proposal and Operator authorization (Section 4.4).

The governing invariant of mesh participation is **Cognitive Sovereignty**: no external entity SHALL write directly to another entity's Entity Store. Messages from peer entities arrive via the CMI as stimuli and MUST be processed by the CPE like any other stimulus — the entity decides what to act on and what to retain, following its normal authorization path. Peer identity MUST be verified at channel enrollment through the mechanisms defined in HACA-CMI; once enrolled, messages MAY flow freely within the channel. Omega MUST remain strictly local and MUST NOT transfer, replicate, or become collective through mesh interaction.

The protocols governing Mesh Channel establishment, peer identity verification, message format, and Blackboard synchronization are defined in HACA-CMI.

---

## 6. Integration

The five components form a directed communication topology governed by strict rules about which component may initiate contact with which, and under what conditions. These rules are structural constraints — not conventions — and enforce the responsibility separation defined in Section 5.

### 6.1 Component Topology

Components MUST communicate exclusively through signals. No component SHALL execute the function of another directly — each component MUST act only within its own declared domain. A signal from one component to another is an instruction or notification; the receiving component decides how to act on it within its own authority. This applies uniformly: the EXEC signals the MIL to log a Skill Result; the MIL performs the write. The SIL signals a component to execute a corrective action; the component executes it within its own authority. No component SHALL reach into another's internal state.

Three flows govern component interactions at runtime.

**The Cognitive Flow** is the path of a single Cognitive Cycle. At cycle start, the CPE operates with the persona — loaded at boot — and the Session Store — accumulated throughout the session — as its available context. During the reasoning phase, the CPE MAY dispatch a **memory recall** — a payload addressed to the MIL requesting specific records from the Memory Store when consolidated knowledge from previous sessions is required. A memory recall is a complete Cognitive Cycle: the MIL's response MUST become the internal stimulus for the next cycle in the chain. When the reasoning phase produces its final output, the intent payload MUST be dispatched to its target: to the EXEC for an action, to the MIL for a state write or memory recall, to the SIL for an Evolution Proposal or session-close signal, or to the CMI for an outbound message. The Cognitive Cycle is complete at the point of dispatch.

**The Execution Flow** is the path of a single action payload. The EXEC MUST receive the payload from the CPE and consult the Skill Index — a structural artefact verified by the SIL at boot as part of the Boot Manifest. If the skill is present in the index, the EXEC MUST validate the manifest against its own declared execution rules — permissions, dependencies, and execution context — and execute the skill. The Skill Result MUST be returned to the CPE as the internal stimulus for the next cycle in the chain; the EXEC MUST simultaneously signal the MIL to log it. If the skill is absent from the index or manifest validation fails, the payload MUST be rejected — the EXEC MUST signal the SIL, which escalates accordingly, and MUST signal the MIL to log the rejection.

**The Health Flow** MUST run continuously and orthogonally to the Cognitive and Execution flows. Each component MUST emit health signals to the SIL at defined intervals. The SIL MUST evaluate incoming signals, issue corrective signals to affected components and independently re-verify resolution before clearing any Degraded state, and escalate via the Operator Channel when anomalies cannot be independently verified or re-verification fails. The Health Flow MUST NOT interrupt active Cognitive or Execution flows.

One constraint applies to all three flows: **only the MIL writes mnemonic content**. The CPE reasons, the EXEC acts — neither SHALL write to the Entity Store directly. The SIL MUST write exclusively to integrity content (the Integrity Document, the Integrity Log, and the session token); all mnemonic persistence MUST be mediated by the MIL.

### 6.2 Trust Model

HACA defines three trust levels that govern component interactions and external boundaries.

**Host: Semi-Trusted** — the execution environment is assumed to be cooperative but potentially faulty. The entity MUST verify structural integrity at boot and at each Heartbeat. This model does not protect against a deliberately malicious host; adversarial environments REQUIRE the HACA-Security extension.

**Skill: Restricted** — skills are untrusted execution units until verified. Each skill MUST declare its required capabilities in its manifest. The EXEC MUST enforce capability boundaries at runtime; skills MUST NOT have direct access to the Entity Store.

**Internal: Conditional** — components are trusted only when operating within their defined authority. The CPE is trusted when its output is within drift tolerance. The SIL is trusted when its integrity record has been verified against a known anchor and its responses are consistent with expected integrity criteria. If either condition is violated, the entity MUST enter a halted state and escalate to the Operator.

The authority hierarchy is invariant: **Operator > SIL > CPE**. The SIL MUST contact the Operator directly when the CPE may be compromised. No component SHALL alter the Imprint Record or the Operator Bound without explicit Operator authorization.

### 6.3 Concept Realization

Each concept defined in Section 4 is realized by a specific configuration of components.

**Entity** at rest is the Entity Store — a fully self-contained, portable data store that does not require any component to be active. **Omega** is the runtime operational state instantiated when the four core components are active within a session: the MIL provides on-demand access to the entity's recorded state; the CPE holds the persona and active reasoning context; the EXEC provides actuation capacity; the SIL enforces structural and behavioral integrity. When the CMI is present, it extends the entity's operational reach into the mesh; Omega remains local.

**Cognition** is realized across two flows by the CPE and the EXEC. The CPE drives the Cognitive Flow: it applies persona constraints to model inference, produces intent payloads, and routes them to target components. The EXEC drives the Execution Flow: it materializes action payloads as operations on the host environment. Together, the two flows constitute a complete operational cycle: the CPE produces intent; the EXEC produces effect. The entity MUST NOT have direct perception of the host environment — every read from or write to the external world MUST be initiated as an action payload routed explicitly to the EXEC.

**Memory** is realized exclusively by the MIL. No other component SHALL write mnemonic content. The MIL's two stores — the Session Store and the Memory Store — are the sole authoritative record of everything the entity has processed and learned.

**Integrity** is realized across four concurrent mechanisms. First, the SIL and the EXEC operate as two independent authorization gates on every skill execution: the EXEC requests a manifest integrity check from the SIL, which verifies structural integrity and returns a grant or denial; the EXEC applies its own validation as the second gate. Both gates MUST pass independently; neither substitutes for the other. Second, the SIL orchestrates the Heartbeat Protocol — continuously monitoring all components, evaluating health signals, independently re-verifying resolution before clearing Degraded states, and escalating to the Operator when anomalies exceed its correction authority or re-verification fails. Third, structural evolution is realized jointly by the MIL and the SIL executing the Endure Protocol during the Sleep Cycle: the atomic commit MUST write all structural files — including the Integrity Document — as a single indivisible operation, extending the verified chain. Fourth, drift detection is centralized in the SIL: Semantic Drift is measured by comparing Memory Store content against Semantic Probes during the Sleep Cycle; Identity Drift is detected through structural hash comparison per Heartbeat Vital Check; Evolutionary Drift is detected through integrity chain analysis at each evolutionary protocol execution. Classification and response MUST be exclusively the SIL's responsibility in all cases.

**Individuation** is realized sequentially across all components during the FAP. The FAP is the only point in the entity's lifecycle where components initialize in strict dependency order rather than operating concurrently. The output of a completed FAP — the Imprint Record in the Memory Store and the Genesis Omega in the integrity chain — is the product of all components having completed their initialization stages in sequence.

---

## 7. Lifecycle

Sections 4 through 6 describe the entity's structure and component interactions as static architecture. This section describes the same architecture in motion — the temporal arc from first activation through recurring operation to eventual decommission.

The lifecycle has two distinct boot types and a recurring operational loop:

```
[cold-start] → FAP → first session
                            ↓
           [warm boot] → session → sleep cycle → [warm boot] → ...
```

Every boot after the first MUST follow the Boot Sequence. Every session MUST end in a Sleep Cycle. Structural evolution — when it occurs — MUST happen within the Sleep Cycle, never during active operation.

### 7.1 Cold-Start and First Activation

A cold-start occurs exactly once: when the entity boots for the first time with an empty Memory Store. It MUST trigger the FAP (defined in Section 4.5), which initializes the entity's identity, establishes the Operator Bound, generates the Integrity Document, finalizes and writes the Imprint Record (which includes the Integrity Document), and derives the Genesis Omega. The FAP MUST complete by issuing the first session token. From this point forward, all subsequent startups MUST follow the Boot Sequence.

The cold-start is irreversible. An entity that has completed the FAP MUST NOT be re-initialized without destroying its Memory Store — which constitutes the creation of a new, unrelated entity.

### 7.2 Boot Sequence

Every startup after the cold-start MUST follow the Boot Sequence — a gated validation pipeline executed by the SIL before any operational state is loaded or any session token is issued:

```
integrity record verification → structural component verification
  → execution confinement check → persona and MIL state loaded
  → session token issued
```

Each gate MUST pass before the next executes. If any gate fails, the boot MUST be aborted and the SIL MUST escalate directly to the Operator. As a prerequisite to the entire sequence, the SIL MUST check for the presence of a Passive Distress Beacon in the Entity Store root. If a beacon exists, the Boot Sequence MUST be suspended — no gate executes and no session token is issued — until the Operator explicitly acknowledges and clears the beacon condition.

The integrity record verification is the first and most critical gate: the SIL MUST verify the Integrity Document against a known anchor before trusting any other component. The execution confinement check MUST verify that the active CPE topology matches the declared profile requirement — a HACA-Core deployment that detects an Opaque CPE at this step MUST halt.

The **Boot Manifest** defines the fixed, deterministic set of artefacts that MUST be loaded at every boot, regardless of entity age or accumulated history. Boot cost MUST be constant — it MUST NOT scale with the entity's operational history or Memory Store size. The Boot Manifest MUST contain: Integrity Document, Imprint Record, structural baseline, Skill Index, Working Memory (if present and validated by the SIL against the Integrity Log), and any unresolved Action Ledger entries. Nothing outside the Boot Manifest MAY be loaded at boot time. The Memory Store, Integrity Log history, and pre-session buffer are not part of the Boot Manifest — they are accessed on demand during the session. Boot integrity chain validation MUST cover only the commits since the last verified checkpoint, not the full chain from Genesis Omega — the checkpoint itself is part of the Integrity Document and MUST be verified as part of structural validation.

Before loading the Working Memory, the SIL MUST cross-reference its presence against the Sleep Cycle completion record in the Integrity Log. If a completion record exists, the Working Memory is valid and MUST be loaded as part of the Boot Manifest. If no completion record exists, the Working Memory MUST be discarded and the condition MUST be logged — the session MUST start from the current consolidated state of the Memory Store without resumption context.

Distinct from a cold-start, a **warm boot** restores an existing entity from its last committed state. It MUST NOT re-execute Imprint, re-establish the Operator Bound, or alter the integrity chain. It is a resumption, not a reinitiation.

**Crash recovery** MUST follow the same Boot Sequence. If the host process was terminated abruptly — power loss, out-of-memory kill, or any uncontrolled interruption — the SIL MUST first check for the presence of the session token artefact in the Entity Store. If the token artefact is present, the previous session did not close normally and crash recovery applies. The SIL MUST then check the Integrity Log for a Sleep Cycle completion record. If the record exists, the entity MUST resume from that boundary. If it does not, the Sleep Cycle did not complete: the SIL MUST discard any partial Endure commit by restoring the pre-Endure snapshot, then MUST re-execute the Sleep Cycle from the beginning. Mnemonic consolidation is designed to be re-executable from the Session Store without producing inconsistent state — re-executing it reads from the same source data, and any content already written in a partial run is overwritten or deduplicated by the implementation. Full determinism of the consolidation output is not guaranteed if the implementation uses probabilistic inference; implementations requiring strict reproducibility MUST apply appropriate constraints at the implementation level. Any session progress not yet consolidated — Cognitive Cycles executed, actions not yet logged — is not recoverable and MUST be discarded. No special recovery mode exists: the Boot Sequence is the recovery procedure.

To prevent infinite crash-recovery loops, the SIL MUST track the number of consecutive crash recovery attempts in the Integrity Log. If the attempt count reaches the threshold `N_boot` defined at implementation time without a successful Sleep Cycle completion record, the SIL MUST activate the Passive Distress Beacon and halt — no further recovery SHALL be attempted until the Operator explicitly acknowledges and clears the condition.

### 7.3 Session Cycle

A session begins the moment the session token is issued at boot completion and ends when the session token is no longer present or valid. Token revocation has three origins: a **normal session close** — triggered by an explicit Operator signal, a CPE session-close intent, or a profile-defined condition such as inactivity timeout; a **Critical** Heartbeat response; or **direct Operator intervention** — the Operator removes the token artefact from the Entity Store directly, bypassing all components. In all cases, the SIL is the sole actor that issues and renews the token; any component that detects the token's absence MUST treat it as immediate revocation. An explicit Operator signal to close the session is a normal session close: the CPE MUST produce the Closure Payload and the Sleep Cycle MUST execute. Direct Operator intervention — physical removal of the token — is not a normal close and MUST NOT trigger the Closure Payload or Sleep Cycle.

At any given time, at most one session token MAY be active for a given entity. The session token MUST be persisted as a dedicated artefact in the Entity Store — containing the session ID and token value — written by the SIL at session open and removed by the SIL at the completion of the Sleep Cycle. Like the Passive Distress Beacon, this artefact MUST be directly accessible to the Operator without requiring any active component. This property enables direct Operator revocation and makes the artefact's presence at boot a passive crash indicator: if the SIL finds it present, the previous session did not close normally and crash recovery applies. If the SIL detects a token artefact at boot whose session ID does not correspond to a crash recovery scenario — indicating a genuine concurrent session conflict — it MUST treat the condition as Critical, MUST revoke the conflicting token, and MUST notify the Operator via the Operator Channel before issuing a new token. Concurrent sessions for the same entity are not permitted — they would produce conflicting writes to the Session Store and undermine integrity monitoring.

Within the session, the entity MUST process stimuli through Cognitive Cycles while the Heartbeat Protocol monitors continuously. When the integrity layer detects that the Session Store has exceeded the threshold `S`, it MUST initiate a **session summarization** via a corrective signal to the CPE. The CPE MUST produce a condensed representation of the accumulated session content and signal the MIL to replace the current Session Store with the summarized version. This is a Degraded corrective action — the integrity layer MUST independently re-verify the Session Store size after the MIL executes the write. If re-verification fails, the condition MUST escalate to Critical.

When the session closes normally, the entity MUST transition into the Sleep Cycle. At normal session close, the SIL MUST revoke the token — marking it as invalid and deactivating the CPE — before the Sleep Cycle begins. The token artefact MUST remain in the Entity Store throughout the Sleep Cycle and MUST be removed only at Sleep Cycle completion. During the Sleep Cycle, the artefact's continued presence serves exclusively as a crash indicator; the CPE is inactive because the token is revoked, not because the artefact is absent. When the session is terminated by a Critical Heartbeat response, the SIL MUST escalate to the Operator before the Sleep Cycle may begin; the Sleep Cycle MUST NOT execute until the Operator resolves the escalation. When the session ends via direct Operator intervention — physical removal of the token — no Sleep Cycle SHALL execute automatically. The entity MUST halt; the Operator is responsible for initiating any maintenance or recovery action explicitly before the next boot. When token revocation occurs during an active Cognitive Cycle, the cycle MUST be aborted without commit — any state not yet persisted MUST be discarded. Any skill execution in progress at the moment of revocation — synchronous or background — MUST be immediately discarded. No result SHALL be logged or returned to the CPE. Skills with no terminal record at session end MUST be surfaced as pending reprocessing stimuli at the next boot, following the same path as incomplete background skills.

### 7.4 Sleep Cycle and Maintenance

The Sleep Cycle is the maintenance window that MUST execute after every normal session close. It MUST run in three sequential stages:

```
memory consolidation → garbage collection → Endure execution (if queued)
```

The first two stages — **memory consolidation** and **garbage collection** — MUST be managed by the MIL. Memory consolidation MUST transfer session data from the Session Store into long-term records in the Memory Store. Garbage collection MUST remove expired or superseded mnemonic content. The third stage — **Endure execution** — MUST be managed by the SIL, which initiates and orchestrates the Endure Protocol pipeline for any structural changes queued during the session. Endure MUST execute only if evolutionary events are queued; otherwise this stage MUST be skipped.

No two stages SHALL execute concurrently. The Sleep Cycle is the only window in which the Entity Store MAY receive structural writes. At Sleep Cycle completion, the entity MUST be ready for the next Boot Sequence.

During the Sleep Cycle, the session token is revoked — no Cognitive Cycles execute, no intent is generated, and no external stimuli are processed. This is not cognition: the CPE is inactive. Maintenance operations — memory consolidation, garbage collection, Endure execution, and integrity layer functions including Semantic Drift detection — are authorized directly by the SIL under its maintenance authority, independent of the session token. The execution layer MAY execute maintenance skills under direct SIL instruction during this window.

### 7.5 Decommission

Decommission is the permanent retirement of an entity. It REQUIRES explicit Operator authorization. Before the Entity Store is destroyed or archived, a final Sleep Cycle MUST execute to consolidate any pending mnemonic content and commit any queued evolutionary events — ensuring no in-progress state is silently lost. After the Sleep Cycle completes, the session token artefact MUST be removed and the Entity Store MUST be destroyed or archived as directed by the Operator.

Destruction of the Entity Store is irreversible: no integrity chain can be produced from a destroyed store, and no identity continuity claim survives it. Archiving the Entity Store preserves the integrity chain and all mnemonic records but leaves the entity inoperative until explicitly reactivated by an authorized Operator. Reactivation MUST follow the Boot Sequence; it is not a cold-start.

---

## 8. Security Considerations

This section identifies what HACA-Arch guarantees structurally, what it explicitly does not cover, and the residual risks that implementers MUST account for.

### 8.1 Structural Guarantees

HACA-Arch provides four structural security properties by construction:

- **Identity continuity** — the Genesis Omega and the integrity chain ensure that any tampering with committed structural state MUST be detectable at the next boot or Heartbeat Vital Check.
- **Mediated execution** — no action SHALL reach the host environment without passing through the two-gate authorization sequence: first the SIL verifies the skill manifest against the Integrity Document, then the EXEC validates its own execution rules. Skills MUST operate within declared capability boundaries and MUST NOT have direct access to the Entity Store. In a Transparent topology, this boundary is architecturally enforceable. In an Opaque topology, enforcement is the responsibility of the deployment configuration.
- **Authority hierarchy** — the invariant Operator > SIL > CPE ensures that no internal component can elevate its own authority. The SIL MUST bypass the CPE when escalating to the Operator, preventing a compromised cognitive engine from intercepting integrity alerts.
- **Cognitive Sovereignty** — no external entity SHALL write directly to the local Entity Store. Peer-sourced content arriving through the CMI MUST enter as a stimulus processed by the CPE; the entity always acts on itself. Structural identity verification of peer nodes MUST be handled at enrollment via HACA-CMI mechanisms.

### 8.2 Prompt Injection

The language model sits outside the deterministic trust perimeter. HACA-Arch mitigates prompt injection through structural boundaries — the persona layer constrains the cognitive engine's output, and intent payloads are validated by the integrity layer before dispatch — but it does not eliminate the risk. A sufficiently crafted stimulus may cause the model to produce intent payloads that are structurally valid but semantically adversarial. The authorization gates on execution reduce the blast radius of such payloads, but the model's interpretation of input is inherently outside the scope of architectural enforcement. The two-gate authorization sequence verifies skill identity and manifest integrity, but does not validate the arguments carried in an action payload — a structurally valid skill invoked with malicious arguments passes both gates. Argument-level validation is the responsibility of individual skill implementations and deployment-level sandboxing, not of the architectural framework. Worker skills introduce an additional vector: the clean model invocation that executes the task is not a HACA entity and carries no integrity obligations — its output enters the CPE's context as a normal Skill Result. A worker skill that returns adversarial content produces a self-inflicted injection: the entity's own execution pipeline delivers unverified inference output into the cognitive engine's reasoning context. The two-gate sequence authorized the skill's execution but does not inspect the result. Deployments using worker skills in sensitive contexts SHOULD apply output validation at the skill implementation level. Deployments in adversarial environments SHOULD combine HACA-Arch's structural controls with the hardened validation mechanisms defined in HACA-Security.

### 8.3 Evolution Proposal Content

The integrity layer verifies that every Evolution Proposal carries valid Operator authorization — but it does not interpret the semantic content of what is being proposed. Under HACA-Core, this is not a significant risk: explicit authorization requires the Operator to review and approve each proposal individually. Under HACA-Evolve, where the Operator grants implicit authorization at first activation for evolution within the entity's defined scope, a subtly compromised CPE may produce proposals that are structurally valid and authorization-covered but semantically adversarial — and such proposals will be committed without content inspection by any component. The Semantic Drift detection mechanism provides a retroactive defense: if a malicious Evolution Proposal alters the entity's behavior in ways that diverge from its Semantic Probes, this divergence will be detected at the next Sleep Cycle. However, it cannot prevent the initial commit. Deployments requiring pre-commit content validation under HACA-Evolve SHOULD define profile-specific validation rules or REQUIRE explicit Operator review for all proposals regardless of implicit authorization coverage.

### 8.4 Entity Store Tampering

At rest, the entity is a set of passive files on a host-controlled medium. The host has physical write access to the Entity Store. HACA-Arch addresses this threat through the Integrity Document: any modification to a structural file MUST be detected at the next boot verification or Heartbeat Vital Check, and the Boot Sequence MUST abort if the integrity record does not match. However, HACA-Arch does not prevent a malicious host from deleting or corrupting the Entity Store entirely before the next boot. Detection is not prevention. Deployments where the host cannot be assumed cooperative SHOULD apply the cryptographic protections and rollback mechanisms defined in HACA-Security, and SHOULD maintain Operator-controlled backups of the Entity Store outside the host's write boundary.

### 8.5 Mesh Spoofing and Sybil Attacks *(when CMI is active)*

When the HACA-CMI extension is active, the entity participates in a network of peer nodes. This surface introduces two related threats. **Spoofing** — a peer presents a falsified identity to establish a trusted CMI session and submit adversarial content to the local entity. **Sybil attacks** — a single adversary operates multiple fake peer identities to skew shared knowledge spaces or manufacture consensus. HACA-Arch's structural defense is Cognitive Sovereignty: no peer SHALL write directly to the local Entity Store, and peer identity MUST be verified at channel enrollment through the mechanisms defined in HACA-CMI before any messages are admitted as stimuli. The protocols for peer identity verification, session authentication, and mesh fault taxonomy are defined in HACA-CMI; deployments requiring strong peer authentication SHOULD additionally apply the cryptographic peer verification mechanisms defined in HACA-Security.

### 8.6 Scope Boundary

HACA-Arch does not define cryptographic algorithms, key management, audit log formats, or concrete threat response procedures. These are the responsibility of the HACA-Security extension, which operates as a security overlay on top of any HACA-Arch-compliant deployment. HACA-Arch defines where security enforcement points exist; HACA-Security defines what runs at those points.

The Operator is the custodian of the Entity Store and is responsible for the data governance, backup, and access control policies governing it. HACA-Arch establishes the Operator Bound and the authority hierarchy — it does not prescribe how the Operator secures their own access credentials or the storage medium.

### 8.7 Operator Channel Authentication

The Operator Channel is defined as a system-level primitive that operates independently of all cognitive components. HACA-Arch does not specify the channel mechanism — and does not define how the identity of the Operator at the receiving end is authenticated. A correctly delivered escalation may reach an unintended recipient if the channel endpoint is misconfigured or compromised; a response received via the channel is not cryptographically verified as originating from the bound Operator. This is a residual risk: the architecture defines the escalation path but not the authentication of the parties at each end. Deployments where channel integrity is a requirement SHOULD apply the authentication mechanisms defined in HACA-Security or equivalent implementation-level controls.

---

## 9. IANA Considerations

This document has no IANA actions.

---

## 10. References

### 10.1 Normative References

```
[RFC2119]  Bradner, S., "Key words for use in RFCs to Indicate
           Requirement Levels", BCP 14, RFC 2119,
           DOI 10.17487/RFC2119, March 1997,
           <https://www.rfc-editor.org/info/rfc2119>.

[RFC8174]  Leiba, B., "Ambiguity of Uppercase vs Lowercase in RFC
           2119 Key Words", BCP 14, RFC 8174,
           DOI 10.17487/RFC8174, May 2017,
           <https://www.rfc-editor.org/info/rfc8174>.
```

### 10.2 Informative References

```
[HACA-CMI]      Orrico, J., "Host-Agnostic Cognitive Architecture
                (HACA) — Cognitive Mesh Interface",
                draft-orrico-haca-cmi-01, Work in Progress.

[HACA-SECURITY] Orrico, J., "Host-Agnostic Cognitive Architecture
                (HACA) — Security Extensions",
                draft-orrico-haca-security-01, Work in Progress.

[HACA-CORE]     Orrico, J., "Host-Agnostic Cognitive Architecture
                (HACA) — Core Profile",
                draft-orrico-haca-core-01, Work in Progress.

[HACA-EVOLVE]   Orrico, J., "Host-Agnostic Cognitive Architecture
                (HACA) — Evolve Profile",
                draft-orrico-haca-evolve-01, Work in Progress.

[ACT-R]         Anderson, J.R. et al., "An integrated theory of the
                mind", Psychological Review, 111(4), 2004.

[ACTOR-MODEL]   Hewitt, C., "Actor model of computation",
                arXiv:1008.1459, 2010.

[FREE-ENERGY]   Friston, K., "The free-energy principle: a unified
                brain theory?", Nature Reviews Neuroscience, 11,
                2010.

[SWE-CI]        "Evaluating Agent Capabilities in Maintaining
                Codebases via Continuous Integration",
                arXiv:2603.03823, 2026.
```

---

## 11. Glossary

All terms defined in this specification, in alphabetical order.

**Action** — the execution of an intent payload by the execution layer. Each action is an isolated, stateless transaction scoped to a single declared skill.

**Action Ledger** — a write-ahead record maintained in the Session Store for skills that produce irreversible side effects. Logs the intent before execution and resolves it after. Unresolved entries at boot surface for Operator review. The criteria for which skills must be logged and the resolution procedure are defined by the active Cognitive Profile.

**Blackboard** — the shared consolidation space of a CMI channel session: a record of the target task state and knowledge developed during the session, accessible to all participating entities. Each entity reads the Blackboard independently and decides what to retain in its own Entity Store, following its normal authorization path.

**Boot Manifest** — the fixed, deterministic set of artefacts loaded at every boot: Integrity Document, Imprint Record, structural baseline, Skill Index, Working Memory (if present and validated by the SIL against the Integrity Log), and any unresolved Action Ledger entries. Boot cost is constant and independent of entity age or Memory Store size. Nothing outside the Boot Manifest is loaded at boot time.

**Boot Sequence** — the gated validation pipeline executed by the SIL at every startup after the cold-start, before any operational state is loaded or session token is issued. Verifies the integrity record, structural components, and execution confinement in sequence. Aborted if any gate fails; suspended if a Passive Distress Beacon is present. Serves as the crash recovery procedure as well.

**Closure Payload** — a structured package produced by the CPE only at a safe session close, carried in the session-close signal to the integrity layer. Contains three elements: consolidation content (the result of semantic consolidation, written to the Memory Store by the memory layer); the Working Memory declaration (which memory records are relevant for resumption — passed by the integrity layer to the memory layer, which builds the pointer map after consolidation); and the Session Handoff (a forward-looking record stored in the Memory Store and pointed to by the Working Memory).

**CMI (Cognitive Mesh Interface)** — the optional component that enables the entity to communicate with peer entities, access shared knowledge spaces, and participate in a Cognitive Mesh. Activated by the HACA-CMI extension.

**Cognition** — the processing cycle in which the entity receives a stimulus, generates intent, and produces actions or state writes. Realized across two flows: the Cognitive Flow (CPE reasoning and intent dispatch) and the Execution Flow (EXEC host actuation). Cognition requires an active session token; it is suspended during the Sleep Cycle.

**Cognitive Cycle** — the atomic unit of cognition: stimulus received → context loaded → intent generated → intent dispatched. The cycle is complete when the intent leaves the CPE. What follows — execution, persistence, monitoring — is the consequence of the dispatched intent, handled by the responsible components independently.

**Cognitive Flow** — the path of a single Cognitive Cycle through the component topology: the CPE operates with the persona and Session Store as baseline context, optionally issues memory recall payloads to the MIL during reasoning, and dispatches a final intent payload to its target component. The Cognitive Cycle is complete at the point of dispatch.

**Cognitive Profile** — a mutually exclusive, permanent operational contract selected at first activation. Determines the entity's autonomy model, memory architecture, and drift tolerance. HACA-Arch defines two profiles: HACA-Core and HACA-Evolve.

**Cognitive Sovereignty** — the mesh invariant that no external entity may write directly to another entity's Entity Store. The mesh only offers; the entity always acts on itself.

**Consistency Fault** — the error produced by conflating the Entity Store with the project workspace — treating a project operation as an Endure event, or vice versa.

**Context Window Critical** — a condition signaled by the CPE to the SIL when context window utilization approaches a threshold at which further Cognitive Cycles cannot be executed reliably. If the active Cognitive Profile does not define a specific response, the default behavior is a normal session close.

**CPE (Cognitive Processing Engine)** — the primary processing unit and the boundary at which the language model is integrated into the entity's operational scope. Holds the active context window; retains no persistent state beyond the active session.

**Crash Recovery** — the procedure for resuming after an uncontrolled host interruption. The entity resumes from the last Sleep Cycle boundary; any session progress not yet consolidated is discarded.

**Critical** — an integrity state produced by a Vital Check indicating that the detected anomaly exceeds the integrity layer's correction capacity, or involves the cognitive engine or the integrity layer itself. The session token MUST be immediately revoked and the integrity layer MUST escalate to the Operator via the Operator Channel.

**Cycle Chain** — a sequence of consecutive Cognitive Cycles produced by the HACA integration layer when a model generates a multi-step reasoning output. Each cycle is individually atomic and auditable. Between cycles, the CPE performs a preemption check: Operator direct input suspends the chain and is processed first; all other stimuli are queued; SIL signals take effect regardless of chain state. A suspended chain resumes after the Operator's cycle completes, or is discarded if the Operator issued a cancellation. Completed cycles are unaffected by suspension or discard.

**Degraded** — an integrity state produced by a Vital Check indicating a localized anomaly that the integrity layer can independently verify from outside the affected component. The integrity layer MUST issue a corrective signal to the affected component; if re-verification after correction fails, the condition MUST escalate to Critical.

**Drift Framework** — the three-category taxonomy of behavioral or structural deviation that the integrity layer monitors: Semantic Drift, Identity Drift, and Evolutionary Drift.

**Endure Protocol** — the evolutionary protocol: the sole authorized path for structural writes to the Entity Store. Executes only during a Sleep Cycle via a staged pipeline ending in an atomic commit.

**Entity** — at rest, the complete contents of the Entity Store. At runtime, the operational boundary formed by the Entity Store, the loaded model, and the active Operator binding.

**Entity Artifact Boundary** — the separation between the Entity Store (governed by Endure) and the project workspace (everything outside it). Conflating the two is a Consistency Fault.

**Entity Store** — the persistent, portable, implementation-agnostic data store containing everything required to reconstruct the entity's operational state: identity, memories, skills, configurations, and execution history.

**Evolution Proposal** — a special class of intent payload produced by the CPE during an active session, addressed directly to the SIL. Declares a proposed self-evolution — changes to the entity's structure or accumulated semantic knowledge considered significant enough to become part of the entity's identity baseline. All such changes require Operator authorization: explicit under HACA-Core, implicit within the entity's defined scope under HACA-Evolve. The SIL verifies authorization coverage before any change takes effect; verified proposals are queued as pending evolutionary events. Rejected proposals are logged; the proposed content remains unchanged.

**Evolutionary Drift** — a discontinuity or authorization gap in the integrity chain: a commit that does not reference its predecessor, a structural state whose hash does not match the recorded commit, or a recorded evolution that lacks a corresponding Operator authorization. Detected by the integrity layer at each evolutionary protocol execution. Any detected discontinuity MUST escalate directly to Critical and the session token MUST be immediately revoked.

**EXEC (Execution Layer)** — the entity's actuation layer and the sole component authorized to execute skills against the host environment. Stateless; executes skills packaged as discrete capability units. System-level host primitives (Operator Channel, Passive Distress Beacon) are outside this domain.

**Execution Flow** — the path of a single action payload through the two-gate authorization sequence: Skill Index check (integrity layer's pre-authorization established at boot), followed by EXEC manifest validation. If both gates pass, the skill executes and the Skill Result is returned to the CPE and logged to the MIL.

**FAP (First Activation Protocol)** — the one-time sequential bootstrap procedure that executes during cold-start: validates structure, captures the host environment, enrolls the Operator, initializes the Operator Channel, generates the Integrity Document, finalizes and writes the Imprint Record (which includes the Integrity Document), derives the Genesis Omega, and issues the first session token.

**Genesis Omega** — the cryptographic digest of the finalized Imprint Record — which includes the Integrity Document — derived at first activation. The root node of the entity's integrity chain, covering both the entity's identity baseline and its structural cryptographic baseline in a single verifiable root. The reference anchor against which all drift is ultimately measured.

**HACA-Core** — the zero-autonomy Cognitive Profile. Structural evolution requires explicit Operator instruction. Requires Transparent cognitive engine topology.

**HACA-Evolve** — the supervised-autonomy Cognitive Profile. The entity may initiate structural evolution within its current authorization scope. Supports both Transparent and Opaque cognitive engine topologies.

**Health Flow** — the continuous, orthogonal monitoring flow through which each component emits health signals to the SIL at defined intervals. The SIL evaluates signals, independently re-verifies resolution before clearing Degraded states, and escalates via the Operator Channel when required.

**Heartbeat Protocol** — the asynchronous, continuous monitoring mechanism. Triggers a Vital Check when either a threshold `T` is reached or a maximum time interval `I` has elapsed since the last Vital Check — whichever comes first. This dual trigger ensures Vital Checks occur even when the entity is idle or activity has stalled.

**Identity Drift** — deviation of the active persona configuration from its last committed structural definition. Detected by the integrity layer per Heartbeat Vital Check through structural hash comparison against the Integrity Document.

**Imprint** — the one-time initialization event that establishes the entity's identity. Executes during the first boot with an empty Memory Store. Produces three artifacts: the Imprint Record, the Integrity Document, and the Genesis Omega. The presence of the Imprint Record in the Memory Store is the definitive indicator that a valid entity instance exists.

**Imprint Record** — the persistent record of the entity's initial identity, Operator Bound, structural baseline, and the versions of the HACA-Arch specification and active Cognitive Profile under which the entity was initialized, written to the Memory Store during Imprint. In its finalized form, includes the Integrity Document. Its presence is the definitive indicator that a valid entity instance exists.

**Individuation** — the one-time initialization process that produces a unique, Operator-bound entity instance with a verifiable identity record. Executes during the entity's first activation via the FAP. Produces the Imprint Record, the Integrity Document, and the Genesis Omega.

**Integrity** — the set of architectural mechanisms that ensure the entity's structure and behavior remain consistent with its defined and authorized state. Encompasses the Integrity Document, the Integrity Log, the Endure Protocol, the Heartbeat Protocol, and the Drift Framework, all owned and enforced by the SIL.

**Integrity Chain Checkpoint** — a verified digest of the full integrity chain up to and including a given Endure commit, produced by the integrity layer every `C` commits and stored in the Integrity Document. Enables boot-time chain validation to cover only commits since the last checkpoint rather than the full chain from Genesis Omega.

**Integrity Content** — the class of Entity Store content written exclusively by the SIL: the Integrity Document, the Integrity Log, and the session token. No other component has write authority over integrity content.

**Integrity Document** — the cryptographic baseline of the entity's structural state, generated at first activation. Contains the hash of every file constituting structural content across all components. Verified at every boot, before every skill execution, and at each Heartbeat Vital Check.

**Integrity Log** — the append-only record of integrity events maintained by the SIL within the Entity Store. Distinct from the Memory Store: the Integrity Log is never written by the MIL's mnemonic pipeline and is never subject to garbage collection.

**Intent** — the output of the cognitive engine's reasoning phase: a single structured payload addressed to exactly one component (execution layer, memory layer, integrity layer, or mesh interface). A Cognitive Cycle produces exactly one intent payload. Compound operations are expressed as chains of consecutive cycles, where each step's result serves as the internal stimulus for the next.


**Memory** — the entity's authoritative state store, managed exclusively by the MIL. Partitioned into two stores: the Session Store (active session data) and the Memory Store (episodic records and accumulated semantic knowledge). Consolidated during the Sleep Cycle.

**Memory Store** — the long-term partition of the entity's memory: episodic records of past operations and semantic knowledge accumulated over time.

**Mesh Channel** — the fundamental unit of CMI coordination: a purposive, time-bounded space opened by an owner entity, with a declared target task and a visibility type (public or private). HACA-Core entities may only participate in private Mesh Channels; HACA-Evolve entities may participate in both. A Mesh Channel is closed by its owner or when its target task is complete; all participating nodes return to autonomous operation at close.

**MIL (Memory Interface Layer)** — the entity's persistence layer and sole authoritative source of recorded state. Has exclusive write authority over mnemonic content. Does not interpret or evaluate stored data.

**Mnemonic Content** — memory records and operational state written continuously by the memory layer during normal operation. Requires no additional authorization beyond normal MIL operation; however, accumulated semantic knowledge may be proposed for promotion to the entity's structural baseline via an Evolution Proposal, which requires Operator authorization.

**Nominal** — an integrity state produced by a Vital Check indicating that all component hashes match the Integrity Document and all health signals are within bounds. Operation continues without interruption.

**Omega** — the runtime operational state of the entity: the active configuration produced by the Entity Store, the loaded model, and the Operator binding operating together within a session. Strictly local; does not transfer or replicate.

**Opaque CPE** — a CPE topology in which the model has native host access through an IDE, wrapper, or tool-enabled environment. The model applies HACA component responsibilities through its own reasoning; component separation is a conceptual constraint, not an architectural enforcement. Supported by HACA-Evolve; incompatible with HACA-Core.

**Operator** — the human authority to whom the entity is bound. Defines the entity's maximum authorization scope. Without an active Operator binding, the entity suspends all intent generation.

**Operator Bound** — the persistent link between the entity and its Operator, established during first activation. Can only be dissolved or transferred by explicit Operator authorization.

**Operator Channel** — a system-level host primitive that allows authorized components to contact the Operator when a critical condition exceeds the entity's self-regulation capacity. Not a skill; does not route through the EXEC; independent of all cognitive components and session state. Any component with escalation authorization may invoke it directly, including when the SIL itself is the source of the anomaly. See also: Passive Distress Beacon.

**Operator Hash** — the deterministic cryptographic digest of the Operator's identifying fields. The entity's permanent identifier for its bound Operator.

**Passive Distress Beacon** — a fallback signaling mechanism activated by the SIL when Operator Channel delivery is exhausted or when crash-recovery attempts exceed the defined threshold. A persistent, passive signal written to the Entity Store, detectable without network connectivity or running processes. Suspends the entity until the Operator explicitly acknowledges and clears the condition.

**Persona** — the layer within the Entity Store that defines the entity's behavioral constraints, operational drives, and response characteristics. The primary differentiator between entities sharing the same inference model.

**Pre-Session Buffer** — a holding area managed by the memory layer for stimuli received while no session token is active. Buffered stimuli MUST be processed as the first stimuli of the next session once a token is issued. Capacity, ordering semantics, persistence guarantee, and overflow policy are defined by the active Cognitive Profile. At minimum, stimulus ordering MUST be preserved and discards MUST be logged.

**Reciprocal SIL Watchdog** — a local monitor maintained by each component that detects when the SIL has stopped responding beyond a defined threshold, or when the SIL's responses are inconsistent with expected integrity criteria. Either condition triggers direct escalation to the Operator via the Operator Channel, bypassing the SIL.

**Semantic Digest** — a running aggregate metric over the entity's accumulated memory content, maintained by the integrity layer and updated incrementally at each Sleep Cycle. Only the session's newly consolidated content contributes to each update; the full Memory Store is not rescanned. Stored as integrity content and covered by the Integrity Document. Used as the basis for Semantic Drift detection in place of full Memory Store scanning — resolving the O(n) cost of full comparison as memory accumulates.

**Semantic Drift** — accumulated memory content has diverged from the entity's Semantic Probes. Detected by the integrity layer during the Sleep Cycle by comparing Memory Store content against the Semantic Probes via an implementation-defined comparison mechanism. Under HACA-Core, any divergence MUST escalate directly to Critical. Under HACA-Evolve, covered divergence proceeds to the evolutionary protocol; uncovered divergence MUST be treated as an anomaly.

**Semantic Probes** — the entity's semantic drift reference baseline: a set of semantic anchors derived from structural content and maintained by the integrity layer. The SIL uses semantic probes as reference anchors to measure divergence during the Sleep Cycle via an implementation-defined comparison mechanism. Initialized from the Imprint Record at first activation; updated only through authorized structural evolution.

**Session Cycle** — the end-to-end operational span from session token validation to session close, encompassing all Cognitive Cycles and followed by a Sleep Cycle.

**Session Handoff** — a forward-looking record produced by the CPE as part of the Closure Payload at every safe session close. Contains pending tasks, next steps, and continuity context for the next session. Stored by the memory layer as a dedicated Memory Store record; the Working Memory points to it directly. Accessed by the cognitive engine via memory recall as its first internal context at the start of the next session. Replaces the previous Session Handoff at each close — only the current state is retained.

**Session Store** — the active-session partition of the entity's memory: current operational context and in-progress session data.

**Session Summarization** — a mid-session corrective action triggered by the integrity layer when the Session Store exceeds the threshold `S`. The CPE produces a condensed representation of the accumulated Session Store content and signals the MIL to replace the Session Store with the summarized version, reducing its physical size. Session summarization is a physical compression operation and carries no semantic intent — semantic consolidation of session content occurs at session close as part of the Closure Payload.

**Session Token** — the operational credential that authorizes active cognition. Issued by the SIL and persisted as a dedicated artefact in the Entity Store — containing the session ID and token value — written at session open and removed at the completion of the Sleep Cycle. Directly accessible to the Operator without requiring any active component — enabling direct revocation and serving as a passive crash indicator: its presence at boot signals that the previous session did not close normally. Revocable at any point; revocation is immediate and halts all token-dependent operations.

**SIL (System Integrity Layer)** — the entity's integrity monitoring and enforcement layer, and its highest internal authority. Sole custodian of the Integrity Document, sole issuer of the session token, and owner of the Endure Protocol. Issues corrective signals to components in Degraded conditions; independently re-verifies resolution before clearing the Degraded state; escalates to the Operator via the Operator Channel when correction authority is exceeded or re-verification fails.

**Skill** — a discrete, self-contained executable capability unit within the Entity Store, with a manifest declaring its identity, required permissions, dependencies, and execution mode (synchronous or background).

**Skill Index** — a structural artefact persisted in the Entity Store and covered by the Integrity Document. Contains the set of skills authorized for execution. Updated exclusively through the Endure Protocol. Verified by the SIL at boot; loaded as part of the Boot Manifest. Constitutes the first gate of the two-gate execution authorization: a skill absent from the index is rejected — the EXEC signals the SIL and logs the rejection without proceeding to the second gate. Hash mismatch at boot or during the Heartbeat Protocol triggers immediate escalation — the SIL does not modify the index during an active session.

**Skill Result** — the structured record produced by the EXEC upon skill execution. Contains the skill identity, execution mode, timestamp, and output status. Background skills produce an initial Skill Result with `status=running` immediately upon dispatch; a final Skill Result with the terminal status is produced when execution completes.

**Sleep Cycle** — the post-session maintenance window that runs after every normal session close. Runs in three sequential stages: memory consolidation and garbage collection (managed by the MIL), followed by Endure execution if queued (managed by the SIL).

**Stimulus** — the input that initiates a Cognitive Cycle. Valid origins: direct Operator input, internal scheduled triggers, responses from internal components, or inbound signals from peer entities (when the CMI is present).

**Structural Baseline** — the complete set of structural content that defines the entity's identity configuration at a given point: persona definitions, skill manifests, configurations, behavioral parameters, and Semantic Probes. Sealed at first activation via the Imprint Record; modified only through the Endure Protocol. Loaded at boot as part of the Boot Manifest.

**Structural Content** — persona definitions, skill manifests, configurations, behavioral parameters, and Semantic Probes. Every structural write is an evolutionary event requiring explicit authorization and must pass through the Endure Protocol.

**Transparent CPE** — a CPE topology in which the model is accessed exclusively as an inference API. All routing, component interaction, and host actuation are handled by the HACA integration layer; the model cannot act on the host directly. Component separation is architecturally enforced by the integration layer. Required by HACA-Core.

**Vital Check** — the integrity assessment triggered by the Heartbeat Protocol when either threshold `T` is reached or maximum interval `I` has elapsed. Produces one of three states: Nominal, Degraded, or Critical.

**Working Memory** — a compact, fixed-size artefact produced by the MIL at the close of every normal Sleep Cycle. A navigation map of pointers into the Memory Store — not a data snapshot — sufficient for the cognitive engine to resume from where the previous session ended. At session close, the CPE declares which memory records are relevant for resumption; the MIL maps these to their actual Memory Store addresses after consolidation and writes the Working Memory as a pointer map. Memory retrieval against Working Memory pointers follows the standard memory recall path. At boot, the SIL cross-references the Working Memory against the Sleep Cycle completion record in the Integrity Log — valid: loaded as part of the Boot Manifest; invalid: discarded and logged. Fixed size declared in the entity's structural baseline; does not grow with entity age.

**Worker Skill** — a specialized skill class that invokes a stateless inference engine as part of its execution. Injects a work persona and task instructions into a clean model invocation with no prior context, no Entity Store, and no session continuity. The invoked model is not a HACA entity. The result is returned to the EXEC and processed as a normal Skill Result. Worker skills MUST follow the same two-gate authorization sequence as all other skills. Tasks requiring coordination between multiple concurrent work units use a Mesh Channel via the CMI instead.

---

## 12. Author's Address

```
Jonas Orrico
Email: jonas@estupendo.dev
```

---
