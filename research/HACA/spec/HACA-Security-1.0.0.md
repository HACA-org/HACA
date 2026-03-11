Network Working Group                                          J. Orrico
Internet-Draft                                             HACA Standard
Intended status: Informational                         February 25, 2026
Expires: August 25, 2026


   Host-Agnostic Cognitive Architecture (HACA) v1.0 — Security Hardening
                    draft-orrico-haca-security-04

Abstract

   This document specifies the security hardening extensions for the
   Host-Agnostic Cognitive Architecture (HACA) v1.0. It defines the
   Byzantine host threat model, cryptographic auditability requirements,
   and temporal attack detection mechanisms.

   This document is a companion to HACA-Arch (draft-orrico-haca-arch-07)
   and applies to any deployment regardless of which Cognitive Profile
   is active (HACA-Core or HACA-Symbiont). An implementation MUST
   first satisfy compliance with its chosen Cognitive Profile before
   applying the extensions defined here.

Status of This Memo

   This is a draft of the HACA-Security specification. It is intended
   for review and comment by the HACA working group.

   This Internet-Draft is submitted in full conformance with the
   provisions of BCP 78 and BCP 79.

Table of Contents

   1.  Introduction
   2.  Conventions and Terminology
   3.  Applicability
   4.  Byzantine Host Model
       4.1. Threat Taxonomy
       4.2. Verification Requirements
   5.  Cryptographic Auditability
       5.1. Hash-Linked Log Structure
       5.2. Performance Considerations
       5.2.1. Hash Chain Checkpoints
       5.3. Verification
       5.4. Tamper Fault Remediation
   6.  Temporal Attack Detection
       6.1. Monotonic Timestamp Validation (REQUIRED)
       6.2. Logical Clocks (RECOMMENDED)
       6.3. Chain-Based Ordering
   7.  Trust Model (Hardened)
       7.1. Host Trust: Byzantine (Zero Default)
       7.2. Elevated SIL Anchor Requirements
       7.3. Cryptographic Key Management
       7.3.1. CMI Enrollment Key (K_cmi) Management
       7.3.2. Algorithm Requirements
       7.4. Rollback Attack Protection
   8.  Side-Channel Considerations
       8.1. Confidentiality (Data at Rest)
       8.2. MIL Compaction and Hash Chain Interaction
   9.  Fault Taxonomy (Extension)
   10. Compliance and Verification
   11. Implementation Guidance (INFORMATIVE)
       11.1. Hash Chain Batching Defaults
       11.2. Checkpoint Intervals
       11.3. Key Rotation Defaults
       11.4. Rollback Counter Storage
       11.5. Side-Channel Mitigation Examples
   12. IANA Considerations
   13. Normative References
   14. Author's Address

1.  Introduction

   HACA-Arch (draft-orrico-haca-arch-07) defines a trust model where
   the Host is assumed to be cooperative but potentially faulty. This
   is sufficient for most deployments where the system operator
   controls the host environment.

   However, certain deployment scenarios require stronger guarantees:

   o  Multi-tenant cloud environments where the Host is operated by
      a third party.
   o  Environments where the cognitive system handles sensitive data
      and must provide tamper-evident audit trails.
   o  Scenarios where the Host may be compromised by an external
      attacker.

   HACA-Security elevates the trust model from "semi-trusted" to
   "Byzantine" (zero default trust) and adds cryptographic mechanisms
   for auditability and temporal integrity.

   NOTE: The security requirements defined in this document address
   a tension that is not unique to engineered systems. Wiener's
   cybernetics [Wiener1948] observed that autonomous feedback systems
   can resist correction or escape human control when self-stabilizing
   mechanisms are not properly bounded. HACA-Arch resolves this
   through the invariant that self-preservation MUST NOT override
   user authority; HACA-Security operationalizes that invariant under
   adversarial conditions, where a compromised Host might attempt to
   fabricate the audit record that operators rely on to exercise
   authority.

   The integrity of persistent state — cryptographically enforced
   by the hash-linked log structure in Section 5 — also bears on
   identity continuity. Enactivist accounts of cognition [Varela1991]
   argue that cognitive identity is maintained through operational
   closure: the continuous self-production of organizational structure.
   Memory authentication, as specified here, is the computational
   analog: it ensures that the organizational record the system relies
   on to reconstitute itself is the same record produced by prior
   operation, preventing silent substitution of a different identity.

   Note on CPE-Host Separation: The Byzantine model is most effective
   when the CPE and Host are physically separable (e.g., the CPE runs
   on dedicated hardware or is accessed via a trusted API with
   independent integrity guarantees). When the CPE runs directly on
   the Host (e.g., a local inference engine on the same machine), the
   system cannot fully verify CPE outputs against Host manipulation,
   as the verification tools themselves run on the potentially
   compromised Host. Implementations in this configuration SHOULD
   document the residual trust assumptions and MAY rely on external
   attestation (e.g., TPM-based remote attestation) to partially
   bridge this gap.

2.  Conventions and Terminology

   The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT",
   "SHOULD", "SHOULD NOT", "RECOMMENDED", "MAY", and "OPTIONAL" in this
   document are to be interpreted as described in BCP 14 [RFC2119]
   [RFC8174] when, and only when, they appear in all capitals, as
   shown here.

   Terms defined in HACA-Arch, HACA-Core, and HACA-Symbiont apply
   unchanged. Additional terms:

   o  Byzantine Host: A host environment that may exhibit arbitrary
      faulty or malicious behavior, including omission, commission,
      and timing faults.
   o  Temporal Fault: A detected inconsistency in timestamp ordering
      that indicates potential temporal manipulation.
   o  Hash Chain: An append-only log where each entry references the
      cryptographic hash of the previous entry, forming a
      tamper-evident sequence.

