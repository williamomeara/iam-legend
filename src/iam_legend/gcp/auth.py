"""ADC auth + identity introspection."""
from __future__ import annotations

import google.auth
from google.auth.exceptions import DefaultCredentialsError


class AuthError(RuntimeError):
    pass


def get_credentials():
    try:
        creds, _project = google.auth.default()
        return creds
    except DefaultCredentialsError as e:
        raise AuthError(f"No ADC credentials available: {e}") from e


def who_am_i() -> str:
    """Best-effort identity of the ADC principal.

    Order:
      - service_account_email attr (service-account creds, including impersonation)
      - user account attr
      - 'unknown-principal' fallback
    """
    creds = get_credentials()
    email = getattr(creds, "service_account_email", None)
    if email:
        return email
    user_account = getattr(creds, "account", None)
    if user_account:
        return user_account
    return "unknown-principal"
