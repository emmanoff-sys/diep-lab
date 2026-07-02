"""reos-config — DAEP / RE-OS shared configuration framework.

Authority: WP-002-01 | LLD v2.0 §2.1.2 (``config.py`` — Pydantic Settings, all env-driven).

Every DAEP / RE-OS Python service subclasses :class:`ReosBaseSettings` instead of
hand-rolling its own ``config.py``.
"""

from reos_config.settings import Environment, ReosBaseSettings

__all__ = ["Environment", "ReosBaseSettings"]
