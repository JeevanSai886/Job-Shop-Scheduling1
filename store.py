"""Small persistent store; each request uses its own SQLite connection."""

import hashlib
import os
import sqlite3
from pathlib import Path

from backend.models import JobShopInstance
from backend.parser import parse_jssp_instance

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"


def _connection() -> sqlite3.Connection:
    path = Path(os.environ.get("JSSP_DB_PATH", str(ROOT / ".local" / "instances.sqlite3")))
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=30)
    connection.execute("CREATE TABLE IF NOT EXISTS instances (id TEXT PRIMARY KEY, name TEXT, raw TEXT)")
    return connection


def save_instance(raw: str, name: str) -> tuple[str, JobShopInstance]:
    instance = parse_jssp_instance(raw, name)
    instance_id = hashlib.sha256((name + "\0" + raw).encode()).hexdigest()
    with _connection() as connection:
        connection.execute("INSERT OR IGNORE INTO instances VALUES (?, ?, ?)", (instance_id, name, raw))
    connection.close()
    return instance_id, instance


def get_instance(instance_id: str) -> JobShopInstance:
    with _connection() as connection:
        row = connection.execute("SELECT name, raw FROM instances WHERE id = ?", (instance_id,)).fetchone()
    connection.close()
    if row is None:
        raise KeyError(instance_id)
    return parse_jssp_instance(row[1], row[0])
