"""Shared data types for iam-legend.

Every parser emits DetectedGCPResource; the resolver folds them into a
ResolvedRequirements; the orchestrator returns a FullReport.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Literal, TypeAlias

Operation: TypeAlias = Literal["create", "update", "delete"]
ParserSource: TypeAlias = Literal[
    "terraform_plan",
    "terraform_hcl",
    "adk_python",
    "gcloud_sh",
    "cloudbuild",
    "github_actions",
]


@dataclass(slots=True)
class DetectedGCPResource:
    kind: str            # e.g. "google_storage_bucket" or "vertex.agent_engine_create"
    name: str            # tf name, python variable, or synthetic id
    operation: Operation
    file: str
    line: int            # 0 if unknown
    source: ParserSource

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class ResolvedRequirements:
    permissions: set[str] = field(default_factory=set)
    apis: set[str] = field(default_factory=set)
    by_file: dict[str, list[str]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class RoleRecommendation:
    roles: list[str]
    reasoning: str
    alternatives: list[list[str]]


@dataclass(slots=True)
class AccessRequestDraft:
    subject: str
    body: str
    suggested_approvers: list[str] = field(default_factory=list)


@dataclass(slots=True)
class LiveState:
    granted: list[str]
    missing: list[str]


@dataclass(slots=True)
class FullReport:
    resources: list[DetectedGCPResource]
    required_permissions: list[str]
    required_apis: list[str]
    by_file: dict[str, list[str]]
    live_state: LiveState | None
    recommendation: RoleRecommendation
    grant_commands: list[str]
    access_request: AccessRequestDraft
    warnings: list[str]

    def to_dict(self) -> dict:
        d = asdict(self)
        # asdict already handles nested dataclasses; just ensure resources -> dicts
        return d
