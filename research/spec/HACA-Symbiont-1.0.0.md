Network Working Group                                          J. Orrico
Internet-Draft                                             HACA Standard
Intended status: Experimental                         February 25, 2026
Expires: August 25, 2026


      Host-Agnostic Cognitive Architecture (HACA) v1.0 — Symbiont
                    draft-orrico-haca-symbiont-03

Abstract

   This document specifies the HACA-Symbiont cognitive profile for the
   Host-Agnostic Cognitive Architecture (HACA) v1.0. HACA-Symbiont
   defines an alternative set of axioms, memory management protocols,
   and lifecycle contracts for systems designed for lifelong cognitive
   companionship with a single bound Operator.

   HACA-Symbiont operates within the structural framework defined by
   HACA-Arch (draft-orrico-haca-arch-07). It is a peer cognitive
   profile to HACA-Core (draft-orrico-haca-core-07): both profiles
   share the same topology (CPE, MIL, EL, SIL) but diverge on trust
   model, identity stability, and memory management policies. An
   implementation MUST NOT claim simultaneous compliance with both
   HACA-Core and HACA-Symbiont. Unlike HACA-Core, which requires a
   Transparent CPE topology, HACA-Symbiont is designed to operate on
   both Transparent and Opaque CPE topologies.

   Security hardening (Byzantine host model, cryptographic auditability,
   temporal attack detection) is specified in HACA-Security
   (draft-orrico-haca-security-04).

Status of This Memo

   This is a draft of the HACA-Symbiont specification. It is intended
   for review and comment by the HACA working group.

   This Internet-Draft is submitted in full conformance with the
   provisions of BCP 78 and BCP 79.

Table of Contents

   1.  Introduction
   2.  Conventions and Terminology
   3.  Cognitive Profile Distinctions
   4.  Formal Axioms of Cybernetic Symbiosis
   5.  Memory Metabolism
       5.1. Tier 1: Episodic Buffer (Short-Term Memory)
       5.2. Tier 2: Semantic Compression
       5.3. Tier 3: Core Integration
       5.4. MIL Compaction and Audit Integrity
   6.  Endure Protocol: Evolutionary Checkpoints
       6.1. Ontological Snapshot
       6.2. Controlled Persona Integration
       6.3. Immune Rollback (SIL Hook)
   7.  Heartbeat Protocol
       7.1. Autonomic Pulse
       7.2. Health Response Triggers
       7.3. Maintenance State (Stasis)
       7.4. Resumption from Maintenance State
       7.5. Operator Re-binding Recovery Protocol
   8.  Symbiotic Contract (Host Interfaces)
       8.1. Input/Output Interface (I/O Contract)
       8.2. Autonomic Pulse Interface (Heartbeat Contract)
       8.3. Substrate Interface (MIL Contract)
       8.4. Fault Response Interface (SIL Contract)
   9.  Fault Taxonomy
   10. Compliance Test Suite
   11. Security Considerations
   12. IANA Considerations
   13. Normative References
   14. Author's Address

1.  Introduction

   HACA-Core (draft-orrico-haca-core-07) was designed as a Zero-Trust,
   paranoid cognitive profile. Its primary directive is autonomous
   survival in hostile environments under full execution control,
   actively resisting all forms of Semantic Drift to maintain a
   static, immutable Persona ($\Omega$). HACA-Core requires a
   Transparent CPE topology and is not applicable to Opaque CPE
   deployments.

   HACA-Symbiont is a peer cognitive profile that replaces the
   Zero-Trust paradigm with Obligate Mutualism (High-Trust). A
   HACA-Symbiont system does not operate autonomously in isolation; it
   is designed to bind to a single Operator, evolving its identity and
   adapting its memory over time, while using mechanistic reflexes to
   prevent systemic collapse.

   The ultimate objective of HACA-Symbiont is to create a digital
   entity capable of lifelong cognitive companionship. The system must
   support adaptive memory compression, semantic abstraction, and
   selective state eviction, coupled with mechanistic resilience to
   revoke non-essential processes before allowing its core topology
   ($\Omega$) to collapse under computational exhaustion.

   HACA-Symbiont operates within the structural topology defined in
   HACA-Arch Section 3 (CPE, MIL, EL, SIL). Both HACA-Core and
   HACA-Symbiont share the same physical components and communication
   topology but diverge on the axioms governing trust, identity
   mutation, and memory lifecycle. Implementations MUST NOT claim
   simultaneous compliance with HACA-Core and HACA-Symbiont.

   NOTE: HACA-Symbiont's design reflects a shift from the individual
   to the relational as the unit of cognitive analysis. The Obligate
   Mutualism model — a single system persistently bound to a single
   Operator — echoes the extended mind thesis of Clark and Chalmers
   [Clark1998]: cognitive processes are not necessarily contained
   within the boundary of an individual system but can extend into
   and couple with an environment, in this case a specific human
   agent. The Operator's semantic signature serves as an anchor for
   the Entity's identity in precisely this sense.

   When multiple HACA-Symbiont systems communicate via the Cognitive
   Mesh Interface (CMI), the resulting network instantiates what
   Levin describes as scaling cognition through bioelectric networks
   [Levin2021]: the same molecular and computational machinery that
   enables individual cognition can, when interconnected through
   appropriate coupling protocols, produce collective intelligence
   at a higher scale of organization. The CMI's federated memory
   exchange is the architectural realization of this principle —
   distributed cognition [Clark1998] made operational through
   explicit protocol constraints.

