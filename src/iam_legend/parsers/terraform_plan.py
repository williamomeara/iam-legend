"""Parse `terraform show -json plan.tfplan` output.

The plan JSON is the authoritative input for the CI gate: Terraform fully
resolves every module to leaf resources and lists the actions to apply.
"""
from __future__ import annotations

import json
from pathlib import Path

from iam_legend.parsers.base import register
from iam_legend.types import DetectedGCPResource, Operation


_ACTION_MAP: dict[str, Operation] = {
    "create": "create",
    "update": "update",
    "delete": "delete",
}


class TerraformPlanParser:
    name = "terraform_plan"

    def matches(self, path: str) -> bool:
        return path.endswith(".json") and "plan" in Path(path).name.lower()

    def parse_file(self, path: str) -> list[DetectedGCPResource]:
        data = json.loads(Path(path).read_text())
        return self.parse_dict(data, source_file=path)

    def parse_dict(self, plan: dict, source_file: str = "plan.json") -> list[DetectedGCPResource]:
        out: list[DetectedGCPResource] = []
        for change in plan.get("resource_changes", []):
            kind = change.get("type", "")
            if not kind.startswith("google_"):
                continue
            actions = change.get("change", {}).get("actions", [])
            op = self._pick_operation(actions)
            if op is None:
                continue
            out.append(DetectedGCPResource(
                kind=kind,
                name=change.get("name", change.get("address", "")),
                operation=op,
                file=source_file,
                line=0,
                source="terraform_plan",
            ))
        return out

    @staticmethod
    def _pick_operation(actions: list[str]) -> Operation | None:
        if "create" in actions:
            return "create"
        if "update" in actions:
            return "update"
        if "delete" in actions:
            return "delete"
        return None


register(TerraformPlanParser())