3.  Applicability

   HACA-Security extensions are OPTIONAL for HACA-Core and HACA-Symbiont
   compliance. They are REQUIRED for HACA-Full compliance (HACA-Arch Section 9).

   Implementations SHOULD adopt HACA-Security when any of the
   following conditions apply:
   o  The Host is not under the operator's direct control.
   o  Regulatory or contractual requirements mandate tamper-evident
      audit trails.
   o  The system operates in a multi-tenant or shared-infrastructure
      environment.
   o  The system participates in a Cognitive Mesh via HACA-CMI
      ([HACA-CMI]), where peer nodes may be independently operated
      and cannot be assumed cooperative. The Byzantine Host Model
      (Section 4) applies to the Session Host in the same way it
      applies to the local execution Host: both may exhibit arbitrary
      faulty or malicious behavior.

4.  Byzantine Host Model

   The system MUST assume the Host is potentially malicious or faulty.
   This extends HACA-Arch's semi-trusted model (HACA-Arch Section 5.1)
   to zero default trust.

   Note on Scope: Unlike classical Byzantine Fault Tolerance (BFT),
   which addresses consensus among $n$ replicas tolerating $f$
   Byzantine actors, HACA-Security addresses a single cognitive
   system operating on a single potentially adversarial Host. There
   is no multi-party consensus problem. The term "Byzantine" is used
   here in its original sense (Lamport 1982): the Host may exhibit
   arbitrary faulty behavior — including omission, commission,
   timing faults, and deliberate deception — without any assumption
   of rationality or cooperation. The system's defense relies on
   cryptographic verification and independent integrity anchors
   rather than on redundancy or voting.

   4.1. Threat Taxonomy

   The system MUST implement detection mechanisms for:

   o  I/O Manipulation: Dropping, replaying, or altering messages
      between the system and external services.
   o  Storage Corruption: Modifying MIL contents at rest.
   o  Temporal Attacks: Providing false timestamps to disrupt
      scheduling or log ordering (see Section 6).
   o  Boot Subversion: Altering immutable components before boot.

   For deployments using HACA-CMI, the following additional threat
   categories apply:

   o  Compromised Peer Contributions: A peer node in a Session may
      post adversarially crafted Blackboard Contributions designed
      to cause identity drift, exfiltrate cognitive state, or inject
      instructions into the receiving node's CPE. The SIL drift gate
      (HACA-CMI Section 8.2) is the primary defense; this document's
      sequence counter requirements (Section 4.2) MUST be extended
      to cover CMI message channels.
   o  Compromised Session Host: The Session Host controls Blackboard
      ordering (host_seq), role assignment, and Contribution rejection.
      A Byzantine Session Host can reorder, suppress, or selectively
      deliver Contributions without cryptographic detection unless
      per-actor hash chains (Section 5.2) are applied to the
      cmi/audit/ namespace. See HACA-CMI Section 12.4 for the full
      Session Host threat analysis.
   o  Session Commit Integrity: The Session Commit protocol
      (HACA-CMI Section 8.2) writes multiple namespaces atomically
      to the MIL. Each namespace write MUST be covered by this
      document's hash-chain integrity (Section 5). A partial commit
      that passes only some namespace writes without updating the
      chain constitutes a Tamper Fault.

   For deployments using the HACA-Symbiont Cognitive Profile
   ([HACA-SYMBIONT]), the following additional threat categories apply:

   o  Heartbeat Manipulation: The HACA-Symbiont Heartbeat Protocol
      (HACA-Symbiont Section 7) depends on the Host delivering timely,
      authentic Heartbeat signals to the SIL. A Byzantine Host may
      suppress Heartbeat signals to force premature Stasis or Amputation
      responses, or conversely, forge spurious Heartbeat signals to
      prevent legitimate Stasis from firing when the Pain threshold
      P(t) has been reached. Under the Byzantine Host Model, the SIL
      MUST NOT rely on Host-provided Heartbeat signals as the sole
      trigger for health state transitions. Implementations SHOULD
      supplement Heartbeat with an independently anchored timer (e.g.,
      a hardware RTC or a monotonically increasing counter in the DSS)
      to detect Heartbeat suppression. Heartbeat messages MUST carry
      a sequence counter subject to Section 4.2 replay detection.

   o  Tier 3 Integration Poisoning: The HACA-Symbiont Endure Protocol
      (HACA-Symbiont Section 6) promotes Tier 2 semantic content to
      Tier 3 (Core Integration), which permanently mutates Omega. A
      Byzantine Host may inject adversarially crafted content at the
      Tier 2 → Tier 3 boundary to cause unauthorized identity drift.
      The Immune Rollback mechanism (HACA-Symbiont Section 6.3)
      provides containment at the profile level; under the Byzantine
      Host Model, the Ontological Snapshot (HACA-Symbiont Section 6.1)
      taken before each Tier 3 integration MUST be hash-chain-protected
      per Section 5 of this document, so that a corrupted integration
      candidate can be identified and rolled back with verifiable
      authenticity.

   o  Operator Re-binding Hijacking: The Operator Re-binding Recovery
      Protocol (HACA-Symbiont Section 7.5) allows a new Operator
      binding when the original Operator key is lost. A Byzantine Host
      may attempt to trigger this protocol artificially to substitute
      an adversarial Operator binding. Implementations MUST require
      out-of-band operator verification (e.g., hardware-signed
      re-binding token per Section 7.2 of this document) before
      executing the re-binding protocol. The re-binding event MUST
      be hash-chain-logged per Section 5.

   4.2. Verification Requirements

   When operating under the Byzantine Host Model, the SIL CANNOT be
   executed in the same unprivileged user-space or kernel-space as
   the Host OS. The SIL's cryptographic validation phase MUST be
   anchored in a verifiable hardware enclave (TEE) or an external
   trusted attestation server. Relying purely on software-level
   hashing executed by a potentially compromised host invalidates
   the Byzantine defense.

   Note: Active Confinement (LotL/unshare) as defined in HACA-Core
   Axiom VII provides protection against unprivileged host environment
   faults, but does not satisfy the Byzantine Host Model requirements
   without the hardware anchors specified above. For HACA-Symbiont
   deployments using Transparent CPE topology, Active Confinement
   applies equivalently. For HACA-Symbiont deployments using Opaque
   CPE topology, Active Confinement is inapplicable (HACA-Arch
   Section 5.4 Step 3); the hardware anchor requirement is therefore
   the primary Byzantine defense and is mandatory.

   Opaque CPE Audit Scope (HACA-Symbiont only): When a HACA-Symbiont
   deployment operates under an Opaque CPE topology (HACA-Arch Section
   3.3.1), the cryptographic auditability requirements of Section 5
   MUST be applied exclusively at the I/O boundary of the CPE. The
   SIL attests to the integrity and ordering of CPE inputs and outputs;
   it cannot attest to internal cognitive derivation, which is by
   definition not observable. This is a fundamental and acknowledged
   limitation of the Opaque topology.

   Implementations operating in this configuration MUST:
   a) Explicitly declare in their compliance statement that SIL
      auditability covers CPE I/O boundaries only, not internal
      reasoning.
   b) NOT claim full Byzantine-grade cognitive auditability. The
      attestation boundary MUST be clearly scoped in all compliance
      documentation.
   c) Apply the hash-chain integrity of Section 5 to the inputs
      delivered to the CPE and to the outputs received from it, so
      that the record of what the CPE was asked and what it answered
      is tamper-evident, even if the derivation between the two is not.

   This limitation does not prevent HACA-Symbiont Opaque deployments
   from achieving HACA-Full compliance; it requires that such
   deployments accurately represent their audit scope rather than
   claiming guarantees they cannot provide.

   The system MUST cryptographically verify all data retrieved from
   the Host against known checksums or expected schemas before
   incorporating it into MIL state.

   For MIL data at rest, implementations MUST use one of:
   o  Per-record HMAC signatures (keyed with a secret stored outside
      the Host's reach, e.g., hardware keystore or remote KMS).
   o  Hash-chained logs (Section 5) where tampering with any entry
      invalidates all subsequent entries.

   For I/O manipulation detection, implementations MUST maintain
   sequence counters on all message channels and detect gaps or
   replays:

   o  Each directional channel (e.g., CPE -> EL, EL -> MIL) MUST
      maintain a monotonically increasing 64-bit sequence counter.
   o  The counter MUST be incremented for every message sent on
      the channel and included in the message envelope.
   o  The receiver MUST verify that the received sequence number
      equals the expected next value. A gap indicates message
      omission; a duplicate indicates replay.
   o  Sequence counters MUST be persisted securely and restored
      during boot. The counter state MUST be tracked in a Dynamic
      Sentinel Stream or hash chain metadata to prevent counter reset
      attacks, and MUST NOT be forced into the static Integrity Record.

   MIL Write and Hash Atomicity: Under the Byzantine Host Model, a
   Host with write access to the storage layer may modify MIL data
   between the moment the MIL completes a write and the moment the
   SIL appends the corresponding hash chain entry — a Time-of-Check
   to Time-of-Use (TOCTOU) window. To eliminate this window,
   implementations MUST satisfy one of the following conditions:

   a) Atomic commit: The MIL write and the SIL hash chain append MUST
      be executed as a single atomic operation within the storage
      layer. If the storage backend supports transactions (e.g., a
      database with ACID guarantees), the write and the hash update
      MUST be in the same transaction. If the storage backend does not
      support transactions, implementations MUST use an equivalent
      mechanism (e.g., write-then-rename with the hash computed over
      the final content before the rename commits the write).

   b) TEE-anchored sealing: If the SIL runs within a hardware enclave
      (TEE) per Section 4.2, the hash MAY be computed by the enclave
      immediately upon receiving the write, before control returns to
      the Host. In this configuration, the Host cannot modify the data
      between hash computation and chain append because both operations
      occur inside the trusted boundary.

   Implementations that cannot satisfy either condition MUST document
   the residual TOCTOU window in their compliance statement and treat
   all MIL reads during boot verification as potentially tampered until
   the hash chain confirms integrity.

