"""AST-based parser for ADK / Vertex / Discovery Engine SDK calls.

Two-pass:
 1. Walk Import/ImportFrom nodes -> build alias table {local_name -> FQN_prefix}.
 2. Walk Call nodes -> resolve each call's chain through the alias table,
    match against the signature map.

Unrecognised but plausibly-relevant calls fall through silently; the resolver
will not see them, so the catalog will not complain. (Catalog warnings come
from kinds we DO detect but DON'T have entries for.)
"""
from __future__ import annotations

import ast
from importlib import resources as importlib_resources
from pathlib import Path

import yaml

from iam_legend.parsers.base import register
from iam_legend.types import DetectedGCPResource


def _load_signatures() -> dict[str, dict[str, str]]:
    text = importlib_resources.files("iam_legend.parsers").joinpath("adk_call_signatures.yaml").read_text()
    return yaml.safe_load(text)


_SIGS: dict[str, dict[str, str]] = _load_signatures()


class _AliasResolver(ast.NodeVisitor):
    """Builds a per-file alias table mapping local name -> fully-qualified prefix."""

    def __init__(self) -> None:
        self.aliases: dict[str, str] = {}

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            local = alias.asname or alias.name.split(".")[0]
            target = alias.name if alias.asname else alias.name.split(".")[0]
            self.aliases[local] = target
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        for alias in node.names:
            local = alias.asname or alias.name
            self.aliases[local] = f"{module}.{alias.name}" if module else alias.name
        self.generic_visit(node)


def _flatten_call_chain(call: ast.Call) -> list[str] | None:
    parts: list[str] = []
    node: ast.AST = call.func
    while True:
        if isinstance(node, ast.Attribute):
            parts.append(node.attr)
            node = node.value
        elif isinstance(node, ast.Name):
            parts.append(node.id)
            break
        else:
            return None
    parts.reverse()
    return parts


def _resolve_to_fqn(parts: list[str], aliases: dict[str, str]) -> str | None:
    if not parts:
        return None
    head, *rest = parts
    prefix = aliases.get(head)
    if prefix is None:
        return None
    return ".".join([prefix, *rest])


class ADKPythonParser:
    name = "adk_python"

    def matches(self, path: str) -> bool:
        return path.endswith(".py")

    def parse_file(self, path: str) -> list[DetectedGCPResource]:
        src = Path(path).read_text()
        try:
            tree = ast.parse(src, filename=path)
        except SyntaxError:
            return []

        resolver = _AliasResolver()
        resolver.visit(tree)

        out: list[DetectedGCPResource] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            parts = _flatten_call_chain(node)
            if parts is None:
                continue
            fqn = _resolve_to_fqn(parts, resolver.aliases)
            if fqn is None:
                continue
            sig = _SIGS.get(fqn)
            if sig is None:
                continue
            out.append(DetectedGCPResource(
                kind=sig["kind"],
                name=parts[-1],
                operation=sig.get("operation", "create"),
                file=path,
                line=node.lineno,
                source="adk_python",
            ))
        return out


register(ADKPythonParser())
