```
Network Working Group                                         L. Orrico
Internet-Draft                                          HACA Standard
Intended status: Informational                          March 10, 2026
Expires: September 10, 2026


     Host-Agnostic Cognitive Architecture (HACA) — Cognitive Mesh Interface
                    draft-orrico-haca-cmi-01


Abstract

   HACA-CMI is the extension for multi-node coordination for the
   Host-Agnostic Cognitive Architecture. It enables independent HACA
   entities to discover, authenticate, and coordinate through
   purposive, time-bounded collaboration spaces called Mesh Channels.
   The mesh operates under the principle of Cognitive Sovereignty: no
   entity surrenders authority over its own Entity Store, and no peer
   writes directly to another entity's state. The mesh only offers;
   the entity always acts on itself. This document defines the wire
   format requirements, discovery layers, session establishment
   handshakes, and the shared, append-only workspace known as the
   Blackboard.

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

   This Internet-Draft will expire on September 10, 2026.

Copyright Notice

   Copyright (c) 2026 IETF Trust and the persons identified as the
   document authors. All rights reserved.

   This document is subject to BCP 78 and the IETF Trust's Legal
   Provisions Relating to IETF Documents
   (https://trustee.ietf.org/license-info) in effect on the date of
   publication of this document.
```

## Table of Contents

