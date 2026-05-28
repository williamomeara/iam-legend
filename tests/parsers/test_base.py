from iam_legend.parsers.base import register, all_parsers, walk_repo
from iam_legend.types import DetectedGCPResource


class StubParser:
    name = "stub"

    def matches(self, path: str) -> bool:
        return path.endswith(".stub")

    def parse_file(self, path: str) -> list[DetectedGCPResource]:
        return [
            DetectedGCPResource(
                kind="google_storage_bucket", name="x", operation="create",
                file=path, line=1, source="terraform_hcl",
            )
        ]


def test_walk_invokes_matching_parser(tmp_path):
    register(StubParser())
    (tmp_path / "a.stub").write_text("hi")
    (tmp_path / "b.txt").write_text("nope")
    out = walk_repo(str(tmp_path))
    assert len(out) == 1
    assert out[0].file.endswith("a.stub")
