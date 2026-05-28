from pathlib import Path
from unittest.mock import patch

from iam_legend.analyze import analyze
from iam_legend.types import FullReport

FIXTURE = Path(__file__).parent.parent / "fixtures" / "plan_json" / "simple.json"


def test_analyze_plan_json_returns_full_report():
    with patch("iam_legend.recommender.justify._call_gemini", side_effect=RuntimeError("offline")), \
         patch("iam_legend.gcp.iam.test_iam_permissions", return_value={"granted": [], "missing": ["storage.buckets.create"]}):
        report = analyze(input=str(FIXTURE), kind="plan_json", project="some-proj")
    assert isinstance(report, FullReport)
    assert any(r.kind == "google_storage_bucket" for r in report.resources)
    assert "storage.buckets.create" in report.required_permissions
    assert report.live_state is not None
    assert "storage.buckets.create" in report.live_state.missing
    assert len(report.recommendation.roles) > 0
    assert len(report.grant_commands) > 0


def test_analyze_static_mode_no_project_means_no_live_diff():
    with patch("iam_legend.recommender.justify._call_gemini", side_effect=RuntimeError("offline")):
        report = analyze(input=str(FIXTURE), kind="plan_json", project=None)
    assert report.live_state is None


def test_analyze_repo_mode():
    fixture_dir = Path(__file__).parent.parent / "fixtures" / "terraform"
    with patch("iam_legend.recommender.justify._call_gemini", side_effect=RuntimeError("offline")):
        report = analyze(input=str(fixture_dir), kind="repo")
    kinds = {r.kind for r in report.resources}
    assert "google_storage_bucket" in kinds