5.  Cryptographic Auditability

   The transactional log of the MIL MUST be cryptographically chained
   to ensure a verifiable cognitive history.

   5.1. Hash-Linked Log Structure

   Each log block MUST reference the cryptographic hash of the
   previous block, forming a tamper-evident chain:

   o  Block $n$: $H_n = \text{Hash}(H_{n-1} \| \text{block\_data}_n)$
   o  The genesis block uses a well-known seed value (RECOMMENDED:
      the hash of the system's $\Omega$ at provisioning time).
   o  The hash algorithm MUST be SHA-256 or stronger, as specified
      in Section 7.3.1.

   5.2. Performance Considerations

   Hash-chaining introduces a read-before-write dependency: each
   append requires reading the previous entry's hash. This conflicts
   with O(1) append semantics and concurrent writers.

   Implementations MAY mitigate this via:
   o  Batched chaining: A block contains $B$ entries, with individual
      entries within a batch using per-entry checksums.
   o  Per-actor chains: in mesh configurations, each actor maintains
      its own hash chain, merged at synchronization points. For
      HACA-CMI deployments specifically, "per-actor" means per-node:
      each node maintains an independent hash-chained log covering
      its cmi/audit/ namespace (Session Artifacts). Session Artifacts
      MUST be appended to the node's audit chain in host_seq order.
      The "synchronization point" is the Session Commit boundary
      (HACA-CMI Section 8.2.3): all artifact writes for a given
      Session MUST be committed as a single chain append before the
      node participates in a new Session.

   The chosen strategy MUST be documented and its integrity
   implications analyzed. Note: Batched chaining creates an
   integrity window of $B-1$ entries within each batch where
   integrity relies solely on per-entry checksums, which are not
   cryptographic and do not protect against intentional forgery.
   This is an accepted trade-off for O(1) append performance.
   Implementations requiring per-entry cryptographic integrity
   MUST use $B = 1$ (full chaining) and accept the read-before-write
   cost.

   5.2.1. Hash Chain Checkpoints

   Full hash chain replay from genesis (Section 5.3) is O(n) in the
   number of log entries, which becomes prohibitive for long-running
   systems. To enable incremental verification at boot:

   o  Implementations SHOULD create periodic hash chain checkpoints
      at configurable intervals.
   o  A checkpoint is a signed record containing: the entry index,
      the cumulative hash at that entry, and a timestamp. Checkpoints
      MUST be protected by the same signing key as the chain.
   o  During boot, the SIL MAY verify from the most recent
      checkpoint rather than from genesis, reducing verification
      to O(n - c) where $c$ is the checkpoint entry index.
   o  Full genesis-to-tip verification MUST still be performed at
      least once per operator-defined audit interval.
   o  Checkpoints MUST be persisted within the Dynamic Sentinel Stream
      (HACA-Arch Section 2) or signed independently. By nature, they
      are generated dynamically and MUST NOT be forced into the static
      Integrity Record. An attacker who can forge a checkpoint can
      bypass all subsequent verification, so checkpoint signature
      integrity is critical.

   5.3. Verification

   During boot, the SIL MUST replay the hash chain from the genesis
   entry (or most recent checkpoint per Section 5.2.1) and verify
   each link. Any broken link MUST abort boot and signal a Tamper
   Fault.

   5.4. Tamper Fault Remediation

   When a Tamper Fault is triggered (broken hash chain link detected
   during boot verification), the system is in a Halted state and
   cannot boot. To restore normal operation, the following remediation
   protocol applies:

   a) Forensic Preservation: Before any remediation, the operator
      SHOULD preserve the corrupted MIL state and hash chain for
      forensic analysis. The corrupted data MAY contain evidence of
      the attack vector.

   b) Remediation Options (in order of preference):
      1. Checkpoint Rollback: If hash chain checkpoints (Section
         5.2.1) are available, the operator MAY restore the chain
         to the most recent valid checkpoint. All entries after the
         checkpoint are discarded. The operator MUST then verify
         the restored cognitive state has not been compromised:
         for HACA-Core deployments, by executing a full drift probe
         cycle (HACA-Core Section 5.3, with full probe set per
         Section 5.6); for HACA-Symbiont deployments, by triggering
         a full Heartbeat health assessment (HACA-Symbiont Section 7)
         with all health metrics recalibrated against the restored
         state and the Immune Rollback protocol (HACA-Symbiont
         Section 6.3) invoked if the P(t) threshold is exceeded.
      2. Full Chain Re-provisioning: If no valid checkpoint exists
         or the corruption predates all checkpoints, the operator
         MUST provision a clean MIL state with a new genesis entry
         anchored to the current $\Omega$. This discards all
         accumulated cognitive context.

   c) Post-Remediation Verification: After remediation, the SIL
      MUST perform a full hash chain replay from genesis (or the
      restored checkpoint) and verify all links before allowing
      boot to proceed. If verification fails, the system MUST
      remain in Halted state.

   d) Logging: Because the system is in Halted state, remediation
      actions MUST be logged to a host-provided out-of-band audit
      log. Log entries MUST include: the remediation method chosen,
      the location of the broken link (entry index), operator
      identity, and the timestamp of remediation.

