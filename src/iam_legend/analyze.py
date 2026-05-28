"""The analyze() orchestrator. The MCP server, CLI, and GitHub Action all
call into here. Pure Python — no protocol-specific code.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from iam_legend.catalog.loader import load_catalog
from iam_legend.catalog.resolver import resolve
from iam_legend.gcp.auth import who_am_i, AuthError
from iam_legend.gcp import iam as iam_module
from iam_legend.parsers.base import all_parsers, walk_repo
from iam_legend.parsers.terraform_plan import TerraformPlanParser
from iam_legend.parsers.terraform_hcl import TerraformHCLParser
from iam_legend.parsers.adk_python import ADKPythonParser
from iam_legend.parsers.gcloud_sh import GcloudShellParser
from iam_legend.recommender.grants import generate_grant_commands
from iam_legend.recommender.justify import justify_recommendation
from iam_legend.recommender.set_cover import cover
from iam_legend.types import (
    AccessRequestDraft, DetectedGCPResource, FullReport, LiveState,
    RoleRecommendation,
)


def _draft_access_request(
    missing: list[str], roles: list[str], deployer: str, project: str | None,
) -> AccessRequestDraft:
    subject = f"[iam-legend] Grant {len(roles)} role(s) to deployer SA"
    body_lines = [
        f"Hi platform team,",
        f"",
        f"To ship the current PR's terraform apply, the deployer SA",
        f"`{deployer}`{' on project `' + project + '`' if project else ''}",
        f"needs the following predefined role(s):",
        f"",
    ]
    for r in roles:
        body_lines.append(f"  • {r}")
    body_lines += [
        f"",
        f"These cover the {len(missing)} permission(s) the current set of resources",
        f"requires that the SA does not yet hold. iam-legend confirmed this against",
        f"the live project IAM policy.",
        f"",
        f"Happy to chat through justifications per-permission if useful.",
        f"",
        f"— iam-legend",
    ]
    return AccessRequestDraft(subject=subject, body="\n".join(body_lines))


def _detect_from_input(input_: str, kind: str) -> list[DetectedGCPResource]:
    if kind == "plan_json":
        return TerraformPlanParser().parse_file(input_)
    if kind == "repo":
        # walk_repo dispatches via registered parsers (terraform_plan won't fire
        # on a directory walk because plan files don't sit in repos by default).
        return walk_repo(input_)
    if kind == "dir":
        return TerraformHCLParser().parse_dir(input_)
    if kind == "file":
        for p in [TerraformPlanParser(), TerraformHCLParser(), ADKPythonParser(), GcloudShellParser()]:
            if p.matches(input_):
                return p.parse_file(input_)
        return []
    if kind == "snippet":
        raise NotImplementedError("snippet kind not yet supported")
    raise ValueError(f"unknown kind: {kind}")


def analyze(
    input: str | dict,
    *,
    kind: str = "auto",
    project: str | None = None,
    principal: str = "self",
) -> FullReport:
    catalog = load_catalog()

    if kind == "auto":
        if isinstance(input, dict):
            kind = "plan_json"
        elif Path(input).is_dir():
            kind = "repo"
        elif input.endswith(".json") and "plan" in Path(input).name.lower():
            kind = "plan_json"
        else:
            kind = "file"

    if isinstance(input, dict):
        resources = TerraformPlanParser().parse_dict(input)
    else:
        resources = _detect_from_input(input, kind)

    rr = resolve(resources, catalog)

    live_state: LiveState | None = None
    if project:
        try:
            r = iam_module.test_iam_permissions(project, sorted(rr.permissions))
            live_state = LiveState(granted=r["granted"], missing=r["missing"])
        except (AuthError, RuntimeError) as e:
            rr.warnings.append(f"live IAM diff unavailable: {e}")

    missing_perms = set(live_state.missing) if live_state else set(rr.permissions)
    rc = cover(missing_perms, catalog)
    reasoning = justify_recommendation(rc, missing_perms)

    deployer = "unknown-principal"
    if principal == "self":
        try:
            deployer = who_am_i()
        except AuthError:
            pass
    else:
        deployer = principal

    grant_cmds = generate_grant_commands(rc.chosen, project or "<PROJECT_ID>", deployer)
    access_req = _draft_access_request(sorted(missing_perms), rc.chosen, deployer, project)

    return FullReport(
        resources=resources,
        required_permissions=sorted(rr.permissions),
        required_apis=sorted(rr.apis),
        by_file=rr.by_file,
        live_state=live_state,
        recommendation=RoleRecommendation(
            roles=rc.chosen, reasoning=reasoning, alternatives=rc.alternatives,
        ),
        grant_commands=grant_cmds,
        access_request=access_req,
        warnings=rr.warnings,
    )
