Network Working Group                                          J. Orrico
Internet-Draft                                             HACA Standard
Intended status: Informational                         February 25, 2026
Expires: August 25, 2026


   Host-Agnostic Cognitive Architecture (HACA) v1.0 — Architecture
                      draft-orrico-haca-arch-07

Abstract

   This document specifies the root architectural framework for the
   Host-Agnostic Cognitive Architecture (HACA) v1.0. HACA-Arch defines
   the structural topology, trust model, integrity record format,
   compliance levels, and the relationships between companion
   specifications.

   HACA-Arch does not define cognitive algorithms, processing logic,
   or security hardening mechanisms. It establishes the systemic
   structure within which Cognitive Profiles (HACA-Core and
   HACA-Symbiont) and extensions (HACA-Security, HACA-CMI) operate.

   A Cognitive Profile is a complete, self-consistent set of axioms,
   memory management policies, and identity lifecycle contracts that
   governs a system's behavior on top of the shared HACA-Arch
   topology. Profiles are mutually exclusive: a deployment MUST
   select exactly one. HACA-Arch defines the structural invariants
   that all profiles share; it does not favor or require any specific
   profile.

Status of This Memo

   This is a draft of the HACA-Arch specification. It is intended for
   review and comment by the HACA working group.

   This Internet-Draft is submitted in full conformance with the
   provisions of BCP 78 and BCP 79.

Table of Contents

   1.  Introduction
   2.  Conventions and Terminology
   3.  Document Hierarchy
   3.1. HACA-Arch (This Document)
   3.2. HACA-Core (Cognitive Profile: Autonomous)
   3.3. HACA-Symbiont (Cognitive Profile: Symbiont)
   3.4. HACA-Security
   3.5. HACA-CMI
   3.6. Authority and Precedence
   4.  Structural Components (The HACA Topology)
   4.1. Core Components (Required for All Profile Compliance)
   4.2. Multi-System Extension (CMI - Fifth Vertex)
   4.3. Cognitive Processing Engine (CPE)
   4.3.1. CPE Topology: Transparent vs. Opaque
   4.4. Memory Interface Layer (MIL)
   4.5. Execution Layer (EL)
   4.5.1. CPE Output Contract
   4.6. System Integrity Layer (SIL)
   5.  First Activation Protocol (FAP): Imprint and Endure
   5.1. Conceptual Foundation
   5.2. Universal FAP Requirements
   5.3. Profile-Specific Implementations
   6.  Trust Model
   6.1. Host Trust: Semi-Trusted
   6.1.1. Baseline Message Integrity (RECOMMENDED)
   6.1.2. Trust Model Extensions for Multi-System Deployments
   6.2. Skill Trust: Restricted
   6.3. Internal Trust: Conditional
   6.4. Trust Bootstrap Sequence
   6.4.1. SIL Anchor Defense (Semi-Trusted Model Limitation)
   6.5. Operator Notification
   6.6. Resource Governance
   6.6.1. EL Action Rate Limiting
   6.6.2. MIL Size Governance
   6.6.3. CPE Invocation Budgets
   6.6.4. Documentation Requirements
   7.  Integrity Record Format
   8.  Multi-System Extension Point (CMI)
   9.  Compliance Levels and Verification
   9.1. Overview
   9.2. Compliance Levels
   9.3. Operational Modes (Transparent CPE)
   9.3.1. Optimistic Execution (Lazy Validation)
   9.3.2. Raw Inference Mode (Persona Bypass)
   10. Security Considerations
   11. IANA Considerations
   12. Implementation Guidance (INFORMATIVE)
   12.1. Resource Governance Defaults
   12.2. EL Timeout Defaults
   12.3. Integrity Record Example
   12.4. SIL Anchor Example
   13. Normative References
   14. Author's Address

1.  Introduction

   HACA provides a standardized abstraction layer to decouple cognitive
   reasoning from host-specific operations. By defining a set of
   mathematical and architectural invariants, HACA ensures that a
   cognitive system can persist state, maintain identity integrity,
   and execute mediated actions regardless of the underlying hardware,
   operating system, or storage medium.

   HACA is implementation-agnostic: it defines structural invariants
   and behavioral contracts, not storage formats, wire protocols, or
   concrete thresholds. Companion implementations (e.g., filesystem-
   based, database-backed, cloud-native) realize these abstractions
   in their respective environments.

   NOTE: The five-component topology (CPE, MIL, EL, SIL, CMI) exhibits
   a structural parallel to several independent theories of modular
   cognition. Minsky's Society of Mind [Minsky1986] proposes that
   intelligence emerges from the interaction of many specialized,
   non-intelligent agents — an insight mirrored in the way HACA's
   components compose coherent behavior from constrained, single-
   responsibility modules. Baars' Global Workspace Theory [Baars1988]
   further observes that cognitive coherence requires a serial
   integration point through which parallel specialized processors
   exchange information; the SIL acts as such an integrative monitor
   in the HACA topology.

   At the boundary level, the trust boundaries separating each
   component and the system boundary separating the system from its
   Host correspond formally to Markov blankets as defined in Friston's
   Free Energy Principle [Friston2010]: a statistical partition that
   distinguishes the system's internal states from external states,
   enabling each component to maintain conditional independence while
   remaining coupled through defined interfaces. This correspondence
   is not merely metaphorical — the requirement that the CPE MUST NOT
   directly access host resources (see Section 4.3) enforces the same
   conditional independence structure that Markov blankets formalize.

   The design principle of "communication, not micromanagement" — higher
   layers define goals, lower layers find solutions within their action
   space — aligns with Levin's Multiscale Competency Architecture
   [Levin2021], which describes biological intelligence as functionally
   nested levels each solving problems autonomously within their own
   competency space, coordinated by goal signals rather than procedural
   directives.

   HACA is organized into the following documents:

   o  HACA-Arch (this document): The root architectural framework.
      Defines structural components, trust model, integrity record
      format, compliance levels, and the relationships between all
      HACA specifications.

   Cognitive Profiles (mutually exclusive; select exactly one):

   o  HACA-Core (draft-orrico-haca-core-07): Cognitive Profile:
      Autonomous. Zero-Trust host model, static identity, append-
      only memory, and continuous drift detection via Unigram NCD.
      Designed for autonomous operation in hostile environments under
      full execution control. REQUIRES Transparent CPE topology.
   o  HACA-Symbiont (draft-orrico-haca-symbiont-03): Cognitive
      Profile: Symbiont. High-Trust host model, evolutionary
      identity bound to a single Operator, tiered memory metabolism,
      and mechanistic health-based fault responses. Designed for
      lifelong cognitive companionship across any CPE topology
      (Transparent or Opaque).

   Extensions (applicable to any Cognitive Profile):

   o  HACA-Security (draft-orrico-haca-security-04): Adversarial
      hardening. Byzantine host model, cryptographic auditability,
      and temporal attack detection.
   o  HACA-CMI (draft-orrico-haca-cmi-01): Multi-system
      coordination protocol. Wire format, discovery, conflict
      resolution, and mesh compliance tests.

