from __future__ import annotations

import json
import sqlite3
import time
from typing import Any

DB_PATH = __import__("os").getenv("DB_PATH", "koya_ai_player.db")


def connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS agent_sessions (
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 0,
            mode TEXT NOT NULL DEFAULT 'advisory',
            state_json TEXT NOT NULL DEFAULT '{}',
            last_decision_json TEXT NOT NULL DEFAULT '{}',
            updated_at REAL NOT NULL DEFAULT 0,
            PRIMARY KEY (guild_id, user_id)
        );
        CREATE TABLE IF NOT EXISTS game_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            source TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_game_events_session
            ON game_events(guild_id, user_id, id DESC);
        """
    )
    con.commit()
    return con


def ensure_session(guild_id: int, user_id: int) -> None:
    con = connect()
    con.execute(
        "INSERT OR IGNORE INTO agent_sessions(guild_id,user_id,updated_at) VALUES(?,?,?)",
        (guild_id, user_id, time.time()),
    )
    con.commit(); con.close()


def get_session(guild_id: int, user_id: int) -> dict[str, Any]:
    ensure_session(guild_id, user_id)
    con = connect()
    row = con.execute(
        "SELECT * FROM agent_sessions WHERE guild_id=? AND user_id=?",
        (guild_id, user_id),
    ).fetchone()
    con.close()
    return dict(row)


def update_session(guild_id: int, user_id: int, **fields: Any) -> None:
    ensure_session(guild_id, user_id)
    if not fields:
        return
    fields["updated_at"] = time.time()
    cols = ", ".join(f"{key}=?" for key in fields)
    values = list(fields.values()) + [guild_id, user_id]
    con = connect()
    con.execute(f"UPDATE agent_sessions SET {cols} WHERE guild_id=? AND user_id=?", values)
    con.commit(); con.close()


def save_event(guild_id: int, user_id: int, source: str, content: str) -> None:
    con = connect()
    con.execute(
        "INSERT INTO game_events(guild_id,user_id,source,content,created_at) VALUES(?,?,?,?,?)",
        (guild_id, user_id, source, content[:12000], time.time()),
    )
    con.commit(); con.close()


def recent_events(guild_id: int, user_id: int, limit: int = 12) -> list[dict[str, Any]]:
    con = connect()
    rows = con.execute(
        "SELECT source,content,created_at FROM game_events WHERE guild_id=? AND user_id=? ORDER BY id DESC LIMIT ?",
        (guild_id, user_id, limit),
    ).fetchall()
    con.close()
    return [dict(r) for r in reversed(rows)]


def read_state(guild_id: int, user_id: int) -> dict[str, Any]:
    s = get_session(guild_id, user_id)
    return json.loads(s["state_json"] or "{}")


def write_state(guild_id: int, user_id: int, state: dict[str, Any]) -> None:
    update_session(guild_id, user_id, state_json=json.dumps(state, ensure_ascii=False))
