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
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(hpd_complaints)")}
    if "address_norm" not in cols:          # databases created in phase 0
        conn.execute("ALTER TABLE hpd_complaints ADD COLUMN address_norm TEXT")
    conn.execute("CREATE INDEX IF NOT EXISTS ix_hpd_addr_norm ON hpd_complaints(address_norm)")
    conn.commit()
