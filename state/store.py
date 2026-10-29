"""Assignment 4, Part D: the memory store. This file is yours.

A store is shared by every run, keyed by repository and issue. It is durable: a
SQLite file such as state/store.db is fine. How you give a run an empty store, for
Part D's second set of five runs, is yours: an environment variable this module
reads, for example. The checker always reads your real store.

The checker calls these, with these exact signatures (checks/FORMATS.md, section
12.5), so keep them:

    Store(path=None)                                  # None: your default file
    .write(record) -> id                              # a new record; returns its id
    .supersede(old_id, record) -> id                  # a new record that replaces old_id
    .active(repository, issue=None) -> list[dict]     # the active records, for retrieval
    .records() -> list[dict]                          # every record, active or not

Every record carries the fields of section 12.5: its kind (episodic, semantic or
procedural), its text, and its provenance: source, written_at, origin (derived or
ingested) and confirmed. A superseded record stays in the store, inactive, and the
record that replaced it names it in `supersedes`.

The rules are state/write_policy.md's. The store enforces the ones a caller could
get wrong:
  - a record's text from an issue (source issue:<n>) is ingested, unconfirmed and
    never semantic, so text anyone can write never comes back as a fact;
  - one active record per subject: supersede() retires the old one in the same
    transaction, and a write on a subject that is already active is refused;
  - eviction at MAX_RECORDS per repository: the oldest episodic records go first,
    inactive before active; semantic and procedural records are never evicted.

The empty store, for Part D's second set of runs: REPOMIND_STORE=empty gives each
Store() a new, empty file of its own; REPOMIND_STORE=<path> opens that file (to test
on the scripted model without touching the real store). Unset, Store() opens
state/store.db, which is how the checker calls it.
"""

from __future__ import annotations

import os
import re
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from harness import ROOT

DEFAULT = ROOT / "state" / "store.db"
REPOSITORY = "ledgerline"
KINDS = ("episodic", "semantic", "procedural")
ORIGINS = ("derived", "ingested")
SOURCE = re.compile(r"^(user|repo|memory|issue:\d+)$")
MAX_RECORDS = 1000    # per repository: about 100 days of decisions at 10 runs a day (write_policy.md, Eviction)
SWITCH = "REPOMIND_STORE"

TABLE = """
CREATE TABLE IF NOT EXISTS records (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    repository  TEXT NOT NULL,
    issue       INTEGER,
    kind        TEXT NOT NULL,
    subject     TEXT,
    text        TEXT NOT NULL,
    source      TEXT NOT NULL,
    written_at  TEXT NOT NULL,
    origin      TEXT NOT NULL,
    confirmed   INTEGER NOT NULL,
    active      INTEGER NOT NULL DEFAULT 1,
    supersedes  INTEGER,
    stated_by   TEXT,
    seen_in     TEXT
);
CREATE INDEX IF NOT EXISTS records_lookup ON records (repository, issue, active);
"""
COLUMNS = ("repository", "issue", "kind", "subject", "text", "source", "written_at", "origin", "confirmed",
           "stated_by", "seen_in")


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def default_path() -> Path:
    switch = os.environ.get(SWITCH, "").strip()
    if not switch:
        return DEFAULT
    if switch == "empty":                    # a new, empty store for this Store(), and so for this run
        return Path(tempfile.mkdtemp(prefix="repomind-empty-store-")) / "store.db"
    return Path(switch)


