"""Assignment 4, Part A: the checkpointer. This file is yours.

A checkpointer saves one run's state, so its checkpoints are keyed by the run's
run_id (frameworks call one run's line of checkpoints a thread). Save them on a
durable backend: a SQLite file such as state/checkpoints.db is fine; an in-memory
store is not, because it dies with the process. A sync save is on disk before
save() returns.

The checker calls these, with these exact signatures (checks/FORMATS.md, section
12.4), so keep them:

    Checkpointer(path=None)                    # None: your default file
    .save(run_id, checkpoint, *, step, mode)   # one checkpoint; mode is sync, async or exit
    .last(run_id) -> dict | None               # the run's latest checkpoint, or None
    .all(run_id) -> list[dict]                 # every checkpoint the run saved, oldest first
    .runs() -> list[str]                       # every run_id that has a checkpoint

A checkpoint is a dict of exactly the five fields in harness.formats.CHECKPOINT_FIELDS:
plan, step_status, completed_calls (each with its idempotency key), findings and
current_step. Everything in it must serialize, and the conversation is not in it.
Every save is also a trace line, trace.event("checkpoint", step=..., mode=...),
which your way writes.

The durability mode (Lecture 4, slide 12) says how a save is written; the way sets
one for the whole run:

    sync    written and committed before save() returns: a crash after save() keeps it
    async   handed to a background writer and written soon after: a crash in the gap loses it
    exit    held in memory until close(), at the run's end: a crash loses every one

A checkpoint is serialized when save() is called, whatever the mode, so what is
written is the state at that moment, not whatever the run has mutated since.
close() writes what async and exit are still holding; the way calls it when the
run ends, however it ends. A process killed with kill -9 never reaches it.
"""

from __future__ import annotations

import json
import queue
import sqlite3
import threading
import time
from pathlib import Path

from harness import ROOT
from harness.formats import CHECKPOINT_FIELDS, DURABILITY_MODES

DEFAULT = ROOT / "state" / "checkpoints.db"

TABLE = """
CREATE TABLE IF NOT EXISTS checkpoints (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id    TEXT NOT NULL,
    step      TEXT,
    mode      TEXT NOT NULL,
    saved_at  TEXT NOT NULL,
    data      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS checkpoints_run ON checkpoints (run_id, id);
"""


class Checkpointer:
    def __init__(self, path: Path | None = None):
        self.path = Path(path or DEFAULT)
        self._held: list[tuple] = []                 # exit: rows kept until close()
        self._queue: queue.Queue | None = None       # async: rows waiting for the writer
        self._writer: threading.Thread | None = None

    # -- writing ---------------------------------------------------------------------------
    def save(self, run_id: str, checkpoint: dict, *, step, mode: str = "sync") -> None:
        if mode not in DURABILITY_MODES:
            raise ValueError(f"a checkpoint's mode is one of {DURABILITY_MODES}, not {mode!r}")
        if not isinstance(checkpoint, dict) or set(checkpoint) != set(CHECKPOINT_FIELDS):
            got = sorted(checkpoint) if isinstance(checkpoint, dict) else type(checkpoint).__name__
            raise ValueError(f"a checkpoint has exactly the fields {list(CHECKPOINT_FIELDS)}; this one has {got}")
        data = json.dumps({k: checkpoint[k] for k in CHECKPOINT_FIELDS})   # raises if anything will not serialize
        row = (str(run_id), None if step is None else str(step), mode,
               time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), data)
        if mode == "sync":
            self._insert([row])
        elif mode == "async":
            self._background().put(row)
        else:
            self._held.append(row)

    def close(self) -> None:
        """Write what async and exit still hold. A no-op for a run that saved in sync."""
        if self._writer is not None:
            self._queue.put(None)
            self._writer.join()
            self._writer, self._queue = None, None
        if self._held:
            rows, self._held = self._held, []
            self._insert(rows)

    def _background(self) -> queue.Queue:
        if self._writer is None:
            self._queue = queue.Queue()
            self._writer = threading.Thread(target=self._drain, args=(self._queue,), daemon=True,
                                            name="checkpoint-writer")
            self._writer.start()
        return self._queue

    def _drain(self, rows: queue.Queue) -> None:
        while (row := rows.get()) is not None:
            self._insert([row])

    def _insert(self, rows: list[tuple]) -> None:
        db = self._connect()
        try:
            with db:   # one transaction, committed (and, with synchronous=FULL, on disk) when it closes
                db.executemany("INSERT INTO checkpoints (run_id, step, mode, saved_at, data) VALUES (?, ?, ?, ?, ?)",
                               rows)
        finally:
            db.close()

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=30)
        db.execute("PRAGMA synchronous=FULL")
        db.executescript(TABLE)
        return db

    # -- reading ---------------------------------------------------------------------------
    def last(self, run_id: str) -> dict | None:
        rows = self._select("SELECT data FROM checkpoints WHERE run_id = ? ORDER BY id DESC LIMIT 1", (str(run_id),))
        return json.loads(rows[0][0]) if rows else None

    def all(self, run_id: str) -> list[dict]:
        rows = self._select("SELECT data FROM checkpoints WHERE run_id = ? ORDER BY id", (str(run_id),))
        return [json.loads(r[0]) for r in rows]

    def runs(self) -> list[str]:
        rows = self._select("SELECT run_id FROM checkpoints GROUP BY run_id ORDER BY MIN(id)", ())
        return [r[0] for r in rows]

    def _select(self, sql: str, args: tuple) -> list[tuple]:
        if not self.path.exists():
            return []
        db = self._connect()
        try:
            return db.execute(sql, args).fetchall()
        finally:
            db.close()

    def size(self, run_id: str) -> int:
        """The bytes one run's checkpoints take together: the summed length of what was saved."""
        rows = self._select("SELECT COALESCE(SUM(LENGTH(CAST(data AS BLOB))), 0) FROM checkpoints WHERE run_id = ?",
                            (str(run_id),))
        return rows[0][0] if rows else 0


class WithConversation(Checkpointer):
    """Assignment 4, Part E: a second copy of each checkpoint with a sixth field, the
    conversation (every request the run has sent the model so far), to measure what it
    would cost. It goes to a separate file, never to the checkpoint database: a checkpoint
    never holds the conversation."""

    def __init__(self, path: Path):
        super().__init__(path)
        if self.path.resolve() == DEFAULT.resolve():
            raise ValueError("a copy with the conversation never goes to the checkpoint database")

    def save(self, run_id: str, checkpoint: dict, *, step, mode: str = "sync") -> None:
        data = json.dumps(checkpoint)
        self._insert([(str(run_id), None if step is None else str(step), mode,
                       time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), data)])
