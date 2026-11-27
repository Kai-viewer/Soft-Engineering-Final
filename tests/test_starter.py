import os
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import make_url
from sqlalchemy.schema import CreateSchema, DropSchema


@pytest.fixture
def starter(tmp_path, monkeypatch):
    from app.main import create_app
    from app.seed import seed

    test_url = os.getenv("TEST_DATABASE_URL")
    engine = None
    if test_url:
        url = make_url(test_url)
        if url.get_backend_name() != "postgresql":
            raise ValueError("TEST_DATABASE_URL must point to PostgreSQL.")
        engine = create_engine(url)
        schema = f"test_{uuid4().hex}"
        with engine.begin() as connection:
            connection.execute(CreateSchema(schema))
        url = url.update_query_dict({"options": f"-csearch_path={schema}"})
        url = url.render_as_string(hide_password=False)
    else:
        url = f"sqlite:///{tmp_path / 'starter.db'}"

    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("COOKIE_SECURE", "false")
    config = Config("alembic.ini")
    try:
        command.upgrade(config, "head")
        app = create_app()
        with TestClient(app) as client:
            seed(app.state.engine, "local-demo-password")
            seed(app.state.engine, "local-demo-password")
            yield client, url
        command.downgrade(config, "base")
    finally:
        if engine is not None:
            with engine.begin() as connection:
                connection.execute(DropSchema(schema, cascade=True))
            engine.dispose()


def test_initial_migration_has_shared_tables(starter):
    _, url = starter
    engine = create_engine(url)
    inspector = inspect(engine)
    assert {"users", "sessions", "rooms", "equipment", "bookings",
            "booking_items", "courses"} <= set(inspector.get_table_names())
    assert {key["referred_table"] for key in inspector.get_foreign_keys("bookings")} >= {
        "users", "rooms"
    }
    engine.dispose()


def test_visitor_can_open_homepage_and_login_form(starter):
    client, _ = starter
    assert client.get("/").status_code == 200
    assert client.get("/login").status_code == 200


@pytest.mark.parametrize("role", ["member", "teacher", "admin"])
@pytest.mark.parametrize("use_email", [True, False], ids=["email", "short-account"])
def test_shared_login_preserves_role_and_logout_requires_csrf(starter, role, use_email):
    client, _ = starter
    assert client.get("/api/accounts/me").status_code == 401
    account = f"{role}@example.test" if use_email else role
    response = client.post(
        "/login",
        data={"email": account, "password": "local-demo-password"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "HttpOnly" in response.headers["set-cookie"]
    profile = client.get("/api/accounts/me").json()
    assert profile["role"] == role
    assert client.post("/logout").status_code == 403
    response = client.post(
        "/logout", data={"csrf_token": profile["csrf_token"]}, follow_redirects=False,
    )
    assert response.status_code == 303
    assert client.get("/api/accounts/me").status_code == 401


def test_login_rejects_unknown_accounts(starter):
    client, _ = starter
    response = client.post(
        "/login", data={"email": "unknown@example.test", "password": "local-demo-password"},
        follow_redirects=False,
    )
    assert response.status_code == 401
    assert client.get("/api/accounts/me").status_code == 401


def test_login_rejects_a_cross_origin_form(starter):
    client, _ = starter
    response = client.post(
        "/login",
        headers={"Origin": "https://other.example.test"},
        data={"email": "member@example.test", "password": "local-demo-password"},
        follow_redirects=False,
    )
    assert response.status_code == 403
    assert client.get("/api/accounts/me").status_code == 401
