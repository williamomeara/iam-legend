from pathlib import Path

from iam_legend.parsers.terraform_hcl import TerraformHCLParser

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "terraform"


def test_parses_basic_hcl():
    p = TerraformHCLParser()
    out = p.parse_file(str(FIXTURE_DIR / "main.tf"))
    kinds = {r.kind for r in out}
    assert "google_storage_bucket" in kinds
    assert "google_pubsub_topic" in kinds
    assert "null_resource" not in kinds


def test_line_numbers_populated():
    p = TerraformHCLParser()
    out = p.parse_file(str(FIXTURE_DIR / "main.tf"))
    by_kind = {r.kind: r for r in out}
    assert by_kind["google_storage_bucket"].line > 0
    assert by_kind["google_pubsub_topic"].line > by_kind["google_storage_bucket"].line


def test_recurses_local_modules():
    p = TerraformHCLParser()
    out = p.parse_dir(str(FIXTURE_DIR / "with_module"))
    kinds = {r.kind for r in out}
    assert "google_storage_bucket" in kinds
    assert "google_compute_network" in kinds


def test_assumes_create_operation():
    p = TerraformHCLParser()
    out = p.parse_file(str(FIXTURE_DIR / "main.tf"))
    assert all(r.operation == "create" for r in out)
