from iam_legend.gcp.auth import who_am_i, AuthError


def test_who_am_i_returns_string_or_raises(monkeypatch):
    """ADC may or may not be configured in the test env. Either is fine:
    if configured, we get a principal string; if not, we get a clean AuthError.
    """
    try:
        principal = who_am_i()
        assert isinstance(principal, str)
        assert "@" in principal or principal.endswith(".iam.gserviceaccount.com") or "/" in principal or principal == "unknown-principal"
    except AuthError as e:
        assert "ADC" in str(e) or "credentials" in str(e).lower()
