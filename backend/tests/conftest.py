import os
import sys
import tempfile
from pathlib import Path

import pytest

_TMP = Path(tempfile.mkdtemp(prefix="fitai-test-"))
os.environ["FITAI_DATABASE_URL"] = f"sqlite:///{(_TMP / 'test.db').as_posix()}"
os.environ["FITAI_TRAINED_MODELS_DIR"] = str(_TMP / "no-models")
os.environ["FITAI_JWT_SECRET"] = "test-secret-with-enough-length-0123456789"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


_counter = {"n": 0}


@pytest.fixture
def auth_headers(client):
    _counter["n"] += 1
    r = client.post("/api/auth/register", json={"email": f"user{_counter['n']}@example.com", "password": "secret123"})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def profile_payload():
    return {
        "display_name": "Test",
        "age": 25,
        "sex": "unspecified",
        "height_cm": 175,
        "weight_kg": 70,
        "goal": "general_fitness",
        "experience": "beginner",
        "equipment": ["dumbbells"],
        "days_per_week": 3,
        "preferred_days": [],
        "session_minutes": 45,
        "exclusions": [],
        "dietary_preferences": [],
        "allergies": [],
        "health_flags": [],
    }
