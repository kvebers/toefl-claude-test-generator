"""Validate a test against the JSON schema plus semantic rules the schema cannot express.

usage: python tools/validate.py <test_id | path/to/test.json> [...]
exit code 1 on errors; warnings are printed but do not fail.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import jsonschema

from common import SCHEMA_PATH, find_test_dir, gaps, iter_tasks, load_json, load_spec


def validate(test: dict) -> tuple[list[str], list[str]]:
    errors, warnings = [], []
    schema = load_json(SCHEMA_PATH)
    for e in sorted(jsonschema.Draft202012Validator(schema).iter_errors(test), key=lambda e: list(e.path)):
        errors.append(f"schema: /{'/'.join(map(str, e.path))}: {e.message[:200]}")
    if errors:
        return errors, warnings

    spec = load_spec()
    voices = set(spec["voices"])
    task_ids, answer_positions = Counter(), Counter()

    sec_ids = [s["id"] for s in test["sections"]]
    if test["mode"] == "full" and sec_ids != spec["order"]:
        errors.append(f"full test must contain sections {spec['order']} in order, got {sec_ids}")
    for sec in test["sections"]:
        adaptive = spec["sections"][sec["id"]]["adaptive"]
        if test["mode"] == "full" and adaptive and "m2_easy" not in sec["modules"]:
            errors.append(f"{sec['id']}: adaptive section needs m1 + m2_easy + m2_hard")

    for sid, mkey, task in iter_tasks(test):
        where = f"{sid}/{mkey}/{task['id']}"
        task_ids[task["id"]] += 1
        allowed = spec["sections"][sid]["tasks"]
        if task["type"] not in allowed:
            errors.append(f"{where}: task type {task['type']} does not belong in {sid}")
        goal = spec.get("goals", {}).get(task["type"])
        if goal is None:
            errors.append(f"{where}: no goals defined for task type {task['type']} in the spec")
        else:
            covered = {sk for c in goal["criteria"].values() for sk in c.get("skills", [])}
            for q in task.get("questions", []) + (task.get("items", []) if task["type"] == "build_sentence" else []):
                if covered and q.get("skill") and q["skill"] not in covered:
                    warnings.append(f"{where}/{q['id']}: skill {q['skill']} is not part of any {task['type']} goal "
                                    f"(use one of: {', '.join(sorted(covered))})")
        q_ids = Counter()
        for q in task.get("questions", []):
            if "answer" in q:
                q_ids[q["id"]] += 1
                if q["answer"] >= len(q["options"]):
                    errors.append(f"{where}/{q['id']}: answer index {q['answer']} out of range")
                if len(set(q["options"])) != len(q["options"]):
                    errors.append(f"{where}/{q['id']}: duplicate options")
                answer_positions[q["answer"]] += 1
        errors += [f"{where}: duplicate question id {k}" for k, v in q_ids.items() if v > 1]
        for line in task.get("audio", []):
            if line["voice"] not in voices:
                errors.append(f"{where}: unknown voice '{line['voice']}' (spec voices: {sorted(voices)})")
        for it in task.get("items", []):
            if it.get("voice") and it["voice"] not in voices:
                errors.append(f"{where}/{it['id']}: unknown voice '{it['voice']}'")
            if task["type"] == "build_sentence":
                if sorted(it["chunks"]) != sorted(it["answer"]):
                    errors.append(f"{where}/{it['id']}: answer must be a permutation of chunks")
                elif it["chunks"] == it["answer"]:
                    errors.append(f"{where}/{it['id']}: chunks are already in answer order, shuffle them")
        if task["type"] == "listen_and_repeat":
            lo, hi = spec["sections"]["speaking"]["tasks"]["listen_and_repeat"]["response_sec"]
            for it in task["items"]:
                if "response_sec" in it and not lo <= it["response_sec"] <= hi:
                    warnings.append(f"{where}/{it['id']}: response_sec {it['response_sec']}, spec says {lo} to {hi}")
        if task["type"] == "interview" and task.get("voice") and task["voice"] not in voices:
            errors.append(f"{where}: unknown voice '{task['voice']}'")
        if task["type"] == "complete_the_words":
            n = len(gaps(task["text"]))
            if n < 5:
                warnings.append(f"{where}: only {n} gaps")

    errors += [f"task id '{k}' used {v} times (must be unique across the test)" for k, v in task_ids.items() if v > 1]
    if test["mode"] == "full" and "sample" not in test.get("tags", []):
        for sec in test["sections"]:
            for mkey, module in sec["modules"].items():
                got = Counter(t["type"] for t in module["tasks"])
                for ttype, cfg in spec["sections"][sec["id"]]["tasks"].items():
                    want = cfg.get(mkey, cfg.get(mkey[:2], cfg.get("count")))
                    if ttype in ("build_sentence", "listen_and_repeat", "interview"):   # counted in items/questions
                        n = sum(len(t.get("items") or t.get("questions")) for t in module["tasks"] if t["type"] == ttype)
                        if want and n != want:
                            warnings.append(f"{sec['id']}/{mkey}: {n} {ttype} items, ETS spec says {want}")
                    elif want is not None and got[ttype] != want:
                        warnings.append(f"{sec['id']}/{mkey}: {got[ttype]} x {ttype}, spec says {want}")
    if "—" in json.dumps(test, ensure_ascii=False):
        errors.append("test text contains em dashes (—); use a comma, colon or full stop instead")
    total = sum(answer_positions.values())
    if total >= 8 and max(answer_positions.values()) / total > 0.45:
        warnings.append(f"answer positions are unbalanced: {dict(answer_positions)}")
    return errors, warnings


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    rc = 0
    for arg in argv:
        path = Path(arg) if arg.endswith(".json") else find_test_dir(arg) / "test.json"
        errors, warnings = validate(load_json(path))
        for w in warnings:
            print(f"WARN  {path}: {w}")
        for e in errors:
            print(f"ERROR {path}: {e}")
        if errors:
            rc = 1
        else:
            print(f"OK    {path}")
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
