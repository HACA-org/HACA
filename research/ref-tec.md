## 8. Theoretical Foundations

This architecture synthesizes established principles from cognitive science, distributed systems, and artificial immunology into a deterministic structure for language model-based entities.

### 8.1 Cognitive Architectures (ACT-R and SOAR)

HACA's strict separation between the stateless reasoning engine (the model) and the persistent state (the Entity Store) operationalizes the processor/memory separation found in classical cognitive architectures like ACT-R and SOAR — where procedural and declarative memory are structurally distinct from the central processing mechanism that operates over them. Where ACT-R relies on manually authored procedural rules to drive condition-action cycles, HACA replaces this bottleneck with the statistical inference of language models, while retaining the structural invariant that the processor itself retains no state between cognitive transitions.

### 8.2 Artificial Immune Systems (AIS) and Homeostasis

The System Integrity Layer (SIL) and the Heartbeat Protocol are practical abstractions of Artificial Immune Systems (AIS) and cognitive homeostasis. In AIS, algorithms deploy the biological concept of "self vs. non-self" to dynamically detect anomalies. HACA realizes this through structural hashing and the Drift Framework: any mnemonic content or structural state that diverges from the sealed "self" — the Integrity Document and Genesis Omega — is treated as an anomaly. The entity does not attempt to reason its way out of a critical drift; it invokes a homeostatic shutdown (revoking the session token) to preserve the healthy state.

### 8.3 Memory Consolidation and the Sleep Cycle

The architectural invariant that structural writes and memory consolidation occur exclusively during the Sleep Cycle parallels the neuroscientific mechanisms of "dream pruning" and offline memory replay. In modern machine learning, preventing catastrophic forgetting caused by continuous, unbounded knowledge ingestion requires discrete periods of offline consolidation. HACA elevates this from a training heuristic to a structural law: the entity cannot self-modify its identity baseline or commit semantic conclusions while actively processing stimuli.

### 8.4 Actor Model and Capability-Based Security

The Cognitive Mesh Interface (CMI) invariant of Cognitive Sovereignty — where no external node can write directly to the local Entity Store — is a formal implementation of the Actor Model. It guarantees that independent agents share no state and interact purely through mediated message passing. Furthermore, the two-gate authorization pattern in the execution layer (EXEC) traces its lineage to Object-Capability (OCap) security models, ensuring that capabilities are isolated and explicitly verified prior to any host environment actuation.

### 8.5 Markov Blanket and Active Inference

In the context of the Free Energy Principle (Friston), a Markov Blanket defines the boundary that separates the internal states of a system from its external environment, mediating all sensory and active interactions. In HACA, this boundary is structurally realized by the **Entity Artifact Boundary** and the EXEC's two-gate authorization — the mechanisms that mediate every interaction between the entity's internal states and the external host environment. The **Omega** corresponds to the internal states that the boundary protects: the active configuration of Entity Store, model, and Operator binding operating within a session. The entity has no direct unmediated perception of the host; every stimulus (sensory state) is explicitly routed into the Cognitive Cycle, and every action (active state) must pass through the execution layer's authorization gates. This strict boundary allows the entity to maintain its internal structural integrity independently of the fluctuating, untrusted states of the external host environment.

### 8.6 Cybernetics and Double-Loop Learning

In cognitive and organizational cybernetics (Argyris & Schön), learning is divided into single-loop (adjusting actions within existing rules) and double-loop (modifying the underlying rules themselves). HACA structurally separates these two cognitive processes. Mnemonic writes during active sessions represent single-loop learning — accumulating facts and episodic context without altering the underlying persona framework. Structural writes executed via the Endure Protocol during the Sleep Cycle represent double-loop learning — fundamentally evolving the persona, skills, and defining constraints based on accumulated experience, but strictly governed by a separate, highly authorized, and computationally atomic pathway.

### 8.7 Integrated Information Theory (IIT)

Developed by Giulio Tononi, IIT posits that an entity's complexity and distinct emergent properties correspond to its capacity to integrate information in a way that cannot be subdivided into independent components without dissolving the whole. HACA draws a structural analogy to this principle — without claiming the formal mathematical equivalence of phi — in the way the Genesis Omega and the Integrity Document enforce indivisible identity. The entity is not merely a fragmented collection of files or a transient context window; it is the cryptographically bound intersection of its persistent memory, its active reasoning, and its integrity enforcement. A hash mismatch detected by the SIL signals a breaking of this binding — a failure of the system to maintain a coherent, unified "self" — prompting an immediate, unreasoned system halt. The analogy is structural: HACA does not define a phi-equivalent measure, but the architectural insistence that the entity's identity is only valid as an indivisible whole echoes IIT's core intuition.

### 8.8 Subsumption Architecture

Pioneered by Rodney Brooks in autonomous robotics, Subsumption Architecture organizes behavior in hierarchical layers of independent control loops, where lower-level reactive survival layers can seamlessly override higher-level cognitive layers without waiting for their computation to complete. HACA realizes this model cleanly through the continuous, parallel Health Flow of the SIL. While the CPE engages in heavy, complex semantic reasoning (the higher-level cognition), the SIL enforces basal structural survival (the lower-level reactive loop). When the SIL detects an anomaly or executes a system halt via a Critical Vital Check or failed watchdog, it *subsumes* control — bypassing the CPE entirely and breaking the reasoning loop without needing to negotiate or request permission from the reasoning engine itself.

### 8.9 Evolutionary Codebase Maintenance (SWE-CI)

The SWE-CI benchmark (Evaluating Agent Capabilities in Maintaining Codebases via Continuous Integration, 2026) empirically validates several of HACA's structural invariants by studying agent behavior across long-horizon software maintenance tasks spanning hundreds of days and dozens of iterative commits. Its central finding — that current LLMs fail at sustained maintenance primarily due to regression accumulation rather than inability to produce correct code — maps directly onto HACA's architectural separation between active cognition and offline structural consolidation.

The benchmark's dual-agent protocol (Architect Agent producing high-level requirements; Programmer Agent executing implementation) is a natural realization of HACA's CMI collaboration model: two entities with distinct roles operating over a shared Blackboard representing the codebase and CI state, each preserving Cognitive Sovereignty over its own Entity Store. The deliberate isolation of agents from direct test-gap visibility — to encourage architectural thinking over metric-chasing — is enforced structurally in HACA by the Evolution Proposal pathway: the CPE proposes structural changes, but cannot directly commit them, preventing the equivalent of a shortcut collapse between reasoning and execution.

The EvoScore metric, which weights later iterations more heavily (γ ≥ 1) on the principle that maintainable code remains easy to modify over time, validates the Sleep Cycle's role as a regression barrier. By requiring all structural commits to pass through the Endure Protocol during an offline consolidation window, HACA prevents the incremental architectural debt accumulation that the benchmark identifies as the primary cause of long-horizon failure. The Semantic Probes mechanism extends naturally to this domain: in a codebase maintenance context, probes can anchor the entity's semantic baseline to the established test invariants, making regressions detectable as Semantic Drift during memory consolidation.

---