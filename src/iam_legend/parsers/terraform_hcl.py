"""Static HCL parsing for *.tf files. Used when plan JSON isn't available.

Assumes 'create' for every detected resource (worst case for perms).
Recurses into local modules.
"""
from __future__ import annotations

from pathlib import Path

import hcl2

from iam_legend.parsers.base import register
from iam_legend.parsers.line_recovery import recover_lines
from iam_legend.types import DetectedGCPResource


class TerraformHCLParser:
    name = "terraform_hcl"

    def matches(self, path: str) -> bool:
        return path.endswith(".tf")

    def parse_file(self, path: str) -> list[DetectedGCPResource]:
        with open(path) as f:
            try:
                parsed = hcl2.load(f)
            except Exception:
                return []
        resources = parsed.get("resource", [])
        targets: list[tuple[str, str]] = []

        def _unquote(s: str) -> str:
            # python-hcl2 wraps string-key values in literal quotes
            if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
                return s[1:-1]
            return s

        for block in resources:
            for rtype_raw, by_name in block.items():
                rtype = _unquote(rtype_raw)
                if not rtype.startswith("google_"):
                    continue
                for rname_raw in by_name.keys():
                    targets.append((rtype, _unquote(rname_raw)))

        line_map = recover_lines(path, targets)
        return [
            DetectedGCPResource(
                kind=rtype,
                name=rname,
                operation="create",
                file=path,
                line=line_map.get((rtype, rname), 0),
                source="terraform_hcl",
            )
            for (rtype, rname) in targets
        ]

    def parse_dir(self, directory: str) -> list[DetectedGCPResource]:
        out: list[DetectedGCPResource] = []
        for tf in Path(directory).rglob("*.tf"):
            out.extend(self.parse_file(str(tf)))
        return out


register(TerraformHCLParser())
