"""Operator experience presentation layer for WP-013-02."""

from .app import APPLICATION_NAME, create_operator_experience_app
from .components import (
    BulletList,
    Card,
    KeyValueList,
    SearchForm,
    StatusPill,
    Table,
    Timeline,
    join,
)
from .framework import (
    DEFAULT_THEME,
    AppShell,
    Component,
    Navigation,
    NavigationItem,
    Page,
    Route,
    Router,
    Theme,
    escape,
)
from .workspaces import (
    NAVIGATION,
    build_router,
    render_dashboard,
    render_history,
    render_network,
    render_recommendations,
    render_topology_explorer,
)

__all__ = [
    "APPLICATION_NAME",
    "DEFAULT_THEME",
    "NAVIGATION",
    "AppShell",
    "BulletList",
    "Card",
    "Component",
    "KeyValueList",
    "Navigation",
    "NavigationItem",
    "Page",
    "Route",
    "Router",
    "SearchForm",
    "StatusPill",
    "Table",
    "Theme",
    "Timeline",
    "build_router",
    "create_operator_experience_app",
    "escape",
    "join",
    "render_dashboard",
    "render_history",
    "render_network",
    "render_recommendations",
    "render_topology_explorer",
]
