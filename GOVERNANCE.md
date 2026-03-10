# HACA Governance Model

Version: 1.0
Status: Active

## 1. Purpose

This document defines the governance model for the HACA (Host-Agnostic Cognitive Architecture) specification, including decision-making processes, release management, and conformance policy.

HACA is intended to be a vendor-neutral, open architectural and protocol standard for persistent cognitive systems.

---

## 2. Principles

HACA governance is guided by the following principles:

- **Vendor Neutrality** — No single implementation defines the standard.
- **Specification First** — The normative specification has authority over any reference implementation.
- **Clarity Over Complexity** — Architectural minimalism is preferred.
- **Backward Stability** — Breaking changes are strictly controlled.
- **Open Participation** — Contributions are welcome under defined processes.

---

## 3. Roles

### 3.1 Specification Owner

The Specification Owner is responsible for:

- Maintaining architectural coherence
- Approving releases
- Resolving disputes
- Ensuring alignment with HACA’s long-term vision

Initially, the repository founder serves as Specification Owner.

### 3.2 Maintainers

Maintainers may be appointed to:

- Review pull requests
- Propose draft revisions
- Maintain documentation clarity

Maintainers do not unilaterally redefine architectural invariants.

### 3.3 Contributors

Contributors may:

- Submit issues
- Propose changes
- Submit RFC drafts
- Improve documentation

All contributions must follow CONTRIBUTING.md.

---

## 4. Specification Lifecycle

Each HACA specification document MUST declare its status:

- **Draft** — Under active development. Not stable.
- **Proposed Standard** — Feature complete. Implementation feedback encouraged.
- **Stable Standard** — Considered mature and suitable for production use.
- **Deprecated** — Scheduled for removal in a future major version.

Status changes require explicit approval by the Specification Owner.

---

## 5. Versioning Policy

HACA follows Semantic Versioning (SemVer):

MAJOR.MINOR.PATCH

- MAJOR — Breaking architectural or protocol changes.
- MINOR — Backward-compatible feature additions.
- PATCH — Editorial or clarifying changes only.

Breaking changes require:

- Justification document
- Migration guidance
- Version negotiation rules (if protocol-relevant)

---

## 6. Change Management

Normative changes MUST:

- Be clearly identified in pull requests
- Include rationale
- Specify compatibility impact
- Update Conformance Requirements section

Non-normative edits (grammar, formatting) may be merged without formal review cycle.

---

## 7. RFC Process

Major architectural changes SHOULD begin as RFC documents inside the `/spec/rfc/` directory.

An RFC must include:

- Motivation
- Detailed specification text
- Backward compatibility analysis
- Security considerations

RFC acceptance requires:

- Public review period
- Explicit approval by Specification Owner

---

## 8. Conformance and Compliance

A system may claim:

- **HACA Compliant** — If it satisfies all mandatory (MUST) requirements in the specification.
- **HACA Profile Compliant** — If it satisfies both the core spec and a declared profile (e.g., FCP).

Reference implementations are NON-NORMATIVE.

Conformance is determined by specification requirements, not by matching reference code behavior.

---

## 9. Extension Policy

Extensions MUST:

- Not violate core invariants
- Declare compatibility impact
- Clearly define whether they are experimental or stable

Profiles (such as FCP) are formalized extension sets.

---

## 10. Intellectual Property and Licensing

The HACA specification is released under the license declared in LICENSE.

Contributors agree that submitted contributions may be redistributed under that license.

The project does not accept proprietary or patent-encumbered normative requirements without explicit disclosure.

---

## 11. Future Foundation Model

If the project reaches multi-stakeholder adoption, governance may transition to a foundation or multi-party steering group.

Such transition requires:

- Public governance proposal
- Defined voting structure
- Transparent leadership selection process

Until then, governance remains centralized under the Specification Owner.

---

## 12. Final Authority

In case of ambiguity, the normative specification text is the final authority.

Reference implementations, examples, or external documentation do not override specification requirements.