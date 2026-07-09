"""Shared UI component library for WP-013-02 (OA-062).

Every component renders escaped, deterministic HTML. Components carry
no state and issue no requests — they are pure functions of their
inputs, reusable by every current and future operator workspace.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .framework import Component, escape


@dataclass(frozen=True)
class StatusPill(Component):
    label: str
    tone: str  # "ok" | "attention"

    def render(self) -> str:
        return f'<span class="pill pill-{escape(self.tone)}">{escape(self.label)}</span>'


@dataclass(frozen=True)
class Card(Component):
    title: str
    body: str

    def render(self) -> str:
        return (
            f'<section class="card"><h3>{escape(self.title)}</h3>'
            f"<div>{self.body}</div></section>"
        )


@dataclass(frozen=True)
class KeyValueList(Component):
    pairs: tuple[tuple[str, str], ...]

    def render(self) -> str:
        items = "".join(
            f"<dt>{escape(key)}</dt><dd>{escape(value)}</dd>" for key, value in self.pairs
        )
        return f"<dl>{items}</dl>"


@dataclass(frozen=True)
class Table(Component):
    headers: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]

    def render(self) -> str:
        head = "".join(f"<th>{escape(header)}</th>" for header in self.headers)
        body = "".join(
            "<tr>" + "".join(f"<td>{escape(cell)}</td>" for cell in row) + "</tr>"
            for row in self.rows
        )
        return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


@dataclass(frozen=True)
class BulletList(Component):
    items: tuple[str, ...]

    def render(self) -> str:
        rendered = "".join(f"<li>{escape(item)}</li>" for item in self.items)
        return f"<ul>{rendered}</ul>"


@dataclass(frozen=True)
class Timeline(Component):
    entries: tuple[tuple[str, str], ...]  # (occurred_at, description)

    def render(self) -> str:
        rendered = "".join(
            f"<li><time>{escape(occurred_at)}</time> {escape(description)}</li>"
            for occurred_at, description in self.entries
        )
        return f'<ol class="timeline">{rendered}</ol>'


@dataclass(frozen=True)
class SearchForm(Component):
    """Read-only search: GET form only, by design."""

    action: str
    query_param: str
    placeholder: str
    value: str = ""

    def render(self) -> str:
        return (
            f'<form method="get" action="{escape(self.action)}">'
            f'<input type="search" name="{escape(self.query_param)}" '
            f'value="{escape(self.value)}" placeholder="{escape(self.placeholder)}"/>'
            '<button type="submit">Search</button></form>'
        )


def join(components: Sequence[Component | str]) -> str:
    return "".join(
        component if isinstance(component, str) else component.render() for component in components
    )
