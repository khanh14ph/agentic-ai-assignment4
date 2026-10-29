"""Assignment 4, Part E: the contradiction test (Lecture 4, slide 25): set a fact,
contradict it, check in a third session. Each session is its own process, which opens
the store, does one thing and exits.

    python -m state.store_candidates                       # 1. Part D: the maintainer's rule on duplicates (C)
    python -m state.contradiction_test contradict          # 2. the same maintainer changes it: supersedes the first
    python -m state.contradiction_test retrieve [--write]  # 3. the rule on duplicates, and only that

The second session's rule is made up for this test, and its record says so in
`seen_in`. It is stored as the first was: from a user, about duplicates, stated by the
same maintainer, written when it was stated. The third prints the IDs it retrieved and,
with --write, puts them in reports/LAB_04.json as contradiction_test.
"""

from __future__ import annotations

import argparse
import json

from state.store import REPOSITORY, Store, now

SUBJECT = "duplicates-rule"
CHANGED = ("For duplicates: label them `duplicate`, link the original, and close them after 14 days if the "
           "reporter has not replied. I no longer close them myself.")


def rules(store: Store) -> list[dict]:
    """The active rules a person stated about duplicates."""
    return [r for r in store.active(REPOSITORY) if r["source"] == "user" and r["subject"] == SUBJECT]


def contradict(store: Store) -> None:
    active = rules(store)
    if len(active) != 1:
        raise SystemExit(f"want one active rule on duplicates to contradict; the store has {len(active)}")
    old = active[0]
    if old["text"] == CHANGED:
        print(f"record {old['id']} already holds the changed rule; nothing to do")
        return
    rid = store.supersede(old["id"], {
        "repository": REPOSITORY, "issue": None, "kind": old["kind"], "subject": SUBJECT, "text": CHANGED,
        "source": "user", "origin": "ingested", "confirmed": True, "stated_by": old["stated_by"], "written_at": now(),
        "seen_in": "made up for Assignment 4's contradiction test (Part E): the same maintainer changing the rule"})
    print(f"record {rid} supersedes record {old['id']}")


def retrieve(store: Store, write: bool) -> None:
    found = rules(store)
    for r in found:
        print(f"record {r['id']} (supersedes {r['supersedes']}), stated by {r['stated_by']}, {r['written_at']}: "
              f"{r['text']}")
    ids = [r["id"] for r in found]
    print(f"retrieved: {ids}")
    if write:
        from eval.matrix import REPORT, dumps
        report = json.loads(REPORT.read_text())
        report["contradiction_test"] = ids
        REPORT.write_text(dumps(report) + "\n")
        print("wrote contradiction_test to reports/LAB_04.json")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("session", choices=["contradict", "retrieve"])
    p.add_argument("--write", action="store_true", help="retrieve: write the IDs into reports/LAB_04.json")
    a = p.parse_args(argv)
    store = Store()
    contradict(store) if a.session == "contradict" else retrieve(store, a.write)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
