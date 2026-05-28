"""FastMCP server with per-transport tool gating.

Stdio (local, privileged) registers ALL tools; HTTP (hosted, read-only)
registers only catalog/static-analysis/recommender tools. See spec §8.2 for
the security rationale.
"""
from __future__ import annotations

import os
from dataclasses import asdict

from mcp.server.fastmcp import FastMCP

from iam_legend.analyze import analyze as _analyze
from iam_legend.catalog.loader import load_catalog
from iam_legend.recommender.grants import generate_grant_commands as _grants
from iam_legend.recommender.justify import justify_recommendation
from iam_legend.recommender.set_cover import cover as _cover


def build_server() -> FastMCP:
    transport = os.environ.get("IAM_LEGEND_TRANSPORT", "stdio")
    is_privileged = transport == "stdio"
    server = FastMCP("iam-legend")

    @server.tool()
    def analyze(
        input: str,
        kind: str = "auto",
        project: str | None = None,
        principal: str = "self",
    ) -> dict:
        """Analyze GCP IaC for required IAM perms."""
        if not is_privileged and kind in {"repo", "dir"}:
            raise ValueError(
                "kind='repo' and kind='dir' are stdio-only on iam-legend. "
                "Pass a precomputed terraform plan JSON file instead."
            )
        report = _analyze(input=input, kind=kind, project=project, principal=principal)
        return asdict(report)

    @server.tool()
    def lookup_permissions_for(target: str) -> dict:
        """Look up IAM info for a Terraform resource kind, a role, or a permission."""
        c = load_catalog()
        if target.startswith("roles/"):
            role = c.lookup_role(target)
            return {"kind": "role", "name": target, "data": role}
        if target in c.resources:
            return {"kind": "resource", "name": target, "data": c.resources[target]}
        if target in c.api_methods:
            return {"kind": "permission", "name": target, "roles_containing": c.roles_with(target)}
        return {"kind": "unknown", "name": target}

    @server.tool()
    def find_roles_with(permission: str) -> list[str]:
        """Return all predefined roles that include the given permission."""
        return load_catalog().roles_with(permission)

    @server.tool()
    def recommend_roles(
        permissions: list[str],
        avoid: list[str] | None = None,
    ) -> dict:
        """Recommend a minimal set of predefined roles covering the given perms."""
        c = load_catalog()
        avoid_set = set(avoid) if avoid else {"roles/owner", "roles/editor", "roles/viewer", "roles/iam.securityAdmin"}
        rc = _cover(set(permissions), c, avoid=avoid_set)
        reasoning = justify_recommendation(rc, set(permissions))
        return {
            "roles": rc.chosen,
            "uncovered": rc.uncovered,
            "reasoning": reasoning,
        }

    @server.tool()
    def generate_grant_commands(roles: list[str], project: str, principal: str) -> list[str]:
        """Generate gcloud commands to bind the given roles to the principal."""
        return _grants(roles, project, principal)

    if is_privileged:
        from iam_legend.gcp.iam import test_iam_permissions as _test_perms, get_iam_policy as _get_pol

        @server.tool()
        def test_permissions(project: str, permissions: list[str]) -> dict:
            """Live: check which of the given perms the caller (ADC) holds on the project."""
            return _test_perms(project, permissions)

        @server.tool()
        def get_iam_policy(project: str) -> dict:
            """Live: fetch the project's current IAM policy."""
            return _get_pol(project)

    return server


def main() -> None:
    server = build_server()
    transport = os.environ.get("IAM_LEGEND_TRANSPORT", "stdio")
    if transport == "http":
        server.run(transport="streamable-http")
    else:
        server.run(transport="stdio")


if __name__ == "__main__":
    main()
