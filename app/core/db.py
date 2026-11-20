import os
from collections.abc import Iterator
from typing import Annotated

from dotenv import load_dotenv
from fastapi import Depends, Request
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session


class Base(DeclarativeBase):
    pass


def database_url() -> str:
    load_dotenv()
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("Set DATABASE_URL in .env (see .env.example).")
    return url


def make_engine():
    engine = create_engine(database_url(), pool_pre_ping=True)
    if engine.dialect.name == "sqlite":
        @event.listens_for(engine, "connect")
        def enable_foreign_keys(connection, _record):
            connection.execute("PRAGMA foreign_keys=ON")
    return engine


def get_db(request: Request) -> Iterator[Session]:
    with Session(request.app.state.engine) as db:
        yield db


Db = Annotated[Session, Depends(get_db)]
