"""Small SQLite persistence layer for per-device watchlists."""

import sqlite3
from pathlib import Path


def _connect(database_path: Path) -> sqlite3.Connection:
    """Create a connection with dictionary-like rows."""
    connection = sqlite3.connect(database_path, timeout=10)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database(database_path: Path) -> None:
    """Create the watchlist table and its uniqueness constraint."""
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with _connect(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS watchlist (
                device_id TEXT NOT NULL,
                coin_id TEXT NOT NULL,
                added_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (device_id, coin_id)
            )
            """
        )


def list_watchlist(database_path: Path, device_id: str) -> list[str]:
    """Return a device's coin IDs in the order they were added."""
    with _connect(database_path) as connection:
        rows = connection.execute(
            "SELECT coin_id FROM watchlist WHERE device_id = ? ORDER BY added_at, coin_id",
            (device_id,),
        ).fetchall()
    return [str(row["coin_id"]) for row in rows]


def add_to_watchlist(database_path: Path, device_id: str, coin_id: str) -> None:
    """Add a coin to a device's watchlist without creating duplicates."""
    with _connect(database_path) as connection:
        connection.execute(
            "INSERT OR IGNORE INTO watchlist (device_id, coin_id) VALUES (?, ?)",
            (device_id, coin_id),
        )


def remove_from_watchlist(database_path: Path, device_id: str, coin_id: str) -> None:
    """Remove a coin from a device's watchlist if it exists."""
    with _connect(database_path) as connection:
        connection.execute(
            "DELETE FROM watchlist WHERE device_id = ? AND coin_id = ?",
            (device_id, coin_id),
        )
