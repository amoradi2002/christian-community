import sqlite3
from pathlib import Path
from bot.config.settings import CONFIG

_SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def get_connection():
    db_path = CONFIG["database"]["path"]
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    conn = get_connection()
    with open(_SCHEMA_PATH, "r") as f:
        conn.executescript(f.read())
    conn.close()