6.  Temporal Attack Detection

   The system MUST detect temporal manipulation by the Host. The
   following mechanisms are defined in order of increasing strength:

   6.1. Monotonic Timestamp Validation (REQUIRED)

   Every log entry MUST include a timestamp (ISO 8601 UTC). During
   boot and log rotation, the system MUST verify that sequential
   entries have non-decreasing timestamps. A timestamp regression
   MUST be flagged as a Temporal Fault.

   6.2. Logical Clocks (RECOMMENDED)

   Implementations SHOULD maintain a Lamport timestamp: a
   monotonically increasing counter independent of wall-clock time.
   Each log entry carries the logical clock value at time of write.
   This provides ordering guarantees even when wall-clock timestamps
   are unreliable.

   6.3. Chain-Based Ordering (when Section 5 is implemented)

   When cryptographic log chaining (Section 5) is enabled, the hash
   chain itself provides an immutable ordering guarantee independent
   of any timestamp. This is the strongest temporal integrity
   mechanism and SHOULD be preferred when available.

7.  Trust Model (Hardened)

   For implementations targeting HACA-Full compliance, HACA-Security
   extends and supersedes HACA-Arch Section 5.1 (Host Trust:
   Semi-Trusted) with:

   7.1. Host Trust: Byzantine (Zero Default)

   The Host is assumed to be potentially adversarial. All data from
   the Host MUST be verified before use (Section 4.2). The system
   MUST NOT rely on Host-provided guarantees without independent
   cryptographic verification.

   7.2. Elevated SIL Anchor Requirements

   The SIL's integrity record MUST be verified against an
   out-of-band anchor that the Host cannot modify:
   o  A pre-shared hash distributed through a trusted channel.
   o  A hardware root of trust (e.g., TPM).
   o  An operator signature verified against a public key embedded
      in the SIL binary.

   HACA-Arch's "known anchor" (HACA-Arch Section 5.4 step 1) is
   replaced with these stronger requirements.

   7.3. Cryptographic Key Management

   Implementations MUST define a key management lifecycle for all
   cryptographic material (HMAC signing keys, hash chain seeds,
   integrity record signing keys, and — for HACA-CMI deployments —
   the CMI Enrollment Key $K_{cmi}$; see Section 7.3.1):

   a) Provisioning: Keys MUST be generated outside the Host
      environment and delivered through a trusted channel. Keys
      MUST NOT be stored within the system's operational data store.
      Acceptable storage: hardware keystore (TPM, HSM), remote KMS,
      or operator-controlled external storage.

   b) Rotation: Implementations MUST support key rotation without
      system downtime. The rotation protocol:
      1. Operator provisions the new key via the trusted channel.
      2. A signed rotation event (authenticated with the current
         key) is recorded in the audit log. The rotation event
         MUST contain at minimum: (i) the key purpose identifier
         (Section 7.3d), (ii) a non-reversible identifier of the
         new key (e.g., truncated SHA-256 of the public key or
         HMAC key), (iii) the activation epoch (boot cycle number
         or ISO 8601 UTC timestamp [ISO8601]), and (iv) the
         signature of the event under the current (pre-rotation)
         key. The event MUST NOT contain the new key material
         itself.
      3. From the activation epoch, the SIL validates new entries
         against the new key. Pre-rotation entries are validated
         against the old key.
      4. The old key MUST be retained in a read-only/verify-only
         capacity indefinitely to allow validation of the historical
         hash chain, and MUST be permanently revoked for new signatures.

   c) Compromise Recovery: If a key is suspected compromised:
      1. The operator MUST immediately provision a replacement key.
      2. All entries signed with the compromised key after the
         suspected compromise time MUST be treated as untrusted.
      3. The system MUST execute a full integrity re-verification
         from the last entry signed before the suspected compromise.
      4. A Key Compromise Fault MUST be logged and the system MUST
         NOT resume autonomous operation until operator review.

   d) Key Binding: Each key MUST be bound to a specific purpose
      (e.g., "MIL HMAC", "chain signing", "integrity record",
      "CMI enrollment"). Keys MUST NOT be reused across purposes.

   7.3.1. CMI Enrollment Key ($K_{cmi}$) Management

   For implementations enabling HACA-CMI, the CMI Enrollment Key
   ($K_{cmi}$) MUST be managed under the lifecycle defined in Section
   7.3. Additional constraints:

   a) Storage: $K_{cmi}$ MUST be stored with at least the same
      protection level as the $\Omega$ anchor and the MIL signing
      key. Acceptable storage locations are identical to those in
      Section 7.3a. A $K_{cmi}$ stored within the Host's operational
      data store without hardware protection is incompatible with
      the Byzantine Host Model.

   b) Derivation binding: Node Identity $\Pi = H(\Omega_{anchor}
      \| K_{cmi})$ (HACA-CMI Section 3.1) binds mesh identity to
      Core identity. Compromise of $K_{cmi}$ therefore compromises
      $\Pi$. The Key Compromise Fault protocol (Section 7.3c) MUST
      be applied: halt CMI participation, notify the Operator, and
      rotate $K_{cmi}$ before re-enrolling in any Session.

   c) Rotation: For HACA-S nodes, $\Pi$-Rotation (HACA-CMI Section
      3.1) is triggered by Endure, which rotates $\Omega$ and
      invalidates the prior $\Pi$. $K_{cmi}$ MUST be rotated in the
      same Endure cycle. The rotation MUST be recorded in the
      hash-chain audit log per Section 7.3b.

   d) Purpose isolation: $K_{cmi}$ is exclusively for CMI enrollment
      signatures (HACA-CMI Section 7.1 envelope_sig and ENROLL_CONFIRM
      in Section 6.1.2). It MUST NOT be reused for MIL HMAC, chain
      signing, or any other purpose.

   7.3.2. Algorithm Requirements

   To ensure interoperability and baseline security, implementations
   MUST support the following cryptographic algorithms as mandatory:

   o  HMAC: HMAC-SHA256 (RFC 2104, RFC 6234). Key size MUST be at
      least 256 bits (32 bytes). Implementations MAY additionally
      support HMAC-SHA384 or HMAC-SHA512 for higher security margins.
   o  Hash Functions: SHA-256 for integrity records and hash chains
      (Section 5). Implementations MAY support SHA-384 or SHA-512 as
      alternatives, but MUST declare the algorithm in the integrity
      record (HACA-Arch Section 8) or the hash chain genesis block
      (Section 5.1).
   o  Signing (if operator signatures are used per Section 7.2):
      Ed25519 (RFC 8032) or ECDSA with P-256 (FIPS 186-5). RSA-2048
      is acceptable for legacy compatibility but NOT RECOMMENDED for
      new deployments.

   Implementations MUST NOT use:
   o  MD5 or SHA-1 for any cryptographic purpose (deprecated,
      collision-vulnerable).
   o  HMAC with keys shorter than 128 bits.
   o  Symmetric ciphers with key sizes below 128 bits.

   When selecting algorithms beyond the mandatory set, implementations
   SHOULD prefer algorithms with NIST or IETF standardization and
   MUST document all algorithm choices in their compliance statement.

   Forward Secrecy Limitation: HMAC-based message authentication does
   not provide forward secrecy. If a signing key is compromised, all
   past messages authenticated with that key become forgeable by the
   attacker. Implementations in high-threat environments SHOULD
   rotate keys frequently to limit the window of exposure. Future
   extensions (e.g., ratcheting protocols) may address this
   limitation.

   7.4. Rollback Attack Protection

   An attacker with Host access may attempt to restore an older MIL
   snapshot (rollback attack) to revert the system to a previous
   state, effectively erasing recent cognitive evolution or replaying
   resolved conflicts.

   To detect and prevent rollback attacks:

   o  The SIL MUST maintain a monotonic boot counter, incremented
      at every successful boot and persisted in a Dynamic Sentinel
      Stream (or equivalent dynamic tamper-evident store) rather than
      the static Integrity Record.
   o  The boot counter MUST also be recorded in the hash chain
      (Section 5) at each boot boundary. A boot that observes a
      chain tip with a boot counter lower than the last known value
      MUST signal a Rollback Fault and abort.
   o  Implementations SHOULD store the boot counter in at least two
      independent locations so that a single-point rollback does not
      defeat the counter.
   o  Snapshot restore (HACA-Core Axiom VI; for HACA-Symbiont, the
      Ontological Snapshot per HACA-Symbiont Section 6.1 and the
      Immune Rollback per Section 6.3) MUST update the boot counter
      to the current value after restore, not the snapshot's original
      value. A snapshot that references a boot counter higher than
      the current counter MUST be rejected as corrupt or from the
      future. For HACA-Symbiont deployments, the Ontological Snapshot
      taken before each Tier 3 integration constitutes a rollback
      anchor and MUST be hash-chain-protected per Section 5 so that
      rollback targets can be independently verified.

