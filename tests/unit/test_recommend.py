"""Tests for the hybrid recommender (set_cover proposes + Gemini picks)."""
from __future__ import annotations

import json
from unittest.mock import patch

from iam_legend.catalog.loader import load_catalog
from iam_legend.recommender.recommend import recommend
from iam_legend.recommender.set_cover import propose_candidates


# ─── propose_candidates ────────────────────────────────────────────────


def test_propose_candidates_returns_multiple_distinct_bundles():
    c = load_catalog()
    candidates = propose_candidates(
        {
            "storage.buckets.create",
            "pubsub.topics.create",
            "aiplatform.endpoints.create",
        },
        c,
    )
    assert len(candidates) >= 2
    # All candidates should be unique sets of roles
    role_tuples = {tuple(b.roles) for b in candidates}
    assert len(role_tuples) == len(candidates)


def test_propose_candidates_excludes_service_agent_roles():
    c = load_catalog()
    candidates = propose_candidates({"storage.buckets.create"}, c)
    for b in candidates:
        for role in b.roles:
            assert not role.endswith("ServiceAgent"), f"service-agent leaked: {role}"
            assert not role.endswith("serviceAgent"), f"service-agent leaked: {role}"


def test_propose_candidates_excludes_migration_roles():
    c = load_catalog()
    candidates = propose_candidates({"storage.objects.create"}, c)
    for b in candidates:
        for role in b.roles:
            assert "migration" not in role.lower(), f"migration role leaked: {role}"


def test_propose_candidates_empty_input():
    c = load_catalog()
    assert propose_candidates(set(), c) == []


def test_strict_per_service_strategy_prefers_service_prefix_match():
    """For storage perms, at least one candidate bundle should contain a roles/storage.* role."""
    c = load_catalog()
    candidates = propose_candidates(
        {"storage.buckets.create", "storage.objects.create"}, c
    )
    has_storage_role = any(
        any(r.startswith("roles/storage.") for r in b.roles) for b in candidates
    )
    assert has_storage_role, "no candidate bundle includes a roles/storage.* role"


# ─── recommend (Gemini integration with fallback) ──────────────────────


def test_recommend_with_gemini_offline_falls_back():
    """If Gemini is unreachable, fall back to set-cover top candidate deterministically."""
    c = load_catalog()
    with patch(
        "iam_legend.recommender.recommend._call_gemini",
        side_effect=RuntimeError("offline"),
    ):
        rec = recommend({"storage.buckets.create"}, c, project_id="x")
    assert rec.source == "fallback"
    assert len(rec.roles) >= 1
    # Reasoning should be deterministic templated prose
    assert "Recommended" in rec.reasoning


def test_recommend_with_invalid_gemini_response_falls_back():
    """If Gemini returns garbage, fall back."""
    c = load_catalog()
    with patch(
        "iam_legend.recommender.recommend._call_gemini",
        return_value="not valid JSON, just garbage",
    ):
        rec = recommend({"storage.buckets.create"}, c, project_id="x")
    assert rec.source == "fallback"


def test_recommend_with_out_of_range_gemini_index_falls_back():
    """If Gemini picks an index that doesn't exist, fall back."""
    c = load_catalog()
    with patch(
        "iam_legend.recommender.recommend._call_gemini",
        return_value=json.dumps({"bundle_index": 99, "reasoning": "I picked 99"}),
    ):
        rec = recommend({"storage.buckets.create"}, c, project_id="x")
    assert rec.source == "fallback"


def test_recommend_with_valid_gemini_pick_uses_it():
    c = load_catalog()
    with patch(
        "iam_legend.recommender.recommend._call_gemini",
        return_value=json.dumps(
            {
                "bundle_index": 0,
                "reasoning": "Per-service match — this is the most narrow option.",
                "warnings": ["Double-check actAs is needed."],
            }
        ),
    ):
        rec = recommend({"storage.buckets.create"}, c, project_id="x")
    assert rec.source == "gemini"
    assert "Per-service match" in rec.reasoning
    assert "actAs" in rec.reasoning  # warning got appended


def test_recommend_empty_input():
    c = load_catalog()
    rec = recommend(set(), c)
    assert rec.source == "no-candidates"
    assert rec.roles == []


def test_recommend_uncoverable_perms():
    """Perms with no role that contains them."""
    c = load_catalog()
    # Mix one real perm (covered by many roles) with one fake.
    rec = recommend(
        {"storage.buckets.create", "definitely.not.a.real.permission"}, c
    )
    assert "definitely.not.a.real.permission" in rec.uncovered


# ─── No-database-role-for-non-database-perms regression ───────────────


def test_recommend_no_databases_admin_for_non_database_perms():
    """The class of bug we set out to fix: roles/iam.databasesAdmin should
    not appear for perms that have nothing to do with Spanner/Datastore."""
    c = load_catalog()
    # These are exclusively NON-database perms.
    perms = {
        "pubsub.topics.create",
        "storage.buckets.create",
        "aiplatform.endpoints.create",
    }
    with patch(
        "iam_legend.recommender.recommend._call_gemini",
        side_effect=RuntimeError("force fallback"),
    ):
        rec = recommend(perms, c)
    # Deterministic fallback should pick the per-service-prefix strategy's
    # bundle, which doesn't include iam.databasesAdmin.
    assert "roles/iam.databasesAdmin" not in rec.roles, (
        f"databases admin leaked into non-database recommendation: {rec.roles}"
    )
