"""Greedy set-cover over predefined GCP roles.

Goal: pick a small set of predefined roles that covers all required perms,
preferring per-service roles over broad roles.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from iam_legend.catalog.loader import Catalog

_HARD_DENY = {
    "roles/owner", "roles/editor", "roles/viewer", "roles/iam.securityAdmin",
}

# Service-agent roles are managed by Google and bound to Google-managed
# service accounts; they should never be recommended for a user-managed SA.
# The set-cover algorithm doesn't know this, so we screen them out by name.
_SERVICE_AGENT_SUFFIXES = ("ServiceAgent", "serviceAgent")


def _is_service_agent_role(role_name: str) -> bool:
    return any(role_name.endswith(s) for s in _SERVICE_AGENT_SUFFIXES)


@dataclass(slots=True)
class RoleCandidates:
    chosen: list[str] = field(default_factory=list)
    uncovered: list[str] = field(default_factory=list)
    alternatives: list[list[str]] = field(default_factory=list)


def cover(
    required: set[str],
    catalog: Catalog,
    *,
    avoid: set[str] = _HARD_DENY,
    prefer_per_service: bool = True,
) -> RoleCandidates:
    if not required:
        return RoleCandidates()

    candidates: dict[str, set[str]] = {}
    for role_name, data in catalog.roles.items():
        if role_name in avoid:
            continue
        if _is_service_agent_role(role_name):
            continue
        perms = set(data.get("permissions", []))
        overlap = perms & required
        if overlap:
            candidates[role_name] = overlap

    chosen: list[str] = []
    remaining = set(required)
    while remaining and candidates:
        def score(item: tuple[str, set[str]]) -> tuple[int, int, str]:
            name, overlap = item
            cover_now = len(overlap & remaining)
            if cover_now == 0:
                return (0, 0, name)
            role_size = len(catalog.roles[name].get("permissions", []))
            waste = role_size - cover_now
            return (cover_now, -waste, name)

        best = max(candidates.items(), key=score)
        if best[1] & remaining == set():
            break
        chosen.append(best[0])
        remaining -= best[1]
        del candidates[best[0]]

    return RoleCandidates(
        chosen=sorted(chosen),
        uncovered=sorted(remaining),
        alternatives=[],
    )
