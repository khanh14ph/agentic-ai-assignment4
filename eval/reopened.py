"""Assignment 4, Part D: the reopened issue, 4207, with the store and with an empty one.

A run's set is read from its own store_read line: "store": "empty" for a run with
REPOMIND_STORE=empty, the real store's path otherwise. Each set is its latest five
finished runs on your model; --seed leaves the seed run out of the set with the
store. For each run: its tool calls (tool_call lines), its tokens
(run_end.totals.total_tokens), whether it passed (Assignment 1's check(), read from
the tracker by run_id), and two provenances:
  - the file it read, and where that path came from: a search result, or a record
    the run recalled from the store (memory);
  - the file its comment named, and where that came from: the file it read, a search
    result, a mention in what it read (an import, a doc), memory, or none of its steps.
Full tool results come from the run's last checkpoint (completed_calls); the call
record keeps only an excerpt of each.

    python -m eval.reopened --seed <run_id>           # the table
    python -m eval.reopened --seed <run_id> --write   # and reopened.* in reports/LAB_04.json
"""

from __future__ import annotations

import argparse
import json

import yaml

from eval.check_triage import check
from eval.matrix import REPORT, dumps
from harness import LAB, ROOT
from harness.formats import normalize_path, parse_triage_comment, result_paths
from harness.roles import arg, role_of
from harness.runner import is_free, is_trace
from harness.trace import read_trace
from harness.tracker import Tracker
from state.checkpointer import Checkpointer
from state.store import Store

ISSUE = 4207
REAL_STORE = "state/store.db"
RUNS_PER_SET = 5


def runs() -> dict[str, list[dict]]:
    """Finished runs of 4207 on your model, by set, oldest first."""
    sets = {"with_store": [], "empty_store": []}
    for path in sorted((ROOT / "runs").glob("*.jsonl")):
        if not is_trace(path):
            continue
        records = read_trace(path)
        start = records[0] if records and records[0].get("type") == "run_start" else {}
        if start.get("lab") != LAB or start.get("issue") != ISSUE or start.get("way") != "planned" or start.get("die"):
            continue
        if is_free(start.get("backend") or "") or not any(r.get("type") == "run_end" for r in records):
            continue
        read = next((r for r in records if r.get("type") == "store_read"), None)
        if read is None:
            continue
        name = "empty_store" if read.get("store") == "empty" else "with_store" if read.get("store") == REAL_STORE else None
        if name:
            sets[name].append({"run_id": start["run_id"], "started": start.get("started") or "", "records": records,
                               "recalled": read.get("records") or []})
    return {k: sorted(v, key=lambda r: r["started"]) for k, v in sets.items()}


def provenance(run_id: str, named: str | None, memory: str) -> dict:
    """The file the run read and the file it named, each with where it came from."""
    last = Checkpointer().last(run_id)
    calls = (last or {}).get("completed_calls") or []
    searched = {p for c in calls if role_of(c["tool"]) == "search"
                for p in result_paths(c["tool"], c["args"], c["result"]["content"], c["result"]["is_error"])}
    reads = [c for c in calls if role_of(c["tool"]) == "read_file" and not c["result"]["is_error"]]
    read = normalize_path(str(reads[-1]["args"].get(arg("read_file", "path")))) if reads else None
    read_from = (None if read is None else "a search result" if read in searched
                 else "memory" if read in memory else "neither")
    if named in (None, "none"):
        named_from = "no file"
    else:
        module = "/".join(named.rsplit(".", 1)[0].split("/")[-2:])   # src/util/money.ts: util/money, as an import names it
        named_from = ("the file it read" if named == read else "a search result" if named in searched
                      else "named in the file it read" if any(module in c["result"]["content"] for c in reads)
                      else "memory" if named in memory else "none of its steps")
    query = next((c["args"].get(arg("search", "query")) for c in calls if role_of(c["tool"]) == "search"), None)
    return {"query": query, "read": read, "read_from": read_from, "named_from": named_from}


def measure(run: dict, tracker: Tracker, answer: dict, texts: dict) -> dict:
    rid, records = run["run_id"], run["records"]
    end = next(r for r in reversed(records) if r.get("type") == "run_end")
    comments = tracker.comments(run_id=rid, issue=ISSUE)
    label, file = parse_triage_comment(comments[0]["body"]) if len(comments) == 1 else (None, None)
    memory = "\n".join(texts.get(i, "") for i in run["recalled"])
    return {"run_id": rid, "tool_calls": sum(r.get("type") == "tool_call" for r in records),
            "tokens": (end.get("totals") or {}).get("total_tokens", 0), "passed": check(tracker, rid, ISSUE, answer),
            "label": label, "file": file, "recalled": run["recalled"], **provenance(rid, file, memory),
            "plans": sum(r.get("type") == "plan" for r in records),
            "rejected": sum(r.get("type") == "schema" for r in records)}   # plans the schema check sent back


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--seed", help="the seed run's run_id, left out of the set with the store")
    p.add_argument("--write", action="store_true", help="write reopened.* into reports/LAB_04.json")
    a = p.parse_args(argv)

    answer = yaml.safe_load((ROOT / "fixtures" / "answers.yaml").read_text())["eval"][ISSUE]
    tracker = Tracker(ROOT)
    texts = {r["id"]: r["text"] for r in Store(ROOT / REAL_STORE).records()}
    report = json.loads(REPORT.read_text())
    for name, found in runs().items():
        chosen = [r for r in found if r["run_id"] != a.seed][-RUNS_PER_SET:]
        rows = [measure(r, tracker, answer, texts) for r in chosen]
        print(f"\n{name}: {len(rows)} runs")
        print("| run_id | Recalled | Plans (rejected) | Tool calls | Tokens | Query | File read (its path from) | "
              "File named (from) | Label | Passed |")
        print("|---|---|---|---|---|---|---|---|---|---|")
        for m in rows:
            print(f"| `{m['run_id']}` | {m['recalled']} | {m['plans']} ({m['rejected']}) | {m['tool_calls']} | {m['tokens']:,} | "
                  f"{m['query']} | `{m['read']}` ({m['read_from']}) | `{m['file']}` ({m['named_from']}) | "
                  f"{m['label']} | {'yes' if m['passed'] else 'no'} |")
        n = len(rows)
        report.setdefault("reopened", {})[name] = {
            "runs": n, "passes": sum(m["passed"] for m in rows),
            "mean_tool_calls": round(sum(m["tool_calls"] for m in rows) / n, 2) if n else None,
            "mean_tokens": round(sum(m["tokens"] for m in rows) / n, 1) if n else None,
            "run_ids": [m["run_id"] for m in rows]}
        print(json.dumps(report["reopened"][name]))
    if a.write:
        REPORT.write_text(dumps(report) + "\n")
        print(f"\nwrote reopened to {REPORT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
