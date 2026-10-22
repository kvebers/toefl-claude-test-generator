"""Blind-solver quality gate for generated items.

usage:
  python tools/blind.py export <test_id>              # -> tests/<id>/blind.json (no answer keys)
  python tools/blind.py check <test_id> <answers.json>

answers.json format (written by the solver subagent):
  { "<task_id>": { "<question_id>": <option index>, ... }, "<build_task_id>": { "<item_id>": ["chunk", ...] },
    "<ctw_task_id>": { "gaps": ["letters", ...] } }
`check` prints every item where the solver disagrees with the key; those items are ambiguous or wrong
and must be fixed or replaced, then re-checked.
"""
from __future__ import annotations

import sys

from common import find_test_dir, iter_tasks, load_json, sanitize, save_json, score_task


def main() -> int:
    cmd, test_id = sys.argv[1], sys.argv[2]
    d = find_test_dir(test_id)
    test = load_json(d / "test.json")
    if cmd == "export":
        save_json(d / "blind.json", sanitize(test))
        print(f"Wrote {d / 'blind.json'}")
        return 0
    answers = load_json(sys.argv[3])
    bad = 0
    for sid, mkey, task in iter_tasks(test):
        a = answers.get(task["id"], {})
        resp = {"answers": a, "items": a, "gaps": a.get("gaps", []) if isinstance(a, dict) else []}
        for r in score_task(sid, mkey, task, resp):
            if not r["correct"]:
                bad += 1
                print(f"DISAGREE {sid}/{mkey}/{task['id']}/{r['item_id']}: key='{r['expected']}' solver='{r['given']}'  ({r['prompt'][:70]})")
    total = sum(len(score_task(s, m, t, {})) for s, m, t in iter_tasks(test))
    print(f"{total - bad}/{total} items agree with the key")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