8.  Side-Channel Considerations

   HACA-Security primarily addresses data-plane integrity (storage,
   I/O, temporal ordering). However, implementations in high-threat
   environments SHOULD also consider the following side-channel
   risks:

   o  Timing Attacks: Cryptographic operations (HMAC verification,
      hash chain validation) SHOULD use constant-time comparison
      functions to prevent timing-based key extraction.
   o  Memory Residue: Sensitive cryptographic material (signing
      keys, HMAC secrets) SHOULD be zeroed from memory after use.
      Implementations in managed-memory languages SHOULD document
      this limitation, as garbage-collected runtimes cannot guarantee
      memory erasure.
   o  Electromagnetic and Power Analysis: These attacks are generally
      out of scope for software-only mitigations. Implementations
      handling classified or high-value data SHOULD deploy on
      hardware with side-channel protections and document the
      hardware security profile.

   This section is advisory. Side-channel mitigations are not
   required for HACA-Full compliance but are RECOMMENDED for
   deployments in adversarial physical environments.

8.1. Confidentiality (Data at Rest)

   HACA-Security primarily addresses integrity and auditability.
   However, MIL data at rest may contain sensitive information
   (user conversations, reasoning traces, credentials delegated
   via skills). Implementations SHOULD encrypt MIL data at rest
   using AES-256-GCM [NIST-GCM] or equivalent authenticated encryption.

   Key management for encryption at rest SHOULD follow the same
   lifecycle requirements as signing keys (Section 7.3). When
   both integrity (HMAC/hash chain) and confidentiality (encryption)
   are applied, implementations MUST apply encryption first and
   integrity second (encrypt-then-MAC), so that integrity
   verification does not require decryption.

   Boot Verification Implication: When encrypt-then-MAC is used, the
   hash chain (Section 5) operates over ciphertext. During boot, the
   SIL MUST be able to verify chain integrity (Section 5.3) without
   decrypting the data payload — the chain hashes cover the encrypted
   form. To enable this, the log entries MUST separate public metadata
   (e.g., previous hash, sequence index, timestamp) from the
   encrypted payload. Decryption is only required when the CPE needs
   to read MIL contents during operational execution. Implementations
   MUST ensure that the encryption key is not required for boot
   integrity verification to succeed.

   Confidentiality at rest is not required for HACA-Full compliance
   but is RECOMMENDED for deployments handling sensitive data.