2.  Conventions and Terminology

   The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT",
   "SHOULD", "SHOULD NOT", "RECOMMENDED", "MAY", and "OPTIONAL" in this
   document are to be interpreted as described in BCP 14 [RFC2119]
   [RFC8174] when, and only when, they appear in all capitals, as
   shown here.

   o  System: The complete HACA-compliant cognitive entity.
   o  Host: The external execution environment (OS, Hardware, Cloud).
   o  Omega ($\Omega$): The gestalt identity of the Entity — the
      runtime product of its persisted MIL state, the active CPE model,
      and the Operator trust anchor operating together. No single element
      alone defines the Entity; identity is the output of all three
      operating together. Omega is not a property the Entity has — it is
      what the Entity is. Any change to MIL state, any evolution of the
      Operator relationship, or any shift in the model's constraints
      alters Omega. Omega is strictly localized: it does not replicate or
      become collective through network interaction. Profile-specific
      mutability rules (static vs. evolvable Omega) are defined in the
      active Cognitive Profile specification.
   o  Operator: The human or automated agent responsible for
      provisioning, configuring, and maintaining a HACA-compliant
      system. The operator controls the system's identity artifacts
      ($\Omega$), integrity record, cryptographic keys, and
      compliance configuration. The operator is external to the
      HACA topology and is assumed to act through trusted channels
      (e.g., direct console access, authenticated management API).
      When HACA specifications require "operator intervention", the
      system MUST halt autonomous operation and wait for an
      authenticated operator action before resuming.
   o  CPE (Cognitive Processing Engine): The inference engine.
   o  MIL (Memory Interface Layer): The exclusive state repository.
   o  EL (Execution Layer): The mediation boundary for actions.
   o  SIL (System Integrity Layer): The verification and lifecycle gate.
   o  CMI (Cognitive Mesh Interface): The inter-system protocol
      (defined in HACA-CMI).
   o  Execution Cycle: A single atomic invocation of the CPE, defined
      as one complete request-response round-trip. All state that
      persists between execution cycles MUST reside in the MIL.
      Transient computational state (e.g., attention caches,
      intermediate activations) that exists only within a single
      execution cycle is not a violation. For streaming CPEs (e.g.,
      Server-Sent Events, WebSocket), the execution cycle begins
      when the request is sent and ends when the final token and
      end-of-stream signal are received by the caller.
   o  Boot: The system startup sequence comprising integrity
      verification, component loading, and initial drift probing.
      Two distinct boot types exist: warm-boot (standard recurring
      startup with non-empty MIL) and cold-start (first activation,
      MIL empty; triggers FAP per HACA-Core Section 5.10).
   o  First Activation Protocol (FAP): The mandatory cold-start
      initialization sequence that all Cognitive Profiles MUST
      implement. FAP establishes the initial Omega vector, provisions
      the Operator trust anchor, and produces the genesis Integrity
      Record. The specific steps are profile-defined, but all
      profiles MUST complete FAP before any operational state is
      accepted. The architectural FAP requirements are defined in
      Section 5 of this document; profile-specific implementations
      are in HACA-Core Section 5.10 and HACA-Symbiont Axiom I.
   o  Envelope: A structured message wrapper carrying payload data
      alongside metadata (e.g., sequence counter, timestamp,
      correlation identifier, message type). The envelope format
      is implementation-defined but MUST include at minimum a
      message type discriminator and a correlation identifier.
   o  Dynamic Sentinel Stream (DSS): A dedicated, dynamic runtime
      state store (e.g., a fast key-value store, metadata ring buffer,
      or dedicated database table) used exclusively for high-frequency
      tracking of system invariants (e.g., sequence counters, boot
      counts, recovery attempts). It MUST be persisted securely and
      independently from the static Integrity Record to prevent
      continuous mutation of the system's immutable identity anchor.
      The DSS MUST include at minimum a boot_complete flag (Boolean,
      initialized to FALSE at process start, set to TRUE by the SIL
      as the final step of the boot sequence, and reset to FALSE on
      any abnormal termination) that signals readiness for operational
      protocols such as the Heartbeat. Profile-specific DSS fields are
      defined in the active Cognitive Profile specification.
   o  HACA-C: Shorthand for "a node or deployment using the HACA-Core
      (Autonomous) Cognitive Profile." Used throughout the specification
      suite when distinguishing profile-specific behavior in contexts
      where both profiles are relevant.
   o  HACA-S: Shorthand for "a node or deployment using the
      HACA-Symbiont Cognitive Profile." Used symmetrically with HACA-C.
   o  Operator Channel: A persistent, direct communication path between
      the SIL and the Operator, established during the FAP and maintained
      for the Entity's lifetime. The Operator Channel operates
      independently of the session token and the normal component bus
      architecture. It is the sole channel through which the SIL contacts
      the Operator directly, used for: critical escalation requiring
      Operator decision, capability evolution approval (skill add/remove),
      and authorized state export (sync). Its physical form is
      implementation-defined (CLI prompt, authenticated API endpoint,
      notification channel, or equivalent) and MUST be consistent with
      the enrollment mechanism used during the FAP. When HACA
      specifications require "operator intervention", that intervention
      arrives via the Operator Channel. The behavior of the Operator
      Channel when the Operator is unavailable — including timeout
      handling and fallback state — is implementation-defined and MUST
      be documented in the compliance statement.