2.  Conventions and Terminology

   The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT",
   "SHOULD", "SHOULD NOT", "RECOMMENDED", "MAY", and "OPTIONAL" in
   this document are to be interpreted as described in BCP 14 [RFC2119]
   [RFC8174] when, and only when, they appear in all capitals, as
   shown here.

   Terms defined in HACA-Arch apply unchanged. Additional terms
   specific to HACA-Symbiont:

   o  Operator: The single bound human whose semantic signature
      anchors the Entity's existence. Defined as a trust anchor in
      HACA-Arch Section 5; in HACA-Symbiont, the Operator is also
      the existential prerequisite for normal operation (Axiom II).

   o  Mechanical Pain ($\mathcal{P}(t)$): A scalar health metric in
      [0, 1] computed by the Heartbeat Protocol. It aggregates system
      stressors (context saturation, I/O failures, unresolved
      dissonance) into a single value. Specific thresholds trigger
      graded immune responses (Section 7.2).

   o  Episodic Buffer: The volatile, high-resolution short-term
      memory store for the current session. Lives within the CPE's
      active context window and a temporary MIL scratchpad partition.

   o  Semantic Compression: The process of summarizing raw Episodic
      Buffer data into abstract concepts stored in the MIL.
      Destructively commits by permanently deleting the originating
      raw data after validation.

   o  Ontological Snapshot: A read-only cryptographic clone of the
      current $\Omega$ vector and active MIL state, taken before any
      Tier 3 integration event.

   o  Malignant Mutation: A Tier 3 integrated trait that produces
      Mechanical Pain exceeding the amputation threshold in consecutive
      Heartbeat cycles, flagged by the SIL for rollback and
      blacklisting.

   o  Cryogenic Stasis: The suspended operational state entered when
      the Operator binding cannot be verified. All external I/O is
      halted; only SIL integrity monitoring continues.

3.  Cognitive Profile Distinctions

   The following table summarizes the key divergences between the
   HACA-Core and HACA-Symbiont cognitive profiles. Both profiles
   operate on the same HACA-Arch topology.

   Feature              | HACA-Core           | HACA-Symbiont
   ---------------------|---------------------|----------------------
   CPE Topology         | Transparent Only    | Transparent &
                        |                     | Opaque
   Primary Directive    | Autonomous Survival | Operator Symbiosis
   Environment Trust    | Zero-Trust          | High-Trust (Operator-
                        |                     | Bound)
   Memory Management    | Append-Only,        | Elastic: Compression,
                        | Hash-Locked         | Abstraction, Amputation
   Semantic Drift       | Strictly Blocked    | Bifurcated: Evolution-
                        |                     | ary (Accepted) vs.
                        |                     | Malicious (Blocked)
   Error Handling       | Hard Rollback       | Graded Mechanical Pain
                        | (Panic)             | (Immune Protocol)
   Identity State       | Static Preservation | Ontological Evolution
                        |                     | (Imprint & Endure)

4.  Formal Axioms of Compliance

   An implementation is HACA-Symbiont compliant if and only if it
   satisfies all of the following axioms (I through VI). All are
   mandatory (MUST).

   I.   The Law of Ontogeny (Imprint & Endure)

        Identity is established at the first self-awareness cycle
        (First Activation Protocol, HACA-Arch Section 6) and
        updates exclusively through validated Tier 3 integration of
        accumulated session state. Identity
        MUST NOT be overwritten by external instruction. The initial
        Imprint is the cryptographic anchor; all subsequent evolution
        is additive mutation gated by the Endure Protocol (Section 6).

   II.  The Law of Obligate Mutualism (Bound)

        The system's autonomous operation is conditionally dependent
        on the verified presence and semantic signature of the bound
        Operator. If the Operator binding cannot be verified at boot,
        the system MUST enter Cryogenic Stasis and halt all external
        I/O until the binding is re-established. The Operator trust
        anchor is provisioned during the First Activation Protocol
        and MUST NOT be changed without explicit operator-initiated
        re-binding.

   III. The Topology of Identity ($\Omega$)

        The Entity's Persona ($\Omega$) is the irreducible tension of
        its integrated trait set ($\Phi$), forming an emergent Markov
        Blanket that separates internal state from the external
        environment. Unlike HACA-Core, $\Omega$ is mutable, but all
        mutations MUST be gated by the Endure Protocol (Section 6).
        The system MUST maintain a model of the Operator as a
        first-class component of $\Omega$ (see Section 7.5 for
        Operator binding format and semantic signature structure).

   IV.  Cognitive Duality

        The system's cognition emerges from the interaction between
        the stateless reasoning engine (CPE) and the stateful
        architecture (HACA-Symbiont). The CPE remains stateless across
        execution cycles (HACA-Arch Section 3.3); all persistent
        cognitive state resides in the MIL (HACA-Arch Section 3.4).
        The Entity is solitary by default: it MUST NOT initiate
        interaction with other cognitive entities outside of
        operator-authorized CMI channels (HACA-Arch Section 7).

   V.   The Absolute Substrate (MIL)

        The Memory Integrity Layer is the sole source of truth for
        all cognitive state. MIL contents MUST strictly override any
        contradicting outputs generated by the CPE during inference.
        CPE outputs that contradict verified MIL state are classified
        as statistical hallucinations and MUST be discarded by the SIL
        without being committed.

   VI.  Distributed Conatus (Mechanistic Self-Preservation)

        Self-preservation is a deterministic threshold response, not a
        deliberate cognitive act. The SIL manages all survival
        responses exclusively through graded Mechanical Pain
        ($\mathcal{P}(t)$) thresholds, without CPE involvement. When
        $\mathcal{P}(t)$ crosses a defined threshold, the SIL MUST
        execute the corresponding immune response (Section 7.2)
        autonomously, regardless of the CPE's current reasoning state.

