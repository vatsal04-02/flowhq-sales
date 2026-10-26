import uuid
from collections.abc import Iterator
from typing import TypeVar

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings

T = TypeVar("T")


class Base(DeclarativeBase):
    pass


_engine = None
_SessionLocal: sessionmaker[Session] | None = None


def get_engine():
    global _engine, _SessionLocal
    if _engine is None:
        _engine = create_engine(get_settings().database_url, pool_pre_ping=True)
        _SessionLocal = sessionmaker(_engine, expire_on_commit=False)
    return _engine


def session_factory() -> sessionmaker[Session]:
    get_engine()
    assert _SessionLocal is not None
    return _SessionLocal


def get_db() -> Iterator[Session]:
    with session_factory()() as session:
        yield session


def must_get(db: Session, model: type[T], pk: uuid.UUID) -> T:
    """db.get() for rows that must exist (FK targets): a clear error instead of an AttributeError on None later."""
    obj = db.get(model, pk)
    if obj is None:
        raise LookupError(f"{model.__name__} {pk} not found")
    return obj
