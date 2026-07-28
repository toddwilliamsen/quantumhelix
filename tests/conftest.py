"""Shared fixtures for API tests. Avoids the live event generator and uses an isolated DB."""
import os
import tempfile

import pytest

# Must be set before importing app.
os.environ.setdefault("FLASK_ENV", "development")
os.environ["SIM_LEADER"] = "0"
# Keep tests fast: don't fit the detector stack or run the generator.
os.environ["QUANTUM_SKIP_DETECTORS"] = "1"
os.environ["SECRET_KEY"] = "test-secret-key-not-for-production"
os.environ["ADMIN_PASSWORD"] = "test-admin-password-ok"

_db_fd, _db_path = tempfile.mkstemp(suffix=".db")
os.close(_db_fd)
os.environ["DATABASE_URL"] = f"sqlite:///{_db_path}"


@pytest.fixture(scope="session")
def app():
    from app import app as flask_app

    flask_app.config.update(TESTING=True)
    yield flask_app
    try:
        os.unlink(_db_path)
    except OSError:
        pass


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def admin_token(client):
    res = client.post("/api/login", json={
        "username": "admin",
        "password": os.environ["ADMIN_PASSWORD"],
    })
    assert res.status_code == 200, res.get_json()
    data = res.get_json()
    assert "token" in data
    return data["token"]


def auth_header(token):
    return {"Authorization": f"Bearer {token}"}