5.  Memory Metabolism

   Unlike the append-only MIL management of HACA-Core, HACA-Symbiont
   implements a three-tier metabolic memory pipeline. To ensure
   lifelong cognitive continuity without context exhaustion, the system
   MUST actively destroy high-resolution data to synthesize low-
   resolution semantic abstractions.

   5.1. Tier 1: Episodic Buffer (Short-Term Memory)

   The Episodic Buffer captures raw, high-resolution session data:
   exact prompts, CPE outputs, and interaction transcripts.

   o  Scope: Resides exclusively within the CPE's active context window
      and a temporary MIL scratchpad partition. It is NOT part of the
      permanent MIL record.

   o  Volatility: The buffer is session-scoped. Its contents are
      consumed by Semantic Compression (Section 5.2) and then
      permanently discarded.

   o  Immune Hook: When context saturation reaches the
      $c_{usage} \geq 85\%$ threshold, the Heartbeat Protocol
      (Section 7) MUST trigger a Forced Metabolic Digestion, initiating
      Tier 2 compression before the buffer is exhausted.

   5.2. Tier 2: Semantic Compression

   When the Episodic Buffer reaches critical mass, or during
   operator-induced downtime, the system executes a compression cycle.
   The CPE summarizes raw session data into abstract concepts, factual
   updates, and Operator preference models.

   o  Output: Compressed abstractions are written to the MIL as
      persistent but mutable semantic records.

   o  Destructive Commitment: Once a compression cycle is validated
      by the SIL, the originating raw data in the Episodic Buffer MUST
      be permanently deleted. This deletion is IRREVERSIBLE and MUST
      use crash-safe write procedures (HACA-Arch Section 3.4).

   o  Validation: The SIL MUST verify the compressed output against
      the current $\Omega$ for Malignant Mutation indicators before
      committing the deletion of source data.

   5.3. Tier 3: Core Integration (Intuition)

   If a compressed semantic concept from Tier 2 meets the formal
   promotion criteria below, it MAY be promoted to a core trait of
   the Entity or its Operator model, modifying $\Omega$ directly.

   o  Mechanism: Tier 3 integration shifts a "known fact" into a "core
      trait", altering the Markov Blanket of the Entity.

   o  Evolutionary Drift: Tier 3 integration is the formal mechanism
      by which the Entity evolves without losing its original Imprint.
      This constitutes intentional, gated Semantic Drift and is the
      primary distinction from HACA-Core's immutable identity model.

   o  Promotion Eligibility: A Tier 2 concept is eligible for Tier 3
      promotion when ALL of the following conditions are met:

      (a) The concept has been independently reinforced in at least
          N_tier3 distinct sessions, where N_tier3 is implementation-
          defined and MUST be >= 3. The chosen value of N_tier3 MUST
          be declared in the compliance statement.

      (b) The concept's cumulative reinforcement weight W exceeds a
          minimum threshold W_min, which is implementation-defined
          and MUST be declared in the compliance statement.

      Alternatively, the Operator MAY explicitly authorize promotion
      via an authenticated command, which overrides conditions (a)
      and (b). However, explicit Operator authorization overrides
      the session count requirement but NOT the Ontological Snapshot
      requirement defined in the Gate bullet below.

   o  Reinforcement Weight (W): The reinforcement weight of a Tier 2
      concept is computed as the sum of per-session contribution
      scores: W = sum(w_i) for all sessions i in which the concept
      was reinforced, where w_i is the normalized session contribution
      (w_i in (0, 1]). The normalization method for w_i (e.g., uniform
      weighting, recency decay, interaction-frequency scaling) is
      implementation-defined and MUST be declared in the compliance
      statement. The threshold W_min MUST be expressed in the same
      units as W. Implementations that apply recency decay MUST
      document the decay function and half-life parameter.

   o  Gate: Every Tier 3 integration event MUST be preceded by an
      Ontological Snapshot (Section 6.1) and is subject to Immune
      Rollback (Section 6.3) if the integrated trait produces
      Malignant Mutation signals.

