"""Canonical VIOS control and evidence contracts.

These dataclasses are deliberately dependency-free.  They are the stable seam
between capture, processing, materialization, Atlas projections, Telegram
checkpoint manifests, and operator-facing status.  SQLite/Redis/Postgres
adapters may serialize them differently, but they must preserve these fields and
identity rules.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Mapping

CONTRACT_VERSION = "v1"


def stable_json(value: Any) -> str:
    """Canonical JSON used in hashes and manifests."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), default=str)


def content_key(*parts: Any, prefix: str = "") -> str:
    """Return a deterministic, filesystem/queue-safe content identity."""
    raw = "\x1f".join(stable_json(p) if isinstance(p, (dict, list, tuple))
                       else "" if p is None else str(p) for p in parts)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"{prefix}{digest}" if prefix else digest


class OperationState(str, Enum):
    ACCEPTED = "accepted"
    VALIDATED = "validated"
    QUEUED = "queued"
    RUNNING = "running"
    PARTIALLY_COMPLETE = "partially_complete"
    MATERIALIZING = "materializing"
    SEARCHABLE = "searchable"
    ENRICHING = "enriching"
    PUBLISHED = "published"
    COMPLETE = "complete"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SUPERSEDED = "superseded"


class JobState(str, Enum):
    CREATED = "created"
    QUEUED = "queued"
    LEASED = "leased"
    RUNNING = "running"
    COMMITTED = "committed"
    ACKNOWLEDGED = "acknowledged"
    DEFERRED = "deferred"
    RETRYABLE_FAILURE = "retryable_failure"
    PERMANENT_FAILURE = "permanent_failure"
    DEAD_LETTER = "dead_letter"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class AssetRef:
    asset_id: str
    corpus_id: str = "default"
    source_channel: str = ""
    source_message_id: str = ""
    sha256: str = ""
    duration_seconds: float = 0.0
    mime_type: str = "video/mp4"
    source_uri: str = ""
    local_uri: str = ""
    created_at: float = field(default_factory=time.time)

    @classmethod
    def from_source(cls, *, channel: str, message_id: str,
                    sha256: str = "", filename: str = "",
                    corpus_id: str = "default", **kwargs) -> "AssetRef":
        identity = content_key(channel, str(message_id), sha256, filename,
                               prefix="asset_")
        return cls(asset_id=identity, corpus_id=corpus_id,
                   source_channel=channel, source_message_id=str(message_id),
                   sha256=sha256, **kwargs)


@dataclass(frozen=True)
class GenerationRef:
    generation_id: str
    schema_version: str = CONTRACT_VERSION
    model: str = ""
    revision: str = ""
    prompt_hash: str = ""
    params: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ResourceContract:
    resource_class: str = "cpu"
    gpu_count: int = 0
    gpu_index: int | None = None
    vram_mb: int = 0
    exclusive: bool = False
    batch_size: int = 1
    model_residency: str = "ephemeral"
    priority: int = 50

    def validate(self) -> None:
        if self.gpu_count < 0:
            raise ValueError("gpu_count cannot be negative")
        if self.vram_mb < 0:
            raise ValueError("vram_mb cannot be negative")
        if self.batch_size < 1:
            raise ValueError("batch_size must be positive")
        if self.gpu_count == 0 and self.gpu_index is not None:
            raise ValueError("gpu_index requires gpu_count > 0")


@dataclass(frozen=True)
class ArtifactRef:
    artifact_id: str
    asset_id: str
    artifact_type: str
    uri: str = ""
    sha256: str = ""
    bytes: int = 0
    generation_id: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def for_output(cls, asset_id: str, artifact_type: str,
                   generation_id: str, input_refs: list[str] | tuple[str, ...] = (),
                   **kwargs) -> "ArtifactRef":
        artifact_id = content_key(asset_id, artifact_type, generation_id,
                                  list(input_refs), prefix="artifact_")
        return cls(artifact_id=artifact_id, asset_id=asset_id,
                   artifact_type=artifact_type, generation_id=generation_id,
                   **kwargs)


@dataclass(frozen=True)
class JobRef:
    job_id: str
    operation_id: str
    asset_id: str
    component: str
    generation_id: str
    state: JobState = JobState.CREATED
    attempt: int = 0
    max_attempts: int = 3
    priority: int = 50
    resource: ResourceContract = field(default_factory=ResourceContract)
    input_refs: tuple[str, ...] = ()
    output_refs: tuple[str, ...] = ()
    lease_owner: str = ""
    lease_expires_at: float = 0.0
    next_try_at: float = 0.0
    error_type: str = ""
    error_message: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    @classmethod
    def create(cls, *, operation_id: str, asset_id: str, component: str,
               generation_id: str, resource: ResourceContract | None = None,
               input_refs: list[str] | tuple[str, ...] = (),
               **kwargs) -> "JobRef":
        resource = resource or ResourceContract()
        resource.validate()
        job_id = content_key(asset_id, component, generation_id,
                             list(input_refs), prefix="job_")
        return cls(job_id=job_id, operation_id=operation_id,
                   asset_id=asset_id, component=component,
                   generation_id=generation_id, resource=resource,
                   input_refs=tuple(input_refs), **kwargs)


