"""SQLite engine construction and per-connection pragma configuration.

The API and worker share one database through this module. Every connection is
configured identically so serialization guarantees do not depend on which
process opened it.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Final

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

BUSY_TIMEOUT_MS: Final = 5000

_PRAGMAS: Final = (
    ("foreign_keys", "ON"),
    ("journal_mode", "WAL"),
    ("synchronous", "FULL"),
    ("busy_timeout", str(BUSY_TIMEOUT_MS)),
)


def database_url(database_path: Path) -> str:
    return f"sqlite+pysqlite:///{database_path}"


def create_database_engine(database_path: Path, *, echo: bool = False) -> Engine:
    """Build an engine whose every connection carries the documented pragmas.

    The parent directory is created because the data root is a mounted empty
    volume on first boot; the database file itself is created by the migration.
    """
    database_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        database_url(database_path),
        echo=echo,
        future=True,
        connect_args={"timeout": BUSY_TIMEOUT_MS / 1000},
    )
    register_pragmas(engine)
    return engine


def register_pragmas(engine: Engine) -> None:
    @event.listens_for(engine, "connect")
    def _apply_pragmas(dbapi_connection: Any, _record: Any) -> None:
        cursor = dbapi_connection.cursor()
        try:
            for name, value in _PRAGMAS:
                cursor.execute(f"PRAGMA {name}={value}")
        finally:
            cursor.close()


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


@contextmanager
def connection_pragmas(connection: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Apply the pragmas to a raw DBAPI connection, used by migrations."""
    for name, value in _PRAGMAS:
        connection.execute(f"PRAGMA {name}={value}")
    yield connection


def read_pragma(engine: Engine, name: str) -> str:
    with engine.connect() as connection:
        return str(connection.execute(text(f"PRAGMA {name}")).scalar_one())