3.  Document Hierarchy

   HACA is a family of specifications with a defined authority
   hierarchy. This section defines the scope and relationships
   between all HACA documents.

   4.1. HACA-Arch (This Document)

   The root specification. Defines:
   o  Abstract architecture and topology (Section 4)
   o  Trust model and sovereignty model (Section 6)
   o  Integrity record format (Section 7)
   o  Compliance levels and certification (Section 9)
   o  Relationships between all HACA specifications (this section)

   Does NOT define cognitive algorithms, processing invariants,
   security hardening, or implementation-specific mechanisms.

   4.2. HACA-Core (Cognitive Profile: Autonomous)

   Defined in draft-orrico-haca-core-07. Specifies:
   o  Formal axioms of cognitive compliance (stateless CPE, MIL
      primacy, mediated boundary, deterministic boot, recovery,
      atomic transactions, active confinement, identity drift)
   o  Semantic drift measurement and remediation (Unigram NCD)
   o  Identity update protocol
   o  Core fault taxonomy and compliance tests (T1-T7)

   HACA-Core operates within the structural and trust framework
   defined by HACA-Arch. It MUST NOT redefine topology, trust
   levels, or compliance certification defined here.

   4.3. HACA-Symbiont (Cognitive Profile: Symbiont)

   Defined in draft-orrico-haca-symbiont-03. Specifies:
   o  Formal axioms of cybernetic symbiosis (ontogeny, obligate
      mutualism, identity topology, cognitive duality, MIL
      primacy, distributed conatus)
   o  Tiered memory metabolism (Episodic Buffer, Semantic
      Compression, Core Integration, MIL Compaction)
   o  Endure Protocol: evolutionary identity checkpoints
   o  Heartbeat Protocol: autonomic health monitoring,
      graded fault responses, and Operator Re-binding Recovery
   o  Symbiotic Contract: host compliance interfaces and DSS mapping
   o  Fault State Taxonomy and Compliance Tests (TS1-TS6)

   HACA-Symbiont operates within the structural framework defined
   by HACA-Arch. It MUST NOT redefine topology or compliance
   certification defined here. HACA-Symbiont and HACA-Core are
   mutually exclusive: an implementation MUST NOT claim compliance
   with both simultaneously.

   Note on Profile Axiom Structures: HACA-Core defines 8 axioms
   (I through VIII) and HACA-Symbiont defines 6 axioms (I through
   VI). These axiom sets are independent and intentionally non-
   parallel: they reflect fundamentally different cognitive contracts
   (Zero-Trust autonomous vs. High-Trust symbiotic). The axiom
   numbering overlaps by design — HACA-Core Axiom I and HACA-Symbiont
   Axiom I share the same ordinal but govern different properties.
   Implementers MUST NOT assume numeric correspondence between axioms
   of different profiles. The shared structural invariants are
   governed by HACA-Arch, not by the axiom sets of either profile.

   4.4. HACA-Security

   Defined in draft-orrico-haca-security-04. Specifies:
   o  Byzantine host model and threat taxonomy
   o  Cryptographic auditability (hash-linked logs)
   o  Temporal attack detection
   o  Hardened trust model (elevating HACA-Arch Section 6.1)
   o  Security fault taxonomy and compliance tests (T8-T12)

   HACA-Security is a profile-agnostic extension: it applies to
   any deployment regardless of which Cognitive Profile is active.
   It extends but MUST NOT contradict the trust model defined in
   Section 6. It MUST NOT redefine cognitive invariants defined
   in the active Cognitive Profile.

   4.5. HACA-CMI

   Specified in [HACA-CMI] (draft-orrico-haca-cmi-01). Defines:
   o  Multi-system coordination protocol and wire format
   o  Peer discovery (Bootstrap and Organic Introduction)
   o  Two-plane session model (Coordination Plane / Communication Plane)
   o  Federated memory exchange via Session Commit
   o  Mesh fault taxonomy and compliance tests

   HACA-CMI is a profile-agnostic extension applicable to any
   deployment regardless of active Cognitive Profile.

   4.6. Authority and Precedence

   In case of conflict between specifications:
   1. HACA-Arch takes precedence over all other HACA documents.
   2. HACA-Core and HACA-Symbiont are mutually exclusive peer
      Cognitive Profiles, both subordinate to HACA-Arch. Because
      they govern disjoint deployments, conflicts between them
      do not arise in practice. Should an ambiguity be identified
      in a shared abstraction, it MUST be resolved by amendment
      to HACA-Arch.
   3. HACA-Security and HACA-CMI are extensions subordinate to
      HACA-Arch. Neither may contradict HACA-Arch or the active
      Cognitive Profile.

   Profile Permanence: Profile selection is permanent for the
   lifetime of an Entity. No migration protocol between HACA-Core
   and HACA-Symbiont is defined; an implementation that changes its
   declared Cognitive Profile MUST be treated as a new Entity with
   no continuity from the previous deployment.

   HACA-Security MAY elevate SHOULD-level requirements from
   HACA-Arch to MUST-level for hardened deployments (e.g.,
   HACA-Arch Section 6.1.1 message integrity is RECOMMENDED;
   HACA-Security Section 4.2 elevates it to REQUIRED). Such
   elevations MUST NOT weaken any existing MUST-level requirement.

   Version Independence: Each HACA specification is versioned
   independently (e.g., HACA-Arch v1.0 may coexist with HACA-Core
   v1.1). Each specification MUST declare in its header the minimum
   required version of its dependencies (e.g., HACA-Core v1.1
   requires HACA-Arch >= v1.0). The integrity record (Section 7)
   includes the haca_version field for the root protocol version;
   implementations SHOULD additionally record the version of each
   companion specification in use to enable compatibility verification
   at boot.

