"""HTTP surface for the Operator API (OA-061).

Every route is GET — the application exposes no mutating method, which
is the structural guarantee that the operator experience is read-only.
Authentication is a bearer token resolved by the injected authenticator;
authorisation requires a read role.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, FastAPI, Header, HTTPException

from .api import OperatorApi
from .auth import StaticTokenAuthenticator, require_read_access
from .models import (
    AuthenticationError,
    AuthorizationError,
    OperatorApiError,
    OperatorPrincipal,
    UnknownAssetError,
)

API_PREFIX = "/api/v1"

PrincipalDependency = Callable[..., OperatorPrincipal]


def bearer_principal_dependency(
    authenticator: StaticTokenAuthenticator,
) -> PrincipalDependency:
    """FastAPI dependency resolving the bearer token to a read principal."""

    def principal(authorization: str | None = Header(default=None)) -> OperatorPrincipal:
        token = None
        if authorization and authorization.startswith("Bearer "):
            token = authorization.removeprefix("Bearer ").strip()
        try:
            return require_read_access(authenticator.authenticate(token))
        except AuthenticationError as error:
            raise HTTPException(status_code=401, detail=str(error)) from error
        except AuthorizationError as error:
            raise HTTPException(status_code=403, detail=str(error)) from error

    return principal


def create_operator_api_app(
    api: OperatorApi,
    authenticator: StaticTokenAuthenticator,
) -> FastAPI:
    app = FastAPI(
        title="RE-OS Operator API",
        version=api.api_version,
        description="Read-only operator situational awareness API (WP-013-02).",
    )
    principal = bearer_principal_dependency(authenticator)
    _register_overview_routes(app, api, principal)
    _register_history_routes(app, api, principal)
    return app


def _register_overview_routes(
    app: FastAPI, api: OperatorApi, principal: PrincipalDependency
) -> None:
    @app.get(f"{API_PREFIX}/dashboard")
    def dashboard(_: OperatorPrincipal = Depends(principal)) -> dict:
        return api.dashboard()

    @app.get(f"{API_PREFIX}/network")
    def network(_: OperatorPrincipal = Depends(principal)) -> dict:
        return api.network()

    @app.get(f"{API_PREFIX}/assets/search")
    def search(q: str = "", _: OperatorPrincipal = Depends(principal)) -> dict:
        return api.search_assets(q)

    @app.get(f"{API_PREFIX}/assets/{{asset_id}}")
    def asset(asset_id: str, _: OperatorPrincipal = Depends(principal)) -> dict:
        return _map_errors(lambda: api.asset(asset_id))

    @app.get(f"{API_PREFIX}/topology/{{node_id}}")
    def topology(node_id: str, _: OperatorPrincipal = Depends(principal)) -> dict:
        return _map_errors(lambda: api.topology(node_id))

    @app.get(f"{API_PREFIX}/recommendations")
    def recommendations(_: OperatorPrincipal = Depends(principal)) -> dict:
        return api.recommendations()


def _register_history_routes(
    app: FastAPI, api: OperatorApi, principal: PrincipalDependency
) -> None:
    @app.get(f"{API_PREFIX}/history")
    def history(
        kind: str | None = None,
        subject_id: str | None = None,
        actor: str | None = None,
        text: str | None = None,
        _: OperatorPrincipal = Depends(principal),
    ) -> dict:
        return api.history(kind=kind, subject_id=subject_id, actor=actor, text=text)

    @app.get(f"{API_PREFIX}/history/recommendations")
    def recommendation_history(_: OperatorPrincipal = Depends(principal)) -> dict:
        return api.recommendation_history()

    @app.get(f"{API_PREFIX}/history/{{record_id}}/trace")
    def record_trace(record_id: str, _: OperatorPrincipal = Depends(principal)) -> dict:
        return _map_errors(lambda: api.record_trace(record_id))

    @app.get(f"{API_PREFIX}/timeline")
    def timeline(asset_id: str | None = None, _: OperatorPrincipal = Depends(principal)) -> dict:
        return _map_errors(lambda: api.timeline(asset_id))


def _map_errors(operation):
    try:
        return operation()
    except UnknownAssetError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except OperatorApiError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
