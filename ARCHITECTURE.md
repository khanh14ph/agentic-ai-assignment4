# ARCHITECTURE.md · RepoMind on the seven layers

For each layer: what does this job, and where is it enforced. Cite code as a file
path and line number joined by a colon, inside backticks; a checker opens every
reference (`checks/FORMATS.md`, section 8). A layer held only by a sentence in a
prompt (any file under `prompts/`) is **EMPTY**, and so is a layer nothing does
yet. Status is one of: present, partial (say what is missing), or **EMPTY**. Each
assignment brings this file up to date.

What each layer is for (Lecture 1, slides 42 to 44):

- **Model**: reasoning, choosing tools, generating text.
- **Harness**: runs the loop, builds each prompt, trims old history.
- **Tools**: where the system acts on the world.
- **Memory & State**: what survives a step, a session, a restart.
- **Control & Policy**: what the system may do, and when it must ask.
- **Observability**: a step-by-step record of what it did.
- **Evaluation**: measuring quality, before and after release.

The table below is RepoMind as Assignment 4 leaves it.

| Layer | What does this job | Where it is enforced | Status |
|---|---|---|---|
| Model | The configured model, called only through the metered client | `harness/client.py:150` | present |
| Harness | The loop, with three bounds checked in code; a plan validated before it runs, every step's arguments included, and an executor that runs only the plan's steps; with compaction on, the history the fill calls see is summarized past a threshold, the issue pinned outside it and a maintainer's note kept outside it, in every call | `agent/loop.py:38`, `ways/planned.py:262`, `ways/planned.py:244`, `ways/planned.py:380`, `ways/planned.py:406`, `ways/planned.py:484`, `ways/planned.py:439` | present |
| Tools | Five namespaced tools behind one registry: every call checked at the boundary before it runs; every write keyed by the harness, checked before each attempt and read back after a timeout; every attempt in the call record | `tools/__init__.py:166`, `tools/__init__.py:249`, `tools/__init__.py:254`, `tools/__init__.py:271`, `tools/__init__.py:315` | present |
| Memory & State | A run's progress file, outside the model's context; the run's state saved in sync to a SQLite checkpointer, after each read a model call fills and immediately before each write; a killed run resumed from its last checkpoint, its finished steps skipped and a write replayed with its saved arguments; a memory store shared by every run, each record with its source, time, origin and whether it is confirmed, read before the plan and written at a run's end, a changed fact superseding the old one; a maintainer's rule a run is told, stored as stated, with who stated it and when | `ways/notes.py:67`, `ways/planned.py:488`, `ways/planned.py:588`, `ways/planned.py:613`, `state/checkpointer.py:72`, `ways/planned.py:194`, `ways/planned.py:511`, `ways/planned.py:607`, `state/store.py:98`, `state/store.py:113`, `ways/planned.py:211`, `ways/planned.py:621`, `ways/planned.py:666` | partial: eviction is a cap on the count, and a stale procedure is only labelled, never checked again |
| Control & Policy | A hook runs before every call and denies when it fails; a write that cannot be confirmed goes to a person; the second pass holds a draft that still fails; the store refuses an issue's text as a fact or as confirmed | `tools/__init__.py:221`, `ways/planned.py:345`, `state/store.py:147` | partial: the hook allows every call |
| Observability | One trace line per model call and per tool call, and the plan as data before it runs | `agent/loop.py:50`, `ways/planned.py:201` | partial: traces, no alerts |
| Evaluation | The grounded check reads the tracker, never the agent | `eval/check_triage.py:7` | partial: offline only |

**Empty layers: 0 of 7**, and five are partial.