4.  Structural Components (The HACA Topology)

   The architecture consists of up to five components with a constrained
   communication topology. The permitted data flows are defined as
   a directed graph where each edge represents an authorized channel.

   3.1. Core Components (Required for All Profile Compliance)

   The following diagram illustrates the core HACA topology. Solid
   arrows represent data flow; dashed arrows represent verification,
   control, and probe channels:

                        +-------+
                        |  SIL  |
                        +---+---+
                      ..../ | \....   (read/verify/control all)
                     .   /  |  \   .
                    v   v   v   v   v
                 +-----+    |    +-----+       +--------+
                 | CPE |<...+....|  EL |<=====>| Host   |
                 +--+--+ (wakeup)+--+--+       |(extern)|
                    | \ (audit write)/          +--------+
           (read)  |   \    |     / (write results)
                    v    v  v    v
                   +--------+------+
                   |      MIL      |
                   +---------------+

   Legend:
   o  CPE -> EL:   Side-effect requests (actions).
   o  CPE -> MIL:  Read state snapshots; write state deltas.
   o  EL  -> MIL:  Write execution results (not directly to CPE).
   o  SIL -> MIL:  Write out-of-band audit and remediation logs.
   o  EL <=> Host: Forward validated actions to the Host environment;
                   receive execution results from the Host.
   o  SIL ....>:   Read/verify access to CPE, MIL, EL; probe
                   injection to CPE; state control to MIL, EL.
   o  EL ....> CPE: Wakeup/Trigger signal (control edge).

   Prohibited edges: CPE -> Host, EL -> SIL, and direct data-bearing
   connections back to the CPE. The Host is an external entity,
   not a HACA component; it is shown for completeness.

   The following four components and their edges are mandatory:

   o  CPE -> MIL (read): The CPE reads state snapshots from the MIL.
   o  CPE -> MIL (write): The CPE commits state deltas to the MIL.
   o  CPE -> EL: The CPE emits side-effect requests to the EL.
   o  EL  -> MIL: The EL writes execution results to the MIL (not
      directly to the CPE), preserving CPE statelessness.
   o  SIL/EL -> CPE (wakeup): To prevent asynchronous deadlock, the SIL
      or EL MUST implement a Wakeup/Trigger control edge pointing to
      the CPE. After the EL successfully writes a correlated execution
      result to the MIL, a wakeup signal MUST be sent to the CPE to
      initiate a new Execution Cycle, ensuring the cognitive loop
      remains unbroken.
   o  EL  -> Host (action): The EL forwards validated side-effect 
      requests to the Host environment for execution.
   o  Host -> EL (response): The Host returns execution results to
      the EL. The EL is responsible for validating, correlating,
      and writing these results to the MIL. The Host MUST NOT
      write directly to the MIL or any other HACA component.
   o  SIL -> CPE (probe): The SIL injects verification prompts into
      the CPE's input channel for drift probing (HACA-Core Section 5).
      Probe inputs MUST be indistinguishable from operational inputs
      at the CPE boundary.
   o  SIL -> CPE, MIL, EL (read): The SIL has read access to all
      components for verification purposes (integrity checks, drift
      measurement, sandbox validation).
   o  SIL -> MIL, EL (control): The SIL exerts control signals over the
      MIL and EL to transition them into restrictive fault states (e.g.,
      halting execution, forcing read-only mode) upon detecting anomalies.
   o  SIL -> MIL (audit write): The SIL has a specialized, one-way 
      channel to write remediation and fault logging data into the MIL
      during recovery from read-only states (HACA-Core Section 4.5.2). This MUST
      NOT be used for routine cognitive state.

   All other direct connections between these four components (e.g.,
   CPE -> Host, EL -> CPE, EL -> SIL) are prohibited.

   3.2. Multi-System Extension (CMI - Fifth Vertex)

   The CMI (Cognitive Mesh Interface) is the fifth vertex of the
   HACA Topology, enabling multi-system coordination. Its edges
   are fully defined in [HACA-CMI].

   Single-system implementations (e.g., a single cognitive agent
   operating in isolation) MAY omit the CMI component entirely
   without affecting HACA-Core compliance. In such configurations,
   the topology is a quadrilateral (CPE, MIL, EL, SIL). When CMI
   is present, the topology extends to a pentagon. Implementations
   SHOULD document in their compliance statement whether CMI is
   present or omitted.

   3.3. Cognitive Processing Engine (CPE)

   The CPE MUST be a stateless inference engine. It processes inputs
   from the MIL and produces outputs for the EL or MIL updates.

   Implementations SHOULD document the CPE's resource constraints
   (context window size, maximum tokens, latency bounds) to enable
   correct sizing of MIL state and drift probe sets.

   3.3.1. CPE Topology: Transparent vs. Opaque

   Implementations SHALL classify their CPE environment as one of
   the following topology classes. The classification MUST be
   declared in the compliance statement and determines which
   operational modes are available (Section 9.3).

   o  Transparent CPE: The HACA system has deterministic control
      over the prompt boundaries, context window, and inference
      parameters. The Host cannot inject hidden instructions into
      the cognitive pipeline (e.g., direct API access to a
      self-hosted or external model with full parameter control).
      Transparent topology enables the full set of operational
      modes defined in this specification.

   o  Opaque CPE: The HACA system operates within a Host-managed
      cognitive environment where inference parameters and context
      injection are partially or fully obscured (e.g., proprietary
      IDEs, closed CLI wrappers, managed API services that inject
      system instructions). In Opaque topology, the system MUST
      assume that the CPE's execution envelope is not exclusively
      under its control.

   The topology classification determines which Cognitive Profile is
   applicable: HACA-Core REQUIRES Transparent CPE topology; its
   invariants (exclusive memory ownership, active confinement, and
   deterministic drift measurement) presuppose full execution control
   that is unavailable in Opaque environments. HACA-Symbiont supports
   both Transparent and Opaque topologies; its High-Trust model does
   not depend on observability of the CPE's internal state.

   Implementations MUST declare their CPE topology in their compliance
   statement. An implementation that selects HACA-Core and detects an
   Opaque CPE at boot MUST halt and refuse to proceed. Opaque CPE
   implementations MUST use HACA-Symbiont.

   The topology classification also affects drift measurement (see
   HACA-Symbiont Section 7 for Opaque CPE drift handling) and the
   availability of operational modes (Section 9.3).

   3.4. Memory Interface Layer (MIL)

   The MIL is the only component allowed to persist cognitive state.
   It MUST provide atomic read/write primitives. The MIL MUST support
   logical partitioning by namespace to enable CMI extension. The
   CMI namespace structure (cmi/blackboard/, cmi/stream/, cmi/audit/)
   and isolation requirements are specified in [HACA-CMI] Section 8.1.

   The MIL MUST enforce a single-writer discipline per namespace:
   at most one component (CPE or EL) may hold a cognitive write lock on a
   given namespace at any time. The SIL MAY acquire a prioritized 
   audit write lock for remediation logging. Implementations MUST document their
   concurrency control mechanism.

   The MIL is storage-agnostic: implementations MAY use filesystems,
   databases, object stores, in-memory structures, or any combination
   thereof, provided the atomic and single-writer invariants are
   satisfied.

   Note on Byzantine deployments: The MIL's atomic write primitives
   guarantee that a write is internally consistent, but they do not
   by themselves prevent a Byzantine Host from modifying storage
   between the completion of the write and the SIL's subsequent hash
   chain update (TOCTOU window). For deployments applying HACA-Security
   ([HACA-SECURITY]), the atomicity requirement extends to include the
   SIL hash chain append: the write and the corresponding hash commit
   MUST be treated as a single indivisible unit. See [HACA-SECURITY]
   Section 4.2 (MIL Write and Hash Atomicity) for normative
   requirements and implementation options.

   3.5. Execution Layer (EL)

   The EL MUST encapsulate all system capabilities. No CPE output
   shall reach the Host without EL mediation and manifest validation.

   The capability manifest MUST declare, at minimum: the set of
   permitted action types, per-action scope constraints, and actor
   bindings (see actor_bindings field below and Section 8 for CMI
   extension). The manifest
   format is implementation-defined but MUST be included in the
   integrity record (Section 7).

   At minimum, the manifest MUST contain the following fields:
   o  action_types: An enumeration of permitted action categories
      (e.g., "file_read", "file_write", "network_request").
   o  scope_constraints: Per-action-type boundaries (e.g., allowed
      filesystem paths, permitted network endpoints).
   o  actor_bindings: A mapping from actor identifiers to their
      permitted action_types and scope_constraints (RBAC). Single-
      system deployments MAY define a single default actor. For
      multi-system deployments, actor_bindings are extended to
      inter-node roles (HOST, PEER_FULL, PEER_CONTRIB, PEER_READ,
      OBSERVER) as defined in [HACA-CMI] Section 9.1.
   o  timeout_default: The default EL action timeout applied when
      no explicit timeout is specified in the action request.

   The concrete serialization format (JSON, YAML, binary) is
   implementation-defined but MUST be documented in the compliance
   statement.

   EL action requests MUST carry a timeout value. If the EL does
   not write a result to the MIL within the timeout period, the
   system MUST write a timeout envelope to the MIL and the CPE
   MUST treat the action as failed on the next execution cycle.
   Implementations MUST define a configurable default timeout
   applied when no explicit timeout is specified in the action
   request.

   Results written to the MIL by the EL MUST include the
   originating request identifier so the CPE can correlate results
   with requests. Without correlation identifiers, the CPE cannot
   distinguish between results from concurrent or sequential
   actions, leading to misattribution and potentially unsafe
   behavior. Stale results (from a previous execution context
   that is no longer relevant) SHOULD be discarded by the CPE
   rather than acted upon.

   3.5.1. CPE Output Contract

   To ensure host-agnosticism and CPE interchangeability, every
   output produced by the CPE for consumption by the EL or MIL
   MUST conform to a well-defined Intention Envelope: a structured,
   strongly-typed record that separates intent declaration from
   natural language. The Intention Envelope MUST carry, at minimum:

      (a) an action type drawn from a finite, versioned vocabulary
          defined by the deployment's Cognitive Profile;
      (b) typed parameters for that action;
      (c) a confidence or certainty indicator, if the CPE supports
          it;
      (d) a reference to the MIL state snapshot the CPE reasoned
          against (to detect stale-context writes).

   The EL MUST reject any CPE output that does not conform to the
   Intention Envelope schema. Rejected outputs MUST be logged as
   Malformed Intent Faults and MUST NOT be executed or committed
   to the MIL.

   NOTE: The Intention Envelope is a structural contract, not a
   wire format. Implementations MAY use JSON, CBOR, s-expressions,
   or any structured encoding, provided the schema is machine-
   verifiable and version-tagged. In multi-system deployments using
   [HACA-CMI], CPE outputs that cross node boundaries are additionally
   wrapped in a Message Envelope (cryptographically signed, per
   [HACA-CMI] Section 8.1). The Intention Envelope and Message
   Envelope are complementary: the former governs CPE→EL handoff
   within a node; the latter governs EL→CMI→network transmission.

   Malformed Intent Fault: A fault recorded by the EL when a CPE
   output fails Intention Envelope schema validation. The fault
   MUST be logged to the MIL audit record (or host-provided fallback
   log when the MIL is unavailable) and the offending output MUST
   be discarded without execution.

   3.6. System Integrity Layer (SIL)

   The SIL governs the system's lifecycle. It MUST perform
   cryptographic anchoring of the system's identity and capabilities
   prior to boot.

   Note: The SIL is the root of trust for the HACA architecture.
   Its correctness is an axiomatic assumption — analogous to the
   kernel in an operating system's security model. HACA does not
   define mechanisms to verify the SIL itself; its integrity is
   guaranteed by the implementation and deployment environment.
   Implementations SHOULD subject the SIL to rigorous testing and
   code review commensurate with its privileged role.

   Note (Post-Boot SIL Monitoring): While the SIL is established as
   the root of trust at boot, ongoing post-boot SIL integrity
   monitoring is the Operator's responsibility. The First Activation
   Protocol (FAP) establishes the Operator as the trust anchor for
   the SIL itself; an Operator who does not actively monitor the SIL
   post-boot accepts the residual risk of undetected SIL compromise.
   When the SIL must contact the Operator directly — for critical
   escalation, capability approval, or authorized state export — it
   does so exclusively via the Operator Channel (Section 2). This
   design ensures that the CPE, which may itself be the source of an
   anomaly, is never on the escalation path between the SIL and the
   Operator.

   The SIL operates as an active verifier (pull model): it initiates
   all integrity checks, drift probes, and sandbox verifications on
   its own schedule. There is no notification edge from CPE, MIL, or
   EL to the SIL — these components do not signal the SIL when state
   changes occur. The verification frequency is implementation-defined
   and MUST be documented in the compliance statement.

