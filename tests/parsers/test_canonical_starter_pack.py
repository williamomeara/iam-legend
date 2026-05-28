"""Regression test: the agent-starter-pack canonical resource set parses with
ZERO catalog gaps.

This is the locked-in form of the validation against all 7 official Google
ADK starter templates (adk, agentic_rag, adk_live, adk_a2a, adk_go, adk_java,
adk_ts). The fixture at fixtures/terraform/agent_starter_pack_canonical.tf
collects the union of resource kinds seen across all of them. If iam-legend's
catalog ever drops one of these kinds, this test fails.
"""
from __future__ import annotations

from pathlib import Path

from iam_legend.catalog.loader import load_catalog
from iam_legend.catalog.resolver import resolve
from iam_legend.parsers.terraform_hcl import TerraformHCLParser

FIXTURE = (
    Path(__file__).parent.parent
    / "fixtures"
    / "terraform"
    / "agent_starter_pack_canonical.tf"
)


def test_canonical_starter_pack_zero_catalog_gaps():
    parser = TerraformHCLParser()
    resources = parser.parse_file(str(FIXTURE))
    assert resources, "parser produced no resources from the canonical fixture"

    catalog = load_catalog()
    rr = resolve(resources, catalog)
    unknown_warnings = [w for w in rr.warnings if "unknown resource kind" in w]
    assert unknown_warnings == [], (
        "agent-starter-pack canonical fixture surfaced catalog gaps:\n  "
        + "\n  ".join(unknown_warnings)
    )


def test_canonical_starter_pack_covers_known_wedge_kinds():
    """Sanity: the wedge kinds (Vertex Agent Engine, WIF, service accounts,
    discovery engine) are in the fixture so this test surfaces gaps if their
    catalog entries get removed."""
    parser = TerraformHCLParser()
    resources = parser.parse_file(str(FIXTURE))
    kinds = {r.kind for r in resources}
    assert "google_vertex_ai_reasoning_engine" in kinds
    assert "google_iam_workload_identity_pool" in kinds
    assert "google_iam_workload_identity_pool_provider" in kinds
    assert "google_service_account" in kinds
    assert "google_service_account_iam_member" in kinds
    assert "google_discovery_engine_search_engine" in kinds
    assert "google_discovery_engine_data_store" in kinds
    assert "google_bigquery_connection" in kinds
    assert "google_logging_project_bucket_config" in kinds
    assert "google_logging_linked_dataset" in kinds
