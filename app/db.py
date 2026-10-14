"""SQLite connection and schema setup."""
import sqlite3
from pathlib import Path

from .config import get_settings

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    path = Path(path) if path else get_settings().db_path
    if str(path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_PATH.read_text())
    conn.commit()
