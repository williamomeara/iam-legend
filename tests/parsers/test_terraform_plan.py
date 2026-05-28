from pathlib import Path

from iam_legend.parsers.terraform_plan import TerraformPlanParser

FIXTURE = Path(__file__).parent.parent / "fixtures" / "plan_json" / "simple.json"


def test_matches_only_json():
    p = TerraformPlanParser()
    assert p.matches("plan.json") is True
    assert p.matches("main.tf") is False


def test_parses_real_plan_json():
    p = TerraformPlanParser()
    out = p.parse_file(str(FIXTURE))
    kinds_ops = {(r.kind, r.operation) for r in out}
    assert ("google_storage_bucket", "create") in kinds_ops
    assert ("google_pubsub_topic", "update") in kinds_ops
    assert ("google_iam_service_account", "delete") in kinds_ops
    assert ("google_compute_network", "create") not in kinds_ops
    assert ("google_compute_network", "update") not in kinds_ops


def test_module_path_preserved_in_file_field():
    p = TerraformPlanParser()
    out = p.parse_file(str(FIXTURE))
    addresses = {r.name for r in out}
    assert "data" in addresses
