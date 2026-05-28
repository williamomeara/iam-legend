"""IAM operations: testIamPermissions, getIamPolicy."""
from __future__ import annotations

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from iam_legend.gcp.auth import get_credentials


def test_iam_permissions(project: str, permissions: list[str]) -> dict:
    """Wrapper around projects.testIamPermissions.

    Returns: {"granted": [...], "missing": [...]} for the calling principal.
    The API answers for the CALLER — same SA the process is running as.
    """
    if not permissions:
        return {"granted": [], "missing": []}
    creds = get_credentials()
    crm = build("cloudresourcemanager", "v1", credentials=creds, cache_discovery=False)
    granted: set[str] = set()
    for i in range(0, len(permissions), 100):
        chunk = permissions[i:i + 100]
        try:
            resp = crm.projects().testIamPermissions(
                resource=project, body={"permissions": chunk},
            ).execute()
        except HttpError as e:
            raise RuntimeError(f"testIamPermissions failed for {project}: {e}") from e
        granted.update(resp.get("permissions", []))
    return {
        "granted": sorted(granted),
        "missing": sorted(set(permissions) - granted),
    }


def get_iam_policy(project: str) -> dict:
    """Wrapper around projects.getIamPolicy. Returns the policy dict."""
    creds = get_credentials()
    crm = build("cloudresourcemanager", "v1", credentials=creds, cache_discovery=False)
    try:
        return crm.projects().getIamPolicy(
            resource=project, body={"options": {"requestedPolicyVersion": 3}},
        ).execute()
    except HttpError as e:
        raise RuntimeError(f"getIamPolicy failed for {project}: {e}") from e