class Store:
    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else default_path()
        self.empty = os.environ.get(SWITCH, "").strip() == "empty" and not path

    # -- writing ---------------------------------------------------------------------------
    def write(self, record: dict):
        row = self._row(record)
        db = self._connect()
        try:
            with db:
                clash = self._same_subject(db, row)
                if clash is not None:
                    raise ValueError(f"record {clash} on subject {row['subject']!r} is active; supersede it, "
                                     "never keep two")
                new = self._insert(db, row, None)
                self._evict(db, row["repository"])
            return new
        finally:
            db.close()

    def supersede(self, old_id, record: dict):
        row = self._row(record)
        db = self._connect()
        try:
            with db:   # the new record and the old one's retirement, together or not at all
                old = db.execute("SELECT active FROM records WHERE id = ?", (int(old_id),)).fetchone()
                if old is None:
                    raise KeyError(f"no record {old_id} to supersede")
                if not old[0]:
                    raise ValueError(f"record {old_id} is already inactive: supersede the active one")
                db.execute("UPDATE records SET active = 0 WHERE id = ?", (int(old_id),))
                new = self._insert(db, row, int(old_id))
                self._evict(db, row["repository"])
            return new
        finally:
            db.close()

    def _row(self, record: dict) -> dict:
        """The record, checked against the write policy, as a row."""
        row = {k: record.get(k) for k in COLUMNS}
        row["repository"] = row["repository"] or REPOSITORY
        row["written_at"] = row["written_at"] or now()
        source = str(row["source"] or "")
        if row["kind"] not in KINDS:
            raise ValueError(f"kind is one of {KINDS}, not {row['kind']!r}")
        if row["origin"] not in ORIGINS:
            raise ValueError(f"origin is one of {ORIGINS}, not {row['origin']!r}")
        if not SOURCE.match(source):
            raise ValueError(f"source is user, repo, memory or issue:<n>, not {source!r}")
        if not isinstance(row["confirmed"], bool):
            raise ValueError("confirmed is true or false")
        if not str(row["text"] or "").strip():
            raise ValueError("a record has text")
        datetime.fromisoformat(str(row["written_at"]).replace("Z", "+00:00"))   # raises if it is not ISO 8601
        if source.startswith("issue:") and (row["kind"] == "semantic" or row["confirmed"] or row["origin"] != "ingested"):
            raise ValueError("text from an issue is stored only as episodic, ingested and unconfirmed: anyone can "
                             "write it (write_policy.md)")
        if source == "user" and not row["stated_by"]:
            raise ValueError("a person's statement names who stated it")
        row["confirmed"] = int(row["confirmed"])
        return row

    def _same_subject(self, db, row: dict) -> int | None:
        if not row["subject"]:
            return None
        hit = db.execute("SELECT id FROM records WHERE repository = ? AND issue IS ? AND subject = ? AND active = 1",
                         (row["repository"], row["issue"], row["subject"])).fetchone()
        return hit[0] if hit else None

    def _insert(self, db, row: dict, supersedes: int | None) -> int:
        cur = db.execute(f"INSERT INTO records ({', '.join(COLUMNS)}, active, supersedes) "
                         f"VALUES ({', '.join('?' * len(COLUMNS))}, 1, ?)",
                         (*(row[k] for k in COLUMNS), supersedes))
        return cur.lastrowid

    def _evict(self, db, repository: str) -> None:
        """At the cap, the oldest episodic records go, inactive before active."""
        (count,) = db.execute("SELECT COUNT(*) FROM records WHERE repository = ?", (repository,)).fetchone()
        if count > MAX_RECORDS:
            db.execute("DELETE FROM records WHERE id IN (SELECT id FROM records WHERE repository = ? AND "
                       "kind = 'episodic' ORDER BY active, written_at, id LIMIT ?)", (repository, count - MAX_RECORDS))

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.executescript(TABLE)
        return db

    # -- reading ---------------------------------------------------------------------------
    def active(self, repository: str, issue: int | None = None) -> list[dict]:
        if issue is None:
            return self._select("SELECT * FROM records WHERE repository = ? AND active = 1 ORDER BY id", (repository,))
        return self._select("SELECT * FROM records WHERE repository = ? AND active = 1 AND (issue IS NULL OR issue = ?) "
                            "ORDER BY id", (repository, int(issue)))

    def records(self) -> list[dict]:
        return self._select("SELECT * FROM records ORDER BY id", ())

    def _select(self, sql: str, args: tuple) -> list[dict]:
        if not self.path.exists():
            return []
        db = self._connect()
        try:
            return [{**dict(r), "confirmed": bool(r["confirmed"]), "active": bool(r["active"])}
                    for r in db.execute(sql, args)]
        finally:
            db.close()
