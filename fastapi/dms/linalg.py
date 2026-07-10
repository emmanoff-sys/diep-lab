# Compatibility shim — canonical code is services/adms_grid_analytics/linalg.py
from services.adms_grid_analytics.linalg import *  # noqa: F401, F403
from services.adms_grid_analytics.linalg import (  # noqa: F401
    identity,
    inverse,
    matmul,
    matvec,
    solve,
    transpose,
    zeros,
)
