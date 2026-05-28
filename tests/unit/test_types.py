from iam_legend.types import DetectedGCPResource, Operation, ParserSource


def test_detected_resource_roundtrips_to_dict():
    r = DetectedGCPResource(
        kind="google_storage_bucket",
        name="my-bucket",
        operation="create",
        file="main.tf",
        line=12,
        source="terraform_hcl",
    )
    d = r.to_dict()
    assert d == {
        "kind": "google_storage_bucket",
        "name": "my-bucket",
        "operation": "create",
        "file": "main.tf",
        "line": 12,
        "source": "terraform_hcl",
    }


def test_operation_typing():
    valid: Operation = "create"
    assert valid == "create"


def test_parser_source_typing():
    valid: ParserSource = "terraform_plan"
    assert valid == "terraform_plan"
