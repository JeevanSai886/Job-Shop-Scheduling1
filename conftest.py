from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import app


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("JSSP_DB_PATH", str(tmp_path / "instances.sqlite3"))
    with TestClient(app) as test_client:
        yield test_client
