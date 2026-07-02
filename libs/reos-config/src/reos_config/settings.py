"""Shared base settings for every DAEP / RE-OS Python service.

Authority: WP-002-01 | LLD v2.0 §2.1.2 (Pydantic Settings, all env-driven),
LLD v2.0 §2.1.1 (full typing mandate — every field explicitly typed).

Environment enum single source of truth
---------------------------------------
The ``Environment`` Literal values below are the platform-wide canonical set
(Roadmap v1.0 §11.2). They MUST stay synchronized with:

* ``libs/reos-config-ts/src/config.ts``  (TypeScript — WP-002-02)
* ``libs/reos_config/lib/reos_config.dart`` (Dart — WP-002-02)

Any change to this set requires updating all three files in one commit.
"""

from __future__ import annotations

from typing import Literal

from pydantic import PostgresDsn, RedisDsn
from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = ["Environment", "ReosBaseSettings"]

Environment = Literal["local", "shared_dev", "ci", "staging", "production"]

_MASK = "***"


def _mask_dsn(dsn: str) -> str:
    """Return ``dsn`` with the password component replaced by ``***``.

    Handles the ``scheme://user:password@host`` shape. A DSN without a
    password component is returned unchanged.
    """
    scheme_sep = dsn.find("://")
    at_pos = dsn.rfind("@")
    if scheme_sep == -1 or at_pos == -1 or at_pos < scheme_sep:
        return dsn
    userinfo = dsn[scheme_sep + 3 : at_pos]
    colon = userinfo.find(":")
    if colon == -1:
        return dsn
    masked_userinfo = f"{userinfo[:colon]}:{_MASK}"
    return f"{dsn[: scheme_sep + 3]}{masked_userinfo}{dsn[at_pos:]}"


class ReosBaseSettings(BaseSettings):
    """Base settings class shared by every DAEP / RE-OS Python service.

    Subclass this in each service's ``config.py`` and add service-specific
    fields. Required fields (no default) fail fast at instantiation — a
    misconfigured service refuses to start rather than failing at first use.

    Reserved base field names (do NOT redefine in subclasses):
    ``service_name``, ``environment``, ``log_level``, ``database_url``,
    ``redis_url``, ``kafka_bootstrap_servers``.
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    service_name: str
    environment: Environment
    log_level: str = "INFO"
    database_url: PostgresDsn
    redis_url: RedisDsn
    kafka_bootstrap_servers: str

    def __repr__(self) -> str:
        """Render settings with DSN passwords masked.

        Security requirement (WP-002-01 §25): ``database_url`` / ``redis_url``
        must never be logged in full — the password component is masked.
        """
        parts = []
        for field_name in type(self).model_fields:
            value = getattr(self, field_name)
            if field_name in ("database_url", "redis_url"):
                parts.append(f"{field_name}={_mask_dsn(str(value))!r}")
            else:
                parts.append(f"{field_name}={value!r}")
        return f"{type(self).__name__}({', '.join(parts)})"

    def __str__(self) -> str:
        return self.__repr__()
