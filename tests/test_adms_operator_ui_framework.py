"""WP-013-02 OA-062 — UI framework foundation tests."""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.adms_operator_ui import (  # noqa: E402
    DEFAULT_THEME,
    NAVIGATION,
    AppShell,
    Page,
    Route,
    Router,
    StatusPill,
    Table,
    build_router,
    escape,
)


def test_dynamic_values_are_escaped():
    assert escape('<script>alert("x")</script>') == (
        "&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;"
    )
    pill = StatusPill(label="<b>bad</b>", tone="ok").render()
    assert "<b>" not in pill
    assert "&lt;b&gt;" in pill


def test_table_component_renders_headers_and_rows():
    html = Table(headers=("A", "B"), rows=(("1", "2"), ("3", "4"))).render()
    assert "<th>A</th>" in html and "<th>B</th>" in html
    assert "<td>1</td>" in html and "<td>4</td>" in html


def test_navigation_marks_active_item():
    html = NAVIGATION.render("network")
    assert 'href="/ui/network"' in html
    assert 'aria-current="page"' in html
    assert html.count('aria-current="page"') == 1


def test_router_registers_and_resolves_routes():
    router = build_router()
    route = router.resolve("/ui/dashboard")
    assert route.title == "Situational Awareness"
    assert [item.path for item in router.routes] == [
        "/ui/dashboard",
        "/ui/history",
        "/ui/network",
        "/ui/recommendations",
    ]
    with pytest.raises(KeyError):
        router.resolve("/ui/unknown")


def test_duplicate_route_registration_rejected():
    router = Router()
    router.register(Route("a", "/ui/a", "A"))
    with pytest.raises(ValueError):
        router.register(Route("a2", "/ui/a", "A2"))


def test_theme_tokens_rendered_in_shell():
    shell = AppShell(application_name="Test App", navigation=NAVIGATION)
    page = Page(title="T", active_item_id="dashboard", body="<p>x</p>")
    html = shell.render(page, operator_name="Jane Operator")
    assert "--color-accent:#0f6f5c;" in html
    assert f'data-theme="{DEFAULT_THEME.name}"' in html


def test_shell_renders_identity_and_read_only_notice():
    shell = AppShell(application_name="Test App", navigation=NAVIGATION)
    page = Page(title="T", active_item_id="dashboard", body="<p>x</p>")
    html = shell.render(page, operator_name="Jane <Operator>")
    assert "Signed in as Jane &lt;Operator&gt;" in html
    assert "read-only" in html
    assert "cannot operate" in html


def test_rendering_is_deterministic():
    shell = AppShell(application_name="Test App", navigation=NAVIGATION)
    page = Page(title="T", active_item_id="history", body="<p>x</p>")
    assert shell.render(page, operator_name="A") == shell.render(page, operator_name="A")
