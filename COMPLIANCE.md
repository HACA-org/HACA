# HACA Compliance Guide

This document defines what it means for a system to be **HACA Compliant** and how to document and verify that compliance.

## 1. Compliance Levels

HACA defines three levels of compliance:

### 1.1 Architectural Compliance (HACA-Arch)
The system satisfies all mandatory structural invariants defined in [HACA-Arch](spec/HACA-Arch-1.0.0.md). This includes:
- Component separation (CPE, MIL, EL, SIL).
- Verifiable integrity chain.
- Deterministic boot sequence.
- Identity derivation from Genesis Omega.

### 1.2 Profile Compliance (HACA-Core / HACA-Evolve)
The system satisfies HACA-Arch plus the specific axioms and enforcement policies of a declared Cognitive Profile. 
- **HACA-Core**: Optimized for zero-autonomy, strictly audited environments.
- **HACA-Evolve**: Optimized for supervised-autonomy and long-term relational memory.

### 1.3 Extension Compliance (HACA-CMI / HACA-Security)
The system satisfies the requirements of a specific modular extension while maintaining core architectural compliance.

---

## 2. Claiming Compliance

To claim HACA compliance, an implementation MUST:

1.  **Declare Level**: State explicitly which HACA version and Profile(s) it implements.
2.  **Structural Baseline**: Provide a verifiable Structural Baseline (as defined in HACA-Arch §3.2) that declares all mandatory parameters (thresholds, intervals, component hashes).
3.  **Checklist Verification**: Provide a completed compliance checklist for each implemented specification (found in the "Compliance" section of each document).
4.  **Auditability**: Maintain an Integrity Log that proves core invariants were not violated during operation.

---

## 3. The Role of the Reference Implementation

The HACA reference implementation (FCP-Ref) is **non-normative**. 
- Matching the behavior of FCP-Ref does **not** guarantee HACA compliance.
- Diverging from FCP-Ref does **not** imply non-compliance, provided the specification requirements are met.
- Compliance is determined solely by the normative text in the specification documents.

---

## 4. Misuse of the HACA Mark

Claims of compliance that do not satisfy the mandatory checkpoints in the relevant specifications are invalid. Partial compliance MUST NOT be represented as "HACA Compliant".

Recommended phrasing for partial or experimental systems: 
- *"Inspired by HACA architecture"*
- *"HACA-compatible experimental implementation"*

---

## 5. Verification Tools

Compliance can be verified through:
1.  **Static Verification**: Audit of the Structural Baseline and persona constraints.
2.  **Runtime Verification**: Integrity Log analysis against the declared structural baseline.
3.  **Semantic Probing**: Comparison of CPE outputs against historical records via the Silk (HACA-Arch §5.2).
