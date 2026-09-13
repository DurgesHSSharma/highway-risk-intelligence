"""SQLAlchemy engine/session setup for the Phase 6 SQLite data layer.

Database location is configurable via `Settings.database_path` (see
app/config.py) -- default `data/database/highway_risk.db`, resolved
relative to the repo root. The file is gitignored (matches the existing
`*.db` rule in the repo's .gitignore) because it is fully reproducible from
the committed CSV via `scripts/load_db.py`.
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


def make_engine(database_url: str | None = None) -> Engine:
    url = database_url or settings.database_url
    if url.startswith("sqlite"):
        db_path = url.replace("sqlite:///", "", 1)
        if db_path:
            from pathlib import Path

            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(url, connect_args={"check_same_thread": False})

    # SQLite disables foreign-key enforcement by default per connection;
    # the schema's UNIQUE(project_id, reporting_month) and the
    # project_snapshots -> projects FK (section 7/8 of the Phase 6 brief)
    # must actually be enforced, not just declared.
    @event.listens_for(engine, "connect")
    def _enable_sqlite_fk(dbapi_connection, connection_record) -> None:  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


engine: Engine = make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def create_all(bind: Engine | None = None) -> None:
    """Create tables if they don't exist yet. Never drops or alters existing
    data -- safe to call at API startup."""
    Base.metadata.create_all(bind=bind or engine)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
