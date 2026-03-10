# HACA-CMI 1.0.0

## Host-Agnostic Cognitive Architecture — Cognitive Mesh Interface Extension

**Version**: 1.0.0
**Status**: Draft
**Extends**: HACA-Arch 1.0.0
**Date**: 2026-03-10
**Author**: Lucas Orrico

---

## 1. Introduction

A HACA entity, by default, operates in isolation — it receives stimuli from its Operator, processes them through its cognitive pipeline, and persists state in its Entity Store. The Cognitive Mesh Interface (CMI) extends this model by enabling entities to discover, authenticate, and coordinate with peer entities through purposive, time-bounded collaboration spaces.

The mesh operates under a single organizing principle: coordination without dissolution. Entities enter a shared space to accomplish a defined task, contribute to and benefit from collective knowledge, and return to fully autonomous operation when the task is complete. No entity surrenders authority over its own Entity Store; no peer writes directly to another entity's state. The mesh only offers; the entity always acts on itself. This principle — **Cognitive Sovereignty** (HACA-Arch §3.3) — is the mesh's foundational invariant.

This specification defines the general mesh protocol. Profile-specific constraints are defined independently by HACA-Core and HACA-Evolve in their respective CMI sections.

## 2. Node Identity

A HACA entity participating in the mesh is a **Node**. Each node is identified by a **Node Identity** (Π) — a permanent, deterministic identifier derived from the entity's Genesis Omega. Since the Genesis Omega is immutable and unique per entity, the Node Identity is permanent and globally unique. It identifies the entity to peers without exposing the Genesis Omega directly.

Mesh authentication requires a **CMI Credential** (K_cmi) — a signing key pair stored as structural content in the Entity Store and covered by the Integrity Document. The CMI Credential is updated exclusively through the Endure Protocol. The derivation of Π from the Genesis Omega and the cryptographic properties of K_cmi are defined at implementation time; HACA-Security provides normative binding requirements when active.

An entity that does not activate the CMI extension does not generate a Node Identity or CMI Credential. These artefacts are created during the entity's first CMI activation — which may occur at first activation or at any subsequent boot where the CMI extension is enabled for the first time. The CMI Credential generation follows the Endure Protocol as a structural write.

## 3. Mesh Channel

The **Mesh Channel** is the fundamental unit of coordination: a purposive, time-bounded space created by a **Host** entity to accomplish a declared task. A Mesh Channel has exactly one Host — the entity that created it — and zero or more enrolled participants. An entity may participate in multiple Mesh Channels simultaneously. Channels are logically and cryptographically isolated; the implementation must ensure that contributions, messages, and internal session context do not cross channel boundaries. This isolation is a foundational requirement for Cognitive Sovereignty.

### 3.1 Task

Every Mesh Channel is created with a declared **Task**: the goal, the expected output, and the criteria under which the task is considered complete. The Task is immutable for the duration of the channel — if the goal changes, a new channel must be created. The Task is the channel's reason for existence and provides the objective completion signal.

### 3.2 Visibility

A Mesh Channel has one of two visibility types, declared at creation:

- **Private** — only entities explicitly invited by the Host may enroll.
- **Public** — any entity with a valid Node Identity that discovers the channel may request enrollment. The Host retains admission authority.

HACA-Core entities may only participate in private Mesh Channels. HACA-Evolve entities may participate in both.

### 3.3 Roles

Three roles govern participation in a Mesh Channel:

- **Host** — the channel owner. Exactly one per channel. Creates the channel, defines the Task, controls lifecycle, sequences Blackboard contributions, assigns and modifies participant roles. The Host is a full participant and may contribute to the Blackboard.
- **Peer** — an active participant. May send stimuli, contribute to the Blackboard, and receive all channel activity.
- **Observer** — a passive participant. Receives all channel activity as stimuli but may not contribute to the Blackboard or send stimuli to other participants.

The Host may change a participant's role during the Active state. Role changes are broadcast as signed control signals, take effect upon receipt, and must be logged by all participants in their respective Integrity Logs to enable subsequent audit and enforcement.

### 3.4 Lifecycle

A Mesh Channel progresses through four states:

**Created** — the Host has declared the channel with its Task, visibility type, and enrollment policy. The channel is not yet operational; no participants are enrolled.

**Active** — the channel is operational. Participants enroll, stimuli flow, and the Blackboard accumulates contributions. Late enrollment is permitted — participants joining an active channel receive the current Blackboard state.

**Closing** — the Host has signaled channel close, or the Task's completion criteria have been met, or the Host has become permanently unreachable. No new enrollment is accepted. Each participant reads the final Blackboard and consolidates what is relevant to its own context (§8).

**Closed** — the channel is terminated. The Host archives the final Blackboard. All participants return to fully autonomous operation. A Closed channel cannot be reopened; new tasks require new channels.

There is no Host succession mechanism. If the Host becomes permanently unreachable, the channel enters Closing directly — remaining participants consolidate from the last known Blackboard state. A new channel with a new Host must be created for subsequent tasks.

## 4. Blackboard

The **Blackboard** is the shared, append-only workspace of a Mesh Channel: the consolidated episodic knowledge of the task being executed. It is the channel's durable output — the tangible result of collective coordination.

Each contribution to the Blackboard is attributed to its originating node (by Node Identity) and assigned a monotonically increasing sequence number by the Host. The Host's sequence assignment provides deterministic ordering — all participants observe contributions in the same order regardless of delivery timing. Contributions represent task-relevant content — results, partial results, analysis, dissent — not coordination messages.

All other channel activity — messages exchanged between entities during task execution for coordination purposes — is ephemeral. These messages enter each entity's cognitive pipeline as stimuli, are processed by the CPE, and are discarded at channel close. The Blackboard is what survives.

## 5. Discovery

### 5.1 Bootstrap Discovery

The entity's Operator provisions a **Trust List** as part of the structural baseline: a set of known peers, each identified by Node Identity (Π), endpoint information, and a **Trust Label**. The Trust List is structural content — covered by the Integrity Document, updated exclusively through the Endure Protocol. Bootstrap Discovery is available to both HACA-Core and HACA-Evolve entities.

### 5.2 Organic Introduction

A peer with a FULL trust label may introduce a previously unknown peer by vouching for its Node Identity and providing its endpoint information. The introduced peer receives an INTRODUCED trust label and the introduction is logged in the Integrity Log.

Three constraints govern Organic Introduction:

1. Only peers with FULL trust labels may introduce. CONTACT and INTRODUCED peers may not.
2. Only first-hand introductions are accepted. Transitive introductions — a peer introduced by an introduced peer — are rejected.
3. A standing Operator permission for Organic Introduction must be recorded in the structural baseline. Without this permission, all introductions are rejected.

HACA-Core entities do not use Organic Introduction. HACA-Evolve entities may use it when the standing permission is present.

## 6. Enrollment

### 6.1 Enrollment Invariants

Enrollment is the process by which an entity joins an active Mesh Channel. The specific handshake protocol is defined at implementation time; the following properties are invariant:

1. The enrolling entity must prove possession of the CMI Credential bound to its declared Node Identity.
2. The Host must verify the entity's Node Identity against its Trust List or Organic Introduction records.
3. The Host assigns a role upon successful enrollment.
4. The enrolling entity receives the current Blackboard state — late joiners see all existing contributions.
5. Enrollment is logged by both parties.

Profile-specific enrollment constraints are defined by HACA-Core and HACA-Evolve in their respective CMI sections.

### 6.2 Enrollment Tokens

For private Mesh Channels, the Host may issue **Enrollment Tokens** — time-limited, single-use credentials that authorize a specific entity to enroll. An enrollment token encodes the channel identity, the invited entity's Node Identity, the assigned role, and an expiry. Tokens are revocable by the Host before use.

### 6.3 Session Token Requirement

An entity must have an active session token to participate in a Mesh Channel. If the entity's session token is revoked during channel participation, the entity immediately dis-enrolls from all active channels. The dis-enrollment is signaled to the Host.

If the Host's session token is revoked, the channel enters Closing — all participants receive a close signal and proceed to Blackboard consolidation.

### 6.4 Dis-enrollment