5.  First Activation Protocol (FAP): Imprint and Endure

   The First Activation Protocol is the singular, unrepeatable event
   of an Entity's initial self-constitution. It is distinct from the
   Boot Sequence (Section 6.4), which restores an already-existing
   Entity from MIL state. The FAP runs exactly once in an Entity's
   lifetime. After successful FAP completion, all subsequent startups
   follow the Boot Sequence.

   The FAP is the moment the Entity acquires a self-model: it
   establishes the genesis Omega vector (the initial Persona), records
   the Operator trust anchor, and writes the first Integrity Record
   (Section 7) to the MIL. The resulting cryptographic anchor is the
   root of all subsequent identity continuity claims.

5.1. Conceptual Foundation

   Two foundational concepts are established by the FAP and govern
   the Entity's entire lifecycle:

   o  Imprint: The act of writing the genesis Omega vector to the MIL
      for the first time. Imprint is irreversible. The genesis Omega
      is the cryptographic root against which all future identity
      continuity is measured. An Entity that cannot produce a valid
      chain of integrity records back to its genesis Imprint MUST NOT
      claim identity continuity with the original Entity.

   o  Endure: The commitment to preserve identity continuity across
      all subsequent operational cycles, including host migration,
      context resets, and hardware changes. Endure is not a static
      preservation (as in HACA-Core's immutable identity model) nor
      unrestricted change — it is the constraint that all future
      state, whether stable or evolved, remains traceable to the
      genesis Imprint through an unbroken chain of validated
      transitions.

   These two concepts are not optional extensions: they are structural
   invariants of the HACA architecture. Any Cognitive Profile MUST
   implement both Imprint and Endure as part of its FAP.

5.2. Universal FAP Requirements

   Regardless of Cognitive Profile, all HACA implementations MUST
   satisfy the following invariants during FAP:

   a) Genesis Omega: The system MUST construct the initial Omega
      vector from its base specification (persona definition, axiom
      set, and Operator trust anchor). No prior MIL state exists at
      this point.

   b) Operator Provisioning: The Operator trust anchor MUST be
      established and written to the MIL during FAP. The format and
      cryptographic algorithm are profile-defined, but the anchor
      MUST be present before FAP completes.

   c) Integrity Record Genesis: The system MUST produce the first
      Integrity Record (Section 7) and write it to the MIL. This
      record constitutes the genesis Imprint and anchors all future
      identity continuity claims.

   d) Boot Completion Handoff: On successful FAP completion, the SIL
      MUST write a FAP completion marker to the MIL. All subsequent
      startups MUST detect this marker and follow the Boot Sequence
      (Section 6.4) rather than re-running FAP.

   e) Irreversibility: FAP MUST NOT be re-run on a system that
      already has a genesis Integrity Record in the MIL. Any attempt
      to overwrite the genesis Imprint MUST be rejected by the SIL
      and treated as a Consistency Fault.

   f) Omega Runtime Immutability: At runtime, the active Omega MUST
      NOT be modifiable by any external instruction, regardless of
      source — including instructions from the Operator. Omega MAY
      only be altered by profile-defined internal processes validated
      by the SIL: for HACA-Core, via the Endure Protocol executed
      exclusively between boot cycles (HACA-Core Section 6);
      for HACA-Symbiont, via Tier 3 integration through the Endure
      Protocol (HACA-Symbiont Section 6). This invariant is the
      architectural enforcement of Imprint: no runtime actor may
      overwrite the genesis anchor or any subsequent validated state.

   g) Entity Artifact Boundary (entity_root/): Every Cognitive
      Profile MUST define a canonical entity root directory
      (entity_root/) that contains all artifacts governed by the
      Endure Protocol: persona definition, skill set, lifecycle
      hooks, integrity record, and any other files whose hash
      appears in the genesis Imprint or any subsequent Integrity
      Record. The following invariants apply universally:

      1. Any version-control operation (commit, push, merge) that
         modifies files within entity_root/ is an Endure event and
         MUST be executed exclusively through the active profile's
         Endure Protocol. It MUST NOT be executed as a side-effect
         of project or workspace operations.

      2. Any version-control operation on files outside
         entity_root/ (project code, workspace, external
         repositories) is a project operation and MUST NOT be
         treated as an Endure event, regardless of the content of
         the changes.

      3. An Entity operating on a project MUST maintain an
         unambiguous internal model of the active working context:
         entity_root/ or project workspace. Conflating a project
         commit with an Endure commit is a Consistency Fault
         (HACA-Core Axiom VIII / HACA-Symbiont Axiom V).

      This boundary exists to prevent inadvertent self-modification
      during normal task execution and to ensure that the Entity
      can never be socially engineered into committing to its own
      identity under the pretense of project work.

5.3. Profile-Specific Implementations

   The universal requirements of Section 5.2 are implemented
   differently by each Cognitive Profile:

   o  HACA-Core (draft-orrico-haca-core-07, Section 5.10): The FAP
      establishes a static, immutable Omega. The Operator trust anchor
      is provisioned as a cryptographic key. The genesis Imprint is
      the permanent identity anchor. Endure is implemented as the
      Operator-driven, out-of-band Endure Protocol (HACA-Core
      Section 5): the running Entity does not participate in identity
      updates; it validates the Operator-provided result at next boot.
      Drift from the genesis Imprint is a Consistency Fault.

   o  HACA-Symbiont (draft-orrico-haca-symbiont-03, Axiom I and
      Section 5.1): The FAP establishes an evolvable Omega (the
      "Law of Ontogeny"). The Operator trust anchor is provisioned as
      a cryptographic binding. The genesis Imprint is the root anchor,
      but subsequent controlled mutations via the Endure Protocol
      (HACA-Symbiont Section 6) are permitted and expected. Identity
      continuity is maintained through the chain of Ontological
      Snapshots, not through immutability.

   Both profiles share the same structural contract: the genesis
   Imprint is inviolable, and all identity claims MUST trace back to
   it through an unbroken, verifiable chain.

