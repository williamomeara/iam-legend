"""Generate candidate role bundles for the recommender's Gemini picker.

The historical interface (`cover()`) returns a single chosen list. The
new `propose_candidates()` returns multiple distinct bundles with
metadata so an LLM (or other downstream chooser) can pick contextually.

Both interfaces are kept — `cover()` is still used by some tests and as
the safe fallback when Gemini is unavailable or hallucinates.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Callable

from iam_legend.catalog.loader import Catalog

_HARD_DENY = {
    "roles/owner",
    "roles/editor",
    "roles/viewer",
    "roles/iam.securityAdmin",
}

# Service-agent roles are managed by Google and bound to Google-managed
# service accounts; they should never be recommended for a user-managed SA.
_SERVICE_AGENT_SUFFIXES = ("ServiceAgent", "serviceAgent")


def _is_service_agent_role(role_name: str) -> bool:
    return any(role_name.endswith(s) for s in _SERVICE_AGENT_SUFFIXES)


def _is_migration_role(role_name: str) -> bool:
    # Migration-specific roles (containerRegistryMigrationAdmin, etc.) cover
    # perms only because the migration tooling needs them — meaningless to
    # grant for ordinary deploys.
    lowered = role_name.lower()
    return "migration" in lowered


@dataclass(slots=True)
class RoleCandidates:
    """Historical single-pick result. Kept for backward compatibility."""

    chosen: list[str] = field(default_factory=list)
    uncovered: list[str] = field(default_factory=list)
    alternatives: list[list[str]] = field(default_factory=list)


@dataclass(slots=True)
class CandidateBundle:
    """One candidate role bundle with metadata for downstream LLM picking."""

    roles: list[str]
    covered: list[str]                  # perms in the requirement actually covered by this bundle
    uncovered: list[str]                # perms in the requirement NOT covered
    extra_perms_count: int              # perms granted by this bundle beyond what was required
    service_breakdown: dict[str, int]   # {service_prefix: role_count} — e.g. {"storage": 1, "pubsub": 1}
    strategy: str                       # which scoring strategy produced this bundle


def _greedy_cover(
    required: set[str],
    candidates_pool: dict[str, set[str]],
    catalog: Catalog,
    score_fn: Callable[[str, set[str], set[str]], tuple],
) -> list[str]:
    """One greedy pass. Returns the chosen role list."""
    chosen: list[str] = []
    remaining = set(required)
    pool = dict(candidates_pool)
    while remaining and pool:
        best_role = max(pool, key=lambda r: score_fn(r, pool[r], remaining))
        best_overlap = pool[best_role] & remaining
        if not best_overlap:
            break
        chosen.append(best_role)
        remaining -= best_overlap
        del pool[best_role]
    return sorted(chosen)


def _build_pool(required: set[str], catalog: Catalog, avoid: set[str]) -> dict[str, set[str]]:
    pool: dict[str, set[str]] = {}
    for role_name, data in catalog.roles.items():
        if role_name in avoid:
            continue
        if _is_service_agent_role(role_name):
            continue
        if _is_migration_role(role_name):
            continue
        perms = set(data.get("permissions", []))
        if "*" in perms:
            # roles/owner-equivalent; skip even if not in deny list explicitly
            continue
        overlap = perms & required
        if overlap:
            pool[role_name] = perms
    return pool


def _service_prefix(perm_or_role: str) -> str:
    # Both perms ("storage.buckets.create") and role names ("roles/storage.admin")
    # encode the service in their first dot-separated token.
    stripped = perm_or_role.removeprefix("roles/")
    return stripped.split(".", 1)[0]


def _bundle_metadata(
    roles: list[str], required: set[str], catalog: Catalog, strategy: str
) -> CandidateBundle:
    all_perms: set[str] = set()
    for r in roles:
        all_perms.update(catalog.roles.get(r, {}).get("permissions", []))
    covered = sorted(required & all_perms)
    uncovered = sorted(required - all_perms)
    extra = len(all_perms - required)
    breakdown = Counter(_service_prefix(r) for r in roles)
    return CandidateBundle(
        roles=roles,
        covered=covered,
        uncovered=uncovered,
        extra_perms_count=extra,
        service_breakdown=dict(breakdown),
        strategy=strategy,
    )


def _dedupe_bundles(bundles: list[CandidateBundle]) -> list[CandidateBundle]:
    seen: set[tuple[str, ...]] = set()
    out: list[CandidateBundle] = []
    for b in bundles:
        key = tuple(b.roles)
        if key in seen:
            continue
        seen.add(key)
        out.append(b)
    return out


def propose_candidates(
    required: set[str],
    catalog: Catalog,
    *,
    avoid: set[str] = _HARD_DENY,
    max_candidates: int = 5,
) -> list[CandidateBundle]:
    """Generate up to `max_candidates` distinct role bundles for downstream picking.

    Each bundle is produced by a different scoring strategy so the picker
    sees real variety, not the same bundle ranked differently.
    """
    if not required:
        return []

    pool = _build_pool(required, catalog, avoid)
    if not pool:
        return []

    # Strategy A: prefer per-service name-prefix match
    # Score: (1 if role's service prefix matches MOST common service in covered perms, else 0,
    #         cover_count, -waste, -role_size)
    def _required_service_breakdown() -> Counter:
        return Counter(_service_prefix(p) for p in required)

    req_services = _required_service_breakdown()

    def score_service_prefix(role: str, perms: set[str], remaining: set[str]) -> tuple:
        cover = len(perms & remaining)
        if cover == 0:
            return (0, 0, 0, 0)
        # Award one point if this role's service prefix is among the most-required services
        role_service = _service_prefix(role)
        most_req = req_services.most_common(1)[0][0] if req_services else None
        prefix_match = 1 if role_service == most_req else 0
        waste = len(perms - remaining)
        return (prefix_match, cover, -waste, -len(perms))

    # Strategy B: prefer most-coverage-per-role (consolidate into few broad roles)
    def score_consolidate(role: str, perms: set[str], remaining: set[str]) -> tuple:
        cover = len(perms & remaining)
        waste = len(perms - remaining)
        return (cover, -waste, role)

    # Strategy C: prefer narrowest roles (smallest extra grants)
    def score_narrow(role: str, perms: set[str], remaining: set[str]) -> tuple:
        cover = len(perms & remaining)
        if cover == 0:
            return (0, 0, 0)
        waste_ratio_negated = -len(perms - remaining)
        return (cover, waste_ratio_negated, -len(perms))

    # Strategy D: same as A but exclude any role whose service prefix doesn't
    # match a service in `required`. Stricter form of per-service matching.
    relevant_services = set(req_services.keys())

    def score_strict_per_service(role: str, perms: set[str], remaining: set[str]) -> tuple:
        role_service = _service_prefix(role)
        if role_service not in relevant_services:
            return (-1, 0, 0)  # heavily penalised; not chosen unless nothing else works
        cover = len(perms & remaining)
        return (cover, -len(perms - remaining), -len(perms))

    strategies = [
        ("per_service_prefix", score_service_prefix),
        ("consolidate_broad", score_consolidate),
        ("narrowest_roles", score_narrow),
        ("strict_per_service", score_strict_per_service),
    ]

    bundles: list[CandidateBundle] = []
    for name, score_fn in strategies:
        chosen = _greedy_cover(required, pool, catalog, score_fn)
        if chosen:
            bundles.append(_bundle_metadata(chosen, required, catalog, name))

    return _dedupe_bundles(bundles)[:max_candidates]


def cover(
    required: set[str],
    catalog: Catalog,
    *,
    avoid: set[str] = _HARD_DENY,
    prefer_per_service: bool = True,
) -> RoleCandidates:
    """Single-pick API — kept for backward compatibility. Returns the top
    candidate from propose_candidates(), or empty if nothing covers the
    requirement.
    """
    if not required:
        return RoleCandidates()
    candidates = propose_candidates(required, catalog, avoid=avoid)
    if not candidates:
        return RoleCandidates(
            chosen=[],
            uncovered=sorted(required),
            alternatives=[],
        )
    top = candidates[0]
    return RoleCandidates(
        chosen=top.roles,
        uncovered=top.uncovered,
        alternatives=[c.roles for c in candidates[1:]],
    )
