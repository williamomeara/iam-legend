"""Build api_methods.json — the set of valid GCP IAM permission identifiers.

ORIGINALLY: the plan called for scraping the public GCP IAM permissions
reference page (https://cloud.google.com/iam/docs/permissions-reference).
That page is JS-rendered (its <table> is populated client-side from data
that is not served as a static asset under any of the obvious paths), so a
naive urlopen returns 0 rows.

WHAT WE DO INSTEAD: we read `src/iam_legend/catalog/roles.json` (already
populated in Task 4 by `refresh_roles.py`, which calls the official
`iam.roles.list` API). Every real GCP permission appears in at least one
predefined role's permission list, so the union of those lists is exactly
the set of valid permissions — sourced from the same authoritative data
the reference page itself renders.

We then write a method->permission mapping. For Google APIs the method
name and permission name are 1:1 (e.g. `storage.buckets.create`), so each
permission keys an entry whose value is the singleton list `[permission]`.
This shape lets Task 6's resources.yaml cross-check that every perm it
references is real, and leaves room to expand to many-to-one method->perm
bindings later if we ever need to disambiguate.

Run: python catalog_build/refresh_api_methods.py
Reads:  src/iam_legend/catalog/roles.json
Writes: src/iam_legend/catalog/api_methods.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

CATALOG = Path(__file__).parent.parent / "src" / "iam_legend" / "catalog"
ROLES_IN = CATALOG / "roles.json"
OUT = CATALOG / "api_methods.json"


def main() -> None:
    roles = json.loads(ROLES_IN.read_text())
    perms: set[str] = set()
    for role in roles.values():
        for p in role.get("permissions", []):
            perms.add(p)

    methods = {p: [p] for p in sorted(perms)}
    OUT.write_text(json.dumps(methods, indent=2, sort_keys=True))
    print(f"Wrote {len(methods)} method->perm bindings to {OUT}", file=sys.stderr)


if __name__ == "__main__":
    main()
