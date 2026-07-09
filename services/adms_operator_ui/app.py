"""Operator experience application for WP-013-02.

Wires the Operator API (JSON, /api/v1) and the workspace pages
(HTML, /ui) into one FastAPI application behind the same bearer-token
authentication shell. Every route is GET: the application structurally
cannot operate the network.
"""

from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from services.adms_operator_api.api import OperatorApi
from services.adms_operator_api.auth import StaticTokenAuthenticator
from services.adms_operator_api.http import (
    PrincipalDependency,
    bearer_principal_dependency,
    create_operator_api_app,
)
from services.adms_operator_api.models import OperatorPrincipal, UnknownAssetError
from services.adms_operator_api.service import OperatorViewService

from .framework import AppShell, Page
from .workspaces import (
    NAVIGATION,
    build_router,
    render_dashboard,
    render_history,
    render_network,
    render_recommendations,
    render_topology_explorer,
)

APPLICATION_NAME = "RE-OS Operator Situational Awareness"


def create_operator_experience_app(
    views: OperatorViewService,
    authenticator: StaticTokenAuthenticator,
) -> FastAPI:
    api = OperatorApi(views)
    app = create_operator_api_app(api, authenticator)
    shell = AppShell(application_name=APPLICATION_NAME, navigation=NAVIGATION)
    build_router()  # validates route registry consistency at startup
    principal = bearer_principal_dependency(authenticator)
    _register_ui_routes(app, views, shell, principal)
    return app


def _register_ui_routes(
    app: FastAPI,
    views: OperatorViewService,
    shell: AppShell,
    principal: PrincipalDependency,
) -> None:
    def page_response(page: Page, operator: OperatorPrincipal) -> HTMLResponse:
        return HTMLResponse(shell.render(page, operator_name=operator.display_name))

    @app.get("/ui/dashboard", response_class=HTMLResponse)
    def dashboard_page(operator: OperatorPrincipal = Depends(principal)) -> HTMLResponse:
        return page_response(render_dashboard(views.dashboard()), operator)

    @app.get("/ui/network", response_class=HTMLResponse)
    def network_page(q: str = "", operator: OperatorPrincipal = Depends(principal)) -> HTMLResponse:
        results = views.asset_search(q) if q else ()
        page = render_network(views.network_workspace(), search_query=q, search_results=results)
        return page_response(page, operator)

    @app.get("/ui/network/{node_id}", response_class=HTMLResponse)
    def topology_page(
        node_id: str, operator: OperatorPrincipal = Depends(principal)
    ) -> HTMLResponse:
        try:
            page = render_topology_explorer(
                views.topology_explorer(node_id), views.asset_state_panel(node_id)
            )
        except UnknownAssetError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        return page_response(page, operator)

    @app.get("/ui/recommendations", response_class=HTMLResponse)
    def recommendations_page(
        operator: OperatorPrincipal = Depends(principal),
    ) -> HTMLResponse:
        return page_response(render_recommendations(views.recommendations()), operator)

    @app.get("/ui/history", response_class=HTMLResponse)
    def history_page(
        text: str = "",
        kind: str | None = None,
        subject_id: str | None = None,
        actor: str | None = None,
        operator: OperatorPrincipal = Depends(principal),
    ) -> HTMLResponse:
        history = views.audit_history(
            kind=kind, subject_id=subject_id, actor=actor, text=text or None
        )
        page = render_history(history, views.timeline(), search_text=text)
        return page_response(page, operator)
