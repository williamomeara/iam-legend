import json
from pathlib import Path

from click.testing import CliRunner
from unittest.mock import patch

from iam_legend.cli import cli

FIXTURE = Path(__file__).parent.parent / "fixtures" / "plan_json" / "simple.json"


def test_cli_lookup():
    runner = CliRunner()
    result = runner.invoke(cli, ["lookup", "google_storage_bucket"])
    assert result.exit_code == 0
    assert "storage.buckets.create" in result.output


def test_cli_review_with_plan_outputs_json():
    runner = CliRunner()
    with patch("iam_legend.recommender.justify._call_gemini", side_effect=RuntimeError("offline")):
        result = runner.invoke(cli, [
            "review",
            "--plan", str(FIXTURE),
            "--format", "json",
        ])
    assert result.exit_code == 0
    report = json.loads(result.output)
    assert any(r["kind"] == "google_storage_bucket" for r in report["resources"])
