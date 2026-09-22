"""SQLite connection (WAL, FTS5) and ordered schema migrations."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

MIN_SQLITE = (3, 35, 0)

MIGRATIONS: list[str] = [
    # 1: core tables
    """
    CREATE TABLE frames (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      captured_at REAL NOT NULL,
      until_at REAL NOT NULL,
      day TEXT NOT NULL,
      monitor INTEGER NOT NULL DEFAULT 1,
      app TEXT NOT NULL DEFAULT '',
      window_title TEXT NOT NULL DEFAULT '',
      image_path TEXT NOT NULL,
      thumb_path TEXT NOT NULL,
      width INTEGER NOT NULL,
      height INTEGER NOT NULL,
      phash TEXT NOT NULL,
      bytes INTEGER NOT NULL DEFAULT 0,
      ocr_status TEXT NOT NULL DEFAULT 'pending',
      ocr_ms INTEGER,
      ocr_backend TEXT
    );
    CREATE INDEX frames_captured ON frames(captured_at);
    CREATE INDEX frames_day ON frames(day);
    CREATE INDEX frames_app ON frames(app, captured_at);
    CREATE INDEX frames_ocr ON frames(ocr_status);
    CREATE TABLE blocks (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      frame_id INTEGER NOT NULL REFERENCES frames(id) ON DELETE CASCADE,
      text TEXT NOT NULL,
      x INTEGER NOT NULL, y INTEGER NOT NULL, w INTEGER NOT NULL, h INTEGER NOT NULL,
      conf REAL NOT NULL DEFAULT 0
    );
    CREATE INDEX blocks_frame ON blocks(frame_id);
    CREATE VIRTUAL TABLE frames_fts USING fts5(
      text, window_title, app,
      tokenize = 'unicode61 remove_diacritics 2'
    );
    CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
    CREATE TABLE exclusions (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      kind TEXT NOT NULL CHECK (kind IN ('app', 'title')),
      pattern TEXT NOT NULL,
      enabled INTEGER NOT NULL DEFAULT 1,
      created_at REAL NOT NULL
    );
    CREATE TABLE daily_stats (
      day TEXT PRIMARY KEY,
      frames INTEGER NOT NULL DEFAULT 0,
      hidden INTEGER NOT NULL DEFAULT 0,
      ticks INTEGER NOT NULL DEFAULT 0
    );
    """,
]


def check_sqlite() -> None:
    version = tuple(int(p) for p in sqlite3.sqlite_version.split("."))
    if version < MIN_SQLITE:
        raise RuntimeError(f"SQLite {sqlite3.sqlite_version} is too old; need {'.'.join(map(str, MIN_SQLITE))}+.")
    probe = sqlite3.connect(":memory:")
    try:
        probe.execute("CREATE VIRTUAL TABLE t USING fts5(x)")
    except sqlite3.OperationalError as error:  # pragma: no cover - depends on the build
        raise RuntimeError("This Python's SQLite has no FTS5 support; Argus needs it.") from error
    finally:
        probe.close()


class Database:
    """One connection shared by every thread, guarded by a re-entrant lock.

    The app is the only writer; the MCP bridge never opens this file.
    """

    def __init__(self, path: Path):
        check_sqlite()
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.lock = threading.RLock()
        self.conn = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.migrate()

    def migrate(self) -> None:
        with self.lock:
            self.conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)")
            row = self.conn.execute("SELECT MAX(version) AS v FROM schema_version").fetchone()
            current = row["v"] or 0
            for index, sql in enumerate(MIGRATIONS, start=1):
                if index <= current:
                    continue
                # executescript commits any open transaction first, so the
                # BEGIN/COMMIT pair must live inside the script itself.
                script = f"BEGIN;\n{sql}\nINSERT INTO schema_version(version) VALUES ({index});\nCOMMIT;"
                try:
                    self.conn.executescript(script)
                except Exception:
                    if self.conn.in_transaction:
                        self.conn.execute("ROLLBACK")
                    raise

    def close(self) -> None:
        with self.lock:
            try:
                self.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            except sqlite3.Error:
                pass
            self.conn.close()
