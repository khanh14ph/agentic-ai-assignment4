"""Assignment 4, Part E: what a run's checkpoints cost on disk, without and with the conversation.

The runs measured are the ones that kept a copy with the conversation, made with
REPOMIND_CONVERSATION_COPY=state/checkpoints_with_conversation.db: each saved its
checkpoints through the checkpointer as every run does, and a second copy of each,
with every request sent so far, in that separate file. A run's bytes are the summed
length of what it saved, in bytes; the result is the mean over the runs.

    python -m eval.checkpoint_bytes            # the table
    python -m eval.checkpoint_bytes --write    # and checkpoint_bytes in reports/LAB_04.json
"""

from __future__ import annotations

import argparse
import json

from eval.matrix import REPORT, dumps
from harness import ROOT
from state.checkpointer import Checkpointer, WithConversation

COPIES = ROOT / "state" / "checkpoints_with_conversation.db"


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--write", action="store_true", help="write checkpoint_bytes into reports/LAB_04.json")
    a = p.parse_args(argv)

    structured, copies = Checkpointer(), WithConversation(COPIES)
    rows = []
    print("| run_id | Checkpoints | Structured bytes | With the conversation | Requests in the last copy |")
    print("|---|---|---|---|---|")
    for rid in copies.runs():
        saved, kept = structured.all(rid), copies.all(rid)
        if len(saved) != len(kept):
            raise SystemExit(f"{rid}: {len(saved)} checkpoints and {len(kept)} copies; measure runs that saved both")
        rows.append((rid, structured.size(rid), copies.size(rid)))
        print(f"| `{rid}` | {len(saved)} | {rows[-1][1]:,} | {rows[-1][2]:,} | {len(kept[-1]['conversation'])} |")
    n = len(rows)
    result = {"structured": round(sum(r[1] for r in rows) / n) if n else None,
              "with_conversation": round(sum(r[2] for r in rows) / n) if n else None, "runs": n}
    print(json.dumps(result))
    if a.write:
        report = json.loads(REPORT.read_text())
        report["checkpoint_bytes"] = result
        REPORT.write_text(dumps(report) + "\n")
        print("wrote checkpoint_bytes to reports/LAB_04.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