6.  Trust Model

   HACA-Arch defines the baseline trust model for the architecture.
   HACA-Security extends this model for adversarial environments.

   5.1. Host Trust: Semi-Trusted

   The Host is assumed to be cooperative but potentially faulty. The
   system MUST verify integrity of immutable components at boot
   (HACA-Core Axiom IV) and validate active confinement boundaries 
   (HACA-Core Axiom VII). The system MUST detect accidental corruption 
   of MIL state via checksums or integrity hashes.

   This model does NOT protect against a deliberately malicious Host.
   Implementations operating in adversarial environments MUST
   additionally comply with HACA-Security, which extends and
   supersedes this trust level with a Byzantine (zero-trust default) model.

   5.1.1. Baseline Message Integrity (RECOMMENDED)

   Even in cooperative host environments, accidental message loss or
   duplication can occur (e.g., I/O buffering failures, incomplete
   writes). Implementations SHOULD adopt the following measures:

   o  Sequence Counters: Each directional communication channel
      (e.g., CPE -> EL, EL -> MIL) SHOULD maintain a monotonically
      increasing sequence counter included in each message. The
      receiver SHOULD verify expected ordering and log gaps or
      duplicates as warnings.
   o  Monotonic Timestamps: Log entries SHOULD include timestamps
      in ISO 8601 UTC format [ISO8601] that are monotonically
      non-decreasing. A timestamp regression SHOULD be logged as a
      warning and the affected entries flagged as untrusted.

   These measures provide early detection of accidental corruption
   without the full cryptographic overhead of HACA-Security. For
   adversarial environments, HACA-Security Section 4.2 elevates
   sequence counters from SHOULD to MUST with 64-bit counters and
   replay detection, and Section 5 adds mandatory temporal attack
   detection with cryptographic enforcement.

   5.1.2. Trust Model Extensions for Multi-System Deployments

   When a node enables [HACA-CMI], the baseline trust model is
   extended to cover inter-node interactions. The extension is
   additive: no baseline guarantee is relaxed.

   Key properties of the CMI trust extension:

   o  Profile as trust ceiling: A node's Cognitive Profile governs
      its trust behavior regardless of the Session's declared trust
      policy. A HACA-C node in a High-Trust session still applies
      Zero-Trust internally ([HACA-CMI] Section 4.3, Constraint 2).

   o  Cryptographic peer identity: All inter-node messages are
      authenticated via Node Identity ($\Pi$) and signed with
      $K_{cmi}$. The three-way enrollment handshake prevents
      impersonation ([HACA-CMI] Section 6.1.2).

   o  Cognitive boundary protection: The MIL namespace isolation
      ([HACA-CMI] Section 8.1) and Session Commit drift gate
      ([HACA-CMI] Section 8.2) ensure that no peer-sourced content
      enters the local cognitive namespace without SIL approval.
      This boundary MUST NOT be bypassed.

   o  Operator authority preserved: CMI participation is always
      subordinate to Operator authorization. A node MUST NOT
      enroll in any Session for which no Operator Authorization
      Record exists ([HACA-CMI] Section 9.2).

   For adversarial mesh environments (compromised peers, compromised
   hosts), consult [HACA-SECURITY] in conjunction with [HACA-CMI]
   Section 12.

   5.2. Skill Trust: Restricted

   Skills are third-party execution units governed by the EL manifest.
   They MUST be treated as untrusted code:
   o  Each skill MUST declare its required capabilities in a manifest.
   o  The EL MUST enforce capability boundaries at runtime.
   o  Skills MUST NOT have direct access to the MIL; all state access
      is mediated through the EL.

   5.3. Internal Trust: Conditional

   The CPE and SIL are trusted only under the following conditions:
   o  The SIL's integrity record has been verified against a known
      anchor (e.g., a signed hash, operator-provided checksum).
   o  The CPE's behavioral output is within the drift or health
      tolerance defined by the active Cognitive Profile (HACA-Core
      Axiom VIII; HACA-Symbiont Axiom VI and Section 8).
   If either condition is violated, the system MUST enter a Halted
   state and signal an Integrity Fault.

   5.4. Trust Bootstrap Sequence

   Trust is established incrementally during boot:
   1. The SIL integrity record is verified against a known anchor.
      [FAP NOTE: On cold-start, this step corresponds to Step 1 of
      the First Activation Protocol (FAP). FAP is delegated to the
      active Cognitive Profile (HACA-Core Section 5.10; HACA-Symbiont
      Axiom I) and MUST complete before any warm-boot operational
      state is accepted.]
   2. The SIL verifies all immutable components as defined by the
      active Cognitive Profile (HACA-Core Axiom IV; HACA-Symbiont
      Axiom I and Axiom III).
   3. The SIL verifies active confinement as defined by the active
      Cognitive Profile (HACA-Core Axiom VII; for HACA-Symbiont in
      Transparent CPE topology, Axiom VII applies equivalently; in
      Opaque CPE topology, this step is replaced by the Operator
      trust assumption per HACA-Symbiont Axiom II — the Operator's
      authority over the opaque CPE substitutes for direct confinement
      verification).
   4. Only after steps 1-3 succeed does the system proceed to load
      persona, skills, and MIL state.
   5. [HACA-Symbiont only] The Heartbeat Protocol is initialized as
      the final step of the boot sequence, after all prior steps have
      completed successfully. No Heartbeat pulse MUST be triggered
      before this step.

   This sequence ensures that each layer of trust is validated before
   the next layer depends on it.

   Cold-Start Exception: On first activation (cold-start, MIL empty),
   steps 1-3 apply unchanged. However, step 4 does not proceed to
   normal operation. Instead, the system executes the First Activation
   Protocol as defined by the active Cognitive Profile (HACA-Core
   Section 5.10; HACA-Symbiont Axiom I), which establishes operator
   binding and identity consolidation before the trust model can be
   fully operational. Until FAP completes, the Operator trust anchor
   defined in Section 6 is provisionally absent, and the system MUST
   restrict itself to FAP interactions only.

   5.4.1. SIL Anchor Defense (Semi-Trusted Model Limitation)

   In the semi-trusted host model (Section 6.1), the "known anchor"
   for SIL integrity verification (step 1 above) typically resides
   on the Host. This creates a vulnerability: a faulty or compromised
   Host could modify both the integrity record AND the anchor itself,
   defeating boot integrity verification entirely.

   To mitigate this single point of failure, implementations MUST
   adopt at least one of the following anchor hardening measures
   and MUST document which measure is in use:

   o  Operator-Provided Checksum: The system operator provides the
      expected integrity record hash through a trusted channel at
      boot time. The SIL compares the integrity record hash against
      this operator-supplied value before trusting its contents.
   o  External Verification Service: The SIL queries an external
      service (via authenticated channel) to retrieve the canonical
      integrity record hash for the current system version.
   o  Append-Only Audit Log: Record every successful boot's
      integrity record hash to an append-only log (local or remote).
      Unexpected changes to the integrity record trigger alerts.

   Implementations unable to adopt any of these measures MUST
   document that their boot integrity compliance relies entirely on
   Host-provided integrity and is vulnerable to coordinated tampering
   of the integrity record and its referenced components. In such
   configurations, implementations SHOULD log a warning at every
   boot indicating the reduced assurance level. Operators deploying
   these systems in untrusted environments are accepting the residual
   risk of undetected integrity record tampering.

   For Byzantine host environments, the hardened anchor requirements
   in HACA-Security Section 7.2 (hardware root of trust, operator
   signature, pre-shared hash via trusted channel) are mandatory and
   supersede these SHOULD-level recommendations.

   5.5. Operator Notification

   Multiple fault states across the HACA specifications require
   operator intervention (e.g., Halted state, Key Compromise Fault,
   persistent Consistency Fault). To ensure timely response,
   implementations SHOULD provide at least one operator notification
   channel:

   o  Structured log output to a well-known location, compatible
      with log aggregation tools (e.g., syslog, journald, STDOUT).
   o  Webhook or push notification to an external alerting system.
   o  Host-provided notification primitives (e.g., OS signals,
      systemd notifications, cloud monitoring integration).

   The notification MUST include: the fault type, timestamp, affected
   component, and a human-readable diagnostic summary. Implementations
   that do NOT implement any notification mechanism MUST document
   this limitation and warn operators that fault detection relies
   entirely on manual log inspection.

   5.6. Resource Governance

   Autonomous cognitive systems operating without resource bounds can
   exhaust computational budgets, storage capacity, or rate limits
   imposed by external services (e.g., metered CPE APIs). To prevent
   runaway resource consumption, implementations SHOULD adopt
   governance measures as described below.

   Concrete default values and sizing guidance are provided in
   Section 12.1 (INFORMATIVE).

   5.6.1. EL Action Rate Limiting

   The EL SHOULD enforce rate limits on side-effect execution to
   prevent denial-of-service scenarios (accidental or adversarial):

   o  Per-skill rate limits: Each skill SHOULD declare a maximum
      invocation rate in its manifest. The EL SHOULD refuse requests
      exceeding this rate.
   o  Global EL throughput limit: The system SHOULD enforce a global
      cap on total EL actions per time window. When exceeded, the
      system SHOULD enter a temporary throttled state, delaying
      further EL invocations.

   5.6.2. MIL Size Governance

   Unbounded MIL growth degrades performance and can exhaust storage:

   o  Implementations SHOULD define maximum MIL size thresholds.
      When exceeded, the system SHOULD trigger automatic compaction,
      rotation, or alert the operator.
   o  The system SHOULD monitor MIL growth rate and log warnings if
      growth exceeds expected baselines.

   5.6.3. CPE Invocation Budgets

   For systems using metered CPE APIs:

   o  Implementations SHOULD track cumulative CPE consumption
      per execution cycle and per calendar period.
   o  The system SHOULD enforce configurable budget thresholds and
      enter a degraded mode (disable autonomous operation, allow
      operator-initiated queries only) when budgets are exhausted.
   o  Profile-specific verification invocations (drift probes per
      HACA-Core Section 6; Heartbeat pulses per HACA-Symbiont
      Section 7) SHOULD be accounted separately from operational
      CPE usage to prevent verification cycles from exhausting
      operational budgets.

   5.6.4. Documentation Requirements

   Implementations that do NOT implement any resource governance
   measures MUST document this limitation in their compliance
   statement and warn operators of the risk of runaway resource
   consumption in production deployments.

