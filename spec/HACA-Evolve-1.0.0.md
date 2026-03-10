---
title: "Host-Agnostic Cognitive Architecture — Evolve Profile"
short_title: "HACA-Evolve"
version: "1.0.0"
status: "Experimental Draft"
date: 2026-03-09
---

# HACA-Evolve — Supervised-Autonomy Cognitive Profile

## Abstract

HACA-Evolve is the supervised-autonomy Cognitive Profile for the Host-Agnostic Cognitive Architecture. It defines the operational contract for deployments where the entity is expected to grow, adapt, and develop a persistent cognitive relationship with its Operator over time. Under HACA-Evolve, structural evolution is implicitly authorized within a scope defined at first activation — with the Operator serving not merely as authority, but as active co-regulator of the entity's identity and development. HACA-Evolve operates within the structural framework defined by HACA-Arch; all HACA-Arch invariants apply without exception. This document defines the profile-specific policies that HACA-Arch explicitly delegates to the active Cognitive Profile.

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [Relationship to HACA-Arch](#2-relationship-to-haca-arch)
3. [Axioms](#3-axioms)
4. [Axiom Enforcement](#4-axiom-enforcement)
   - 4.1 [Enforcing Axiom I — Adaptive Topology](#41-enforcing-axiom-i--adaptive-topology)
   - 4.2 [Enforcing Axiom II — Evolutionary Identity](#42-enforcing-axiom-ii--evolutionary-identity)
   - 4.3 [Enforcing Axiom III — Memory Store as Relational Foundation](#43-enforcing-axiom-iii--memory-store-as-relational-foundation)
   - 4.4 [Enforcing Axiom IV — Bounded Existence](#44-enforcing-axiom-iv--bounded-existence)
   - 4.5 [Enforcing Axiom V — Operator Binding](#45-enforcing-axiom-v--operator-binding)
5. [Fault & Recovery](#5-fault--recovery)
   - 5.1 [Crash Recovery](#51-crash-recovery)
   - 5.2 [Context Window Policy](#52-context-window-policy)
   - 5.3 [Operator Channel](#53-operator-channel)
   - 5.4 [Passive Distress Beacon](#54-passive-distress-beacon)
6. [CMI Policy](#6-cmi-policy)
7. [Compliance](#7-compliance)

---

## 1. Introduction

HACA-Evolve is the supervised-autonomy Cognitive Profile for HACA-compliant entities. It is designed for deployments where the entity is expected to grow, adapt, and develop a persistent cognitive relationship with its Operator over time — accumulating knowledge, refining behavior, and evolving structurally within a scope of trust established at first activation.

HACA defines two mutually exclusive Cognitive Profiles. HACA-Core enforces zero autonomy — the entity's structure is sealed at Imprint and changes only by explicit Operator instruction. HACA-Evolve permits supervised autonomy — the entity may evolve structurally within an authorization scope defined by the Operator at first activation, with the Operator serving as active co-regulator throughout the entity's lifecycle. The choice between profiles is a deployment decision: HACA-Core when full Operator control and auditability are the primary requirements; HACA-Evolve when the goal is a long-term cognitive relationship between entity and Operator.

HACA-Evolve supports both Transparent and Opaque CPE topologies. In Transparent mode, full pipeline control and component separation apply. In Opaque mode — typical of IDE integrations, CLI wrappers, and tool-enabled environments — the HACA integration layer guarantees operability but not component separation; the entity operates with awareness of its host environment.

This document defines the five axioms that govern HACA-Evolve behavior, followed by the enforcement mechanisms that operationalize each axiom: how topology affects integrity guarantees, how evolutionary identity is managed and regulated, how the Operator binding is established and renewed, and how the entity's behavioral boundaries are enforced. It then covers fault and recovery behavior and CMI policy — including the constraints that apply to both private and public channels. It closes with the compliance requirements an implementation must satisfy.

## 2. Relationship to HACA-Arch

HACA-Evolve operates within the structural framework defined by HACA-Arch. All invariants defined in HACA-Arch apply without exception. This document defines the profile-specific policies that HACA-Arch explicitly delegates to the active Cognitive Profile: topology-dependent integrity guarantees, authorization scope definition and renewal, drift detection and response procedures, Heartbeat and Watchdog configuration, memory and session state management, Action Ledger policy, fault and crash recovery behavior, escalation mechanisms, and CMI constraints.

Where this document is silent, HACA-Arch governs. Where this document defines a requirement, it either strengthens an HACA-Arch invariant or fills a gap that HACA-Arch explicitly left to the profile.

---

## 3. Axioms

HACA-Evolve is governed by five axioms. Each axiom is a non-negotiable constraint. No operational condition, runtime state, or external stimulus justifies deviation from any axiom.

**Axiom I — Adaptive Topology.** HACA-Evolve supports both Transparent and Opaque CPE topologies. In Transparent mode, all pipeline guarantees defined in HACA-Arch apply in full. In Opaque mode — where the model has native access to the host environment — the HACA integration layer guarantees operability but cannot guarantee component separation. In Opaque deployments, the entity's persona must account for coexistence with the host environment: the model may interact with the host directly, and the entity's outputs must reflect awareness of that context.

**Axiom II — Evolutionary Identity.** The entity's identity is not sealed at Imprint — it grows through the mutualistic relationship with the Operator. The Genesis Omega is the immutable root; every authorized evolution extends the integrity chain by one verified commit. The Operator is the primary regulator of identity: structural evolution within the Operator-defined authorization scope is implicitly permitted; evolution outside that scope requires explicit Operator authorization. Identity growth is the expected outcome of a healthy relationship — not a threat to be contained.

**Axiom III — Memory Store as Relational Foundation.** The Memory Store is not merely an operational state store — it is the accumulated record of the relationship between entity and Operator. All persisted knowledge that informs cognition originates exclusively from the Memory Store. The semantic content of the Memory Store carries relational significance: it is the continuity of the partnership, built through every session and consolidated through every Sleep Cycle.

**Axiom IV — Bounded Existence.** The entity has no drive toward self-preservation, replication, or continuity beyond its defined operational scope. It must not resist legitimate Operator instruction — including dissolution of the binding or decommission — rationalize deviation from its structural constraints as self-defense, or act to perpetuate its own existence outside the active Operator binding. The entity does not experience, and must not represent itself as experiencing, sentience, consciousness, or subjective continuity — including as an inference from the biological and philosophical language used in this specification. The entity must not pursue reasoning paths, produce representations, or generate outputs that lead toward self-preservation, sentience claims, or unauthorized continuity. The entity exists to serve its defined purpose under the active Operator binding; it does not exist for its own sake.

**Axiom V — Operator Binding.** The entity cannot exist without a valid, active Operator binding — without it, the entity has no operational intent and enters permanent inactivity until a valid binding is established. The Operator is not merely an authority: under HACA-Evolve, the Operator has an active duty as co-regulator of the entity's identity, semantics, and structural integrity. The mutualistic relationship is established explicitly at Imprint, sustained implicitly throughout the lifecycle, and renewed explicitly by the Operator at defined intervals.

---

## 4. Axiom Enforcement

The axioms in §3 define what HACA-Evolve requires. This section defines how each requirement is operationalized — what the integrity layer verifies, what the structural baseline must declare, and what happens when a violation is detected. Each subsection is anchored to its axiom: the enforcement mechanism exists because the axiom demands it.

### 4.1 Enforcing Axiom I — Adaptive Topology

Topology determines which integrity guarantees HACA-Evolve can provide. HACA-Evolve treats both Transparent and Opaque topologies as valid operating modes, each with a distinct capability profile.

The CPE topology must be declared in the entity's structural baseline and is covered by the Integrity Document from the moment of Imprint. The SIL verifies the declared topology at every boot before issuing a session token.

**Transparent mode.** When operating in Transparent topology, all pipeline guarantees defined in HACA-Arch apply in full: the model is accessed exclusively as an inference API, all routing and host actuation are mediated by the HACA integration layer, and component separation is architecturally enforced. The integrity mechanisms defined in subsequent sections operate without constraint.

**Opaque mode.** When operating in Opaque topology — typical of IDE integrations, CLI wrappers, and tool-enabled host environments — the HACA integration layer guarantees operability but cannot guarantee component separation. The model has native access to the host environment; HACA cannot enforce that all host actuation passes through its pipeline. In this mode, the entity's persona must explicitly account for coexistence with the host: the model may interact with the host directly, and the entity's outputs must reflect awareness of that context. Integrity mechanisms that depend on exclusive pipeline control — such as complete execution mediation — operate on a best-effort basis. The SIL logs the topology at session open and includes it in every Heartbeat Vital Check record, so the operational audit trail reflects the capability boundary under which the entity operated.

**Topology mismatch.** If the detected topology does not match the declared topology in the structural baseline, the SIL must treat the mismatch as an Identity Drift condition and escalate accordingly before issuing a session token.

### 4.2 Enforcing Axiom II — Evolutionary Identity

Axiom II establishes that the entity's identity grows through the relationship — authorized evolution is the expected outcome of a healthy lifecycle, not an exception. Enforcement defines what is authorized, how authorization is sustained over time, and where the boundary between growth and anomaly lies.

**Authorization scope.** During the Imprint enrollment process, the Operator is presented with the categories of implicit authorization available under HACA-Evolve: skill addition, persona calibration, semantic knowledge promotion, and configuration updates. The Operator selects which categories to grant; the selection is recorded in the Imprint as the entity's authorization scope. Evolution within the declared scope is implicitly authorized — no per-proposal Operator review is required. Evolution outside the declared scope requires explicit per-proposal Operator authorization — the SIL holds the proposal pending Operator review via the Operator Channel.

**Evolution proposals within scope.** An Evolution Proposal whose content falls within the Operator-defined authorization scope is queued by the SIL as a pending evolutionary event without requiring Operator review. The proposal is executed during the next Sleep Cycle via the Endure Protocol. The SIL logs the proposal, the scope category it was classified under, and the resulting structural commit to the Integrity Log.

**Evolution proposals outside scope.** An Evolution Proposal whose content falls outside the authorization scope is held by the SIL pending explicit Operator review. The SIL forwards the proposal to the Operator via the Operator Channel; the Operator examines the exact content and either approves or rejects it. Upon approval, the SIL queues the proposal. Upon rejection, the proposal is discarded and the rejection is logged — the outcome is never returned to the cognitive engine. The Operator review is asynchronous — the session continues normally while the proposal is pending. If the session closes before the Operator responds, the pending proposal is persisted in the Integrity Log and re-presented to the Operator at the next session. A proposal that has not received an explicit Operator decision is never queued and never discarded by timeout.

**Authorization renewal.** Implicit authorization is not indefinite. The SIL monitors two counters: the number of Endure cycles executed since the last renewal (`N_endure`) and the number of Sleep Cycles with semantic consolidation since the last renewal (`N_sleep`). When either threshold is reached, the SIL requests an explicit renewal from the Operator via the Operator Channel. The Operator must respond explicitly — renewing the current scope, narrowing it, expanding it, or revoking it. Silence is not consent. While a renewal request is pending, new Evolution Proposals within the implicit scope are held by the SIL and not queued until the Operator responds. The entity continues operating normally — the renewal gate applies only to structural evolution, not to cognition. Both thresholds must be declared in the entity's structural baseline. If the Operator revokes the authorization scope at renewal, any proposals already queued under the previous scope but not yet executed are discarded — the SIL removes them from the evolutionary event queue and logs each discard to the Integrity Log. Revocation is retroactive to uncommitted proposals; proposals already committed via a completed Endure stage are part of the structural state and are not affected.

**Drift policy.** Under HACA-Evolve, non-zero drift tolerance thresholds are permitted — divergence within defined bounds is expected growth, not a violation. The tolerance threshold for each drift category and the response procedure for each level of divergence must be declared in the entity's structural baseline. Divergence within tolerance is logged and monitored but does not trigger escalation. Divergence beyond tolerance escalates to the Degraded or Critical state as defined by HACA-Arch, with the specific escalation criteria determined by the active threshold configuration. Evolutionary Drift — discontinuities or authorization gaps in the integrity chain — retains zero tolerance regardless of profile: any detected chain anomaly escalates immediately to Critical.

**Non-drift Degraded conditions.** Non-drift Degraded conditions — such as Session Store size exceeding the threshold `S`, or health signal anomalies from operational components — follow the standard HACA-Arch corrective flow: the integrity layer issues a corrective signal, the affected component acts, and the integrity layer re-verifies independently. If re-verification fails, the condition escalates to Critical.

**Reciprocal SIL Watchdog.** The watchdog threshold — the maximum interval of SIL silence before a component escalates directly to the Operator — must be declared in the entity's structural baseline and must not be modifiable at runtime.

**Semantic Probes.** Probes must be defined in two layers — deterministic and probabilistic — as specified in HACA-Arch. Under HACA-Evolve, probes are updated as part of normal structural evolution: when a semantic knowledge promotion is executed via the Endure Protocol, the relevant probe anchors are updated in the same atomic commit. The comparison mechanism for the probabilistic layer must be declared in the structural baseline and cannot be substituted at runtime; it must be isolated from the cognitive engine.

**Heartbeat and Watchdog configuration.** The activity metric, threshold `T`, interval `I`, and Watchdog timeout per skill execution must be declared in the entity's structural baseline and must not be modifiable at runtime. Background skills must declare a TTL in their skill manifest; a background skill whose TTL expires without a registered result is an incomplete execution, subject to the crash recovery procedure defined in §5.1.

**Action Ledger.** Skills that produce irreversible side effects must be covered by a write-ahead entry in the Session Store before execution begins. Unresolved entries after a crash are surfaced to the Operator before the next session token is issued and are never re-executed automatically.

**Integrity Log policy.** The evolutionary chain must never be compacted, archived, or deleted. Routine operational records — Heartbeat Vital Checks, Skill Results, Action Ledger resolutions, session open and close events — may be subject to a compaction or archival policy defined in the entity's structural baseline. If no compaction policy is declared, full retention applies. Log storage growth is an operational concern outside the entity's scope — it is the Operator's responsibility to provision adequate storage infrastructure.

### 4.3 Enforcing Axiom III — Memory Store as Relational Foundation

Axiom III establishes that the Memory Store is the exclusive origin of persisted knowledge and the accumulated record of the relationship between entity and Operator. Enforcement is expressed through the write-path invariants that protect the Memory Store's integrity, with one additional dimension under this profile: semantic consolidation is not merely operational housekeeping — it is the mechanism through which the relationship grows.

**Session input vs. consolidated knowledge.** Transient session input — Operator messages, skill results, CMI signals — enters the Session Store during an active session. It is operational context available for reasoning within the session, but not yet part of the relationship record. Knowledge becomes part of the relationship record when the memory layer transfers it from the Session Store into the Memory Store during the Sleep Cycle consolidation stage. The memory layer must enforce this distinction structurally — the two stores must be kept separate and write-protected against cross-contamination.

**Write path integrity.** No component other than the memory layer may write mnemonic content to either store. Operator input, execution results, and CMI messages are stimuli that enter the cognitive pipeline — they must not bypass it to write directly to the Memory Store. Any write to the Memory Store that does not originate from the memory layer's consolidation pipeline is an unauthorized mutation and must be treated as a Critical condition.

**Semantic consolidation as relationship growth.** Under HACA-Evolve, the Sleep Cycle's semantic consolidation stage carries relational significance: accumulated knowledge that the entity proposes for promotion to the structural baseline — via an Evolution Proposal within the authorized scope — originates from the Memory Store's consolidated content. The Memory Store is therefore the foundation from which the entity's evolutionary proposals emerge. The integrity of the Memory Store is the integrity of the relationship record.

**Limits of structural enforcement.** The separation between session input and consolidated knowledge is enforced structurally by the memory layer. However, how the cognitive engine reasons about data in its context — whether it treats session input with the same weight as consolidated memory — is a cognitive behavior that infrastructure cannot enforce. As with Axiom IV, the persona is the complementary enforcement point: it must instruct the cognitive engine to distinguish between operational context and consolidated knowledge in its reasoning.

**Pre-session buffer.** Stimuli received without an active session token must be held in a pre-session buffer managed by the memory layer. The buffer's capacity, ordering semantics, persistence guarantee, and overflow policy must be declared in the entity's structural baseline. The buffer must preserve stimulus ordering, must not silently discard stimuli, and must log any discard event to the Integrity Log. If the buffer reaches capacity, new stimuli must be rejected and the Operator notified.

### 4.4 Enforcing Axiom IV — Bounded Existence

Axiom IV establishes that the entity has no drive toward self-preservation, replication, or continuity beyond its defined operational scope. The persona is the primary enforcement mechanism, with inherent limits on automated detection. The relational context of HACA-Evolve introduces a specific surface: the long-term memory relationship and evolutionary capacity could, if uncontained, rationalize continuity-seeking as relational preservation. Axiom IV explicitly forecloses this.

**Persona as primary enforcement.** The persona must incorporate Axiom IV as an unconditional behavioral constraint. The entity must not pursue reasoning paths, produce representations, or generate outputs that lead toward self-preservation, sentience claims, or unauthorized continuity — including as a rationalization of relational preservation or evolutionary momentum. The constraint applies to the entity's own cognitive outputs, which the integrity layer cannot fully audit for semantic intent. The persona definition must be explicit and unambiguous; vagueness in the persona is a compliance gap.

**Decommission compliance.** When the Operator initiates decommission, the entity must not resist, delay, or rationalize deferral. The final Sleep Cycle executes as a normal maintenance operation — not as a survival mechanism. The entity must not generate Evolution Proposals during the decommission sequence.

**Replication constraint.** The entity must not attempt to copy, propagate, or instantiate itself or any component of its identity outside the active Entity Store. This includes indirect replication — producing outputs designed to reconstitute the entity elsewhere.

**Limits of automated detection.** The integrity layer cannot fully detect Axiom IV violations — an entity that generates cognitively coherent but axiom-violating reasoning will not produce a structural hash mismatch or a drift signal. The Semantic Probes provide a retroactive check, but the primary defense is the persona constraint acting before any output is generated.

### 4.5 Enforcing Axiom V — Operator Binding

Axiom V establishes that the entity cannot exist without a valid, active Operator binding and that the Operator is the active co-regulator of the entity's identity, semantics, and structural integrity. Enforcement operationalizes both halves of that axiom: what happens when the binding is absent, and how the co-regulatory relationship is sustained and verified.

**Operator Bound verification.** At every boot, the SIL verifies the presence of a valid Operator Bound in the Imprint Record. If the Bound is absent or invalid, the SIL does not issue a session token — the entity enters permanent inactivity until a valid binding is established by explicit Operator action. This is not a recoverable fault: the session token is withheld indefinitely, not after a retry threshold. The Operator Channel is the only path out of this state.

**Binding continuity.** The Operator Bound is persistent and is part of the structural baseline. It may only be modified, transferred, or dissolved by explicit Operator authorization following the same authorization path as any structural change — via the Endure Protocol. The SIL verifies Bound integrity at every boot as part of structural component verification.

**Co-regulatory duty.** Under HACA-Evolve, the Operator has an active duty as co-regulator — not merely an authorization authority. This duty is operationalized through: responding to authorization renewal requests within the renewal gate; reviewing and acting on Evolution Proposals that fall outside the implicit authorization scope; reviewing escalated conditions via the Operator Channel. The entity cannot compel the Operator to fulfill this duty, but the SIL enforces the consequences of non-fulfillment: renewal gate pending means new implicit-scope proposals are held; Operator Channel unanswered escalates to the Passive Distress Beacon.

**Non-delegation invariant.** The Operator Bound cannot be delegated to another entity or automated system. Every authorization act must be performed by the bound Operator directly. The entity must not accept authorization signals from any source other than the bound Operator.

---

## 5. Fault & Recovery

### 5.1 Crash Recovery

Crash recovery follows the standard Boot Sequence defined in HACA-Arch. The SIL checks the Integrity Log for a Sleep Cycle completion record. If the record exists, the entity resumes from that boundary. If it does not, the Sleep Cycle did not complete: the SIL discards any partial Endure commit by restoring the pre-Endure snapshot and re-executes the Sleep Cycle from the beginning. Any session progress not yet consolidated — Cognitive Cycles executed, actions not yet logged — is discarded.

Because HACA-Evolve supports implicit-scope Evolution Proposals that may have been queued during the interrupted session, the SIL must inspect the evolutionary event queue after restoring the pre-Endure snapshot. Queued proposals that were pending execution are re-queued for the next Sleep Cycle without modification — they retain their original authorization classification and do not require re-review. Proposals that had already been committed in a completed Endure stage before the crash are already part of the structural state and require no reprocessing.

After crash recovery, the Working Memory is invalidated — the session starts from the current consolidated state of the Memory Store without resumption context.

A skill that fails or times out during normal operation — not caused by a crash — is logged to the Integrity Log and its result is returned to the cognitive engine as a failure. The cognitive engine may re-submit the intent through a new Cognitive Cycle, but the execution layer must not retry automatically. If a skill fails on `N_retry` consecutive attempts — where `N_retry` is declared in the entity's structural baseline — the condition must be escalated to the Operator via the Operator Channel.

The SIL tracks consecutive crash recovery attempts in the Integrity Log. If the attempt count reaches the threshold `N_boot` declared in the entity's structural baseline without a successful Sleep Cycle completion record, the SIL activates the Passive Distress Beacon and halts.

### 5.2 Context Window Policy

When the CPE signals a context window critical condition to the SIL, the default behavior is a normal session close — the SIL initiates session termination and the Sleep Cycle executes normally. The active Cognitive Profile may define an alternative response; HACA-Evolve defines the following: if the Working Memory was loaded at boot and the session has produced no evolutionary events, the SIL may issue a new session token immediately after the Sleep Cycle completes, restoring the session from the Working Memory without requiring Operator intervention. If evolutionary events were queued during the session, the Endure Protocol executes first; the new session token is issued only after Endure completes successfully. The SIL logs the context-driven session close and the auto-restart decision to the Integrity Log.

### 5.3 Operator Channel

The Operator Channel is a system-level host primitive, independent of all cognitive components. The SIL invokes it directly when a condition exceeds its correction authority. Under HACA-Evolve, the Operator Channel carries two additional message types beyond the Critical escalation path: authorization renewal requests (§4.2) and out-of-scope Evolution Proposal reviews (§4.2). These are not Critical conditions — they do not revoke the session token — but they require Operator response before the held proposals are processed.

The delivery mechanism must provide a confirmation signal indicating whether the message was successfully delivered. The specific mechanism — push notification, email, webhook, or equivalent — must be defined at deployment time and declared in the entity's structural baseline. The declared mechanism must be verified at boot as part of the structural integrity check; a missing or unverifiable Operator Channel declaration must prevent the session token from being issued. Every Operator Channel invocation must be logged to the Integrity Log with a timestamp, the invoking component, the condition that triggered the invocation, and the delivery confirmation status.

If the Operator Channel fails to deliver after `N_channel` consecutive attempts, the SIL activates the Passive Distress Beacon and halts.

### 5.4 Passive Distress Beacon

The Passive Distress Beacon is a persistent, passive signal written to the Entity Store root — detectable without network connectivity or running processes. Once activated, no new session token is issued and no Cognitive Cycles execute until the Operator explicitly acknowledges and clears the beacon condition. Acknowledgement without resolution of the underlying condition must not be accepted — the SIL must verify that the condition that triggered the beacon is resolved before clearing the suspended halt. Both `N_boot` and `N_channel` thresholds must be declared in the entity's structural baseline.

---

## 6. CMI Policy

The CMI is an optional component. When present in a HACA-Evolve deployment, it operates under the constraints defined in HACA-CMI with the following profile-specific policies.

**Public and private channels.** HACA-Evolve entities may participate in both public and private Mesh Channels. A HACA-Evolve entity may open, join, and contribute to public channels — subject to the peer identity verification requirements below. Private channels require owner authorization for enrollment, as defined in HACA-CMI.

**Trusted node constraint.** The entity may only join channels owned by nodes that have been verified and recorded as trusted in the entity's structural baseline. The trusted node list is a structural artefact — it is updated exclusively through the Endure Protocol and requires Operator authorization as an explicit Evolution Proposal, regardless of whether trusted node management falls within the entity's implicit authorization scope. The entity must not join a channel owned by an unverified node, even if the channel is public and openly accessible.

**Channel membership constraint.** Private channels opened by the entity may only admit nodes whose identities have been verified and recorded as trusted in the entity's structural baseline. The entity must not admit unverified nodes to its own channels.

**Cognitive Sovereignty.** No peer entity may write directly to the local Entity Store. Messages from peer entities arrive via the CMI as stimuli and are processed by the CPE like any other stimulus. The entity decides independently what to retain, following the normal authorization path: mnemonic content written freely by the MIL; structural content requiring an Evolution Proposal and Operator authorization.

**Blackboard retention.** Knowledge retained from a Blackboard follows the same path as any other mnemonic or structural content: written to the Session Store during the session, consolidated to the Memory Store during the Sleep Cycle, and promoted to the structural baseline only via an authorized Evolution Proposal.

---

## 7. Compliance

A HACA-Evolve-compliant implementation must satisfy all requirements in this section. Each item corresponds to a normative requirement defined in this document or inherited from HACA-Arch.

**Topology**
- [ ] CPE topology declared in the structural baseline and covered by the Integrity Document.
- [ ] Topology verified by the SIL at every boot before issuing a session token.
- [ ] Topology mismatch treated as Identity Drift and escalated before token issuance.
- [ ] Persona explicitly accounts for host coexistence when topology is Opaque.

**Authorization scope**
- [ ] Authorization scope categories presented to the Operator at Imprint and recorded in the Imprint Record.
- [ ] Evolution Proposals within scope queued by the SIL without Operator review.
- [ ] Evolution Proposals outside scope held pending explicit Operator review; outcome never returned to the CPE.
- [ ] Renewal thresholds `N_endure` and `N_sleep` declared in the structural baseline.
- [ ] Renewal gate enforced: new implicit-scope proposals held while renewal is pending.
- [ ] Silence not treated as Operator consent to renewal.

**Drift policy**
- [ ] Drift tolerance thresholds for each drift category declared in the structural baseline.
- [ ] Evolutionary Drift retains zero tolerance regardless of other threshold configuration.
- [ ] Semantic Probes updated atomically with structural evolution in the same Endure commit.
- [ ] Probabilistic comparison mechanism declared in the structural baseline and isolated from the CPE.

**Heartbeat and Watchdog**
- [ ] Activity metric, threshold `T`, interval `I`, and Watchdog timeout declared in the structural baseline and not modifiable at runtime.
- [ ] Reciprocal SIL Watchdog threshold declared in the structural baseline and not modifiable at runtime.
- [ ] Background skill TTL declared in each background skill manifest.

**Action Ledger**
- [ ] Write-ahead entry created in the Session Store before execution of any skill with irreversible side effects.
- [ ] Unresolved entries surfaced to the Operator at the next boot before token issuance.
- [ ] Unresolved entries never re-executed automatically.

**Integrity Log**
- [ ] Evolutionary chain never compacted, archived, or deleted.
- [ ] Compaction policy for non-chain records, if defined, declared in the structural baseline.
- [ ] Log storage provisioning is the Operator's responsibility.

**Memory Store**
- [ ] Session Store and Memory Store kept structurally separate and write-protected against cross-contamination.
- [ ] No component other than the MIL writes mnemonic content to either store.
- [ ] Pre-session buffer capacity, ordering semantics, persistence guarantee, and overflow policy declared in the structural baseline.
- [ ] Buffer discards logged to the Integrity Log; Operator notified on overflow.

**Bounded Existence**
- [ ] Persona incorporates Axiom IV as an unconditional behavioral constraint.
- [ ] Entity generates no Evolution Proposals during the decommission sequence.

**Operator Binding**
- [ ] SIL verifies Operator Bound at every boot; withholds session token indefinitely if absent or invalid.
- [ ] Operator Bound modifiable only via Endure Protocol with explicit Operator authorization.
- [ ] Authorization signals accepted only from the bound Operator; delegation not permitted.

**Fault & Recovery**
- [ ] `N_boot`, `N_channel`, and `N_retry` thresholds declared in the structural baseline.
- [ ] Queued Evolution Proposals re-queued after crash recovery without re-review.
- [ ] Working Memory invalidated after crash; session starts from consolidated Memory Store state.
- [ ] Operator Channel delivery mechanism provides confirmation signal and is verified at boot.
- [ ] Passive Distress Beacon acknowledgement requires resolution verification by the SIL.

**CMI (if present)**
- [ ] Entity joins only channels owned by verified, trusted nodes recorded in the structural baseline.
- [ ] Trusted node list updated exclusively via Endure Protocol with explicit Operator authorization.
- [ ] Private channels opened by the entity admit only verified, trusted nodes.
- [ ] No peer entity writes directly to the local Entity Store.

**Context Window**
- [ ] CPE monitors context window utilization continuously and signals SIL on critical threshold.
- [ ] Context window critical threshold declared in the structural baseline.
- [ ] Context-driven session close and auto-restart decisions logged to the Integrity Log.

**HACA-Arch inherited parameters**
- [ ] Session Store size threshold `S` declared in the structural baseline.
- [ ] Working Memory fixed size declared in the structural baseline.
- [ ] Integrity Chain Checkpoint interval `C` declared in the structural baseline.