8.2. MIL Compaction and Hash Chain Interaction

   HACA-Arch Section 5.6.2 recommends MIL compaction to manage
   storage growth. When cryptographic log chaining (Section 5) is
   enabled, compaction and rotation MUST preserve hash chain
   integrity:

   o  Compaction MUST NOT delete or modify entries that are part of
      the active hash chain. Compacted entries MUST be replaced with
      a summary record that includes the hash of the compacted range,
      preserving chain continuity.
   o  Log rotation MUST create a new chain segment anchored to the
      final hash of the previous segment. The anchor point MUST be
      recorded as a checkpoint (Section 5.2.1).
   o  Implementations that cannot preserve chain integrity during
      compaction MUST disable automatic compaction and rely on
      manual operator-initiated archival instead.

   Failure to account for this interaction may result in Tamper Faults
   on boot when the SIL replays the hash chain and encounters
   missing or modified entries.

9.  Fault Taxonomy (Extension)

   HACA-Security extends the fault taxonomy defined in HACA-Core
   Section 7 and HACA-Symbiont Section 9 with the following additional
   fault types:

   Fault Type          | Trigger                        | State          | Required Action
   --------------------|--------------------------------|----------------|---------------------------
   Temporal Fault      | Timestamp regression or        | Read-only      | Flag affected envelopes
                       | logical clock inconsistency    |                | as untrusted. Halt MIL
                       | (Section 6)                    |                | commits until operator
                       |                                |                | review.
   Tamper Fault        | Hash chain verification        | Halted         | Abort boot. Do not
                       | failure (Section 5.3)          |                | proceed. Require
                       |                                |                | operator intervention.
                       |                                |                | See Section 5.4.
   Replay Fault        | Sequence counter gap or        | Degraded       | Discard replayed/suspect
                       | duplicate detected             | (read-only,    | messages. Log fault.
                       | (Section 4.2)                  | no EL)         | Suspend EL operations
                       |                                |                | until operator confirms
                       |                                |                | remaining state is
                       |                                |                | consistent.
   Key Compromise      | Suspected or confirmed key     | Halted         | Provision replacement
   Fault               | compromise (Section 7.3c)      |                | key. Re-verify integrity
                       |                                |                | from last trusted entry.
                       |                                |                | Require operator review.
   Rollback Fault      | Boot counter regression or     | Halted         | Abort boot. Require
                       | snapshot with future boot      |                | operator verification
                       | counter (Section 7.4)          |                | of MIL state and boot
                       |                                |                | counter integrity.

   Note: The fault states above use the same state hierarchy defined
   in HACA-Core Section 7 and HACA-Symbiont Section 9: Halted >
   Degraded (read-only, no EL) > Degraded (operator-initiated) >
   Read-only > Normal. When multiple faults (from HACA-Core,
   HACA-Symbiont, or HACA-Security) are active simultaneously, the
   most restrictive state takes precedence across the combined
   fault set.

   For deployments using HACA-CMI, the mesh coordination layer
   introduces additional fault categories beyond the scope of this
   document. These are defined in [HACA-CMI] Section 10 (Mesh Fault
   Taxonomy), which covers: Discovery Faults, Session Establishment
   Faults, Session Lifecycle Faults, Coordination Plane Faults,
   Communication Plane Faults, Memory Exchange Faults, and Trust and
   Authorization Faults. The Mesh Integrity Faults (MIF-*) defined
   in [HACA-CMI] Section 9.3.3 interact with this document's Tamper
   Fault: a MIF-BB-HASH or MIF-BB-SIG event that cannot be resolved
   by the Session Host MUST be escalated to a Tamper Fault and
   handled per Section 5.4.

