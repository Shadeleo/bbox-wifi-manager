"""Persistance SQLite pour l'historique des appareils."""

import os
import sqlite3
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "history.db")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS devices (
                mac        TEXT PRIMARY KEY,
                hostname   TEXT,
                ip         TEXT,
                first_seen TEXT NOT NULL,
                last_seen  TEXT NOT NULL,
                is_blocked INTEGER NOT NULL DEFAULT 0
            )
        """)


def upsert_device(
    mac: str,
    hostname: str,
    ip: str,
    first_seen: str | None = None,
    last_seen: str | None = None,
) -> None:
    now = datetime.now().isoformat(sep=" ", timespec="seconds")
    fs = first_seen or now
    ls = last_seen or now
    with _connect() as conn:
        exists = conn.execute(
            "SELECT first_seen FROM devices WHERE mac = ?", (mac,)
        ).fetchone()
        if exists:
            # Conserve la date de première connexion la plus ancienne
            stored_fs = exists["first_seen"]
            final_fs = stored_fs if stored_fs < fs else fs
            conn.execute(
                "UPDATE devices SET hostname = ?, ip = ?, first_seen = ?, last_seen = ? WHERE mac = ?",
                (hostname, ip, final_fs, ls, mac),
            )
        else:
            conn.execute(
                "INSERT INTO devices (mac, hostname, ip, first_seen, last_seen) VALUES (?,?,?,?,?)",
                (mac, hostname, ip, fs, ls),
            )


def set_blocked(mac: str, blocked: bool) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE devices SET is_blocked = ? WHERE mac = ?",
            (1 if blocked else 0, mac),
        )


def get_all_devices() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM devices ORDER BY last_seen DESC"
        ).fetchall()
    return [dict(r) for r in rows]
