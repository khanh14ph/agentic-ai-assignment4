"""Assignment 4, Part D: the store's rules, and plans whose arguments the planner escaped
once too often. They spend no tokens."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from agent.diff import step_args
from state.store import Store
from ways.planned import schema_check


class Events:
    def __init__(self):
        self.lines = []

    def event(self, kind, **fields):
        self.lines.append((kind, fields))


class Ctx:
    def __init__(self):
        self.trace = Events()


def plan(**args_json) -> dict:
    tools = {1: "issues_read", 2: "code_search", 3: "code_read_file", 4: "pulls_open", 5: "issues_comment"}
    return {"steps": [{"id": i, "tool": t, "action": t, "depends_on": [], "expected_result": "", "status": "pending",
                       "args_json": args_json.get(f"s{i}", "{}")} for i, t in tools.items()]}


class StepArgsTests(unittest.TestCase):
    def test_escaped_once_too_often_reads_as_the_object_it_means(self):
        self.assertEqual(step_args({"args_json": '{\\"issue\\": \\"issue-4207\\"}'}), {"issue": "issue-4207"})

    def test_plain_json_and_args_are_unchanged(self):
        self.assertEqual(step_args({"args_json": '{"issue": "issue-1"}'}), {"issue": "issue-1"})
        self.assertEqual(step_args({"args": {"a": 1}}), {"a": 1})
        self.assertEqual(step_args({"args_json": "not json"}), {})

    def test_a_plan_with_arguments_that_read_as_none_is_rejected(self):
        ctx = Ctx()
        broken = schema_check(ctx, plan(s2='{\\"path_glob\\": null,'), 1)
        self.assertTrue(any("args_json is not a JSON object" in f["error"] for f in broken))
        self.assertFalse([f for f in schema_check(Ctx(), plan(s1='{\\"issue\\": \\"issue-4207\\"}'), 1)
                          if "args_json" in f["error"]])


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.dir.name) / "store.db")

    def tearDown(self):
        self.dir.cleanup()

    def record(self, **fields) -> dict:
        return {"repository": "ledgerline", "issue": None, "kind": "procedural", "subject": "rule", "text": "a rule",
                "source": "user", "origin": "ingested", "confirmed": True, "stated_by": "a maintainer", **fields}

    def test_issue_text_is_never_a_fact_nor_confirmed(self):
        for wrong in ({"kind": "semantic"}, {"confirmed": True}, {"origin": "derived"}):
            with self.assertRaises(ValueError):
                self.store.write(self.record(**{"source": "issue:4188", "issue": 4188, "kind": "episodic",
                                                "confirmed": False, **wrong}))
        rid = self.store.write(self.record(source="issue:4188", issue=4188, kind="episodic", confirmed=False))
        self.assertEqual(self.store.records()[0]["id"], rid)

    def test_supersede_keeps_one_active_and_the_old_one_inactive(self):
        old = self.store.write(self.record())
        with self.assertRaises(ValueError):
            self.store.write(self.record(text="a second rule on the same subject"))
        new = self.store.supersede(old, self.record(text="the rule, changed"))
        by_id = {r["id"]: r for r in self.store.records()}
        self.assertEqual((by_id[old]["active"], by_id[new]["active"], by_id[new]["supersedes"]), (False, True, old))
        self.assertEqual([r["id"] for r in self.store.active("ledgerline")], [new])

    def test_active_for_an_issue_includes_the_repository_wide_records(self):
        wide = self.store.write(self.record())
        mine = self.store.write(self.record(issue=4207, subject="decision", kind="episodic", source="memory",
                                            origin="derived", confirmed=False, stated_by=None))
        other = self.store.write(self.record(issue=4188, subject="decision", kind="episodic", source="memory",
                                             origin="derived", confirmed=False, stated_by=None))
        self.assertEqual([r["id"] for r in self.store.active("ledgerline", 4207)], [wide, mine])
        self.assertIn(other, [r["id"] for r in self.store.active("ledgerline")])
        self.assertIsInstance(json.dumps(self.store.records()), str)


if __name__ == "__main__":
    unittest.main()
