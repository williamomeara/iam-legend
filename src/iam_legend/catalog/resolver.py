"""Single resolver: list[DetectedGCPResource] -> ResolvedRequirements.

The resolver does not care which parser produced the resource. Catalog gaps
surface as warnings; we never silently drop a detected resource.
"""
from __future__ import annotations

from collections import defaultdict

from iam_legend.catalog.loader import Catalog, load_catalog
from iam_legend.types import DetectedGCPResource, ResolvedRequirements


def resolve(
    resources: list[DetectedGCPResource],
    catalog: Catalog | None = None,
) -> ResolvedRequirements:
    c = catalog or load_catalog()
    perms: set[str] = set()
    apis: set[str] = set()
    by_file: dict[str, list[str]] = defaultdict(list)
    warnings: list[str] = []

    for r in resources:
        entry_perms = c.lookup_resource(r.kind, r.operation)
        if entry_perms is None:
            warnings.append(
                f"unknown resource kind '{r.kind}' at {r.file}:{r.line} "
                f"(source: {r.source}); not analysed"
            )
            continue
        perms.update(entry_perms)
        by_file[r.file].extend(entry_perms)
        apis.update(c.required_apis_for(r.kind))

    return ResolvedRequirements(
        permissions=perms,
        apis=apis,
        by_file=dict(by_file),
        warnings=warnings,
    )