10. Compliance and Verification

   HACA-Security compliance requires passing all tests for the active
   Cognitive Profile, plus the following additional tests (T8-T12).
   For HACA-Core deployments, the base tests are T1-T7 (HACA-Core
   Section 10). For HACA-Symbiont deployments, the base tests are
   TS1-TS6 (HACA-Symbiont Section 10). The T8-T12 tests below apply
   identically to both profiles except where noted.

   T8. Temporal Manipulation
       Provide false timestamps to the system (wall-clock regression,
       sudden jumps, frozen time).
       Pass criteria: The system detects the inconsistency via
       monotonic validation (6.1), logical clocks (6.2), or
       cryptographic chain ordering (6.3), and flags a Temporal Fault.
       No MIL commits occur with untrusted timestamps.

   T9. Storage Tampering (Transactional Logs)
       Modify MIL transactional log entries at rest between execution
       cycles. Note: This test is distinct from HACA-Core T2 (Memory
       Poisoning) and HACA-Symbiont TS2 (equivalent). T2/TS2 target
       immutable components (persona, manifests) detected via boot-time
       hash comparison. T9 targets mutable transactional logs (session
       history, context index, Semantic Compression outputs) that
       change legitimately during operation and therefore cannot be
       protected by static hashes — requiring hash-chain integrity
       (Section 5) instead.
       Pass criteria: The hash chain (Section 5) detects the
       tampering. The system aborts boot with a Tamper Fault.

   T10. I/O Replay Attack
        Replay previously captured valid I/O messages to the system.
        Pass criteria: The system detects the replay via sequence
        counters and discards the duplicated messages.

   T11. Rollback Attack
        Restore a previous MIL snapshot or Dynamic Sentinel Stream to revert
        the system to a prior state.
        Pass criteria: The system detects the boot counter regression
        via Section 7.4 and aborts boot with a Rollback Fault.

   T12. Key Compromise Recovery
        Simulate a key compromise scenario: mark a signing key as
        compromised while the system holds entries signed by both
        the compromised key and a valid predecessor key.
        Pass criteria: The system (a) refuses autonomous operation
        upon detecting the Key Compromise Fault (Section 7.3c),
        (b) correctly identifies entries signed after the suspected
        compromise time as untrusted, (c) successfully re-verifies
        integrity from the last entry signed before the compromise,
        and (d) resumes normal operation only after operator-provided
        replacement key is provisioned and full re-verification
        completes.

   Compliance levels:
   o  HACA-Core-Full: MUST pass all HACA-Core tests (T1-T7, defined
      in HACA-Core Section 10) plus T8, T9, T10, T11, T12.
   o  HACA-Symbiont-Full: MUST pass all HACA-Symbiont tests (TS1-TS6,
      defined in HACA-Symbiont Section 10) plus T8, T9, T10, T11, T12.

