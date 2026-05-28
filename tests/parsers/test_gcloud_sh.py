from pathlib import Path

from iam_legend.parsers.gcloud_sh import GcloudShellParser

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "gcloud_sh"


def test_matches_shell_and_makefile():
    p = GcloudShellParser()
    assert p.matches("deploy.sh") is True
    assert p.matches("Makefile") is True
    assert p.matches("makefile") is True
    assert p.matches("main.tf") is False


def test_parses_deploy_sh():
    p = GcloudShellParser()
    out = p.parse_file(str(FIXTURE_DIR / "deploy.sh"))
    kinds = {r.kind for r in out}
    assert "gcloud.storage.buckets.create" in kinds
    assert "gcloud.iam.service_accounts.create" in kinds
    assert "gcloud.projects.add_iam_policy_binding" in kinds
    assert "gcloud.run.deploy" in kinds
    assert "gcloud.services.enable" in kinds


def test_parses_makefile():
    p = GcloudShellParser()
    out = p.parse_file(str(FIXTURE_DIR / "Makefile"))
    kinds = {r.kind for r in out}
    assert "gcloud.ai.agents.deploy" in kinds


def test_line_numbers_populated():
    p = GcloudShellParser()
    out = p.parse_file(str(FIXTURE_DIR / "deploy.sh"))
    assert all(r.line > 0 for r in out)
