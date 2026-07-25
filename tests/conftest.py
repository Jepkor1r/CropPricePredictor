from __future__ import annotations

import sqlite3

import pandas as pd
import pytest

from helpers import make_observation
from pricecast import db as DB
from pricecast import registry


@pytest.fixture(autouse=True)
def _clear_registry_cache():
    registry.reset_cache()
    yield
    registry.reset_cache()


@pytest.fixture
def conn(tmp_path) -> sqlite3.Connection:
    # shared across threads so the FastAPI TestClient can reuse this fixture
    connection = DB.connect(tmp_path / "test.db", check_same_thread=False)
    yield connection
    connection.close()


@pytest.fixture
def observations_df() -> pd.DataFrame:
    return pd.DataFrame([make_observation()])
