"""Operator authentication integration for WP-013-02.

Deterministic token-to-principal resolution. Credentials are supplied
by the deploying environment at construction time — nothing is stored
in the repository, and no principal can hold a control capability: the
Operator API surface is read-only by construction.
"""

from __future__ import annotations

from collections.abc import Mapping

from .models import AuthenticationError, AuthorizationError, OperatorPrincipal

OPERATOR_ROLE = "operator"
VIEWER_ROLE = "viewer"
READ_ROLES = frozenset({OPERATOR_ROLE, VIEWER_ROLE})


class StaticTokenAuthenticator:
    """Maps caller-supplied bearer tokens to operator principals."""

    def __init__(self, principals_by_token: Mapping[str, OperatorPrincipal]) -> None:
        self._principals = dict(principals_by_token)

    def authenticate(self, token: str | None) -> OperatorPrincipal:
        if not token:
            raise AuthenticationError("missing bearer token")
        principal = self._principals.get(token)
        if principal is None:
            raise AuthenticationError("unknown bearer token")
        return principal


def require_read_access(principal: OperatorPrincipal) -> OperatorPrincipal:
    """Read access requires an operator or viewer role — nothing more is
    grantable through this layer; there are no control roles."""
    if not READ_ROLES & set(principal.roles):
        raise AuthorizationError(
            f"principal {principal.operator_id} lacks a read role "
            f"(requires one of: {', '.join(sorted(READ_ROLES))})"
        )
    return principal