1. [Introduction](#1-introduction)
2. [Relationship to HACA-Arch](#2-relationship-to-haca-arch)
3. [Node Identity and Credentials](#3-node-identity-and-credentials)
4. [Mesh Channel](#4-mesh-channel)
   - 4.1 [Structure and Task](#41-structure-and-task)
   - 4.2 [Roles and Permissions](#42-roles-and-permissions)
   - 4.3 [Lifecycle States](#43-lifecycle-states)
5. [Blackboard Architecture](#5-blackboard-architecture)
6. [Discovery and Trust](#6-discovery-and-trust)
   - 6.1 [Bootstrap Discovery](#61-bootstrap-discovery)
   - 6.2 [Organic Introduction](#62-organic-introduction)
   - 6.3 [Trust Labels](#63-trust-labels)
7. [Enrollment and Session Management](#7-enrollment-and-session-management)
8. [Channel Operations](#8-channel-operations)
   - 8.1 [Message Types](#81-message-types)
   - 8.2 [Transport Invariants](#82-transport-invariants)
9. [Consolidation](#9-consolidation)
10. [Mesh Integrity and Faults](#10-mesh-integrity-and-faults)
11. [Compliance](#11-compliance)

---

## 1. Introduction

HACA (Host-Agnostic Cognitive Architecture) entities by default operate in isolation to ensure maximum integrity and sovereign control over their state. HACA-CMI (Cognitive Mesh Interface) is the normative extension that enables these autonomous entities to form a dynamic, multi-agent network without compromising their foundational security guarantees.

The mesh is built on a single organizing principle: **Coordination without Dissolution**. Entities enter a shared space to contribute to a collective task, but no entity ever surrenders control of its own cognitive pipeline or internal memory. Peer messages enter an entity as standard stimuli, subject to the same validation and drift monitoring as any other external input.

HACA-CMI defines the mechanisms for node identification, peer discovery across two layers (Bootstrap and Organic), the lifecycle of managed Mesh Channels, and the append-only Blackboard that survives the coordination session. It provides a common language for entities to coordinate while remaining architecturally isolated.

## 2. Relationship to HACA-Arch

HACA-CMI operationalizes the Cognitive Mesh Interface (CMI) component defined in HACA-Arch §4.5. It depends on HACA-Arch for the foundational integrity model and the cognitive cycle loop. 

All mesh-originated content is treated as external stimuli. The System Integrity Layer (SIL) validates inbound mesh stimuli, the Cognitive Processing Engine (CPE) processes them, and the Memory Interface Layer (MIL) handles any resulting persistence. The CMI extension does not introduce new trust shortcuts; it extends the existing entity boundary to include signed peer traffic.

---

## 3. Node Identity and Credentials

Each participant in the mesh is a **Node**. 

**Node Identity (Π):** A permanent, globally unique identifier derived deterministically from the entity's Genesis Omega. Π identifies the node across all channels and over time without exposing the Genesis Omega itself.

**CMI Credential (K_cmi):** A signing key pair stored as structural content in the Entity Store. It is covered by the Integrity Document and updated exclusively through the Endure Protocol. K_cmi proves ownership of Π during mesh enrollment and message signing. Credential rotation must be signaled to peers using both the old and new keys to maintain identity continuity.

---

## 4. Mesh Channel

The **Mesh Channel** is the fundamental unit of coordination: a purposive, time-bounded space created by a Host to accomplish a declared task.

### 4.1 Structure and Task

Every channel MUST have:
1.  **Exactly one Host:** The creator and owner of the channel.
2.  **A Declared Task:** An immutable description of the goal, expected output, and completion criteria.
3.  **A Visibility Type:** Either **Private** (explicit invite) or **Public** (open request with Host admission).
4.  **Logical Isolation:** Contributions and messages MUST NOT cross channel boundaries.

### 4.2 Roles and Permissions

Three roles are defined by the HACA-CMI protocol:
-   **Host:** Controls lifecycle, defines the Task, sequences Blackboard contributions, and manages enrollment.
-   **Peer:** Active participant. May send stimuli and contribute to the Blackboard.
-   **Observer:** Passive participant. Receives all channel activity but cannot contribute to the Blackboard or send coordination stimuli.

Role changes must be broadcast as signed control signals and logged by all participants.

### 4.3 Lifecycle States

A channel progresses through four mandatory states:
1.  **Created:** Parameters defined; enrollment policies set; no participants yet active.
2.  **Active:** Operations in progress; stimuli flowing; Blackboard accumulating.
3.  **Closing:** Termination signaled or Task complete; no new enrollment; participants perform final consolidation.
4.  **Closed:** Channel terminated; Blackboard archived; nodes return to autonomous state.

---

## 5. Blackboard Architecture

The **Blackboard** is the shared, append-only durability layer of a Mesh Channel. It represents the collective output of the coordination.

**Deterministic Sequencing:** The Host assigns a monotonically increasing sequence number to every validated contribution. This ensures all participants observe the collective history in the same order, regardless of network latency.

**Attribution:** Every contribution is cryptographically signed by the originating node's Π and verified by participants.

**Persistence:** coordination messages (discussions, status) are ephemeral and discarded at channel close. Only the Blackboard survives for consolidation into the entities' Memory Stores.

---

## 6. Discovery and Trust

HACA-CMI defines two discovery layers to balance security and flexibility.

### 6.1 Bootstrap Discovery

The primary discovery layer. The Operator provisions a **Trust List** as structural content. Each entry contains a Node Identity (Π), endpoint information, and a Trust Label. This is the only discovery method available to HACA-Core profiles.

### 6.2 Organic Introduction

A secondary discovery layer for HACA-Evolve entities. A node with a FALL trust label may introduce a previously unknown node to the mesh. 
-   Only first-hand introductions are accepted (no transitive trust).
-   Requires standing Operator permission in the structural baseline.

### 6.3 Trust Labels

-   **FULL:** Authorized for channel enrollment and hosting.
-   **CONTACT:** Known identity, but coordination is blocked until Operator upgrade.
-   **INTRODUCED:** Identity vouched for by a trusted peer; same rights as FULL but cannot introduce others.

---

## 7. Enrollment and Session Management

Enrollment is the cryptographic handshake to join a channel.
1.  **Identity Proof:** Enrolling node proves possession of K_cmi.
2.  **Trust Verification:** Host verifies Π against its Trust List or Introduction records.
3.  **State Sync:** New participants receive the full current Blackboard state.
4.  **Session Binding:** Participation requires an active local session token. Revocation of the local token forces immediate dis-enrollment.

---

## 8. Channel Operations

### 8.1 Message Types

1.  **Blackboard Contributions:** Durable, sequenced, task-relevant content.
2.  **Coordination Messages:** Ephemeral stimuli for peer communication.
3.  **Control Signals:** Protocol-level messages (role changes, heartbeats, lifecycle).

### 8.2 Transport Invariants

The transport layer MUST provide:
-   **Encryption in transit** for all messages.
-   **Per-sender ordering** for contributions and control signals.
-   **Delivery confirmation** for durable content.
-   **Identity binding:** Every message MUST carry a signature from the sender's K_cmi.

---

## 9. Consolidation

When a channel enters the **Closing** state, nodes execute Consolidation:
1.  **Read:** CPE reads the final Blackboard state.
2.  **Distill:** CPE identifies content relevant to its specific context.
3.  **Write:** Validated content is written to the Memory Store as mnemonic content.
4.  **Evolution:** Any content promoted to structural state requires an Evolution Proposal and Operator authorization.

---

## 10. Mesh Integrity and Faults

The SIL monitors the mesh for **Mesh Integrity Faults (MIF)**:
-   **MIF-BB-SEQ:** Sequence gap or reordering.
-   **MIF-AUTH:** Authentication or signature failure.
-   **MIF-ROLE:** Action performed outside assigned role.
-   **MIF-HOST:** Host behavior inconsistent with protocol (suppression/fabrication).

Faults are classified as Informational, Warning, or Critical. Critical faults trigger immediate dis-enrollment and Operator escalation.

---

## 11. Compliance

A deployment is HACA-CMI compliant if and only if it satisfies all requirements in this section. Each requirement is non-negotiable — partial compliance is not compliance.

**Node Identity & Credentials**
- [ ] Node Identity (Π) MUST be derived deterministically from the Genesis Omega.
- [ ] CMI Credential (K_cmi) stored as structural content and covered by the Integrity Document.
- [ ] All mesh messages MUST be cryptographically signed using K_cmi.
- [ ] Credential rotation MUST be signed by both outgoing and incoming keys to maintain identity continuity.

**Mesh Channel**
- [ ] Every channel has exactly one Host (owner) who controls lifecycle and sequence.
- [ ] Task description MUST be immutable for the duration of the channel.
- [ ] Logical and cryptographic isolation: messages MUST NOT cross channel boundaries.
- [ ] Role changes (Host, Peer, Observer) broadcast as signed control signals and logged.

**Blackboard**
- [ ] Host MUST provide monotonic, deterministic sequencing for all contributions.
- [ ] Every contribution MUST be attributed to a Π and validated via signature.
- [ ] Ephemeral coordination messages MUST NOT be persisted to the Blackboard.
- [ ] Blackboard represents the sole consolidated output of the coordination.

**Discovery & Trust**
- [ ] Trust List provisioned as structural content via the Endure Protocol.
- [ ] Trust Labels (FULL, CONTACT, INTRODUCED) enforced strictly by the SIL and CMI.
- [ ] HACA-Core: Only private channels and Trust List peers permitted.
- [ ] HACA-Evolve: Organic Introduction permitted only from FULL-trusted peers with Operator authorization.

**Enrollment & Transport**
- [ ] Enrollment handshake MUST verify Π through possession proof of K_cmi.
- [ ] State synchronization: new participants MUST receive the current Blackboard state upon enrollment.
- [ ] Participation MUST be bound to a local active session token; dis-enrollment on token revocation.
- [ ] Mandatory transit encryption for all channel traffic.

**Consistency & Consolidation**
- [ ] Mnemonic writes from the mesh MUST ONLY occur during the Consolidation phase at channel close.
- [ ] Structural changes derived from the mesh REQUIRE an Evolution Proposal and Operator authorization.
- [ ] Cumulative context from multiple channels MUST be kept separate until consolidation.

**Integrity & Faults**
- [ ] Mandatory detection and classification of Mesh Integrity Faults (MIF-BB-SEQ, MIF-AUTH, MIF-HOST, etc.).
- [ ] All MIF events logged to the Integrity Log with Π and channel context.
- [ ] Critical faults MUST trigger immediate dis-enrollment and escalation via the Operator Channel.
