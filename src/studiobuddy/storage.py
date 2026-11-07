"""Local SQLite storage. Transactions complete before an update is shown."""

import sqlite3
from pathlib import Path


class Store:
    def __init__(self, path=":memory:"):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.db = sqlite3.connect(path)
        if str(path) != ":memory:":
            Path(path).chmod(0o600)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS projects(id INTEGER PRIMARY KEY, name TEXT NOT NULL, xrns TEXT);
        CREATE TABLE IF NOT EXISTS sessions(id INTEGER PRIMARY KEY, project_id INTEGER REFERENCES projects(id), goal TEXT NOT NULL, summary TEXT DEFAULT '', next_step TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY, session_id INTEGER REFERENCES sessions(id), role TEXT CHECK(role IN ('user','assistant')), content TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS state(key TEXT PRIMARY KEY, value TEXT);
        """)

    def project(self, name, xrns=""):
        with self.db:
            return self.db.execute(
                "INSERT INTO projects(name,xrns) VALUES(?,?)", (name, xrns)
            ).lastrowid

    def projects(self):
        return [dict(r) for r in self.db.execute("SELECT * FROM projects ORDER BY id")]

    def session(self, project, goal="Explore a loop"):
        with self.db:
            return self.db.execute(
                "INSERT INTO sessions(project_id,goal) VALUES(?,?)", (project, goal)
            ).lastrowid

    def sessions(self, project):
        return [
            dict(r)
            for r in self.db.execute(
                "SELECT * FROM sessions WHERE project_id=? ORDER BY id DESC", (project,)
            )
        ]

    def messages(self, session):
        return [
            dict(r)
            for r in self.db.execute(
                "SELECT role,content FROM messages WHERE session_id=? ORDER BY id", (session,)
            )
        ]

    def message(self, session, role, content):
        with self.db:
            self.db.execute(
                "INSERT INTO messages(session_id,role,content) VALUES(?,?,?)",
                (session, role, content),
            )

    def state(self, key, value=None):
        if value is not None:
            with self.db:
                self.db.execute("INSERT OR REPLACE INTO state VALUES(?,?)", (key, str(value)))
        row = self.db.execute("SELECT value FROM state WHERE key=?", (key,)).fetchone()
        return row[0] if row else None

    def close(self):
        self.db.close()
