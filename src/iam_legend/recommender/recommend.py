"""Hybrid recommender: set-cover proposes candidate bundles, Gemini picks.

Replaces the v0.1 single-pick `set_cover.cover() + justify.justify_recommendation()`
flow where set-cover deterministically picked one bundle and Gemini only wrote
prose. That decoupled the math from the explanation — Gemini was justifying
picks it had no part in choosing, so weird picks like `roles/iam.databasesAdmin`
for non-database perms slipped through with confident-sounding justification.

New flow:
  1. set_cover.propose_candidates() → up to 5 distinct bundles with metadata
  2. Gemini picks the best with full context (project, perm services, candidate
     metadata, explicit avoid rules)
  3. Verify Gemini's choice exists in the catalog and actually covers the
     perms — fall back to candidate[0] (set-cover's per-service-prefix top)
     if Gemini hallucinates or returns something invalid

Gemini is OFF the correctness path: if the call fails or returns garbage,
the deterministic fallback runs and the user still gets a sensible review.
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field

from iam_legend.catalog.loader import Catalog
from iam_legend.recommender.set_cover import (
    CandidateBundle,
    propose_candidates,
)


@dataclass(slots=True)
class Recommendation:
    """Result of the recommender — the chosen bundle + reasoning + alternatives."""

    roles: list[str]
    reasoning: str
    alternatives: list[list[str]] = field(default_factory=list)
    uncovered: list[str] = field(default_factory=list)
    source: str = "fallback"   # "gemini" | "fallback" | "no-candidates"


_PICKER_PROMPT = """You are picking the best set of predefined GCP IAM roles to grant a
deployer service account so it can apply a Terraform plan.

STRICT RULES (violating these is wrong, not a judgement call):
1. Never recommend roles/owner, roles/editor, roles/viewer, roles/iam.securityAdmin.
2. Never recommend service-agent roles (names ending in ServiceAgent / serviceAgent).
3. Never recommend roles whose primary service is unrelated to the required perms.
   Example: do NOT recommend roles/iam.databasesAdmin for perms like
   pubsub.topics.create or iam.serviceAccounts.create — that role is for
   Cloud Spanner database IAM management.
4. Prefer roles whose name prefix matches the service of the perms they cover:
   storage.* perms → roles/storage.*
   pubsub.* perms → roles/pubsub.*
   aiplatform.* perms → roles/aiplatform.*
   iam.serviceAccounts.* → roles/iam.serviceAccountAdmin or roles/iam.serviceAccountUser
   serviceusage.services.* → roles/serviceusage.serviceUsageAdmin
   resourcemanager.projects.setIamPolicy → roles/resourcemanager.projectIamAdmin

CONTEXT
GCP project: {project_id}
Required permissions ({n_perms}):
{perm_list}

Required services breakdown:
{services_breakdown}

CANDIDATE BUNDLES (from greedy set-cover with 4 different scoring strategies):
{candidates_block}

TASK
Pick the best candidate bundle by INDEX (0-based). You may not invent new
roles — pick from the candidates above. Explain in 2-3 sentences why this
bundle is the best of the options and what (if anything) the engineer should
double-check before approving.

