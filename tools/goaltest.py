"""Check that the goals checklist pinpoints weaknesses per task type (deterministic, no Claude).

For every test in library/ and tests/, and every objective goal criterion, answer only that criterion's
questions wrong (everything else right) and assert that exactly that criterion fails. Also checks that
Listen & Repeat separates short-sentence from long-sentence weakness.

usage: python tools/goaltest.py
"""
from __future__ import annotations

import sys

from common import LIBRARY_DIR, TESTS_DIR, gaps, iter_tasks, load_json, load_spec
from score import goal_checks, objective_results


def responses_for(test: dict, routes: dict, wrong_skills: set[str]) -> dict:
    resp = {}
    for _, _, task in iter_tasks(test, routes):
        if task.get("questions") and "options" in task["questions"][0]:
            resp[task["id"]] = {"answers": {q["id"]: (q["answer"] + 1) % len(q["options"]) if q["skill"] in wrong_skills
                                            else q["answer"] for q in task["questions"]}}
        elif task["type"] == "complete_the_words":
            bad = "reading.vocabulary.form" in wrong_skills
            resp[task["id"]] = {"gaps": ["x" if bad else m for _, m in gaps(task["text"])]}
        elif task["type"] == "build_sentence":
            resp[task["id"]] = {"items": {it["id"]: it["chunks"] if it["skill"] in wrong_skills else it["answer"]
                                          for it in task["items"]}}
    return resp


def status_map(goals: list) -> dict:
    return {(g["task_type"], c["id"]): c["status"] for g in goals for c in g["criteria"]}


def main() -> int:
    spec_goals = load_spec()["goals"]
    tests = [p for base in (LIBRARY_DIR, TESTS_DIR) for p in sorted(base.glob("*/test.json"))]
    failures, checks = [], 0
    for path in tests:
        test = load_json(path)
        for route in ("m2_easy", "m2_hard"):
            routes = {"reading": route, "listening": route}
            present = {t["type"] for _, _, t in iter_tasks(test, routes)}
            # baseline: everything right -> every objective goal met
            base = status_map(goal_checks(test, routes, objective_results(test, responses_for(test, routes, set()), routes, {}), None))
            for key, st in base.items():
                if st not in ("met", "not_tested") and spec_goals.get(key[0], {}).get("criteria", {}).get(key[1], {}).get("skills"):
                    failures.append(f"{path.parent.name}/{route}: {key} is '{st}' with all answers right")
            # one weakness at a time
            for ttype in present:
                for cid, c in spec_goals[ttype]["criteria"].items():
                    if "skills" not in c:
                        continue
                    res = status_map(goal_checks(test, routes, objective_results(
                        test, responses_for(test, routes, set(c["skills"])), routes, {}), None))
                    if res.get((ttype, cid)) == "not_tested":
                        continue
                    checks += 1
                    if res.get((ttype, cid)) != "not_met":
                        failures.append(f"{path.parent.name}/{route}: weakness in {ttype}.{cid} reported as {res.get((ttype, cid))}")
                    # other goals of the same task type must not be blamed unless they share skills
                    for (t2, c2), st in res.items():
                        shared = set(spec_goals.get(t2, {}).get("criteria", {}).get(c2, {}).get("skills", [])) & set(c["skills"])
                        if t2 == ttype and c2 != cid and not shared and st == "not_met":
                            failures.append(f"{path.parent.name}/{route}: {ttype}.{cid} weakness wrongly blamed on {c2}")

        # Listen & Repeat: short sentences perfect, long ones half-dropped -> only long_sentences fails
        lr = [t for _, _, t in iter_tasks(test) if t["type"] == "listen_and_repeat"]
        for task in lr:
            tr = {}
            for i, it in enumerate(task["items"]):
                words = it["text"].split()
                tr[f"{task['id']}__{it['id']}"] = {"text": " ".join(words if i < len(task["items"]) - 3 else words[: (len(words) - 1) // 2])}
            res = status_map(goal_checks(test, {}, objective_results(test, {}, {}, tr), None))
            checks += 1
            if res.get(("listen_and_repeat", "long_sentences")) != "not_met":
                failures.append(f"{path.parent.name}: long-sentence weakness reported as {res.get(('listen_and_repeat', 'long_sentences'))}")

    for f in failures:
        print("FAIL", f)
    print(f"goal checklist: {checks} weakness checks across {len(tests)} tests, {len(failures)} failures")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