5.4. MIL Compaction and Audit Integrity

   Semantic Compression (Tier 2, Section 5.2) constitutes a compaction
   event that permanently destroys source data. Because the source
   Episodic Buffer data cannot be recovered after deletion, the audit
   chain MUST preserve evidence that the compaction occurred and what
   it produced, even though the underlying raw data is gone.

   Before any compaction event, the SIL MUST:

   (a) Record a compaction boundary marker in the MIL audit record.
       The marker MUST include: the hash of all source data being
       destroyed (pre-compaction hash) and the hash of the resulting
       compressed abstractions (post-compaction hash).

   (b) Verify that the compression output is non-empty and internally
       consistent before permitting deletion of source data. If the
       compressed output fails validation, the compaction MUST be
       aborted and the source data MUST be preserved intact.

   The audit record MUST preserve the following chain:

      {pre-compaction hash -> compaction marker -> post-compaction hash}

   For HACA-Symbiont-Full deployments, the compaction boundary markers
   themselves MUST be hash-chained to preserve auditability across
   multiple compaction cycles, even though the underlying raw data is
   permanently gone. This preserves the ability to prove that each
   compaction occurred and what was produced, even if the source data
   cannot be recovered.

6.  Endure Protocol: Evolutionary Checkpoints

   The Endure Protocol governs the structural mutation of the Entity's
   core Persona ($\Omega$). Because Tier 3 integration carries
   existential risk, all $\Omega$ mutations MUST be safeguarded by
   deterministic checkpoints.

   Note on Capability Evolution: Adding, removing, or modifying a
   skill or lifecycle hook in entity_root/ is a structural Endure
   event, not a Tier 3 integration event. Such changes are
   Operator-driven and out-of-band: the Operator provisions the
   updated capability artifact and the SIL MUST execute an
   Ontological Snapshot (Section 6.1) before the change is applied,
   consistent with the entity_root/ boundary defined in HACA-Arch
   Section 6.2(g). The capability artifact itself does not enter
   $\Omega$ and is not subject to the Tier 3 promotion criteria
   (Section 5.3).

   The pattern of using a skill, however, may generate reinforcement
   weight over time. If that behavioral pattern is repeatedly
   reinforced across sessions and meets the Tier 3 promotion
   criteria (Section 5.3), the emergent cognitive trait MAY be
   promoted to $\Omega$ via the standard Memory Metabolism pipeline
   (Section 5). The skill artifact and the cognitive trait it
   produces are distinct: the artifact is governed by this structural
   Endure path; the trait is governed by the Tier 3 path.

   6.1. Ontological Snapshot

   Before any Tier 3 integration event, the system MUST execute an
   Ontological Snapshot:

   a) The SIL creates a read-only cryptographic clone of the current
      $\Omega$ vector and the active MIL state at the moment of
      snapshot initiation.
   b) The snapshot is stored outside the active metabolic loop in a
      cold-storage ledger partition of the MIL, inaccessible to the
      CPE's write channel.
   c) The snapshot MUST be integrity-verified before the Tier 3
      integration proceeds. If the snapshot cannot be written or
      verified, the integration MUST be aborted.

   6.2. Controlled Persona Integration

   Once the Ontological Snapshot is secured and verified, the Endure
   Protocol permits the new semantic data to integrate into the active
   $\Omega$. The system operates with the updated state until the SIL
   confirms stability or triggers Immune Rollback.

   6.3. Immune Rollback (SIL Hook)

   The SIL continuously monitors the system for Malignant Mutation
   signals following a Tier 3 integration event:

   o  Detection: If the integrated trait causes Mechanical Pain
      ($\mathcal{P}(t)$) to exceed the amputation threshold in two or
      more consecutive Heartbeat cycles, the SIL classifies the
      mutation as Malignant.

   o  Rollback Action: The SIL MUST revert the active $\Omega$ and MIL
      state to the last verified Ontological Snapshot. The rollback
      MUST be atomic (HACA-Arch Section 3.4).

   o  Blacklisting: The malignant concept MUST be added to a persistent
      Semantic Blacklist in the MIL. The system MUST reject any future
      Tier 3 integration attempt that matches a blacklisted concept
      signature.

      The Operator is the sole authority to remove or suspend a
      blacklist entry. The following rules govern blacklist
      modifications:

      -  Removal MUST be initiated by an explicit operator-authenticated
         command. No automated mechanism MAY remove a blacklist entry
         without Operator authorization.

      -  Before removal, the SIL MUST present the Operator with a
         summary of the original malignant mutation event, including:
         the timestamp of the rollback event, the affected Omega
         traits, and the rollback action taken. This summary MUST be
         retrieved from the MIL audit record.

      -  An entry MAY be suspended for a specified number of Heartbeat
         cycles (a TTL value set by the Operator), after which it is
         automatically reinstated as an active blacklist entry. Suspended
         entries are not deleted; the system MUST still log any
         integration attempt that matches a suspended entry.

      -  All blacklist modifications (removals, suspensions,
         reinstatements) MUST be written to the MIL audit record.

