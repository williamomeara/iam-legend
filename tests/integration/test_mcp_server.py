import os
from pathlib import Path
from unittest.mock import patch

from iam_legend.mcp_server import build_server


FIXTURE = Path(__file__).parent.parent / "fixtures" / "plan_json" / "simple.json"


def _list_tool_names(srv):
    """FastMCP's tool-listing API has shifted across versions; accommodate both."""
    if hasattr(srv, "_tool_manager"):
        return {t.name for t in srv._tool_manager.list_tools()}
    if hasattr(srv, "tools") and callable(getattr(srv, "tools", None)):
        return {t.name for t in srv.tools()}
    if hasattr(srv, "list_tools"):
        # may be sync or async — try sync first
        try:
            return {t.name for t in srv.list_tools()}
        except TypeError:
            import asyncio
            return {t.name for t in asyncio.run(srv.list_tools())}
    raise RuntimeError("can't find FastMCP tool list API on this version")


def test_stdio_server_registers_all_tools(monkeypatch):
    monkeypatch.setenv("IAM_LEGEND_TRANSPORT", "stdio")
    srv = build_server()
    names = _list_tool_names(srv)
    assert "analyze" in names
    assert "lookup_permissions_for" in names
    assert "test_permissions" in names
    assert "get_iam_policy" in names


def test_http_server_excludes_privileged_tools(monkeypatch):
    monkeypatch.setenv("IAM_LEGEND_TRANSPORT", "http")
    srv = build_server()
    names = _list_tool_names(srv)
    assert "analyze" in names
    assert "lookup_permissions_for" in names
    assert "test_permissions" not in names
    assert "get_iam_policy" not in names
