"""Generate the natural-language justification for a role recommendation.

Tries Vertex Gemini Flash-tier; falls back to a deterministic template if the
call fails or AI Platform isn't configured. Justification is OFF the
correctness path — the math is the math, this is just prose.
"""
from __future__ import annotations

import os

from iam_legend.recommender.set_cover import RoleCandidates


_PROMPT_TEMPLATE = """You are helping a platform engineer pick the smallest sensible set of
predefined GCP IAM roles to cover a list of required permissions before a
terraform apply. The roles/owner, roles/editor, roles/viewer, roles/iam.securityAdmin
roles are FORBIDDEN by org policy — never suggest them.

Required permissions: {perms}
Candidate role set (greedy set-cover output): {roles}

Write 2-3 sentences explaining why this set is appropriate, and surface any
concerning grants the engineer should double-check. Be terse and concrete.
"""


def _call_gemini(prompt: str) -> str:
    """Single Vertex Gemini Flash call. Raises on any error."""
    project = os.getenv("VERTEX_PROJECT")
    location = os.getenv("VERTEX_LOCATION", "us-central1")
    if not project:
        raise RuntimeError("VERTEX_PROJECT not set; cannot call Gemini")
    from vertexai import init as vertex_init
    from vertexai.generative_models import GenerativeModel

    vertex_init(project=project, location=location)
    # Note: `gemini-flash-latest` is an AI Studio alias — it does NOT resolve
    # on Vertex AI. Use a Vertex-supported identifier like `gemini-2.5-flash`.
    model_name = os.getenv("VERTEX_MODEL", "gemini-2.5-flash")
    model = GenerativeModel(model_name)
    resp = model.generate_content(prompt)
    return resp.text.strip()


def justify_recommendation(rc: RoleCandidates, required_perms: set[str]) -> str:
    if not rc.chosen and rc.uncovered:
        return (
            f"No predefined role covers these permissions: {sorted(rc.uncovered)}. "
            "A custom role may be required, or one of the requested actions may be "
            "unavailable in this project."
        )
    if not rc.chosen:
        return "No additional roles required."

    prompt = _PROMPT_TEMPLATE.format(
        perms=sorted(required_perms),
        roles=rc.chosen,
    )
    try:
        return _call_gemini(prompt)
    except Exception as e:
        # Silent fallback is dangerous — surfaces in templated reviews that
        # look identical to the Gemini path being mis-configured. Log so the
        # next debug session is one log line away.
        import sys
        print(
            f"::warning title=iam-legend::Gemini justify call failed; "
            f"using templated fallback. Error: {type(e).__name__}: {e}",
            file=sys.stderr,
        )
        return _template_fallback(rc, required_perms)


def _template_fallback(rc: RoleCandidates, required_perms: set[str]) -> str:
    roles_str = ", ".join(rc.chosen)
    perms_count = len(required_perms)
    base = (
        f"Recommended roles: {roles_str}. "
        f"These cover the {perms_count} required permission(s) without granting "
        f"the broad roles/owner or roles/editor."
    )
    if rc.uncovered:
        base += f" Note: {len(rc.uncovered)} permission(s) could not be covered by any predefined role."
    return base