@dataclass(frozen=True)
class EvidenceMoment:
    moment_id: str
    asset_id: str
    corpus_id: str
    generation_id: str
    start_sec: float
    end_sec: float
    modality: str
    evidence_type: str
    text: str = ""
    confidence: float = 1.0
    frame_start: int | None = None
    frame_end: int | None = None
    source_artifact_refs: tuple[str, ...] = ()
    vector_refs: tuple[str, ...] = ()
    claims: tuple[Mapping[str, Any], ...] = ()
    visibility: str = "corpus_default"

    @classmethod
    def create(cls, *, asset_id: str, corpus_id: str,
               generation_id: str, start_sec: float, end_sec: float,
               modality: str, evidence_type: str, **kwargs) -> "EvidenceMoment":
        if end_sec < start_sec:
            raise ValueError("end_sec cannot be earlier than start_sec")
        moment_id = content_key(asset_id, generation_id, round(start_sec, 3),
                                round(end_sec, 3), modality, evidence_type,
                                kwargs.get("frame_start"),
                                kwargs.get("frame_end"), prefix="moment_")
        return cls(moment_id=moment_id, asset_id=asset_id,
                   corpus_id=corpus_id, generation_id=generation_id,
                   start_sec=float(start_sec), end_sec=float(end_sec),
                   modality=modality, evidence_type=evidence_type, **kwargs)


@dataclass
class OperationRef:
    operation_id: str
    corpus_id: str = "default"
    profile: str = "search"
    generation_id: str = ""
    state: OperationState = OperationState.ACCEPTED
    total_assets: int = 0
    completed_assets: int = 0
    searchable_assets: int = 0
    failed_assets: int = 0
    current_stage: str = ""
    cancel_requested: bool = False
    heartbeat_at: float = field(default_factory=time.time)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    error_type: str = ""
    error_message: str = ""
    output_refs: list[str] = field(default_factory=list)

    @classmethod
    def create(cls, *, corpus_id: str = "default", profile: str = "search",
               generation_id: str = "", total_assets: int = 0) -> "OperationRef":
        operation_id = content_key(corpus_id, profile, generation_id,
                                   time.time_ns(), prefix="op_")
        return cls(operation_id=operation_id, corpus_id=corpus_id,
                   profile=profile, generation_id=generation_id,
                   total_assets=total_assets)

    def heartbeat(self, stage: str = "") -> None:
        now = time.time()
        self.heartbeat_at = now
        self.updated_at = now
        if stage:
            self.current_stage = stage

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["state"] = self.state.value
        return value


@dataclass(frozen=True)
class ProjectionRef:
    projection_id: str
    name: str
    generation_id: str
    source_artifact_refs: tuple[str, ...] = ()
    status: str = "pending"
    last_error: str = ""
    updated_at: float = field(default_factory=time.time)

    @classmethod
    def create(cls, *, name: str, generation_id: str,
               source_artifact_refs: list[str] | tuple[str, ...] = ()) -> "ProjectionRef":
        projection_id = content_key(name, generation_id,
                                    list(source_artifact_refs), prefix="projection_")
        return cls(projection_id=projection_id, name=name,
                   generation_id=generation_id,
                   source_artifact_refs=tuple(source_artifact_refs))


def serialize_contract(value: Any) -> dict[str, Any]:
    """Serialize enums and nested dataclasses for manifests/status APIs."""
    out = asdict(value) if hasattr(value, "__dataclass_fields__") else value

    def convert(item):
        if isinstance(item, Enum):
            return item.value
        if hasattr(item, "__dataclass_fields__"):
            return {k: convert(v) for k, v in asdict(item).items()}
        if isinstance(item, dict):
            return {str(k): convert(v) for k, v in item.items()}
        if isinstance(item, (list, tuple)):
            return [convert(v) for v in item]
        return item

    return convert(out)


__all__ = [
    "CONTRACT_VERSION", "AssetRef", "ArtifactRef", "EvidenceMoment",
    "GenerationRef", "JobRef", "JobState", "OperationRef", "OperationState",
    "ProjectionRef", "ResourceContract", "content_key", "serialize_contract",
    "stable_json",
]
