"""WP-013-02 OA-061 — operator authentication integration tests."""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from _adms_operator_fixtures import (  # noqa: E402
    NO_ROLE,
    NO_ROLE_TOKEN,
    OPERATOR,
    OPERATOR_TOKEN,
    VIEWER,
    VIEWER_TOKEN,
    authenticator,
)

from services.adms_operator_api import (  # noqa: E402
    AuthenticationError,
    AuthorizationError,
    require_read_access,
)


def test_token_resolves_to_principal():
    principal = authenticator().authenticate(OPERATOR_TOKEN)
    assert principal == OPERATOR
    assert principal.display_name == "Jane Operator"


def test_unknown_token_rejected():
    with pytest.raises(AuthenticationError):
        authenticator().authenticate("not-a-real-token")


def test_missing_token_rejected():
    with pytest.raises(AuthenticationError):
        authenticator().authenticate(None)
    with pytest.raises(AuthenticationError):
        authenticator().authenticate("")


def test_operator_and_viewer_roles_grant_read_access():
    assert require_read_access(OPERATOR) is OPERATOR
    assert require_read_access(authenticator().authenticate(VIEWER_TOKEN)) == VIEWER


def test_principal_without_read_role_rejected():
    principal = authenticator().authenticate(NO_ROLE_TOKEN)
    assert principal == NO_ROLE
    with pytest.raises(AuthorizationError):
        require_read_access(principal)


def test_principals_are_immutable():
    with pytest.raises(AttributeError):
        OPERATOR.roles = ("admin",)  # type: ignore[misc]


def test_authentication_is_deterministic():
    first = authenticator().authenticate(OPERATOR_TOKEN)
    second = authenticator().authenticate(OPERATOR_TOKEN)
    assert first == second