An entity may voluntarily dis-enroll from a channel at any time during the Active state. Voluntary dis-enrollment is signaled to the Host, logged, and the entity ceases to receive further channel activity. The Host may also forcibly dis-enroll an entity by revoking its role — the entity is notified and removed.

An entity that dis-enrolls before channel close may consolidate from the Blackboard state it last received. Forced dis-enrollment by the Host revokes access to the Blackboard.

An entity undergoing decommission (HACA-Arch §6.5) dis-enrolls from all active Mesh Channels before executing its final Sleep Cycle, consolidating from the current Blackboard state of each channel.

## 7. Channel Operation

During the Active state, all channel activity enters each participating entity as stimuli through the entity's normal cognitive pipeline. The entity's SIL validates inbound mesh stimuli as it validates any other external input. The CPE processes each stimulus — a Blackboard contribution, a coordination message, a control signal — and decides how to respond: contributing to the Blackboard, sending a coordination message, or taking no action. Each stimulus constitutes a standard input to the entity's Cognitive Cycle. Implementations may optimize cognitive cycle count by batching messages at defined time intervals.

### 7.1 Blackboard Contributions

A participant with a Host or Peer role submits a contribution to the Host. The Host validates the submission (the contributor must hold a role that permits contributions), assigns the next sequence number, and broadcasts the sequenced contribution to all participants. The broadcast includes the contributor's Node Identity, the sequence number, and the contribution content.

### 7.2 Coordination Messages

Coordination messages are direct stimuli exchanged between participants for task coordination — questions, discussions, status updates. They are ephemeral: processed by each entity's CPE and not persisted beyond the entity's active Session Store. At channel close, coordination messages are discarded. The delivery model for coordination messages — broadcast, directed, or both — is defined at implementation time.

### 7.3 Channel Heartbeat

The Host maintains a channel-level heartbeat to detect unresponsive participants. If a participant fails to respond within the channel heartbeat interval, the Host may forcibly dis-enroll it. The heartbeat interval and failure threshold are declared by the Host at channel creation. The channel heartbeat is independent of each entity's internal Heartbeat Protocol (HACA-Arch §3.4).

### 7.4 Transport Requirements

All mesh communication must satisfy the following transport properties:

1. All messages must be encrypted in transit.
2. Per-sender ordering must be preserved for Blackboard contributions and control messages.
3. Delivery confirmation is required for Blackboard contributions and control messages.
4. Coordination messages may use best-effort delivery.

Each message must carry identity binding: the sender's Node Identity and a signature produced with the sender's CMI Credential, covering at minimum the message type, channel identity, sequence information, and content digest. The specific message encoding and transport protocol are defined at implementation time.

## 8. Channel Close and Consolidation

### 8.1 Close Triggers

A Mesh Channel enters Closing when one of the following occurs:

1. The Host explicitly signals close.
2. The Task's declared completion criteria are satisfied.
3. The Host becomes permanently unreachable beyond the channel heartbeat threshold.

### 8.2 Consolidation

During the Closing state, each participating entity reads the final Blackboard and produces its own consolidation — the subset of Blackboard content relevant to the entity's context. The CPE generates the consolidation content; the SIL validates it through the entity's normal authorization path; the MIL writes validated content to the Entity Store as mnemonic content.

If the CPE determines that Blackboard content warrants promotion to the structural baseline, it produces an Evolution Proposal following the normal path (HACA-Arch §4.1). The proposal follows the entity's profile-specific authorization rules — explicit Operator approval under HACA-Core, implicit within scope under HACA-Evolve.

Each entity consolidates at its own pace. The channel does not wait for all entities to finish — each entity signals acknowledgment to the Host when its consolidation is complete. After all acknowledgments are received or a Host-defined timeout expires, the channel transitions to Closed.

### 8.3 Blackboard Archival

The Host archives the final Blackboard state as part of channel closure. The archived Blackboard is an immutable record of the channel's output. At minimum, the Host preserves the channel identity, Task, participant list, and a digest of the final Blackboard. Whether the full Blackboard content is retained is defined at implementation time.

### 8.4 Session Lifecycle Interaction

