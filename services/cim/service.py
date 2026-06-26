#!/usr/bin/env python3
"""DIEP CIM service entrypoint -- runs the FastAPI app from api.py via
uvicorn. Logging configured at module level (same convention as every
other service this branch); graceful shutdown is uvicorn's own SIGTERM/
SIGINT handling, no extra wiring needed here.
"""
from __future__ import annotations

import logging

from .api import app  # noqa: F401 -- imported for uvicorn's "module:attr" target
from .config import Settings

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("diep-cim")


def main() -> None:
    import uvicorn

    logger.info("CIM service starting on :%d", Settings.HEALTH_PORT)
    uvicorn.run(app, host="0.0.0.0", port=Settings.HEALTH_PORT, log_level="info")


if __name__ == "__main__":
    main()
