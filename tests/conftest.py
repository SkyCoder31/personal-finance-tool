"""Shared pytest fixtures.

We point DATABASE_URL at a per-test-run temp SQLite file *before* any
backend module is imported, then rebuild the schema between tests so
each test starts from an empty database.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

# IMPORTANT: set the env var before importing anything under backend.*
_TMP_DIR = Path(tempfile.mkdtemp(prefix="fenmo-tests-"))
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP_DIR.as_posix()}/test.db"
os.environ["DATA_DIR"] = _TMP_DIR.as_posix()

from fastapi.testclient import TestClient  # noqa: E402

from backend.database import Base, engine  # noqa: E402
from backend.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_schema():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)
