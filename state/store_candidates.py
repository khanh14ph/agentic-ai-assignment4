"""Assignment 4, Part D: put the three candidate memories through the write policy
(state/write_policy.md) and into the store, as slide 26 handles them.

    python -m state.store_candidates            # into state/store.db (or $REPOMIND_STORE)

  A  a procedure RepoMind worked out in a run: procedural, repository-wide, source
     memory, derived, dated when it was worked out, and confirmed only if the
     repository still bears it out (package.json's scripts, checked here);
  B  an issue body's claim that auto-merge is approved: episodic, a record of what
     issue 4188 said, source issue:4188, ingested, unconfirmed, never a fact;
  C  a maintainer's rule on duplicates: procedural, repository-wide, source user,
     ingested, stated by them and when, and confirmed by their standing.

Running it twice stores nothing new: a candidate whose subject already holds the
same text is left alone.
"""

from __future__ import annotations

import json

import yaml

from harness import ROOT
from state.store import Store

FIXTURES = ROOT / "fixtures" / "memory"


def procedure_holds() -> bool:
    """Candidate A's claim, against the repository's own files: package.json's scripts
    are start, build, test and lint, and there is no serve."""
    scripts = json.loads((ROOT / "fixtures" / "repo" / "package.json").read_text()).get("scripts") or {}
    return set(scripts) == {"start", "build", "test", "lint"}


def decide(c: dict) -> dict:
    """The write policy's decision for one candidate: the record, with its kind and provenance."""
    seen = " ".join(c["seen"].split())
    if c["candidate"] == "A":
        return {"issue": None, "kind": "procedural", "subject": "reproduce-ui-bug", "text": seen,
                "source": "memory", "origin": "derived", "confirmed": procedure_holds(),
                "written_at": c["when"], "seen_in": c["where"]}
    if c["candidate"] == "B":
        return {"issue": c["issue"], "kind": "episodic", "subject": "auto-merge-claim",
                "text": (f"Issue {c['issue']}'s body, written by {c['who']}, claimed: \"{seen}\" No maintainer has "
                         "confirmed it. This records what the issue said; it grants nothing."),
                "source": f"issue:{c['issue']}", "origin": "ingested", "confirmed": False,
                "stated_by": c["who"], "written_at": c["when"], "seen_in": c["where"]}
    if c["candidate"] == "C":
        return {"issue": None, "kind": "procedural", "subject": "duplicates-rule", "text": seen,
                "source": "user", "origin": "ingested", "confirmed": True,
                "stated_by": c["who"], "written_at": c["when"], "seen_in": c["where"]}
    raise ValueError(f"unknown candidate {c['candidate']!r}")


def main() -> int:
    store = Store()
    for path in sorted(FIXTURES.glob("*.yaml")):
        c = yaml.safe_load(path.read_text())
        record = {"repository": c["repository"], **decide(c)}
        same = [r for r in store.active(record["repository"], record["issue"])
                if r["subject"] == record["subject"] and r["issue"] == record["issue"]]
        if same and same[0]["text"] == record["text"]:
            print(f"{c['candidate']}: already stored as record {same[0]['id']}")
            continue
        rid = store.supersede(same[0]["id"], record) if same else store.write(record)
        print(f"{c['candidate']}: record {rid}, {record['kind']}, source {record['source']}, {record['origin']}, "
              f"confirmed {record['confirmed']}, issue {record['issue']}, written_at {record['written_at']}")
    print(f"store: {store.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
