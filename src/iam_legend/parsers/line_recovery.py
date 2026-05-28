"""Recover (resource_type, resource_name) -> line numbers from a Terraform source file.

python-hcl2 doesn't preserve source positions, so we do a second pass over
the raw text. Cheap (one regex scan per file) and correct enough — Terraform
resource declarations are line-anchored by convention.
"""
from __future__ import annotations

import re
from pathlib import Path


_RESOURCE_RE = re.compile(
    r'^[ \t]*resource\s+"([a-z0-9_]+)"\s+"([A-Za-z0-9_\-]+)"',
    re.MULTILINE,
)


def recover_lines(
    file_path: str,
    targets: list[tuple[str, str]],
) -> dict[tuple[str, str], int]:
    """Return a dict mapping (type, name) -> 1-based line number.
    Targets not found map to 0.
    """
    text = Path(file_path).read_text()
    found: dict[tuple[str, str], int] = {}
    for m in _RESOURCE_RE.finditer(text):
        rtype, rname = m.group(1), m.group(2)
        line_no = text.count("\n", 0, m.start()) + 1
        found[(rtype, rname)] = line_no
    return {t: found.get(t, 0) for t in targets}
