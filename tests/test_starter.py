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


def test_visitor_can_open_space_directory_and_read_seed_data(starter):
    client, _ = starter
    assert client.get("/").status_code == 200
    assert "空間查詢" in client.get("/spaces").text
    rooms = client.get("/api/rooms").json()
    assert sorted(room["code"] for room in rooms) == ["DEMO-301", "DEMO-402"]
    assert client.get(f"/spaces/{rooms[0]['id']}").status_code == 200


def test_borrower_can_log_in_and_logout_but_cannot_access_teacher_api(starter):
    client, _ = starter
    assert client.get("/api/bookings").status_code == 401
    assert client.get("/bookings", follow_redirects=False).headers["location"] == "/login"
    response = client.post(
        "/login", data={"email": "member@example.test", "password": "local-demo-password"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "HttpOnly" in response.headers["set-cookie"]
    assert client.get("/bookings").status_code == 200
    assert len(client.get("/api/bookings").json()) == 1
    assert client.get("/api/courses").status_code == 403
    assert client.post("/logout").status_code == 403
    csrf = client.get("/api/accounts/me").json()["csrf_token"]
    assert client.post("/logout", data={"csrf_token": csrf}, follow_redirects=False).status_code == 303
    assert client.get("/api/bookings").status_code == 401


def test_teacher_can_read_their_own_seed_courses(starter):
    client, _ = starter
    client.post("/login", data={"email": "teacher@example.test", "password": "local-demo-password"})
    assert client.get("/scheduling").status_code == 200
    courses = client.get("/api/courses").json()
    assert [course["title"] for course in courses] == ["軟體工程"]


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
