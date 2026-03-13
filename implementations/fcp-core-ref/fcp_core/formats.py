"""
Core Formats — all Entity Store artefact schemas.  §3

Each class maps 1-to-1 to a named artefact in the spec.  No I/O here —
only structure, field types, and from_dict / to_dict helpers.

Validation is intentionally minimal: required fields must be present and
non-None; deeper semantic checks (e.g. topology == "transparent") belong
in the components that enforce them (SIL, boot).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# §3.1 — ACP envelope type constants
# ---------------------------------------------------------------------------

class ACPType:
    MSG                = "MSG"
    SKILL_REQUEST      = "SKILL_REQUEST"
    SKILL_RESULT       = "SKILL_RESULT"
    SKILL_ERROR        = "SKILL_ERROR"
    SKILL_TIMEOUT      = "SKILL_TIMEOUT"
    HEARTBEAT          = "HEARTBEAT"
    DRIFT_FAULT        = "DRIFT_FAULT"
    IDENTITY_DRIFT     = "IDENTITY_DRIFT"
    EVOLUTION_PROPOSAL = "EVOLUTION_PROPOSAL"
    EVOLUTION_AUTH     = "EVOLUTION_AUTH"
    EVOLUTION_REJECTED = "EVOLUTION_REJECTED"
    PROPOSAL_PENDING   = "PROPOSAL_PENDING"
    ENDURE_COMMIT      = "ENDURE_COMMIT"
    SEVERANCE_COMMIT   = "SEVERANCE_COMMIT"
    SEVERANCE_PENDING  = "SEVERANCE_PENDING"
    SLEEP_COMPLETE     = "SLEEP_COMPLETE"
    ACTION_LEDGER      = "ACTION_LEDGER"
    SIL_UNRESPONSIVE   = "SIL_UNRESPONSIVE"
    CTX_SKIP           = "CTX_SKIP"
    CRITICAL_CLEARED   = "CRITICAL_CLEARED"
    DECOMMISSION       = "DECOMMISSION"
    MEMORY_RESULT      = "MEMORY_RESULT"


class ACPActor:
    FCP      = "fcp"
    SIL      = "sil"
    MIL      = "mil"
    CPE      = "cpe"
    EXEC     = "exec"
    OPERATOR = "operator"


# ---------------------------------------------------------------------------
# §3.2 — Structural Baseline
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class CPEConfig:
    topology: str   # must be "transparent" under HACA-Core
    backend: str

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CPEConfig:
        return cls(topology=d["topology"], backend=d["backend"])

    def to_dict(self) -> dict[str, Any]:
        return {"topology": self.topology, "backend": self.backend}


@dataclass(slots=True)
class StructuralBaseline:
    version: str
    entity_id: str
    cpe: CPEConfig
    heartbeat_cycle_threshold: int
    heartbeat_interval_seconds: int
    watchdog_sil_threshold_seconds: int
    context_window_budget_tokens: int
    context_window_critical_pct: int
    drift_comparison_mechanism: str
    drift_threshold: float
    session_store_rotation_threshold_bytes: int
    working_memory_max_entries: int
    integrity_chain_checkpoint_interval: int
    pre_session_buffer_max_entries: int
    operator_channel_notifications_dir: str
    fault_n_boot: int
    fault_n_channel: int
    fault_n_retry: int

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> StructuralBaseline:
        return cls(
            version=d["version"],
            entity_id=d["entity_id"],
            cpe=CPEConfig.from_dict(d["cpe"]),
            heartbeat_cycle_threshold=d["heartbeat"]["cycle_threshold"],
            heartbeat_interval_seconds=d["heartbeat"]["interval_seconds"],
            watchdog_sil_threshold_seconds=d["watchdog"]["sil_threshold_seconds"],
            context_window_budget_tokens=d["context_window"]["budget_tokens"],
            context_window_critical_pct=d["context_window"]["critical_pct"],
            drift_comparison_mechanism=d["drift"]["comparison_mechanism"],
            drift_threshold=d["drift"]["threshold"],
            session_store_rotation_threshold_bytes=d["session_store"]["rotation_threshold_bytes"],
            working_memory_max_entries=d["working_memory"]["max_entries"],
            integrity_chain_checkpoint_interval=d["integrity_chain"]["checkpoint_interval"],
            pre_session_buffer_max_entries=d["pre_session_buffer"]["max_entries"],
            operator_channel_notifications_dir=d["operator_channel"]["notifications_dir"],
            fault_n_boot=d["fault"]["n_boot"],
            fault_n_channel=d["fault"]["n_channel"],
            fault_n_retry=d["fault"]["n_retry"],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "entity_id": self.entity_id,
            "cpe": self.cpe.to_dict(),
            "heartbeat": {
                "cycle_threshold": self.heartbeat_cycle_threshold,
                "interval_seconds": self.heartbeat_interval_seconds,
            },
            "watchdog": {"sil_threshold_seconds": self.watchdog_sil_threshold_seconds},
            "context_window": {
                "budget_tokens": self.context_window_budget_tokens,
                "critical_pct": self.context_window_critical_pct,
            },
            "drift": {
                "comparison_mechanism": self.drift_comparison_mechanism,
                "threshold": self.drift_threshold,
            },
            "session_store": {
                "rotation_threshold_bytes": self.session_store_rotation_threshold_bytes,
            },
            "working_memory": {"max_entries": self.working_memory_max_entries},
            "integrity_chain": {
                "checkpoint_interval": self.integrity_chain_checkpoint_interval,
            },
            "pre_session_buffer": {"max_entries": self.pre_session_buffer_max_entries},
            "operator_channel": {
                "notifications_dir": self.operator_channel_notifications_dir,
            },
            "fault": {
                "n_boot": self.fault_n_boot,
                "n_channel": self.fault_n_channel,
                "n_retry": self.fault_n_retry,
            },
        }


# ---------------------------------------------------------------------------
# §3.3 — Integrity Document
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class CheckpointRef:
    seq: int
    digest: str  # "sha256:..."

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CheckpointRef:
        return cls(seq=d["seq"], digest=d["digest"])

    def to_dict(self) -> dict[str, Any]:
        return {"seq": self.seq, "digest": self.digest}


@dataclass(slots=True)
class IntegrityDocument:
    version: str
    algorithm: str                        # "sha256"
    last_checkpoint: CheckpointRef | None # None before first checkpoint
    files: dict[str, str]                 # path → sha256 hex

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> IntegrityDocument:
        cp = d.get("last_checkpoint")
        return cls(
            version=d["version"],
            algorithm=d["algorithm"],
            last_checkpoint=CheckpointRef.from_dict(cp) if cp else None,
            files=dict(d["files"]),
        )

    def to_dict(self) -> dict[str, Any]:
        cp = self.last_checkpoint
        return {
            "version": self.version,
            "algorithm": self.algorithm,
            "last_checkpoint": cp.to_dict() if cp is not None else None,
            "files": self.files,
        }


# ---------------------------------------------------------------------------
# §3.4 — Operator Bound  (sub-object of ImprintRecord)
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class OperatorBound:
    name: str
    email: str
    operator_hash: str  # "sha256:..."

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> OperatorBound:
        return cls(
            name=d["operator_name"],
            email=d["operator_email"],
            operator_hash=d["operator_hash"],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "operator_name": self.name,
            "operator_email": self.email,
            "operator_hash": self.operator_hash,
        }


# ---------------------------------------------------------------------------
# §3.5 — Session Token
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class SessionToken:
    session_id: str
    issued_at: str           # ISO 8601 UTC
    revoked_at: str | None   # None while active; set at session close

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> SessionToken:
        return cls(
            session_id=d["session_id"],
            issued_at=d["issued_at"],
            revoked_at=d.get("revoked_at"),
        )

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "session_id": self.session_id,
            "issued_at": self.issued_at,
        }
        if self.revoked_at is not None:
            d["revoked_at"] = self.revoked_at
        return d

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None

    @property
    def is_stale(self) -> bool:
        """Stale token = present at boot without SLEEP_COMPLETE → crash indicator."""
        return True  # presence itself is the indicator; caller decides context


# ---------------------------------------------------------------------------
# §3.6 — Working Memory
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class WorkingMemoryEntry:
    priority: int   # lower = higher priority
    path: str       # relative to entity root

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> WorkingMemoryEntry:
        return cls(priority=d["priority"], path=d["path"])

    def to_dict(self) -> dict[str, Any]:
        return {"priority": self.priority, "path": self.path}


@dataclass(slots=True)
class WorkingMemory:
    version: str
    entries: list[WorkingMemoryEntry]

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> WorkingMemory:
        return cls(
            version=d["version"],
            entries=[WorkingMemoryEntry.from_dict(e) for e in d.get("entries", [])],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "entries": [e.to_dict() for e in self.entries],
        }

    def sorted_entries(self) -> list[WorkingMemoryEntry]:
        """Entries in ascending priority order (lowest value = highest priority)."""
        return sorted(self.entries, key=lambda e: e.priority)


# ---------------------------------------------------------------------------
# §3.7 — Closure Payload
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class SessionHandoff:
    pending_tasks: list[str]
    next_steps: str

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> SessionHandoff:
        return cls(pending_tasks=list(d["pending_tasks"]), next_steps=d["next_steps"])

    def to_dict(self) -> dict[str, Any]:
        return {"pending_tasks": self.pending_tasks, "next_steps": self.next_steps}


@dataclass(slots=True)
class ClosurePayload:
    consolidation: str
    working_memory: list[WorkingMemoryEntry]
    session_handoff: SessionHandoff

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ClosurePayload:
        return cls(
            consolidation=d["consolidation"],
            working_memory=[WorkingMemoryEntry.from_dict(e) for e in d["working_memory"]],
            session_handoff=SessionHandoff.from_dict(d["session_handoff"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "closure_payload",
            "consolidation": self.consolidation,
            "working_memory": [e.to_dict() for e in self.working_memory],
            "session_handoff": self.session_handoff.to_dict(),
        }


# ---------------------------------------------------------------------------
# §3.8 — Semantic Digest
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class ProbeDigest:
    last_score: float
    mean_score: float
    max_score: float

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ProbeDigest:
        return cls(
            last_score=d["last_score"],
            mean_score=d["mean_score"],
            max_score=d["max_score"],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "last_score": self.last_score,
            "mean_score": self.mean_score,
            "max_score": self.max_score,
        }


@dataclass(slots=True)
class SemanticDigest:
    version: str
    last_updated: str               # ISO 8601 UTC
    cycles_evaluated: int
    probes: dict[str, ProbeDigest]  # probe_id → ProbeDigest

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> SemanticDigest:
        return cls(
            version=d["version"],
            last_updated=d["last_updated"],
            cycles_evaluated=d["cycles_evaluated"],
            probes={k: ProbeDigest.from_dict(v) for k, v in d["probes"].items()},
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "last_updated": self.last_updated,
            "cycles_evaluated": self.cycles_evaluated,
            "probes": {k: v.to_dict() for k, v in self.probes.items()},
        }


# ---------------------------------------------------------------------------
# §3.9 — Skill Index
# ---------------------------------------------------------------------------

class SkillClass:
    BUILTIN  = "builtin"
    CUSTOM   = "custom"
    OPERATOR = "operator"


@dataclass(slots=True)
class SkillEntry:
    name: str
    desc: str
    manifest: str   # path relative to entity root
    cls: str        # SkillClass constant

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> SkillEntry:
        return cls(name=d["name"], desc=d["desc"], manifest=d["manifest"], cls=d["class"])

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "desc": self.desc, "manifest": self.manifest, "class": self.cls}


@dataclass(slots=True)
class AliasEntry:
    skill: str
    operator_only: bool = False

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> AliasEntry:
        return cls(skill=d["skill"], operator_only=d.get("operator_only", False))

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"skill": self.skill}
        if self.operator_only:
            d["operator_only"] = True
        return d


@dataclass(slots=True)
class SkillIndex:
    version: str
    skills: list[SkillEntry]
    aliases: dict[str, AliasEntry]  # "/command" → AliasEntry

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> SkillIndex:
        return cls(
            version=d["version"],
            skills=[SkillEntry.from_dict(s) for s in d.get("skills", [])],
            aliases={k: AliasEntry.from_dict(v) for k, v in d.get("aliases", {}).items()},
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "skills": [s.to_dict() for s in self.skills],
            "aliases": {k: v.to_dict() for k, v in self.aliases.items()},
        }

    def get(self, name: str) -> SkillEntry | None:
        for s in self.skills:
            if s.name == name:
                return s
        return None

    def visible_to_cpe(self) -> list[SkillEntry]:
        """builtin + custom only; operator skills excluded from [SKILLS INDEX]."""
        return [s for s in self.skills if s.cls in (SkillClass.BUILTIN, SkillClass.CUSTOM)]


# ---------------------------------------------------------------------------
# §3.10 — Skill Manifest
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class SkillManifest:
    name: str
    cls: str            # SkillClass constant
    version: str        # semver
    description: str
    timeout_seconds: int
    background: bool
    ttl_seconds: int | None
    permissions: list[str]
    dependencies: list[str]

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> SkillManifest:
        return cls(
            name=d["name"],
            cls=d["class"],
            version=d["version"],
            description=d["description"],
            timeout_seconds=d["timeout_seconds"],
            background=d["background"],
            ttl_seconds=d.get("ttl_seconds"),
            permissions=list(d.get("permissions", [])),
            dependencies=list(d.get("dependencies", [])),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "class": self.cls,
            "version": self.version,
            "description": self.description,
            "timeout_seconds": self.timeout_seconds,
            "background": self.background,
            "ttl_seconds": self.ttl_seconds,
            "permissions": self.permissions,
            "dependencies": self.dependencies,
        }


# ---------------------------------------------------------------------------
# §3.11 — Drift Probe
# ---------------------------------------------------------------------------

class DriftCheckType:
    HASH    = "hash"
    STRING  = "string"
    PATTERN = "pattern"


@dataclass(slots=True)
class DeterministicLayer:
    type: str   # DriftCheckType constant
    value: str

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> DeterministicLayer:
        return cls(type=d["type"], value=d["value"])

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "value": self.value}


@dataclass(slots=True)
class DriftProbe:
    id: str
    description: str
    target: str                          # path relative to entity root
    deterministic: DeterministicLayer | None
    reference: str | None                # probabilistic layer input

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> DriftProbe:
        det = d.get("deterministic")
        return cls(
            id=d["id"],
            description=d["description"],
            target=d["target"],
            deterministic=DeterministicLayer.from_dict(det) if det else None,
            reference=d.get("reference"),
        )

    def to_dict(self) -> dict[str, Any]:
        det = self.deterministic
        return {
            "id": self.id,
            "description": self.description,
            "target": self.target,
            "deterministic": det.to_dict() if det is not None else None,
            "reference": self.reference,
        }

    @property
    def is_malformed(self) -> bool:
        """Both layers absent → malformed per spec §3.11."""
        return self.deterministic is None and self.reference is None


# ---------------------------------------------------------------------------
# §3.12 — Integrity Chain Entry
# ---------------------------------------------------------------------------

class ChainEntryType:
    GENESIS          = "genesis"
    ENDURE_COMMIT    = "ENDURE_COMMIT"
    SEVERANCE_COMMIT = "SEVERANCE_COMMIT"
    MODEL_CHANGE     = "MODEL_CHANGE"


@dataclass(slots=True)
class ChainEntry:
    seq: int
    type: str       # ChainEntryType constant
    ts: str         # ISO 8601 UTC
    prev_hash: str | None   # None for genesis

    # genesis
    imprint_hash: str | None = None

    # ENDURE_COMMIT
    evolution_auth_digest: str | None = None

    # SEVERANCE_COMMIT
    skill_removed: str | None = None
    reason: str | None = None

    # MODEL_CHANGE
    from_backend: str | None = None
    to_backend: str | None = None

    # ENDURE_COMMIT, SEVERANCE_COMMIT, MODEL_CHANGE
    files: dict[str, str] = field(default_factory=dict)
    integrity_doc_hash: str | None = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ChainEntry:
        return cls(
            seq=d["seq"],
            type=d["type"],
            ts=d["ts"],
            prev_hash=d.get("prev_hash"),
            imprint_hash=d.get("imprint_hash"),
            evolution_auth_digest=d.get("evolution_auth_digest"),
            skill_removed=d.get("skill_removed"),
            reason=d.get("reason"),
            from_backend=d.get("from"),
            to_backend=d.get("to"),
            files=dict(d.get("files", {})),
            integrity_doc_hash=d.get("integrity_doc_hash"),
        )

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"seq": self.seq, "type": self.type, "ts": self.ts}
        if self.type == ChainEntryType.GENESIS:
            d["imprint_hash"] = self.imprint_hash
            d["prev_hash"] = None
        else:
            d["prev_hash"] = self.prev_hash
            d["files"] = self.files
            d["integrity_doc_hash"] = self.integrity_doc_hash
            if self.type == ChainEntryType.ENDURE_COMMIT:
                d["evolution_auth_digest"] = self.evolution_auth_digest
            elif self.type == ChainEntryType.SEVERANCE_COMMIT:
                d["skill_removed"] = self.skill_removed
                d["reason"] = self.reason
            elif self.type == ChainEntryType.MODEL_CHANGE:
                d["from"] = self.from_backend
                d["to"] = self.to_backend
        return d

    def as_jsonl_line(self) -> str:
        """Canonical serialisation used for prev_hash computation."""
        return json.dumps(self.to_dict(), separators=(",", ":"))


# ---------------------------------------------------------------------------
# §3.13 — Imprint Record
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class ImprintRecord:
    version: str
    activated_at: str       # ISO 8601 UTC
    haca_arch_version: str
    haca_profile: str
    operator_bound: OperatorBound
    structural_baseline: str    # "sha256:..." of state/baseline.json at activation
    integrity_document: str     # "sha256:..." of state/integrity.json at activation
    skills_index: str           # "sha256:..." of skills/index.json at activation

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ImprintRecord:
        return cls(
            version=d["version"],
            activated_at=d["activated_at"],
            haca_arch_version=d["haca_arch_version"],
            haca_profile=d["haca_profile"],
            operator_bound=OperatorBound.from_dict(d["operator_bound"]),
            structural_baseline=d["structural_baseline"],
            integrity_document=d["integrity_document"],
            skills_index=d["skills_index"],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "activated_at": self.activated_at,
            "haca_arch_version": self.haca_arch_version,
            "haca_profile": self.haca_profile,
            "operator_bound": self.operator_bound.to_dict(),
            "structural_baseline": self.structural_baseline,
            "integrity_document": self.integrity_document,
            "skills_index": self.skills_index,
        }


# ---------------------------------------------------------------------------
# §10.7 — Distress Beacon payload
# ---------------------------------------------------------------------------

class BeaconCause:
    N_BOOT          = "n_boot"
    N_CHANNEL       = "n_channel"
    SIL_UNRESPONSIVE = "sil_unresponsive"


@dataclass(slots=True)
class DistressBeacon:
    cause: str          # BeaconCause constant
    ts: str             # ISO 8601 UTC
    consecutive_failures: int

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> DistressBeacon:
        return cls(
            cause=d["cause"],
            ts=d["ts"],
            consecutive_failures=d["consecutive_failures"],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "cause": self.cause,
            "ts": self.ts,
            "consecutive_failures": self.consecutive_failures,
        }
