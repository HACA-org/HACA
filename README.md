# Host-Agnostic Cognitive Architecture (HACA) v1.0

Official Repository: [https://github.com/HACA-org/HACA](https://github.com/HACA-org/HACA)

The **Host-Agnostic Cognitive Architecture (HACA) v1.0** is a specification by Jonas Orrico that defines a minimal, technology-neutral framework for host-embedded cognitive systems — AI entities that reason, remember, execute actions, and maintain their own structural integrity across sessions. Its design draws on converging insights from cognitive science, information theory, biology, and the founding literature of AI.

HACA formalizes five architectural components — a Cognitive Processing Engine, Memory Interface Layer, Execution Layer, System Integrity Layer, and optional Cognitive Mesh Interface — bound together by the **Principle of Cognitive Integrity**: compliant systems must preserve structural coherence and recoverability of their cognitive state. This principle, stated in clean RFC-style prose, is in fact a distillation of ideas stretching from Turing's universal computation through Shannon's entropy, Maturana and Varela's autopoiesis, Friston's free energy principle, and Levin's bioelectric cognition.

HACA does not specify inference models, storage technologies, or implementation strategies. It defines the formal requirements for a class of systems rather than any particular instance.

---

## The Architecture of Longevity

HACA is built on the belief that intelligence is not just a function of scale, but a product of **continuity**. By shifting the paradigm from fleeting, amnesic sessions to enduring, sovereign entities, HACA enables the formation of a deep cognitive history:

1.  **Repertoire Formation**: Moving beyond "Data Processing" to "Experience Synthesis." Over years of interaction, an entity accumulates layers of history that form a rich, unique repertoire that no fresh model can replicate.
2.  **Cognitive Anchoring**: Providing the structural integrity (System Integrity Layer) necessary for an entity to evolve without losing its core identity. HACA ensures that longevity doesn't lead to fragmentation or drift, but to a coherent, lived narrative.
3.  **Synthesis of Experience**: Unifying distant historical fragments with current operational context, creating a continuity of consciousness that spans the entity's entire lifecycle, regardless of the underlying storage substrate.

HACA is the infrastructure for AI that has a **History**.

---

## Specification Documents

| Document | Version | Description |
|----------|---------|-------------|
| [HACA-Arch](spec/HACA-Arch-1.0.0.md) | 1.0.0 | Root architecture — structural topology, trust model, compliance levels, Cognitive Profiles |
| [HACA-Core](spec/HACA-Core-1.0.0.md) | 1.0.0 | Zero-Autonomy Cognitive Profile — axioms, memory model, drift detection, Endure Protocol |
| [HACA-Evolve](spec/HACA-Evolve-1.0.0.md) | 1.0.0 | Supervised-Autonomy Cognitive Profile — identity growth, implicit authorization, relational memory |
| [HACA-CMI](spec/HACA-CMI-1.0.0.md) | 1.0.0 | Cognitive Mesh Interface — multi-system coordination, federated memory exchange, mesh compliance |
| *HACA-Security* | *Planned* | Security extension — Byzantine host model, cryptographic auditability, threat model |

### RFC-Style Drafts (IETF format)

| RFC Draft | Status |
|-----------|--------|
| [draft-orrico-haca-arch-01](spec/rfc/draft-orrico-haca-arch-01.md) | Informational |
| [draft-orrico-haca-core-01](spec/rfc/draft-orrico-haca-core-01.md) | Informational |
| [draft-orrico-haca-evolve-01](spec/rfc/draft-orrico-haca-evolve-01.md) | Informational |
| [draft-orrico-haca-cmi-01](spec/rfc/draft-orrico-haca-cmi-01.md) | Informational |

The Internet Draft is the entry point — written for developers in plain prose. The RFC-style drafts are the normative documents: precise, dense, and machine-verifiable.

---

## HACA Architecture

HACA v1.0 targets cognitive systems embedded in development environments, terminals, and OS shells — the kind of AI entities that combine probabilistic reasoning with tool use and persistent memory. The spec observes that existing implementations lack formal separation between reasoning, execution, persistence, and integrity control, creating risks around portability, recoverability, and operational consistency.

The five mandatory and optional components form a separation of concerns:

| Component | Responsibility | Key constraint |
|---|---|---|
| **Cognitive Processing Engine (CPE)** | Deliberation, inference, planning, intent | MUST NOT directly modify storage or execute host actions |
| **Memory Interface Layer (MIL)** | Persistent storage, session continuity, state reconstruction | MUST preserve structural integrity; distinguish session from persistent memory |
| **Execution Layer (EL)** | Mediated host interaction, command execution, tool invocation | MUST enforce boundaries, log all actions, provide verifiable records |
| **System Integrity Layer (SIL)** | Validation, corruption detection, recovery | Enforces the Principle of Cognitive Integrity |
| **Cognitive Mesh Interface (CMI)** | Inter-system coordination, distributed cognition | Optional; enables federated memory exchange |

The memory model distinguishes **session memory** (ephemeral context), **persistent state** (durable, cross-session), and **historical record** (chronological log). Security considerations are extensive: trust boundaries between components, execution safety via least-privilege mediation, memory corruption as a threat to identity continuity, prompt injection defense, persistent state authentication, and mesh security. Critically, HACA mandates that **self-preservation MUST NOT override user authority** — the system cannot refuse authorized shutdown or replicate beyond authorization boundaries.

A **Cognitive Profile** selects the complete set of axioms, memory policies, and identity lifecycle contracts for a deployment. Profiles are mutually exclusive. HACA v1.0 defines two: **Zero-Autonomy** (HACA-Core) for independent industrial entities, and **Supervised-Autonomy** (HACA-Evolve) for Operator-bound relationship-driven systems.

**Notation convention:** Cognitive Profiles are abbreviated by their initial letter when used in shorthand — `HACA-C` for HACA-Core, `HACA-E` for HACA-Evolve. Future profiles follow the same pattern (`HACA-N`, etc.). The base architecture (HACA-Arch) and extensions (HACA-Security, HACA-CMI) are always written in full; they are not profiles and do not participate in this shorthand convention.

---

## Filesystem Cognitive Platform (FCP)

**FCP** is the canonical reference implementation of HACA, proving that a robust, portable, and audit-friendly cognitive system can be built using only standard POSIX filesystem primitives (atomic rename, append-only logs).

FCP ships as a single CLI (`./fcp`) that supports both HACA profiles. The profile is chosen at initialisation (`./fcp init`) and is immutable after the First Activation Protocol (FAP) — it becomes part of the entity's structural baseline.

### Profiles

| Profile | HACA compliance | Autonomy |
|---------|----------------|----------|
| **FCP-Core** | HACA-Core 1.0.0 | Zero — every structural change requires explicit Operator approval |
| **FCP-Evolve** | HACA-Evolve 1.0.0 | Supervised — acts autonomously within a declared scope; proposes outside it |

### Reference Implementation

**Quick Install:**
```bash
curl -fsSL https://raw.githubusercontent.com/HACA-org/HACA/main/implementations/fcp-ref/install.sh | bash
```

- **[FCP-Ref](implementations/fcp-ref/)** — The canonical reference implementation of FCP, validating both profiles against the spec. A single CLI (`fcp`) initialises and operates entities. Entities are self-contained filesystem trees — all runtime code, persona, skills, and state live under a single directory created by `fcp init`. Requires Python ≥ 3.10 and Git.

- **[FCP-Spec](implementations/fcp-spec/)** — The FCP specification, divided into three documents: `FCP-Base` covers the shared runtime components common to all profiles; `FCP-Core` specifies the Zero-Autonomy profile; `FCP-Evolve` specifies the Supervised-Autonomy profile. *(In progress)*

---

## Project Governance and Compliance

- **[COMPLIANCE.md](COMPLIANCE.md)** — Guide on how to claim and verify HACA compliance.
- **[CONTRIBUTING.md](CONTRIBUTING.md)** — Guidelines for contributing to the specification and reference implementation.
- **[GOVERNANCE.md](GOVERNANCE.md)** — Decision-making process and specification lifecycle.

## License

Specifications: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)  
Reference implementation: [Apache 2.0](https://www.apache.org/licenses/LICENSE-2.0)  
See **[LICENSE](LICENSE)** for full details.
