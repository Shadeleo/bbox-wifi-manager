"""Persistance SQLite pour l'historique des appareils."""

import os
import sqlite3
from datetime import datetime, timedelta

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
        conn.execute("""
            CREATE TABLE IF NOT EXISTS network_stats (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                ts       TEXT NOT NULL,
                rx_bytes INTEGER NOT NULL,
                tx_bytes INTEGER NOT NULL,
                rx_kbps  INTEGER NOT NULL,
                tx_kbps  INTEGER NOT NULL
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
    with _connect() as conn:
        exists = conn.execute(
            "SELECT first_seen, last_seen FROM devices WHERE mac = ?", (mac,)
        ).fetchone()
        if exists:
            # Conserve la date de première connexion la plus ancienne
            stored_fs = exists["first_seen"]
            final_fs = stored_fs if stored_fs < fs else fs
            # last_seen inconnu (sentinelle '-1' de la box pour un hôte hors
            # ligne) : on garde la valeur en base plutôt que de dater à
            # l'instant un appareil parti depuis des mois.
            final_ls = last_seen if last_seen is not None else exists["last_seen"]
            conn.execute(
                "UPDATE devices SET hostname = ?, ip = ?, first_seen = ?, last_seen = ? WHERE mac = ?",
                (hostname, ip, final_fs, final_ls, mac),
            )
        else:
            # Rien en base : à défaut de dernière connexion connue, la
            # première connexion est le seul fait avéré.
            conn.execute(
                "INSERT INTO devices (mac, hostname, ip, first_seen, last_seen) VALUES (?,?,?,?,?)",
                (mac, hostname, ip, fs, last_seen or fs),
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


def insert_network_stat(ts: str, rx_bytes: int, tx_bytes: int, rx_kbps: int, tx_kbps: int) -> None:
    cutoff = (datetime.now() - timedelta(days=30)).isoformat(sep=" ", timespec="seconds")
    with _connect() as conn:
        conn.execute(
            "INSERT INTO network_stats (ts, rx_bytes, tx_bytes, rx_kbps, tx_kbps) VALUES (?,?,?,?,?)",
            (ts, rx_bytes, tx_bytes, rx_kbps, tx_kbps),
        )
        conn.execute("DELETE FROM network_stats WHERE ts < ?", (cutoff,))


def get_network_stats(hours: int = 24) -> list[dict]:
    cutoff = (datetime.now() - timedelta(hours=hours)).isoformat(sep=" ", timespec="seconds")
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM network_stats WHERE ts >= ? ORDER BY ts ASC", (cutoff,)
        ).fetchall()
    return [dict(r) for r in rows]
