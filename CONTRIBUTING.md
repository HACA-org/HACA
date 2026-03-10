# Contributing to HACA

Thank you for your interest in contributing to HACA (Host-Agnostic Cognitive Architecture).

HACA is a vendor-neutral architectural and protocol standard for persistent cognitive systems. Contributions are welcome, but must follow the processes defined in this document to preserve architectural coherence and specification integrity.

---

## 1. Guiding Principles

Contributions MUST respect the following:

- Architectural minimalism
- Clarity of invariants
- Backward stability
- Vendor neutrality
- Specification-first development

Reference implementations do NOT define the standard. The normative specification text is authoritative.

---

## 2. Types of Contributions

Contributions may include:

- Editorial improvements
- Clarifications
- Normative refinements
- New profile proposals
- Security improvements
- RFC drafts for architectural changes

---

## 3. Before Submitting a Change

Before submitting a pull request:

1. Review GOVERNANCE.md.
2. Determine whether the change is:
   - Editorial (non-normative)
   - Normative (affects MUST/SHOULD/MAY requirements)
   - Architectural (affects invariants or protocol structure)
3. If architectural, open an issue first for discussion.

Major changes SHOULD begin as RFC drafts under `/spec/rfc/`.

---

## 4. Normative Language

HACA uses RFC 2119 terminology:

- MUST
- MUST NOT
- SHOULD
- SHOULD NOT
- MAY

Normative changes MUST:

- Clearly identify modified requirements
- Include rationale
- Include compatibility impact analysis

Avoid ambiguous language such as:
- “usually”
- “normally”
- “recommended” (unless explicitly defined)

---

## 5. Pull Request Requirements

All pull requests MUST:

- Clearly describe the purpose of the change
- Identify whether the change is normative or non-normative
- Specify compatibility impact
- Update relevant sections consistently

Normative pull requests MUST include:

- Rationale
- Backward compatibility statement
- Security considerations (if applicable)

---

## 6. Specification Structure Integrity

Contributors MUST NOT:

- Remove or weaken core invariants without justification
- Introduce implementation-specific assumptions into the core spec
- Define behavior solely by referencing the reference implementation

All normative requirements must be self-contained in the specification text.

---

## 7. RFC Process

Significant architectural changes SHOULD follow the RFC process:

An RFC must include:

- Problem statement
- Proposed solution
- Detailed specification text
- Compatibility analysis
- Security considerations

RFC drafts should be placed in `/spec/rfc/`.

Approval requires review and explicit acceptance by the Specification Owner.

---

## 8. Profiles and Extensions

New profiles (e.g., storage backends, execution environments) MUST:

- Declare compatibility with a specific HACA version
- Not violate core invariants
- Clearly define extension boundaries

Profiles must not silently redefine core behavior.

---

## 9. Compliance and Conformance

Changes affecting conformance requirements MUST:

- Update the Conformance section
- Preserve deterministic compliance criteria

A system must be able to objectively determine whether it is compliant.

---

## 10. Licensing

By contributing, you agree that your contributions may be redistributed under the project license specified in LICENSE.

Contributors must disclose any known patent or licensing restrictions affecting their contributions.

---

## 11. Code Contributions (Reference Implementation)

Contributions to the reference implementation:

- MUST not redefine normative behavior
- MUST reflect the specification
- MUST clearly indicate experimental features

The implementation is NON-NORMATIVE.

---

## 12. Professional Conduct

Discussions should remain:

- Technical
- Respectful
- Focused on architecture and specification clarity

Architectural debates must prioritize long-term coherence over short-term convenience.

---

## 13. Final Authority

In case of disagreement, the Specification Owner makes the final determination regarding specification changes, subject to the governance model.