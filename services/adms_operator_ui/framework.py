"""Operator UI framework foundation for WP-013-02 (OA-062).

A deliberately small server-side component framework: components render
deterministic, escaped HTML strings; pages compose components inside a
shared application shell with navigation, routing metadata, and theme
tokens. No JavaScript framework, no client state, no mutation — the
presentation layer is read-only by construction.
"""

from __future__ import annotations

import html
from dataclasses import dataclass, field


def escape(value: object) -> str:
    """All dynamic values pass through here before entering markup."""
    return html.escape(str(value), quote=True)


class Component:
    """Base building block: render() returns an HTML fragment."""

    def render(self) -> str:  # pragma: no cover - abstract by convention
        raise NotImplementedError


@dataclass(frozen=True)
class NavigationItem:
    item_id: str
    label: str
    path: str


@dataclass(frozen=True)
class Navigation:
    items: tuple[NavigationItem, ...]

    def render(self, active_item_id: str) -> str:
        links = []
        for item in self.items:
            active = ' class="active" aria-current="page"' if item.item_id == active_item_id else ""
            links.append(f'<li><a href="{escape(item.path)}"{active}>{escape(item.label)}</a></li>')
        return '<nav aria-label="Workspaces"><ul>' + "".join(links) + "</ul></nav>"


@dataclass(frozen=True)
class Theme:
    """Named design tokens rendered as CSS custom properties."""

    name: str
    tokens: tuple[tuple[str, str], ...]

    def render(self) -> str:
        declarations = "".join(f"--{escape(key)}:{escape(value)};" for key, value in self.tokens)
        return f"<style>:root[data-theme={escape(self.name)}]{{{declarations}}}</style>"


DEFAULT_THEME = Theme(
    name="operations-light",
    tokens=(
        ("color-background", "#f6f8f7"),
        ("color-surface", "#ffffff"),
        ("color-text", "#1c2321"),
        ("color-accent", "#0f6f5c"),
        ("color-attention", "#a03518"),
        ("font-body", "system-ui, sans-serif"),
    ),
)


@dataclass(frozen=True)
class Route:
    """Routing metadata binding a navigation item to a page renderer name."""

    item_id: str
    path: str
    title: str


class Router:
    """Deterministic route registry for the operator application."""

    def __init__(self) -> None:
        self._routes: dict[str, Route] = {}

    def register(self, route: Route) -> None:
        if route.path in self._routes:
            raise ValueError(f"route already registered: {route.path}")
        self._routes[route.path] = route

    def resolve(self, path: str) -> Route:
        route = self._routes.get(path)
        if route is None:
            raise KeyError(f"unknown route: {path}")
        return route

    @property
    def routes(self) -> tuple[Route, ...]:
        return tuple(self._routes[path] for path in sorted(self._routes))


@dataclass(frozen=True)
class Page:
    """A rendered workspace page inside the application shell."""

    title: str
    active_item_id: str
    body: str


@dataclass(frozen=True)
class AppShell:
    """Layout framework: header with identity, navigation, themed body."""

    application_name: str
    navigation: Navigation
    theme: Theme = field(default=DEFAULT_THEME)

    def render(self, page: Page, *, operator_name: str) -> str:
        return (
            "<!-- rendered by the RE-OS operator experience shell -->\n"
            f'<div data-theme="{escape(self.theme.name)}" class="app-shell">'
            f"{self.theme.render()}"
            "<header>"
            f"<h1>{escape(self.application_name)}</h1>"
            f'<p class="operator-identity">Signed in as {escape(operator_name)} '
            "(read-only)</p>"
            "</header>"
            f"{self.navigation.render(page.active_item_id)}"
            f"<main><h2>{escape(page.title)}</h2>{page.body}</main>"
            "<footer>Situational awareness only — this console cannot operate "
            "the network.</footer>"
            "</div>"
        )
