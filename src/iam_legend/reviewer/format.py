"""Turn a FullReport into a GitHub PR review payload.

Gemini composes the top-level body prose when available. Inline comments are
generated deterministically from `by_file` + resources (we know the file/line
already, no LLM needed).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Literal

from iam_legend.types import FullReport


Event = Literal["APPROVE", "REQUEST_CHANGES"]


@dataclass(slots=True)
class InlineComment:
    file: str
    line: int
    body: str


@dataclass(slots=True)
class ReviewPayload:
    event: Event
    body: str
    comments: list[InlineComment] = field(default_factory=list)


def _call_gemini(prompt: str) -> str:
    project = os.getenv("VERTEX_PROJECT")
    location = os.getenv("VERTEX_LOCATION", "us-central1")
    if not project:
        raise RuntimeError("VERTEX_PROJECT not set; cannot call Gemini")
    from vertexai import init as vertex_init
    from vertexai.generative_models import GenerativeModel

    vertex_init(project=project, location=location)
    # Vertex's Gemini IDs differ from AI Studio's aliases. `gemini-2.5-flash`
    # is a stable Vertex name; `gemini-flash-latest` will 404 here.
    model_name = os.getenv("VERTEX_MODEL", "gemini-2.5-flash")
    return GenerativeModel(model_name).generate_content(prompt).text.strip()


_BODY_PROMPT = """Write a concise, friendly GitHub PR review comment from an automated IAM bot.

Context:
- Deployer service account: {deployer}
- Missing GCP IAM permissions: {missing}
- Recommended roles to grant: {roles}
- Recommender reasoning: {reasoning}

Format (markdown):
1. One-sentence verdict
2. The required additions (a markdown bulleted list of roles)
3. The grant commands fenced in ```bash
4. (Brief) why this PR can't ship without these
Keep it under 200 words. No emojis except ✅ / 🚫 in the verdict.
"""


def format_review(report: FullReport, deployer: str) -> ReviewPayload:
    missing = report.live_state.missing if report.live_state else report.required_permissions
    if not missing:
        return ReviewPayload(
            event="APPROVE",
            body=(
                f"✅ **iam-legend: Approved**\n\n"
                f"Deployer SA `{deployer}` holds all {len(report.required_permissions)} "
                f"required permission(s). Safe to apply."
            ),
            comments=[],
        )

    try:
        prompt = _BODY_PROMPT.format(
            deployer=deployer,
            missing=missing,
            roles=report.recommendation.roles,
            reasoning=report.recommendation.reasoning,
        )
        body_prose = _call_gemini(prompt)
    except Exception as e:
        # Surface the reason so silent template-only reviews are debuggable.
        import sys
        print(
            f"::warning title=iam-legend::Gemini review-prose call failed; "
            f"using templated fallback. Error: {type(e).__name__}: {e}",
            file=sys.stderr,
        )
        body_prose = _template_body(report, deployer, missing)

    comments = _build_inline_comments(report, missing)

    return ReviewPayload(event="REQUEST_CHANGES", body=body_prose, comments=comments)


def _template_body(report: FullReport, deployer: str, missing: list[str]) -> str:
    lines: list[str] = [
        "🚫 **iam-legend: Changes requested**",
        "",
        f"Deployer SA `{deployer}` is missing {len(missing)} permission(s) required by this PR:",
        "",
    ]
    for p in missing:
        lines.append(f"- `{p}`")
    lines.append("")
    lines.append("**Recommended additions:**")
    for r in report.recommendation.roles:
        lines.append(f"- `{r}`")
    lines.append("")
    lines.append("**Grant commands:**")
    lines.append("```bash")
    lines.extend(report.grant_commands)
    lines.append("```")
    if report.recommendation.reasoning:
        lines.append("")
        lines.append(f"_{report.recommendation.reasoning}_")
    return "\n".join(lines)


def _build_inline_comments(report: FullReport, missing: list[str]) -> list[InlineComment]:
    """One comment per (file, line). Lists ONLY the perms required by the
    resource AT that line, deduplicated. Earlier versions used the file-level
    aggregation, which leaked perms from other resources in the same file.
    """
    from iam_legend.catalog.loader import load_catalog

    catalog = load_catalog()
    missing_set = set(missing)
    out: list[InlineComment] = []
    seen: set[tuple[str, int]] = set()
    for r in report.resources:
        if r.line <= 0:
            continue
        key = (r.file, r.line)
        if key in seen:
            continue
        per_resource = catalog.lookup_resource(r.kind, r.operation) or []
        relevant = sorted({p for p in per_resource if p in missing_set})
        if not relevant:
            continue
        seen.add(key)
        body = (
            f"💡 **iam-legend**: this `{r.kind}` requires permission(s) the deployer SA "
            f"is missing:\n"
            + "\n".join(f"- `{p}`" for p in relevant)
        )
        out.append(InlineComment(file=r.file, line=r.line, body=body))
    return out