Output STRICTLY this JSON shape, no surrounding prose:
{{"bundle_index": <int>, "reasoning": "<2-3 sentences>", "warnings": ["<concerning grant>", ...]}}
"""


def _format_candidates_block(candidates: list[CandidateBundle]) -> str:
    lines: list[str] = []
    for i, c in enumerate(candidates):
        lines.append(f"Bundle {i} (strategy: {c.strategy}):")
        for r in c.roles:
            lines.append(f"  - {r}")
        lines.append(f"  Covered: {len(c.covered)}/{len(c.covered)+len(c.uncovered)} perms")
        if c.uncovered:
            lines.append(f"  UNCOVERED perms: {c.uncovered}")
        lines.append(f"  Extra perms granted beyond requirement: {c.extra_perms_count}")
        if c.service_breakdown:
            sb = ", ".join(f"{k}:{v}" for k, v in sorted(c.service_breakdown.items()))
            lines.append(f"  Service breakdown: {sb}")
        lines.append("")
    return "\n".join(lines)


def _format_services_breakdown(required: set[str]) -> str:
    from collections import Counter
    services = Counter(p.split(".", 1)[0] for p in required)
    return ", ".join(f"{s}:{c}" for s, c in sorted(services.items()))


def _call_gemini(prompt: str) -> str:
    project = os.getenv("VERTEX_PROJECT")
    location = os.getenv("VERTEX_LOCATION", "us-central1")
    if not project:
        raise RuntimeError("VERTEX_PROJECT not set; cannot call Gemini")
    from vertexai import init as vertex_init
    from vertexai.generative_models import GenerativeModel, GenerationConfig

    vertex_init(project=project, location=location)
    model_name = os.getenv("VERTEX_MODEL", "gemini-2.5-flash")
    model = GenerativeModel(model_name)
    # response_mime_type forces JSON-only output — saves us a regex post-parse.
    resp = model.generate_content(
        prompt,
        generation_config=GenerationConfig(
            response_mime_type="application/json",
            temperature=0.2,
        ),
    )
    return resp.text.strip()


def _parse_gemini_pick(raw: str) -> tuple[int, str, list[str]]:
    """Returns (bundle_index, reasoning, warnings). Raises on invalid shape."""
    # Strip markdown fences if Gemini wrapped them despite the JSON mime type
    raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    parsed = json.loads(raw)
    idx = int(parsed["bundle_index"])
    reasoning = str(parsed.get("reasoning", "")).strip()
    warnings = parsed.get("warnings") or []
    if not isinstance(warnings, list):
        warnings = [str(warnings)]
    return idx, reasoning, [str(w) for w in warnings]


def _verify_bundle_against_catalog(
    bundle: CandidateBundle, required: set[str], catalog: Catalog
) -> bool:
    """Defensive check: all bundle roles exist in the catalog AND together
    cover the required perms (or the bundle's recorded `covered` set, which
    should match)."""
    union: set[str] = set()
    for r in bundle.roles:
        data = catalog.roles.get(r)
        if data is None:
            return False
        union.update(data.get("permissions", []))
    # Bundle's recorded `covered` must match what we actually cover.
    return set(bundle.covered) <= union


def recommend(
    required: set[str],
    catalog: Catalog,
    *,
    project_id: str | None = None,
) -> Recommendation:
    """End-to-end recommender: set-cover + Gemini pick + verification."""
    if not required:
        return Recommendation(
            roles=[],
            reasoning="No additional permissions are required by this PR.",
            source="no-candidates",
        )

    candidates = propose_candidates(required, catalog)
    if not candidates:
        return Recommendation(
            roles=[],
            reasoning=(
                f"No predefined GCP role covers the required permissions: "
                f"{sorted(required)}. A custom role may be needed."
            ),
            uncovered=sorted(required),
            source="no-candidates",
        )

    # Try Gemini picker
    try:
        prompt = _PICKER_PROMPT.format(
            project_id=project_id or "<your-project>",
            n_perms=len(required),
            perm_list="\n".join(f"  - {p}" for p in sorted(required)),
            services_breakdown=_format_services_breakdown(required),
            candidates_block=_format_candidates_block(candidates),
        )
        raw = _call_gemini(prompt)
        idx, reasoning, warnings = _parse_gemini_pick(raw)
        if not (0 <= idx < len(candidates)):
            raise ValueError(f"Gemini returned out-of-range bundle index {idx}")
        chosen = candidates[idx]
        if not _verify_bundle_against_catalog(chosen, required, catalog):
            raise ValueError(f"chosen bundle {chosen.roles!r} failed catalog verification")
        # Append warnings to reasoning if present
        if warnings:
            reasoning = (
                reasoning + "\n\n" + "\n".join(f"⚠️ {w}" for w in warnings)
            ).strip()
        alternatives = [c.roles for c in candidates if c is not chosen]
        return Recommendation(
            roles=chosen.roles,
            reasoning=reasoning,
            alternatives=alternatives,
            uncovered=chosen.uncovered,
            source="gemini",
        )
    except Exception as e:
        # Surface the reason in CI logs so silent fallback isn't invisible.
        print(
            f"::warning title=iam-legend::Gemini recommender pick failed; "
            f"using deterministic top candidate. Error: {type(e).__name__}: {e}",
            file=sys.stderr,
        )

    # Deterministic fallback: top candidate from set-cover's per-service-prefix strategy
    top = candidates[0]
    return Recommendation(
        roles=top.roles,
        reasoning=_template_reasoning(top, required),
        alternatives=[c.roles for c in candidates[1:]],
        uncovered=top.uncovered,
        source="fallback",
    )


def _template_reasoning(bundle: CandidateBundle, required: set[str]) -> str:
    n_perms = len(required)
    n_extra = bundle.extra_perms_count
    base = (
        f"Recommended {len(bundle.roles)} role(s) covering all {n_perms} required "
        f"permission(s) without granting roles/owner or roles/editor. "
        f"This bundle grants {n_extra} additional perms beyond the strict requirement."
    )
    if bundle.uncovered:
        base += (
            f" Note: {len(bundle.uncovered)} required permission(s) could not be "
            f"covered by any predefined role — a custom role or manual grant "
            f"may be needed for: {bundle.uncovered}."
        )
    return base