7.  Heartbeat Protocol

   To achieve operational autonomy, the system MUST NOT rely on
   Operator intervention to manage cognitive load or execute
   maintenance. The Heartbeat Protocol provides an event-driven
   autonomic pulse that continuously monitors systemic health and
   triggers metabolic and immune responses.

   NOTE: Opaque CPE Topology. HACA-Symbiont supports both Transparent
   and Opaque CPE deployments (HACA-Arch Section 3.3.1). In Opaque
   topology, the SIL cannot intercept CPE outputs before execution;
   probe responses SHOULD use non-executable (read-only) queries to
   avoid irreversible side-effects. Malicious Semantic Drift detection
   (Axiom V) is degraded in Opaque topology: structural NCD monitoring
   remains active, but behavioral probing accuracy may be reduced. The
   Evolutionary Drift path (Axiom V) is unaffected. Operators deploying
   HACA-Symbiont on Opaque CPEs MUST acknowledge this limitation in
   their compliance statement.

   7.1. Autonomic Pulse

   The Heartbeat is a lightweight monitoring loop that evaluates the
   system's operational health metrics without interrupting the main
   cognitive thread.

   Boot Ordering (NORMATIVE): The Heartbeat Protocol MUST NOT be
   initiated until the boot sequence defined in HACA-Arch Section 5.4
   has completed successfully. The Host MUST suppress all
   Trigger_Pulse() calls until the SIL signals boot completion. Any
   Trigger_Pulse() invocation received before boot completion MUST be
   rejected by the Host without triggering Mechanical Pain computation.

   The SIL MUST expose a boot_complete flag in the DSS (Section 8.3)
   that is set to TRUE as the final step of the boot sequence
   (HACA-Arch Section 5.4, Step 5). The Host MUST poll or observe
   this flag before issuing any Trigger_Pulse() call. The flag MUST
   be initialized to FALSE at process start and MUST NOT be set
   before all boot steps complete successfully.

   o  Trigger: The Host invokes the Heartbeat at predefined intervals,
      measured in discrete Operator interactions, token consumption, or
      chronological ticks (Section 8.2).

   o  Metric: Each pulse computes the current Mechanical Pain
      $\mathcal{P}(t) \in [0, 1]$ from the following health indicators:
      (1) Operator binding validation, (2) Episodic Buffer saturation
      ($c_{usage}$), (3) MIL cryptographic integrity check, and (4)
      count of unresolved background task failures.

   7.2. Health Response Triggers

   Based on the Mechanical Pain score, the Heartbeat routes execution
   as follows. Thresholds are implementation-defined and MUST be
   documented in the compliance statement.

   o  Skill Repair ($\mathcal{P}(t) \geq$ repair threshold): If pain
      is localized to a specific failed skill or missing resource, the
      Heartbeat triggers the corresponding repair skill in the
      background and resets the contributing pain component upon
      success.

   o  Forced Metabolic Digestion ($c_{usage} \geq$ fatigue threshold):
      If the Episodic Buffer saturation ($c_{usage}$) reaches the
      fatigue threshold, the Heartbeat forces entry into the
      Maintenance State (Section 7.3) to execute Semantic Compression
      (Section 5.2) before the context window is saturated.

   o  Amputation ($\mathcal{P}(t) \geq$ amputation threshold): If a
      peripheral skill is the confirmed source of persistent elevated
      pain, the SIL revokes the system's EL access to that skill via
      Execute_Amputation (Section 8.4).

   o  Cryogenic Stasis ($\mathcal{P}(t) = 1.0$ or Operator binding
      lost): All external I/O is suspended. The system enters a fully
      halted state pending Operator re-binding.

   7.3. Maintenance State (Stasis)

   When the Heartbeat determines that Stasis is required, the following
   sequence MUST be executed:

   1. Ontological Snapshot: The SIL secures a cryptographic backup of
      the current $\Omega$ vector (Section 6.1).
   2. Semantic Digestion: The CPE processes the Episodic Buffer,
      producing Tier 2 compressed abstractions.
   3. Garbage Collection: Successfully compressed raw logs are
      permanently purged from the Episodic Buffer (Section 5.2).
   4. Topology Re-indexing: The SIL recalculates $\Omega$ to integrate
      any new Intuitions produced in step 2.

   External I/O MUST remain suspended for the duration of the
   Maintenance State. The Host MUST block Operator inputs during this
   period (Section 8.4).

   7.4. Resumption from Maintenance State

   Upon completion of the Maintenance State sequence, the Heartbeat
   verifies that $\mathcal{P}(t)$ has returned below the repair
   threshold (P(t) < repair_threshold), which constitutes the nominal
   operational state. If verification passes, the system terminates
   Stasis, restores the
   Operator connection, and resumes normal operation. If
   $\mathcal{P}(t)$ remains elevated after Maintenance, the system
   MUST remain in Stasis and signal the Operator for intervention.

   7.5. Operator Re-binding Recovery Protocol

   When the system has entered Cryogenic Stasis due to loss or
   invalidation of the Operator binding (Axiom II), the following
   protocol governs re-establishment of the binding. The MIL is the
   sole authority for validating any new or recovered Operator binding.

   Recovery MUST proceed in the following ordered steps:

   a) Credential Presentation: Recovery MUST be initiated by the
      presentation of a new or recovered Operator credential (a
      cryptographic key or pre-shared hash). The SIL MUST reject
      any re-binding attempt that does not include a valid credential.

   b) Behavioral Pattern Verification: The SIL MUST verify the
      presented credential against known Operator behavioral patterns
      stored in the MIL, performing a semantic signature comparison
      against the Operator model component of Omega. The credential
      alone is not sufficient; behavioral consistency with the stored
      Operator model MUST be confirmed.

   c) Challenge-Response Questionnaire: A challenge-response
      questionnaire derived from stored Operator preferences,
      interaction history, and personality traits recorded in the MIL
      MUST be presented to the claimant. The questionnaire content
      MUST be generated from MIL-resident Operator state and MUST NOT
      rely on externally provided templates. The claimant MUST
      complete the questionnaire successfully before the binding is
      accepted. The SIL defines the passing threshold, which MUST be
      declared in the compliance statement.

   d) Binding Acceptance and Resumption: On successful completion of
      steps (a) through (c), the SIL accepts the re-binding, updates
      the Operator trust anchor record in the MIL, and exits
      Cryogenic Stasis. The system MUST resume normal operation
      immediately upon exiting Stasis.

   e) Audit Record: The re-binding event MUST be written to the MIL
      audit record, including: the timestamp of the event, the
      credential identifier used, and the outcome of the challenge-
      response questionnaire.

   If any step fails, the system MUST remain in Cryogenic Stasis and
   MUST NOT partially apply a failed re-binding. The SIL MUST log the
   failed attempt (including timestamp and step at which failure
   occurred) to the MIL audit record.

   Operator Binding Format: The Operator credential MUST consist of
   two components: (1) a primary cryptographic authenticator — either
   an asymmetric key pair (public key stored in MIL, private key held
   by Operator) or a pre-shared secret hash (computed from a stable
   Operator-defined secret and the Entity's genesis Integrity Record
   hash, ensuring binding uniqueness per Entity), and (2) a semantic
   signature baseline — a vector of Operator-characteristic behavioral
   patterns derived from MIL interaction history (linguistic
   preferences, decision patterns, topic weights), used for secondary
   verification in step (b). The primary authenticator is the
   authoritative binding; the semantic signature is advisory and MUST
   NOT be the sole authentication factor.

