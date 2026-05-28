from iam_legend.catalog.loader import load_catalog
from iam_legend.catalog.resolver import resolve
from iam_legend.types import DetectedGCPResource


def _r(kind: str, op: str = "create", file: str = "x.tf", line: int = 1) -> DetectedGCPResource:
    return DetectedGCPResource(
        kind=kind, name="x", operation=op, file=file, line=line, source="terraform_hcl",
    )


def test_resolve_known_resource():
    rr = resolve([_r("google_storage_bucket")], load_catalog())
    assert "storage.buckets.create" in rr.permissions
    assert rr.warnings == []


def test_resolve_unknown_resource_emits_warning():
    rr = resolve([_r("google_nonexistent_xyz")], load_catalog())
    assert rr.warnings != []
    assert "google_nonexistent_xyz" in rr.warnings[0]


def test_resolve_aggregates_apis():
    rr = resolve([_r("vertex.agent_engine_create")], load_catalog())
    assert "aiplatform.googleapis.com" in rr.apis


def test_resolve_by_file_grouping():
    rs = [_r("google_storage_bucket", file="a.tf"), _r("google_pubsub_topic", file="b.tf")]
    rr = resolve(rs, load_catalog())
    assert set(rr.by_file["a.tf"]) == {"storage.buckets.create"}
    assert set(rr.by_file["b.tf"]) == {"pubsub.topics.create"}