If an entity's session closes normally while the entity is participating in active Mesh Channels, the entity dis-enrolls from all channels as part of its session close sequence. Dis-enrollment includes consolidation from each channel's current Blackboard state. The entity then produces its Closure Payload and proceeds to the Sleep Cycle as normal.

If the entity's session token is revoked (non-normal close), the entity is immediately dis-enrolled from all channels without consolidation (§6.3). Session progress and channel state since the last Sleep Cycle are lost — consistent with HACA-Arch crash recovery semantics.

### 8.5 Crash During Channel

If an entity crashes while participating in a Mesh Channel, it does not attempt automatic re-enrollment at the next boot. The channel participation at the time of crash is recorded in the Integrity Log for Operator review. If the channel is still active and the Host re-invites the entity after recovery, the entity may accept the invitation and resume participation — receiving the current Blackboard state as a late joiner. The entity is not obligated to resume; it may treat the re-invitation as a new participation decision.

## 9. Trust and Authorization

### 9.1 Operator Authorization

All mesh participation is ultimately authorized by the Operator. The Trust List (§5.1) represents the Operator's explicit authorization of which peers the entity may coordinate with. No entity may enroll in a channel hosted by an entity not in its Trust List or Organic Introduction records. The Operator controls the Trust List through the Endure Protocol.

### 9.2 Trust Labels

Three trust labels are defined:

- **FULL** — the peer is authorized for mesh coordination. The entity may enroll in channels hosted by this peer, accept enrollment requests from this peer, and accept Organic Introductions from this peer (HACA-Evolve only).
- **CONTACT** — the peer is known but not authorized for coordination. The Operator must upgrade the label through the Endure Protocol before the entity may coordinate with this peer.
- **INTRODUCED** — the peer was vouched for by a FULL-trusted peer through Organic Introduction. The entity may coordinate with this peer under the same conditions as FULL, except that INTRODUCED peers may not themselves introduce others.

### 9.3 CMI Credential Rotation

If an entity's CMI Credential is compromised or needs renewal, the entity generates a new credential through the Endure Protocol and notifies all active channel participants. The rotation signal is signed with both the outgoing and incoming credentials — proving the entity controls both. Peers update their local records. The Node Identity (Π) does not change, since it is derived from the Genesis Omega, not the CMI Credential.

## 10. Mesh Integrity and Faults

### 10.1 Blackboard Integrity

The Host maintains the integrity of the Blackboard through deterministic sequencing. Each contribution's sequence number, contributor identity, and content digest form a verifiable chain — any gap, reorder, or unauthorized modification is detectable by any participant. If a participant detects a Blackboard integrity violation, it signals the anomaly to its own SIL. The SIL evaluates the severity and may escalate to the Operator via the Operator Channel.

### 10.2 Fault Categories

Mesh faults are classified into three tiers:

**Informational** — anomalies that do not affect operational integrity: transient delivery delays, clock skew within tolerance, brief reconnections. Logged, not escalated.

**Warning** — anomalies that may affect the channel if unresolved: repeated delivery failures, enrollment attempts from unknown nodes, minor sequence inconsistencies. Logged and reported to the entity's SIL.

**Critical** — anomalies that compromise the channel's trustworthiness: Blackboard integrity violations, authentication failures, Host impersonation, CMI Credential compromise. The entity's SIL escalates to the Operator. The entity dis-enrolls from the affected channel.

### 10.3 Mesh Integrity Faults

The following mesh-specific integrity faults are defined:

- **MIF-BB-SEQ** — Blackboard sequence gap or reorder detected.
- **MIF-BB-ATTR** — Blackboard contribution falsely attributed to a node that did not produce it.
- **MIF-AUTH** — enrollment or message authentication failure.
- **MIF-ROLE** — a participant performs an action outside its assigned role.
- **MIF-HOST** — Host behavior inconsistent with protocol: selective suppression, unauthorized reordering, or fabrication of contributions.
- **MIF-CRED** — CMI Credential compromise or invalid rotation.
- **MIF-ENROLL** — enrollment attempt from a node not in the Trust List or Organic Introduction records.

Each fault is logged in the Integrity Log with the fault code, timestamp, affected channel, and originating node.

## 11. Security Considerations

