"""The memory store (L7): SQLite, one connection per call so any thread may use it.

  cases   the case file as JSON, plus flat columns (stage, owner, side_state) for queries
  events  append-only; THE event log of the case (messages, handoffs, results, stage moves)
  outbox  every outbound message and card, with a sequence number the UI polls from

Writes are patch-style: `update_case(case_id, fn)` takes the case's lock, reloads, applies `fn`
and saves. Nobody saves a case object they held across a model call, so two threads (a claims
prep turn and a support turn) never overwrite each other's changes.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Callable
from contextlib import closing
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from agent.casefile import CaseFile, now

SCHEMA = """
CREATE TABLE IF NOT EXISTS cases (
    case_id TEXT PRIMARY KEY, stage INTEGER, owner TEXT, side_state TEXT, data TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS events (
    seq INTEGER PRIMARY KEY AUTOINCREMENT, case_id TEXT, at TEXT, type TEXT, actor TEXT, data TEXT);
CREATE INDEX IF NOT EXISTS events_case ON events (case_id, seq);
CREATE TABLE IF NOT EXISTS outbox (
    seq INTEGER PRIMARY KEY AUTOINCREMENT, case_id TEXT, at TEXT, kind TEXT, agent TEXT, payload TEXT);
CREATE INDEX IF NOT EXISTS outbox_case ON outbox (case_id, seq);
"""


class Event(BaseModel):
    seq: int
    case_id: str
    at: str
    type: str
    actor: str
    data: dict[str, Any]

    def line(self) -> str:
        """The event verbatim, as one line of a memory block."""
        return f"#{self.seq} {self.at} {self.type} by {self.actor}: {json.dumps(self.data)}"


class OutboxItem(BaseModel):
    seq: int
    case_id: str
    at: str
    kind: str  # message | card
    agent: str
    payload: dict[str, Any]


class Store:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._locks: dict[str, threading.RLock] = {}
        self._locks_guard = threading.Lock()
        with closing(self._connect()) as db, db:
            db.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=30)
        db.execute("PRAGMA journal_mode=WAL")
        return db

    def _lock(self, case_id: str) -> threading.RLock:
        with self._locks_guard:
            return self._locks.setdefault(case_id, threading.RLock())

    # ---------------------------------------------------------------- cases

    def create_case(self, case: CaseFile) -> CaseFile:
        with closing(self._connect()) as db, db:
            db.execute("INSERT INTO cases VALUES (?, ?, ?, ?, ?, ?)", self._row(case))
        return case

    def get_case(self, case_id: str) -> CaseFile:
        with closing(self._connect()) as db:
            row = db.execute("SELECT data FROM cases WHERE case_id = ?", (case_id,)).fetchone()
        if row is None:
            raise KeyError(f"no case {case_id}")
        return CaseFile.model_validate_json(row[0])

    def exists(self, case_id: str) -> bool:
        with closing(self._connect()) as db:
            return db.execute("SELECT 1 FROM cases WHERE case_id = ?", (case_id,)).fetchone() is not None

    def update_case(self, case_id: str, fn: Callable[[CaseFile], Any]) -> CaseFile:
        """Under the case's lock: reload, apply `fn` (mutates the case; no model calls), save."""
        with self._lock(case_id):
            case = self.get_case(case_id)
            fn(case)
            with closing(self._connect()) as db, db:
                db.execute(
                    "UPDATE cases SET stage=?, owner=?, side_state=?, data=?, updated_at=? WHERE case_id=?",
                    self._row(case)[1:] + (case.case_id,),
                )
            return case

    @staticmethod
    def _row(case: CaseFile) -> tuple:
        return (case.case_id, case.stage, case.owner, case.side_state, case.model_dump_json(), now())

    # ---------------------------------------------------------------- events

    def append_event(self, case_id: str, type: str, data: dict | None = None, actor: str = "system") -> Event:
        at = now()
        payload = json.dumps(data or {})
        with closing(self._connect()) as db, db:
            seq = db.execute(
                "INSERT INTO events (case_id, at, type, actor, data) VALUES (?, ?, ?, ?, ?)",
                (case_id, at, type, actor, payload),
            ).lastrowid
        return Event(seq=seq, case_id=case_id, at=at, type=type, actor=actor, data=data or {})

    def events(self, case_id: str, types: tuple[str, ...] | None = None, exclude: tuple[str, ...] = (),
               last: int | None = None) -> list[Event]:  # fmt: skip
        """The case's events, oldest first: optionally only `types`, never `exclude`, the `last` N."""
        sql, args = "SELECT seq, case_id, at, type, actor, data FROM events WHERE case_id = ?", [case_id]
        if types:
            sql += f" AND type IN ({','.join('?' * len(types))})"
            args += types
        if exclude:
            sql += f" AND type NOT IN ({','.join('?' * len(exclude))})"
            args += exclude
        sql += " ORDER BY seq DESC"
        if last is not None:
            sql += f" LIMIT {int(last)}"
        with closing(self._connect()) as db:
            rows = db.execute(sql, args).fetchall()
        return [
            Event(seq=r[0], case_id=r[1], at=r[2], type=r[3], actor=r[4], data=json.loads(r[5]))
            for r in reversed(rows)
        ]

    # ---------------------------------------------------------------- outbox

    def post(self, case_id: str, kind: str, payload: dict, agent: str) -> OutboxItem:
        at = now()
        with closing(self._connect()) as db, db:
            seq = db.execute(
                "INSERT INTO outbox (case_id, at, kind, agent, payload) VALUES (?, ?, ?, ?, ?)",
                (case_id, at, kind, agent, json.dumps(payload)),
            ).lastrowid
        return OutboxItem(seq=seq, case_id=case_id, at=at, kind=kind, agent=agent, payload=payload)

    def outbox_since(self, case_id: str, seq: int = 0) -> list[OutboxItem]:
        with closing(self._connect()) as db:
            rows = db.execute(
                "SELECT seq, case_id, at, kind, agent, payload FROM outbox WHERE case_id = ? AND seq > ? ORDER BY seq",
                (case_id, seq),
            ).fetchall()
        return [
            OutboxItem(seq=r[0], case_id=r[1], at=r[2], kind=r[3], agent=r[4], payload=json.loads(r[5]))
            for r in rows
        ]
