"""Parser protocol and dispatch.

Each concrete parser implements `Parser`. The dispatcher tries each parser
that `matches()` the given path and returns the union of detected resources.
"""
from __future__ import annotations

from pathlib import Path
from typing import Protocol

from iam_legend.types import DetectedGCPResource


class Parser(Protocol):
    name: str

    def matches(self, path: str) -> bool: ...
    def parse_file(self, path: str) -> list[DetectedGCPResource]: ...


_REGISTRY: list[Parser] = []


def register(parser: Parser) -> None:
    _REGISTRY.append(parser)


def all_parsers() -> list[Parser]:
    return list(_REGISTRY)


def walk_repo(root: str, *, follow_symlinks: bool = False) -> list[DetectedGCPResource]:
    """Walk a directory tree, dispatch each file to matching parsers, aggregate."""
    out: list[DetectedGCPResource] = []
    root_path = Path(root)
    if not root_path.exists():
        return out
    for path in root_path.rglob("*"):
        if path.is_dir():
            continue
        if any(seg.startswith(".") for seg in path.relative_to(root_path).parts):
            # skip hidden dirs/files
            continue
        s = str(path)
        for parser in _REGISTRY:
            if parser.matches(s):
                try:
                    out.extend(parser.parse_file(s))
                except Exception:
                    # Parser errors must not crash the walk; the resolver/reviewer
                    # will surface unknowns as warnings.
                    continue
    return out
