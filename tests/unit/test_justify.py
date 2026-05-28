from unittest.mock import patch

from iam_legend.recommender.justify import justify_recommendation
from iam_legend.recommender.set_cover import RoleCandidates


def test_justify_with_gemini_unavailable_uses_template():
    rc = RoleCandidates(chosen=["roles/storage.admin"], uncovered=[])
    with patch("iam_legend.recommender.justify._call_gemini", side_effect=RuntimeError("vertex unavailable")):
        reasoning = justify_recommendation(rc, required_perms={"storage.buckets.create"})
    assert "roles/storage.admin" in reasoning


def test_justify_with_empty_recommendation():
    rc = RoleCandidates(chosen=[], uncovered=["something.unknown"])
    reasoning = justify_recommendation(rc, required_perms={"something.unknown"})
    assert "could not" in reasoning.lower() or "no predefined role" in reasoning.lower()
