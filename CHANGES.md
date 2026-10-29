# CHANGES.md

Three lines per assignment: what it added, what it removed, what it constrained.
Removals are logged like additions.

## Assignment 1
- **Added:** a bounded tool loop; four ways to triage an issue (a direct call, a workflow, an agent, and a hybrid of the two); a grounded success check that reads the tracker; a results script
- **Removed:** nothing
- **Constrained:** every agent run to three bounds checked in code (steps, tokens, wall clock); success to what the tracker holds for the run's ID

## Assignment 2
- **Added:** a plan written as data before the issue is read; a validator with four checks; an executor that runs only the plan's steps; one checkpoint that may revise the plan; a second pass before the comment; detectors and a diff over traces; a progress file and a compaction
- **Removed:** the model's choice of the next tool, in the planned way
- **Constrained:** every tool call to a step of a validated plan; revisions to steps not yet done; the comment to drafts that pass the second pass

## Assignment 3
- **Added:** five rewritten tool definitions with examples, among them open_pr; a boundary check before every call; errors that name the fix; harness-derived idempotency keys, a check before every write attempt and a read-back after a timeout; the call record; a fail-closed hook
- **Removed:** free-text tool descriptions and free-form filters; protocol detail in anything the model sees
- **Constrained:** every write to be safe to retry, and to a person when its outcome cannot be read back; the comment to the last write, after the PR

## Assignment 4
- **Added:** a checkpointer (SQLite, sync saves after each read a model call fills and immediately before each write) and a resume that replays from a run's last checkpoint, sending a write's saved arguments; a memory store whose every record carries its source, time, origin and whether it is confirmed, with supersession and eviction; a write policy written before the store; the contradiction test, the conversation-copy measurement, and Part F's placements of a fact and a compaction that pins the issue and keeps a note outside the history
- **Removed:** state that lived only in the process (a killed run's plan, step results and drafted writes now survive it); a twice-escaped `args_json` read as no arguments, and plans whose arguments do not parse
- **Constrained:** every write to sit behind a sync checkpoint for its own plan step, and a replayed write to the arguments that checkpoint saved; an issue's text to an unconfirmed episodic record, never a fact; a changed rule to supersede the old one, never sit beside it