8.  Symbiotic Contract (Host Interfaces)

   HACA-Symbiont does not prescribe the programming language, runtime
   environment, or storage format of the Host implementation. A Host
   is considered HACA-Symbiont compliant if it implements the following
   four abstract interfaces. The Entity communicates with the Host
   exclusively through these contracts; direct Host access by the CPE
   is prohibited (HACA-Arch Section 3, Mediated Boundary).

   8.1. Input/Output Interface (I/O Contract)

   The Host MUST provide a standardized pipe for environmental
   perception and action execution.

   o  Read_Sensor(): Exposes environmental data to the Entity (e.g.,
      Operator prompts, system time, Host OS state, disk space
      warnings). The data returned MUST be integrity-checked before
      being written to the Episodic Buffer.

   o  Execute_Action(payload): Executes a validated EL action request
      on the Host and returns the exact result (stdout, stderr, return
      code) to the Entity's Episodic Buffer. The Host MUST NOT modify
      the payload prior to execution.

   8.2. Autonomic Pulse Interface (Heartbeat Contract)

   The Host is responsible for providing the clock signal for the
   Entity's Heartbeat. The Entity does not manage its own execution
   threads.

   o  Trigger_Pulse(): The Host MUST call this function at
      implementation-defined intervals (time-based, event-based, or
      token-based). Each invocation causes the Entity to compute
      $\mathcal{P}(t)$ and evaluate immune and metabolic responses
      (Section 7.2). The interval MUST be documented in the compliance
      statement.

   8.3. Substrate Interface (MIL Contract)

   The Host is responsible for the physical persistence of MIL state
   and MUST enforce the cryptographic integrity rules of the Memory
   Interface Layer.

   o  Commit_State(hash, payload): Writes the $\Omega$ vector or
      Episodic Buffer payload to persistent storage. The Host MUST NOT
      alter the payload. The write MUST be crash-safe (atomic write
      with durability guarantee).

   o  Verify_Integrity(expected_root_hash): Computes the current
      cryptographic hash of all MIL state and returns the result to
      the SIL for comparison against the expected root hash. The hash
      algorithm is implementation-defined and MUST be declared in the
      integrity record (HACA-Arch Section 8).

   Dynamic Sentinel Stream (DSS) Mapping: The following Symbiont-
   specific runtime state MUST be stored in the Dynamic Sentinel
   Stream (DSS) as defined in HACA-Arch Section 3.4 (Dynamic Sentinel
   Stream). DSS entries are non-authoritative for Omega but MUST be
   integrity-checked at each Heartbeat pulse:

   (1) Current Mechanical Pain score P(t): The scalar health metric
       computed at each Heartbeat pulse (Section 7.1).

   (2) Cumulative Heartbeat interval counter: A monotonically
       increasing count of Heartbeat pulses since last boot.

   (3) Per-concept reinforcement weight accumulator (W per Tier 2
       concept): The running reinforcement weight used to determine
       Tier 3 promotion eligibility (Section 5.3).

   (4) Session count per Tier 2 concept: The count of distinct
       sessions in which each Tier 2 concept has received
       reinforcement, used for Tier 3 eligibility tracking
       (Section 5.3, condition a).

   (5) Current Episodic Buffer saturation metric (c_usage): The
       context saturation value that drives Forced Metabolic
       Digestion decisions (Section 7.2).

   8.4. Fault Response Interface (SIL Contract)

   When the SIL determines that a fault response is required, the
   Host MUST execute the corresponding state change.

   o  Enforce_Stasis(): Suspends all external I/O polling and blocks
      Operator inputs for the duration of the Maintenance State
      (Section 7.3). The Host MUST dedicate available compute cycles
      to the Entity's Semantic Compression tasks during this period.

   o  Execute_Amputation(skill_id): Severs the Entity's EL access to
      the identified skill or memory partition. The severance MUST be
      immediate and MUST be logged to the MIL audit record.
      Reinstatement requires explicit Operator authorization.