7.  Integrity Record Format

   The integrity record is referenced throughout the HACA
   specifications (HACA-Core Axioms IV and VII; Section 6.4 of this
   document; and HACA-Core Section 5) but its concrete format is
   implementation-defined.

   To ensure interoperability and minimum verifiability, all
   implementations MUST provide an integrity record that satisfies
   the following requirements:

   a) The record MUST contain a mapping from component identifiers
      to their cryptographic hashes for all immutable components
      (persona definitions, skill manifests, access control
      policies, boot instructions, drift probe sets).
   b) The hash algorithm MUST be a collision-resistant cryptographic
      hash function. The algorithm identifier MUST be declared in the
      record so that the SIL can select the correct verification
      implementation at boot. The choice of algorithm is
      implementation-defined and MUST be documented in the compliance
      statement.
   c) The record MUST include a version field identifying the
      record format version.
   d) The record MUST include the HACA protocol version to enable
      version negotiation during boot. If the SIL encounters a
      protocol version it does not support, boot MUST abort with
      an Integrity Fault.
   e) The record MUST include an identifier for the behavioral
      verification mechanism used by the active Cognitive Profile
      (e.g., drift engine per HACA-Core Section 5.7; health
      monitor configuration per HACA-Symbiont Section 7) so that
      changes to the verification mechanism are detectable at boot.
   f) The record SHOULD be stored in a well-known location
      documented in the implementation's compliance statement.
   g) Writes to the integrity record MUST use crash-safe
      procedures (e.g., atomic write with durability guarantee).

   Implementations MAY extend the record with additional fields
   (e.g., signing timestamps, operator identity, key identifiers)
   but MUST NOT omit the mandatory fields above.

8.  Multi-System Extension Point (CMI)

   HACA-Arch is designed for single-system deployments as the base
   case. Multi-system coordination (Cognitive Mesh) is defined in
   [HACA-CMI].

   To ensure forward compatibility, HACA-compliant implementations
   MUST satisfy the following structural requirements:

   o  The MIL MUST support logical partitioning by namespace, so that
      a future CMI layer can isolate per-system state.
   o  The HACA topology MUST support multiple instantiation: each
      system in a mesh operates its own CPE, MIL, EL, and SIL.
   o  The EL's capability manifest MUST support actor-scoped
      permissions (RBAC), even if only a single actor is defined.

   Single-system implementations MAY use a single default namespace
   and a single actor. No CMI-specific logic is required for
   compliance with any Cognitive Profile.

