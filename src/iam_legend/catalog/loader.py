"""Catalog loading + lookup. Catalog snapshots ship in the package."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from importlib import resources
from typing import Any

import yaml


@dataclass(slots=True)
class Catalog:
    roles: dict[str, dict[str, Any]] = field(default_factory=dict)
    api_methods: dict[str, list[str]] = field(default_factory=dict)
    resources: dict[str, dict[str, Any]] = field(default_factory=dict)

    def lookup_resource(self, kind: str, operation: str) -> list[str] | None:
        entry = self.resources.get(kind)
        if entry is None:
            return None
        return entry.get(operation)

    def required_apis_for(self, kind: str) -> list[str]:
        entry = self.resources.get(kind, {})
        return entry.get("required_apis", [])

    def lookup_role(self, role: str) -> dict[str, Any] | None:
        return self.roles.get(role)

    def roles_with(self, permission: str) -> list[str]:
        return [name for name, data in self.roles.items() if permission in data.get("permissions", [])]


_CATALOG: Catalog | None = None


def load_catalog(reload: bool = False) -> Catalog:
    """Load the baked catalog snapshot. Cached after first call."""
    global _CATALOG
    if _CATALOG is not None and not reload:
        return _CATALOG

    pkg = resources.files("iam_legend.catalog")
    roles = json.loads((pkg / "roles.json").read_text())
    api_methods = json.loads((pkg / "api_methods.json").read_text())
    resources_yaml = yaml.safe_load((pkg / "resources.yaml").read_text())

    _CATALOG = Catalog(roles=roles, api_methods=api_methods, resources=resources_yaml or {})
    return _CATALOG