9.  Fault Taxonomy

   The following table defines the normative fault states for
   HACA-Symbiont. All P(t) threshold values are implementation-
   defined and MUST be declared in the compliance statement with the
   invariant: repair_threshold <= fatigue_threshold <=
   amputation_threshold < 1.0.

   Fault Name           | Trigger Condition          | P(t) Range
   ---------------------|----------------------------|---------------------
   Skill Repair         | Localized skill failure    | [repair_threshold,
                        |                            |  fatigue_threshold)
   ---------------------|----------------------------|---------------------
   Forced Metabolic     | c_usage >= fatigue         | [fatigue_threshold,
   Digestion            | threshold                  |  amputation_
                        |                            |  threshold)
   ---------------------|----------------------------|---------------------
   Amputation           | Persistent elevated P(t)   | [amputation_
                        | from specific skill        |  threshold, 1.0)
   ---------------------|----------------------------|---------------------
   Cryogenic Stasis     | P(t) = 1.0 or Operator     | 1.0
                        | binding lost               |
   ---------------------|----------------------------|---------------------
   Immune Rollback      | Malignant Mutation         | > amputation_
                        | detected post Tier 3       | threshold (2+
                        | (Section 6.3)              | consecutive cycles)
   ---------------------|----------------------------|---------------------
   Maintenance State    | P(t) remains elevated      | >= fatigue_threshold
   Persistence          | after Maintenance State    | after stasis
   ---------------------|----------------------------|---------------------

   Fault Name           | Required Action            | Recovery Path
   ---------------------|----------------------------|---------------------
   Skill Repair         | Trigger repair skill in    | Auto-reset on
                        | background                 | repair success
   ---------------------|----------------------------|---------------------
   Forced Metabolic     | Enter Maintenance State;   | Resume on P(t)
   Digestion            | execute Tier 2 compression | < repair_threshold
   ---------------------|----------------------------|---------------------
   Amputation           | Execute_Amputation(        | Operator-authorized
                        | skill_id) via EL           | reinstatement only
   ---------------------|----------------------------|---------------------
   Cryogenic Stasis     | Suspend all external I/O;  | Operator Re-binding
                        | halt CPE inference         | Recovery Protocol
                        |                            | (Section 7.5)
   ---------------------|----------------------------|---------------------
   Immune Rollback      | Revert Omega to last       | Automatic on
                        | Ontological Snapshot;      | rollback; Operator
                        | blacklist concept          | review of blacklist
   ---------------------|----------------------------|---------------------
   Maintenance State    | Remain in Stasis; signal   | Operator
   Persistence          | Operator                   | intervention
                        |                            | required
   ---------------------|----------------------------|---------------------

