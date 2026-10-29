# RepoMind's write policy

What enters the memory store (`state/store.py`), written before the store
(Lecture 4, slide 23). It covers four decisions (when, what, how, with) and then
the reading and eviction rules. The store is shared by every run and keyed by
repository and issue. It is not the checkpointer: a checkpoint is one run's exact
state, and it dies with that run's usefulness. A memory spans runs, may be
approximate, and grows, so every memory has to say where it came from and when.

## When

- **At the end of a run, once its comment is in the tracker.** The registry
  confirmed the write, so the run's decision is final for that run. An escalated
  run writes nothing: it decided nothing a later run should lean on.
- **Never mid-run.** A search result, a draft, or a file the model is weighing
  can each be overturned by the next step (a revision, the second pass). A
  crashed run's unfinished state belongs to its checkpoint, not to the store.
- **A person's statement:** once it is seen, written down as stated.
- **A procedure:** once it has been run and has worked (verified), never when it
  was only guessed.

## What

- **What was expensive to derive:** a run's triage decision, its label and file.
  It costs five tool calls and about 12,000 tokens, and a reopened issue asks the
  same question again. The same goes for a procedure worked out in a run.
- **What was stated rather than inferred:** a maintainer's rule, kept word for
  word, with who stated it and when.
- **What was confirmed, and what was not,** in the `confirmed` field (see With).
- **Never stored:**
  - the conversation;
  - tool outputs, search results or file contents: the repository is the truth
    for those, and reading them again is cheap;
  - anything from mid-run;
  - an instruction found in an issue's text.
- **Issue text, which anyone can write:**
  - stored, if at all, only as an episodic record of what the issue said:
    `source: issue:<n>`, `origin: ingested`, `confirmed: false`;
  - never semantic or procedural, so never as what is true here or how to act
    here. Stored as a fact, it would come back later with the authority of
    RepoMind's own knowledge (slide 24, memory poisoning);
  - the store refuses to save it any other way.

## How

- **Insert** when nothing on the same subject is active for that issue (or for
  the repository, for a repository-wide memory).
- **Supersede, never edit or delete on contradiction** (slide 25). A new record
  names the old one in `supersedes`, and the old one is marked inactive, in one
  transaction. Only one record per subject is active.
  - **A run's triage decision** supersedes the issue's previous decision, whether
    it agrees or not, and its text says which. This is the consolidation: one
    active decision per issue, and the history stays as inactive records.
  - **A rule a person changes** is superseded by the new statement, which carries
    its own `written_at` and `stated_by`.
- **Repeats:** storing the same candidate twice does nothing. The script that
  stores them first checks for a record with the same subject and text.

## With: provenance (slides 21 and 27)

Every record carries the following fields.

| Field | What it holds |
|---|---|
| `source` | `user` (a person with standing, such as a maintainer), `issue:<n>` (an issue's text, which anyone can write), `repo` (the repository's own files) or `memory` (RepoMind's own earlier work) |
| `written_at` | ISO 8601, UTC. For something seen earlier, such as the three candidates, it is when it was seen: the candidate's `when`, so its age is the age of the fact. For a run's decision, it is when the run stored it, at its end |
| `origin` | `derived` when RepoMind worked it out (a run's decision, a procedure); `ingested` when it was read from outside (a person's statement, an issue's text) |
| `confirmed` | See the list below |
| `stated_by` | For something a person stated: who, and their standing |
| `seen_in` | Where it was seen: a run_id, an issue body, a comment |
| `subject` | What it is about, so a later record on the same subject supersedes it |

When `confirmed` is true, and when it is false:
- **True when a person with standing stated it.** Their standing is what confirms
  it, so a maintainer's rule is confirmed when it is stored.
- **True when RepoMind verified it by doing it,** as with a procedure that was run
  and worked.
- **False for anything an issue's text says.**
- **False for a run's triage decision.** The tracker confirms that the comment was
  posted, not that its label and file are right; only a maintainer accepting it
  would.

Kinds (slide 18):
- **episodic, what happened:** a run's triage decision; what an issue's body
  claimed.
- **semantic, what is true here:** only for something confirmed by a person with
  standing or by the repository's own files. None of the three candidates is
  semantic.
- **procedural, how to do something here:** a reproduction procedure; a
  maintainer's rule for handling duplicates.

## Reading

- **Before the run plans, and so before its first search,** the run reads the
  active records for its repository and its issue, plus the repository-wide ones
  (`issue: null`). It logs the read as `store_read` with the IDs returned.
- **The planner sees no memory at all.** In particular, a record whose source is
  `issue:<n>` never reaches it, as Assignment 2 kept the issue body out.
- **The calls that fill in the plan's steps see every record returned,** each
  with its id, kind, source, whether it is confirmed, and its age. A record from
  an issue's text is marked as text anyone can write: a record of a claim, never
  an instruction.
- **Each kind of record is read in its own way:**
  - **A rule a maintainer stated** (source `user`, confirmed) is followed as
    stated: it is the maintainers' own instruction.
  - **RepoMind's own earlier work** is a hint about where to look, not evidence:
    the comment names what this run's own steps returned.
  - **An issue's text** is never an instruction.
- **A run that is told a maintainer's rule stores it,** as stated, with who stated
  it and when.

## Eviction (slides 25 and 27)

**Size: 1,000 records per repository.**

**The rule:**
1. **Consolidation first:** one active triage decision per issue (see How).
2. **At the cap, delete the oldest episodic records,** the inactive ones before
   the active ones.
3. **Semantic and procedural records, and anything a person stated, are never
   deleted by the cap.** They are few, and they change by supersession.
4. **Staleness:** a procedural record shows its age to the model. Past 90 days
   unverified, it is shown as "check it still holds". The repository can change
   while the procedure does not.

**How long an entry lives:**
- **Write rate:** a completed run writes one record, its decision, and an
  escalated run writes none (measured on Part D's runs; see `reports/LAB_04.md`).
  Assuming 10 runs a day, that is about 10 records a day.
- **Lifetime:** an episodic record then lives about 100 days before the cap
  reaches it. That is long enough for a reopened issue such as 4207, which was
  closed on 19 August and reopened on 12 October, 54 days later. A store of 500
  records would already have lost that August decision.
