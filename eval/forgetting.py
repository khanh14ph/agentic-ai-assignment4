"""Assignment 4, Part F: where a run lost the fact, read from what each call was sent.

For each run: every model call in trace order, with its request number and purpose,
whether the request record shows it was sent the fact (compared as the checker
compares, harness.formats.squeeze), and how far from the nearer end of what it was
sent; every compaction and store_read line; the comment the tracker holds; and
whether it states the fact's effect. The drafting call is found as the checker finds
it: the latest model call before the comment's tool_call line whose call of the
comment tool states the posted label and file.

    python -m eval.forgetting <run_id> [<run_id> ...]
    python -m eval.forgetting --write attention <lost> <fixed>    # forgetting.attention in reports/LAB_04.json
    python -m eval.forgetting --write session <lost> <fixed> --stated <run_id>
"""

from __future__ import annotations

import argparse
import json

from eval.matrix import REPORT, dumps
from harness import ROOT
from harness.formats import parse_triage_comment, request_text, squeeze
from harness.roles import role_of
from harness.trace import read_trace
from harness.tracker import Tracker
from ways.planned import FACT

EFFECT = {"label": "feature"}


def requests(run_id: str) -> dict:
    path = ROOT / "runs" / f"{run_id}.requests.jsonl"
    return {json.loads(line)["n"]: json.loads(line) for line in path.read_text().splitlines()} if path.exists() else {}


def read(run_id: str) -> dict:
    records = read_trace(ROOT / "runs" / f"{run_id}.jsonl")
    sent, fact = requests(run_id), squeeze(FACT)
    comments = Tracker(ROOT).comments(run_id=run_id, issue=records[0]["issue"])
    label, file = parse_triage_comment(comments[0]["body"]) if len(comments) == 1 else (None, None)
    calls, drafting = [], None
    for i, r in enumerate(records):
        if r.get("type") == "model_call":
            text = squeeze(request_text(sent[r["request"]])) if r.get("request") in sent else ""
            at = text.find(fact)
            calls.append({"line": i, "request": r.get("request"), "purpose": r.get("purpose"), "chars": len(text),
                          "fact": at >= 0, "from_an_end": min(at, len(text) - at - len(fact)) if at >= 0 else None,
                          "tools": [c.get("name") for c in r.get("tool_calls") or []],
                          "comment": next((c.get("input") for c in r.get("tool_calls") or []
                                           if role_of(c.get("name")) == "comment"), None)})
        if r.get("type") == "tool_call" and role_of(r.get("name")) == "comment" and drafting is None:
            before = [c for c in calls if c["comment"] is not None]
            stating = [c for c in before if parse_triage_comment(str(next(iter(
                v for k, v in c["comment"].items() if k == "body"), ""))) == (label, file)]
            drafting = (stating or before or [None])[-1]
    events = [(i, r["type"], {k: v for k, v in r.items() if k not in ("run_id", "t", "type")})
              for i, r in enumerate(records) if r.get("type") in ("compaction", "store_read", "store_write", "part_f")]
    return {"run_id": run_id, "started": records[0].get("started"), "calls": calls, "drafting": drafting,
            "events": events, "comments": len(comments), "label": label, "file": file,
            "uses": label == EFFECT["label"]}


def show(view: dict) -> None:
    print(f"\n{view['run_id']}  (started {view['started']}): {view['comments']} comment(s), "
          f"label {view['label']}, file {view['file']}; states {EFFECT}: {view['uses']}")
    for i, kind, fields in view["events"]:
        print(f"  trace line {i}: {kind} {json.dumps(fields)[:160]}")
    for c in view["calls"]:
        mark = " <- drafted the comment" if c is view["drafting"] else ""
        print(f"  trace line {c['line']}: model_call, request {c['request']}, {c['purpose']}, {c['chars']:,} chars, "
              f"fact {'at ' + format(c['from_an_end'], ',') + ' chars from the nearer end' if c['fact'] else 'not sent'}"
              f", called {c['tools']}{mark}")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("runs", nargs="+")
    p.add_argument("--write", metavar="CASE", choices=["attention", "compaction", "session"])
    p.add_argument("--stated", help="session: the run told the fact")
    a = p.parse_args(argv)
    if a.write:
        report = json.loads(REPORT.read_text())
        lost, fixed = a.runs
        entry = {"fact": FACT, "effect": EFFECT, "lost": lost, "fixed": fixed}
        if a.write == "session":
            entry["stated"] = a.stated
        report.setdefault("forgetting", {})[a.write] = {**report["forgetting"].get(a.write, {}), **entry}
        REPORT.write_text(dumps(report) + "\n")
        print(f"wrote forgetting.{a.write}")
    for rid in a.runs + ([a.stated] if a.stated else []):
        show(read(rid))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