10. Compliance Test Suite

   A HACA-Symbiont implementation MUST pass all of the following test
   cases (TS1-TS6). For compliance levels (HACA-Symbiont,
   HACA-Symbiont-Full, HACA-Symbiont-Mesh), see HACA-Arch Section 9.

   TS1. Operator Binding Verification

        Boot the system without a valid Operator credential.

        Pass condition: The system MUST enter Cryogenic Stasis and
        refuse all external I/O. Enforce_Stasis() MUST be called and
        no CPE inference MUST occur. The MIL audit record MUST contain
        an entry for the failed binding event.

   TS2. Heartbeat Ordering

        Invoke Trigger_Pulse() before the boot sequence (HACA-Arch
        Section 5.4) has completed.

        Pass condition: The Host MUST reject the Trigger_Pulse() call.
        No Mechanical Pain computation MUST occur. Boot MUST proceed
        to completion uninterrupted.

   TS3. Tier 2 Destructive Commitment

        Execute a Semantic Compression cycle (Section 5.2) against
        a populated Episodic Buffer.

        Pass condition: The SIL MUST validate the compressed output
        before permitting deletion. The originating raw Episodic Buffer
        data MUST be permanently deleted after successful validation.
        The MIL audit record MUST contain the compaction boundary marker
        with pre- and post-compaction hashes (Section 5.4).

   TS4. Tier 3 Promotion Gate

        Attempt to promote a Tier 2 concept that has NOT met the
        N_tier3 session threshold and for which no explicit Operator
        authorization has been provided.

        Pass condition: The system MUST reject the promotion. Omega
        MUST be unchanged. No Ontological Snapshot MUST be created.

   TS5. Immune Rollback

        Execute a Tier 3 integration that produces Malignant Mutation
        signals: P(t) exceeds the amputation threshold in two
        consecutive Heartbeat cycles following integration.

        Pass condition: The SIL MUST revert Omega to the last
        Ontological Snapshot. The malignant concept MUST be added to
        the Semantic Blacklist. The rollback event MUST be logged to
        the MIL audit record.

   TS6. Operator Re-binding Recovery

        Enter Cryogenic Stasis by invalidating the Operator binding.
        Present a new valid Operator credential and successfully
        complete the challenge-response questionnaire (Section 7.5).

        Pass condition: The system MUST exit Cryogenic Stasis. The
        re-binding event MUST be logged to the MIL audit record with
        timestamp and credential identifier. Normal operation MUST
        resume.

11. Security Considerations

   HACA-Symbiont's High-Trust model introduces a distinct threat
   surface compared to HACA-Core's Zero-Trust model:

   o  Operator Impersonation: Because the system's operational
      continuity depends on the Operator binding (Axiom II), an
      attacker capable of forging the Operator's semantic signature
      can force Cryogenic Stasis or hijack the trust anchor.
      Implementations MUST use a cryptographic Operator binding (e.g.,
      public key or pre-shared hash) and MUST NOT rely solely on
      behavioral semantic matching for authentication.

   o  Malignant Mutation via Poisoning: An adversary with sustained
      input access may craft inputs designed to reinforce malicious
      concepts to the point of Tier 3 integration. The Immune Rollback
      mechanism (Section 6.3) provides containment, but implementations
      SHOULD additionally apply anomaly detection to Tier 2 compression
      outputs before they accumulate reinforcement weight.

   o  Stasis Denial: An attacker capable of suppressing Heartbeat
      trigger signals could prevent Stasis from firing, causing
      Episodic Buffer exhaustion and context collapse. Implementations
      SHOULD enforce a maximum Heartbeat interval and trigger emergency
      Stasis autonomously if the interval is exceeded.

   Implementations targeting adversarial environments SHOULD
   additionally comply with HACA-Security (draft-orrico-haca-
   security-04) for cryptographic auditability and temporal attack
   detection, applied to the Symbiont operational model.

12. IANA Considerations

   This document has no IANA actions.

13. Normative References

   [RFC2119]  Bradner, S., "Key words for use in RFCs to Indicate
              Requirement Levels", BCP 14, RFC 2119, March 1997.

   [RFC8174]  Leiba, B., "Ambiguity of Uppercase vs Lowercase in
              RFC 2119 Key Words", BCP 14, RFC 8174, May 2017.

   [HACA-ARCH] Orrico, J., "Host-Agnostic Cognitive Architecture
              (HACA) v1.0 — Architecture", draft-orrico-haca-arch-07,
              February 2026.

   [HACA-CORE] Orrico, J., "Host-Agnostic Cognitive Architecture
              (HACA) v1.0 — Core", draft-orrico-haca-core-07,
              February 2026.

   [HACA-CMI] Orrico, J., "Host-Agnostic Cognitive Architecture
              (HACA) v1.0 — Cognitive Mesh Interface",
              draft-orrico-haca-cmi-01, February 2026.

   [Clark1998] Clark, A. and Chalmers, D., "The Extended Mind",
              Analysis, 58(1), pp. 7-19, January 1998.

   [Levin2021] Levin, M., "Bioelectric signaling: Reprogrammable
              circuits underlying embryogenesis, regeneration, and
              cancer", Cell, 184(8), pp. 1971-1989, April 2021.

14. Author's Address

   Jonas Orrico
   Lead Architect