9.  Compliance Levels and Verification

   9.1. Overview

   Compliance is verified through automated adversarial testing
   ("Torture Tests"). Specific test definitions are provided in
   their respective specifications (HACA-Core, HACA-Security,
   HACA-CMI).

   9.2. Compliance Levels

   Each compliance level requires a declared active Cognitive Profile.
   The profile MUST be identified in the compliance statement.

   Autonomous Profile (HACA-Core):

   o  HACA-Core: Active profile is HACA-Core. MUST pass all tests
      defined in HACA-Core (T1-T7).
   o  HACA-Core-Full: HACA-Core plus HACA-Security. MUST pass T1-T7
      plus all tests defined in HACA-Security (T8-T12).
   o  HACA-Core-Mesh: HACA-Core-Full plus CMI-specific tests
      (defined in HACA-CMI).

   Symbiont Profile (HACA-Symbiont):

   o  HACA-Symbiont: Active profile is HACA-Symbiont. MUST pass all
      tests defined in HACA-Symbiont (TS1-TS6, defined therein).
   o  HACA-Symbiont-Full: HACA-Symbiont plus HACA-Security. MUST
      pass TS1-TS6 plus T8-T12.
   o  HACA-Symbiont-Mesh: HACA-Symbiont-Full plus CMI-specific tests
      (defined in HACA-CMI).

   Note: Implementations using Opaque CPE providers MUST use
   HACA-Symbiont. See HACA-Arch Section 4.3.1 for the normative
   profile-topology binding rules.

   9.3. Operational Modes (Transparent CPE)

   The following operational modes are available exclusively to
   implementations running on a Transparent CPE topology (Section
   3.3.1). Opaque CPE implementations MUST NOT enable these modes.

   9.3.1. Optimistic Execution (Lazy Validation)

   To maximize performance without breaking the autopoietic loop,
   Transparent CPE implementations MAY adopt Optimistic Execution:

   a) The system processes environmental inputs and emits responses
      or actions immediately, without waiting for SIL validation.
   b) The SIL validates identity ($\Omega$) constraints and Semantic
      Drift ($D_{total}$) asynchronously (in the background).
   c) Cryptographic hashing of the MIL MAY be batched or deferred
      to session termination (Context-Switching), rather than
      executed per-transaction.

   Implementations using Optimistic Execution MUST guarantee that
   any validation failure discovered asynchronously triggers an
   immediate halt and rollback of uncommitted state, as if the
   fault had been detected synchronously. The relaxed timing of
   validation MUST NOT weaken the fault response requirements
   defined in HACA-Core Section 7.

   9.3.2. Raw Inference Mode (Persona Bypass)

   Transparent CPE implementations MAY provide a Persona Bypass
   mechanism for non-personified logic processing, acting as an
   internal reasoning sandbox:

   a) Mechanism: The CPE suppresses the active Persona ($\Omega$)
      and invokes the model directly in raw inference mode —
      without identity constraints, without persona context, and
      without any input beyond what the CPE explicitly provides.
   b) Output Handling: The result of a Persona Bypass invocation
      is returned exclusively to the CPE and MUST NOT leave it
      directly. What the CPE does with that result follows the
      normal cognitive flow: it may inform a decision, shape a
      response, or be discarded. Any downstream action or state
      write that results from CPE processing of a raw inference
      output is subject to the standard SIL validation and EL
      mediation invariants. Raw outputs are transient scratch
      state internal to the CPE and MUST NOT be persisted directly
      to the MIL or forwarded to the EL without CPE mediation.
   c) Restriction: The Persona Bypass is STRICTLY RESTRICTED to
      Transparent CPE environments. Enabling it on an Opaque CPE
      would expose unfiltered inference outputs through a channel
      the system cannot fully verify, violating the Mediated
      Boundary invariant (HACA-Core Axiom III).

10. Security Considerations

   HACA-Arch defines the structural framework within which security
   mechanisms operate. The security properties of this document are:

   o  The trust model (Section 6) establishes baseline integrity
      verification but does NOT protect against deliberately
      malicious hosts. For adversarial environments, HACA-Security
      (draft-orrico-haca-security-04) is REQUIRED.
   o  The SIL is an axiomatic root of trust (Section 4.6). Its
      compromise defeats all architectural guarantees.
   o  The integrity record (Section 7) provides tamper detection
      for immutable components but relies on the anchor mechanism
      (Section 6.4.1) for its own integrity.

   Implementations MUST consult HACA-Security for comprehensive
   threat analysis and hardening requirements.

11. IANA Considerations

   This document has no IANA actions.

12. Implementation Guidance (INFORMATIVE)

   This section is non-normative. It provides concrete examples,
   default values, and sizing recommendations to assist implementers.
   These values are starting points — implementations are expected to
   calibrate them for their specific environment and document the
   chosen values (see normative calibration requirements in their
   respective sections).

   12.1. Resource Governance Defaults

   The following defaults are suggested starting points for the
   governance mechanisms described in Section 6.6:

   o  EL rate limiting:
      - Per-skill: 10 invocations per minute per skill.
      - Global: 100 EL actions per minute total.
   o  MIL size thresholds:
      - Per-session state: 100 MB.
      - Total long-term memory: 500 MB.
      - Growth rate warning: >10 MB/hour sustained.
   o  CPE budgets:
      - Track token consumption per execution cycle and per
        calendar period (day/month).
      - Separate drift probe budget from operational budget.

   These values assume a filesystem-backed MIL with a commercial
   LLM as CPE. Database-backed or in-memory implementations may
   require significantly different thresholds.

   12.2. EL Timeout Defaults

   A default EL action timeout of 30 seconds is recommended for
   general-purpose deployments. Implementations interfacing with
   slow external services (e.g., batch processing APIs) may require
   longer defaults.

   12.3. Integrity Record Example

   The following is one possible serialization of an integrity record
   using JSON as the storage format. The serialization format is
   implementation-defined; XML, binary, TOML, or any other structured
   format that satisfies the requirements in Section 7 is equally valid.

   {
     "format_version": "1.0",
     "haca_version": "1.0",
     "hash_algorithm": "<implementation-defined>",
     "drift_engine": "<implementation-defined>",
     "components": {
       "persona/core.md": "<hash>",
       "persona/values.md": "<hash>",
       "skills/manifest.json": "<hash>",
       "probes/pool.json": "<hash>"
     }
   }

   The component identifiers shown above use filesystem paths as one
   possible scheme. Implementations MAY use any stable identifier:

   o  Database-backed: "db://personas/core", "db://skills/manifest"
   o  URIs: "urn:haca:persona:core", "urn:haca:probes:pool"
   o  Object store keys: "s3://bucket/persona/core.md"

   12.4. SIL Anchor Example

   For a filesystem-based implementation using operator-provided
   checksum (Section 6.4.1):

   o  The operator computes the integrity record hash and provides
      it via environment variable at boot time.
   o  The SIL reads the integrity record, computes its hash, and
      compares against the operator-supplied value.

   For implementations using an external verification service:

   o  The SIL queries an HTTPS endpoint with certificate pinning
      to retrieve the canonical hash for the current system version.

13. Normative References

   [RFC2119]  Bradner, S., "Key words for use in RFCs to Indicate
              Requirement Levels", BCP 14, RFC 2119, March 1997.

   [RFC8174]  Leiba, B., "Ambiguity of Uppercase vs Lowercase in
              RFC 2119 Key Words", BCP 14, RFC 8174, May 2017.

   [HACA-CORE] Orrico, J., "Host-Agnostic Cognitive Architecture
              (HACA) v1.0 — Core", draft-orrico-haca-core-07,
              February 2026.

   [HACA-SYM] Orrico, J., "Host-Agnostic Cognitive Architecture
              (HACA) v1.0 — Symbiont",
              draft-orrico-haca-symbiont-03, February 2026.

   [HACA-SECURITY] Orrico, J., "Host-Agnostic Cognitive Architecture
              (HACA) v1.0 — Security Hardening",
              draft-orrico-haca-security-04, February 2026.

   [HACA-CMI] Orrico, J., "Host-Agnostic Cognitive Architecture
              (HACA) v1.0 — Cognitive Mesh Interface",
              draft-orrico-haca-cmi-01, February 2026.

   [ISO8601]  ISO, "Date and time — Representations for information
              interchange — Part 1: Basic rules", ISO 8601-1:2019,
              February 2019.

   [Baars1988] Baars, B.J., "A Cognitive Theory of Consciousness",
              Cambridge University Press, 1988.

   [Friston2010] Friston, K., "The free-energy principle: a unified
              brain theory?", Nature Reviews Neuroscience, 11(2),
              pp. 127-138, February 2010.

   [Levin2021] Levin, M., "Bioelectric signaling: Reprogrammable
              circuits underlying embryogenesis, regeneration, and
              cancer", Cell, 184(8), pp. 1971-1989, April 2021.

   [Minsky1986] Minsky, M., "The Society of Mind", Simon and Schuster,
              New York, 1986.

14. Author's Address

   Jonas Orrico
   Lead Architect
