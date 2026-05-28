from unittest.mock import patch

from iam_legend.reviewer.format import format_review
from iam_legend.types import (
    AccessRequestDraft, FullReport, LiveState, RoleRecommendation,
    DetectedGCPResource,
)


def _sample_report(missing: list[str]) -> FullReport:
    return FullReport(
        resources=[
            DetectedGCPResource(
                kind="google_storage_bucket", name="data", operation="create",
                file="main.tf", line=12, source="terraform_hcl",
            )
        ],
        required_permissions=["storage.buckets.create"],
        required_apis=[],
        by_file={"main.tf": ["storage.buckets.create"]},
        live_state=LiveState(granted=[], missing=missing),
        recommendation=RoleRecommendation(
            roles=["roles/storage.admin"], reasoning="x", alternatives=[],
        ),
        grant_commands=["gcloud projects add-iam-policy-binding ..."],
        access_request=AccessRequestDraft(subject="x", body="y"),
        warnings=[],
    )


def test_format_with_no_gaps_approves():
    report = _sample_report(missing=[])
    with patch("iam_legend.reviewer.format._call_gemini", side_effect=RuntimeError("offline")):
        result = format_review(report, deployer="deployer@p.iam.gserviceaccount.com")
    assert result.event == "APPROVE"
    assert "approved" in result.body.lower() or "✅" in result.body


def test_format_with_gaps_requests_changes():
    report = _sample_report(missing=["storage.buckets.create"])
    with patch("iam_legend.reviewer.format._call_gemini", side_effect=RuntimeError("offline")):
        result = format_review(report, deployer="deployer@p.iam.gserviceaccount.com")
    assert result.event == "REQUEST_CHANGES"
    assert "storage.buckets.create" in result.body
    assert any("storage.buckets.create" in c.body for c in result.comments)


def test_inline_comments_anchor_to_files_and_lines():
    report = _sample_report(missing=["storage.buckets.create"])
    with patch("iam_legend.reviewer.format._call_gemini", side_effect=RuntimeError("offline")):
        result = format_review(report, deployer="x")
    assert any(c.file == "main.tf" and c.line == 12 for c in result.comments)
