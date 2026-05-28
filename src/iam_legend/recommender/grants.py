"""Emit gcloud commands to grant the recommended roles."""
from __future__ import annotations


def _normalise_principal(principal: str) -> str:
    if ":" in principal:
        return principal
    if principal.endswith(".iam.gserviceaccount.com"):
        return f"serviceAccount:{principal}"
    return f"user:{principal}"


def generate_grant_commands(
    roles: list[str], project: str, principal: str,
) -> list[str]:
    p = _normalise_principal(principal)
    return [
        f"gcloud projects add-iam-policy-binding {project} \\\n"
        f"  --member={p} \\\n"
        f"  --role={role}"
        for role in roles
    ]
