"""SQLite cache (research.md §3): per-TU facts + per-run results. Lives outside the analysed repo."""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 2  # 2: flow_facts (spec 006)


class CacheStore:
    def __init__(self, cache_dir: Path):
        cache_dir.mkdir(parents=True, exist_ok=True)
        self.path = cache_dir / "cache.sqlite3"
        self.db = sqlite3.connect(str(self.path))
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE IF NOT EXISTS tu_facts (
                tu TEXT PRIMARY KEY, args_key TEXT NOT NULL, facts TEXT NOT NULL, updated REAL);
            CREATE TABLE IF NOT EXISTS flow_facts (
                tu TEXT PRIMARY KEY, args_key TEXT NOT NULL, facts TEXT NOT NULL, updated REAL);
            CREATE TABLE IF NOT EXISTS runs (
                run_key TEXT PRIMARY KEY, commit_hash TEXT, report TEXT NOT NULL, created REAL);
            """
        )
        row = self.db.execute("SELECT value FROM meta WHERE key='schema'").fetchone()
        if row is None or int(row[0]) != SCHEMA_VERSION:
            self.db.executescript("DELETE FROM tu_facts; DELETE FROM flow_facts; DELETE FROM runs;")
            self.db.execute("INSERT OR REPLACE INTO meta VALUES ('schema', ?)", (str(SCHEMA_VERSION),))
        self.db.commit()

    def get_tu(self, tu: str, args_key: str) -> dict[str, Any] | None:
        row = self.db.execute("SELECT args_key, facts FROM tu_facts WHERE tu=?", (tu,)).fetchone()
        if row is None or row[0] != args_key:
            return None
        return json.loads(row[1])

    def put_tu(self, tu: str, args_key: str, facts: dict[str, Any]) -> None:
        self.db.execute("INSERT OR REPLACE INTO tu_facts VALUES (?,?,?,?)",
                        (tu, args_key, json.dumps(facts), time.time()))
        self.db.commit()

    def get_flow(self, tu: str, args_key: str) -> dict[str, Any] | None:
        row = self.db.execute("SELECT args_key, facts FROM flow_facts WHERE tu=?", (tu,)).fetchone()
        if row is None or row[0] != args_key:
            return None
        return json.loads(row[1])

    def put_flow(self, tu: str, args_key: str, facts: dict[str, Any]) -> None:
        self.db.execute("INSERT OR REPLACE INTO flow_facts VALUES (?,?,?,?)",
                        (tu, args_key, json.dumps(facts), time.time()))
        self.db.commit()

    def get_run(self, run_key: str) -> dict[str, Any] | None:
        row = self.db.execute("SELECT report FROM runs WHERE run_key=?", (run_key,)).fetchone()
        return json.loads(row[0]) if row else None

    def put_run(self, run_key: str, commit_hash: str | None, report: dict[str, Any]) -> None:
        self.db.execute("INSERT OR REPLACE INTO runs VALUES (?,?,?,?)",
                        (run_key, commit_hash, json.dumps(report), time.time()))
        self.db.commit()

    def close(self) -> None:
        self.db.close()