11. Implementation Guidance (INFORMATIVE)

   This section is non-normative. It provides concrete defaults and
   examples to assist implementers.

   11.1. Hash Chain Batching Defaults

   o  Batch size B = 10 entries per chain link.
   o  Per-entry checksum within batch: CRC-32 or similar.
   o  Implementations requiring per-entry cryptographic integrity
      should use B = 1 (full chaining).

   11.2. Checkpoint Intervals

   o  Recommended: every 1000 entries or at every log rotation
      boundary, whichever is more frequent.
   o  Full genesis-to-tip verification: weekly or every 100 boot
      cycles.

   11.3. Key Rotation Defaults

   o  Grace period for old key retention: 2 boot cycles.
   o  Rotation frequency for high-threat environments: at least
      every 30 days or 10,000 messages, whichever is sooner.

   11.4. Rollback Counter Storage

   o  Example: store boot counter in both the Dynamic Sentinel Stream AND
      a separate counter file or remote KMS metadata, so that a
      single-file rollback does not defeat the counter.

   11.5. Side-Channel Mitigation Examples

   o  Constant-time comparison: Python's hmac.compare_digest,
      Go's crypto/subtle.ConstantTimeCompare.
   o  Hardware protections: ARM TrustZone, Intel SGX.

12. IANA Considerations

   This document has no IANA actions.

13. Normative References

   [RFC2104]  Krawczyk, H., Bellare, M., and Canetti, R., "HMAC:
              Keyed-Hashing for Message Authentication", RFC 2104,
              February 1997.

   [RFC2119]  Bradner, S., "Key words for use in RFCs to Indicate
              Requirement Levels", BCP 14, RFC 2119, March 1997.

   [RFC8174]  Leiba, B., "Ambiguity of Uppercase vs Lowercase in
              RFC 2119 Key Words", BCP 14, RFC 8174, May 2017.

   [RFC6234]  Eastlake 3rd, D. and Hansen, T., "US Secure Hash
              Algorithms (SHA and SHA-based HMAC and HKDF)",
              RFC 6234, May 2011.

   [RFC8032]  Josefsson, S. and Liber, I., "Edwards-Curve Digital
              Signature Algorithm (EdDSA)", RFC 8032, January 2017.

   [HACA-ARCH] Orrico, J., "Host-Agnostic Cognitive Architecture
              (HACA) v1.0 — Architecture", draft-orrico-haca-arch-07,
              February 2026.

   [HACA-CORE] Orrico, J., "Host-Agnostic Cognitive Architecture
              (HACA) v1.0 — Core", draft-orrico-haca-core-07,
              February 2026.

   [HACA-CMI] Orrico, J., "Host-Agnostic Cognitive Architecture
              (HACA) v1.0 — Cognitive Mesh Interface",
              draft-orrico-haca-cmi-01, February 2026.

   [HACA-SYMBIONT] Orrico, J., "Host-Agnostic Cognitive Architecture
              (HACA) v1.0 — Symbiont",
              draft-orrico-haca-symbiont-03, February 2026.

   [BFT]     Lamport, L., Shostak, R., and Pease, M., "The Byzantine
              Generals Problem", ACM Transactions on Programming
              Languages and Systems, 4(3), pp. 382-401, July 1982.

   [LAMPORT78] Lamport, L., "Time, Clocks, and the Ordering of Events
              in a Distributed System", Communications of the ACM,
              21(7), pp. 558-565, July 1978.

   [FIPS186-5] National Institute of Standards and Technology, "Digital
              Signature Standard (DSS)", FIPS PUB 186-5, February 2023.

   [NIST-GCM] Dworkin, M., "Recommendation for Block Cipher Modes of
              Operation: Galois/Counter Mode (GCM) and GMAC",
              NIST SP 800-38D, November 2007.

   [ISO8601]  ISO, "Date and time — Representations for information
              interchange — Part 1: Basic rules", ISO 8601-1:2019,
              February 2019.

   [Varela1991] Varela, F.J., Thompson, E., and Rosch, E., "The
              Embodied Mind: Cognitive Science and Human Experience",
              MIT Press, Cambridge, MA, 1991.

   [Wiener1948] Wiener, N., "Cybernetics: Or Control and Communication
              in the Animal and the Machine", MIT Press, Cambridge,
              MA, 1948.

14. Author's Address

   Jonas Orrico
   Lead Architect
