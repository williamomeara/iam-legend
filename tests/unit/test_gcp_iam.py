from iam_legend.gcp.iam import test_iam_permissions as _test_iam_permissions
from iam_legend.gcp.auth import AuthError


def test_test_iam_permissions_with_invalid_project_raises_or_returns_empty():
    """Smoke test: either auth fails cleanly (no ADC) or the call returns a
    well-formed result against a definitely-nonexistent project.
    """
    try:
        result = _test_iam_permissions(
            project="iam-legend-nonexistent-99999",
            permissions=["storage.buckets.create"],
        )
        assert isinstance(result, dict)
        assert "granted" in result
        assert "missing" in result
    except AuthError:
        pass
    except Exception as e:
        assert ("iam-legend-nonexistent" in str(e) or "403" in str(e) or "404" in str(e)
                or "permission" in str(e).lower() or "not found" in str(e).lower()
                or "denied" in str(e).lower())
