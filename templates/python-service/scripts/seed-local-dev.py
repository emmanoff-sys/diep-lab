#!/usr/bin/env python3
"""Synthetic seed data loader — DAEP / RE-OS Local Dev (WP-003-02).

Populates non-PII, synthetic data on first boot, matching Roadmap v1.0
§11.2's Local Dev "Data Policy: synthetic/ephemeral" row. Idempotent —
``docker compose down -v && docker compose up`` always produces fresh,
predictable data (Reset Policy: "Automatic on docker compose down").

NOTE: this scaffold ships no real domain schema yet — ``ExampleModel`` is a
template artifact the README's "Instantiation Steps" §7 says to replace with
real Alembic-migrated entities. This script demonstrates the seeding
*pattern* (connect, verify, report) rather than fabricating INSERTs against
tables that don't exist on the scaffold itself. A real service extends
``SEED_RECORDS`` and the insert loop once it has real, migrated tables.
"""

from __future__ import annotations

import asyncio
import os
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

# Synthetic, non-PII placeholder records — the shape a real service's seed
# data would take once it has migrated domain tables to insert into.
SEED_RECORDS: list[dict[str, str]] = [
    {"name": "Synthetic Customer 1", "tenant_id": "00000000-0000-0000-0000-000000000001"},
    {"name": "Synthetic Customer 2", "tenant_id": "00000000-0000-0000-0000-000000000001"},
    {"name": "Synthetic Customer 3", "tenant_id": "00000000-0000-0000-0000-000000000002"},
]


async def seed() -> None:
    database_url = os.environ["DATABASE_URL"]
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as conn:
            result = await conn.execute(text("SELECT 1"))
            assert result.scalar() == 1
    finally:
        await engine.dispose()

    host = database_url.split("@")[-1]
    print(
        f"[seed-local-dev] connected to {host} — database reachable. "
        f"{len(SEED_RECORDS)} synthetic records staged; no domain schema "
        "exists on the scaffold yet (see README 'Instantiation Steps' §7). "
        "Extend this script's insert loop once your service has real, "
        "Alembic-migrated tables."
    )


if __name__ == "__main__":
    try:
        asyncio.run(seed())
    except Exception as exc:  # noqa: BLE001 — top-level script entrypoint reports and exits
        print(f"[seed-local-dev] FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
