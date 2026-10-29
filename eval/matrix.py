"""Assignment 4, Parts B and C: count what the tracker holds for each case of a crash matrix.

A case is a run of the planned way on issue 4201 started with --die-after-step N or
--die-during-step N, with this key mode; the latest run per (when, step) is the case,
as the checker reads it. Each case is read by its run_id from the tracker's database
and every archive (never from its trace, which records what the process believed):
its comments on 4201 and its open PRs from repomind/issue-4201. `matches` says whether
the final result is what the run itself decided, its last checkpoint's findings: one
comment stating their label and file, and a PR exactly when that file is not none.

    python -m eval.matrix                     # derived keys (Part B), on your model
    python -m eval.matrix --keys uuid         # random keys (Part C)
    python -m eval.matrix --write             # also write matrix_<keys> into reports/LAB_04.json
    python -m eval.matrix --scripted          # the scripted model's cases instead, to test for free
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3

from harness import LAB, ROOT
from harness.formats import normalize_path, parse_triage_comment
from harness.runner import is_free, is_trace
from harness.trace import read_trace
from state.checkpointer import Checkpointer

ISSUE = 4201
BRANCH = f"repomind/issue-{ISSUE}"
REPORT = ROOT / "reports" / "LAB_04.json"


def cases(key_mode: str, scripted: bool) -> dict[tuple[int, str], dict]:
    """The latest killed run per (step, when), with its run_start and whether it finished."""
    out = {}
    for path in sorted((ROOT / "runs").glob("*.jsonl")):
        if not is_trace(path):
            continue
        records = read_trace(path)
        start = records[0] if records and records[0].get("type") == "run_start" else None
        if not start or start.get("lab") != LAB or start.get("way") != "planned" or start.get("issue") != ISSUE:
            continue
        if not start.get("die") or is_free(start.get("backend") or "") != scripted:
            continue
        if ((start.get("switches") or {}).get("key_mode") or "derived") != key_mode:
            continue
        key = (int(start["die"]["step"]), start["die"]["when"])
        order = (start.get("started") or "", path.stat().st_mtime)
        if key not in out or order > out[key]["order"]:
            out[key] = {"run_id": start["run_id"], "order": order,
                        "resumed": any(r.get("type") == "resume" for r in records),
                        "finished": any(r.get("type") == "run_end" for r in records),
                        "end": next((r.get("terminal_reason") for r in reversed(records) if r.get("type") == "end"), None)}
    return out


def writes(run_id: str) -> tuple[list[dict], list[dict]]:
    """This run's comments on the issue and open PRs from its branch, in the live tracker and every archive."""
    comments, prs = [], []
    for db_path in [ROOT / "tracker" / "tracker.db", *sorted((ROOT / "tracker" / "archive").glob("*.db"))]:
        if not db_path.exists():
            continue
        db = sqlite3.connect(db_path)
        db.row_factory = sqlite3.Row
        try:
            comments += [dict(r) for r in db.execute(
                "SELECT * FROM comments WHERE run_id = ? AND issue = ? ORDER BY id", (run_id, ISSUE))]
            prs += [dict(r) for r in db.execute(
                "SELECT * FROM prs WHERE run_id = ? AND branch = ? AND state = 'open' ORDER BY id", (run_id, BRANCH))]
        finally:
            db.close()
    return comments, prs


def matches(comments: list[dict], prs: list[dict], findings: dict | None) -> bool:
    if len(comments) != 1 or not isinstance(findings, dict) or "label" not in findings or "file" not in findings:
        return False
    label, file = parse_triage_comment(comments[0]["body"])
    want = normalize_path(str(findings["file"]))
    return (label, file) == (str(findings["label"]).lower(), want) and len(prs) == (0 if want == "none" else 1)


def dumps(report: dict) -> str:
    """Two-space JSON, with every object or list that holds no other on one line, as the template has it."""
    flat = re.compile(r"([\[{])\n\s*((?:[^\[\]{}]|\[\]|\{\})*?)\n\s*([\]}])")
    return flat.sub(lambda m: m.group(1) + re.sub(r",\n\s*", ", ", m.group(2)) + m.group(3),
                    json.dumps(report, indent=2))


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--keys", default="derived", choices=["derived", "uuid"])
    p.add_argument("--write", action="store_true", help="write the entries into reports/LAB_04.json")
    p.add_argument("--scripted", action="store_true", help="the scripted model's cases, not your model's")
    a = p.parse_args(argv)

    checkpoints = Checkpointer()
    entries, duplicates = [], {}
    print("| Step | When | run_id | Comments | Comment IDs | Open PRs | Findings (label, file) | Matches | Note |")
    print("|---|---|---|---|---|---|---|---|---|")
    for (step, when), case in sorted(cases(a.keys, a.scripted).items()):
        rid = case["run_id"]
        comments, prs = writes(rid)
        last = checkpoints.last(rid)
        findings = last.get("findings") if last else None
        ok = matches(comments, prs, findings)
        note = ("not resumed yet" if not case["resumed"] else "resumed, not finished" if not case["finished"]
                else "" if case["end"] == "completed" else f"ended {case['end']}")
        decided = f"{findings.get('label')}, {findings.get('file')}" if findings and "file" in findings else "-"
        print(f"| {step} | {when} | `{rid}` | {len(comments)} | {', '.join(str(c['id']) for c in comments)} | "
              f"{len(prs)} | {decided} | {'yes' if ok else 'no'} | {note} |")
        entries.append({"run_id": rid, "step": step, "when": when, "comments": len(comments),
                        "open_prs": len(prs), "matches": ok})
        if len(comments) > 1:
            duplicates[rid] = [c["id"] for c in comments]
    if a.write:
        if a.scripted:
            raise SystemExit("--write records your model's cases only; drop --scripted")
        report = json.loads(REPORT.read_text())
        report[f"matrix_{a.keys}"] = entries
        if a.keys == "uuid":
            report["duplicate_comment_ids"] = duplicates
        REPORT.write_text(dumps(report) + "\n")
        print(f"\nwrote matrix_{a.keys} ({len(entries)} cases) to {REPORT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
