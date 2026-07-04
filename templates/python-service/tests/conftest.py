from __future__ import annotations

import pytest
from service_name.main import create_app

from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())
