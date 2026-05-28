"""Pull the full predefined-role catalog from GCP's IAM Admin API.

Run: python catalog_build/refresh_roles.py
Auth: requires ADC with iam.roles.list permission (free, public catalog).
Writes: src/iam_legend/catalog/roles.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from googleapiclient.discovery import build

OUT = Path(__file__).parent.parent / "src" / "iam_legend" / "catalog" / "roles.json"


def main() -> None:
    iam = build("iam", "v1", cache_discovery=False)
    roles: dict[str, dict] = {}
    page_token: str | None = None
    while True:
        req = iam.roles().list(view="FULL", pageToken=page_token, pageSize=1000)
        resp = req.execute()
        for r in resp.get("roles", []):
            name = r["name"]
            roles[name] = {
                "title": r.get("title", ""),
                "stage": r.get("stage", ""),
                "description": r.get("description", ""),
                "permissions": r.get("includedPermissions", []),
            }
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    OUT.write_text(json.dumps(roles, indent=2, sort_keys=True))
    print(f"Wrote {len(roles)} roles to {OUT}", file=sys.stderr)


if __name__ == "__main__":
    main()