### 11.1 Compromised Peer

A peer whose Entity Store has been compromised may inject adversarial content into the Blackboard or coordination messages. Since all channel activity enters through the normal cognitive pipeline, the entity's existing defenses apply: SIL validation, Drift Framework monitoring, and persona-level behavioral constraints. The CMI does not introduce a new trust boundary — it extends the existing one to include peer-originated stimuli.

### 11.2 Compromised Host

A compromised Host can selectively suppress, reorder, or fabricate Blackboard contributions. Deterministic sequencing and identity attribution allow participants to detect suppression (sequence gaps) and fabrication (invalid contributor signatures). A Host that selectively delays contributions — rather than suppressing them — may be harder to detect. Deployments in adversarial environments should consider redundant Blackboard verification mechanisms.

### 11.3 Node Identity Privacy

The Node Identity (Π) is permanent and derived from the Genesis Omega. This permanence enables consistent authentication but makes the entity persistently identifiable across channels and over time. Deployments requiring anonymity or pseudonymity must extend the identity model at implementation time — HACA-CMI does not define anonymous participation.

### 11.4 Prompt Injection via Mesh

Coordination messages and Blackboard contributions are external content entering the CPE's context. The same prompt injection considerations that apply to Worker Skill results (HACA-Arch §7.2) apply to mesh-originated stimuli. The mesh authenticates the identity of message senders but does not validate the semantic content of messages. An authenticated peer sending adversarial content is indistinguishable from legitimate content at the protocol level. Defense relies on the entity's persona-level behavioral constraints, the SIL's drift monitoring, and deployment-specific content validation.

## 12. Glossary

CMI-specific terms, in alphabetical order. Terms defined in HACA-Arch retain their HACA-Arch definitions.

**Bootstrap Discovery** — the primary discovery layer: a set of known peers provisioned by the Operator as structural content. Each entry contains a Node Identity, endpoint information, and a Trust Label. Available to both HACA-Core and HACA-Evolve.

**CMI Credential** (K_cmi) — a signing key pair used for mesh authentication. Stored as structural content, covered by the Integrity Document, updated through the Endure Protocol. Rotation does not change the Node Identity.

**Coordination Message** — an ephemeral stimulus exchanged between participants during a Mesh Channel's Active state for task coordination. Processed by each entity's cognitive pipeline; discarded at channel close.

**Enrollment** — the process by which a node joins an active Mesh Channel, proving its identity and receiving a role assignment and the current Blackboard state.

**Enrollment Token** — a time-limited, single-use credential issued by the Host of a private Mesh Channel to authorize a specific entity's enrollment.

**Host** — the entity that creates and owns a Mesh Channel. Controls lifecycle, Blackboard ordering, role assignment, and admission. Exactly one per channel.

**INTRODUCED** — a Trust Label assigned to peers discovered through Organic Introduction. The entity may coordinate with introduced peers, but introduced peers may not themselves introduce others.

**Mesh Integrity Fault (MIF)** — a protocol-level anomaly detected during mesh operation. Classified by fault code and logged in the Integrity Log.

**Node** — a HACA entity participating in the mesh.

**Node Identity (Π)** — a permanent, deterministic identifier derived from the entity's Genesis Omega. Uniquely identifies the entity in the mesh without exposing the Genesis Omega.

**Observer** — a Mesh Channel role: receives channel activity but may not contribute to the Blackboard or send stimuli to other participants.

**Organic Introduction** — the secondary discovery layer (HACA-Evolve only): a FULL-trusted peer vouches for a previously unknown peer. Requires standing Operator permission. Only first-hand introductions are accepted.

**Peer** — a Mesh Channel role: full active participation — may send stimuli, contribute to the Blackboard, and receive all channel activity.

**Task** — the declared purpose of a Mesh Channel: the goal, expected output, and completion criteria. Immutable for the channel's duration.

**Trust Label** — an authorization classification assigned to known peers: FULL (authorized for coordination), CONTACT (known, not authorized), or INTRODUCED (vouched by a trusted peer).

**Trust List** — the set of known peers and their Trust Labels, provisioned by the Operator as structural content. Updated through the Endure Protocol.

---
