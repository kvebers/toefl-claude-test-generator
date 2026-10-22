"""Turn objective results + Claude's grading into section bands, CEFR and an estimated 0–120 score.

All conversions are ESTIMATES driven by spec/toefl-2026.yaml -> scoring. Edit the spec, not this file.
"""
from __future__ import annotations

from collections import Counter, defaultdict

from common import iter_tasks, load_spec, norm_words, repeat_accuracy, repeat_points, score_task


def half(x: float) -> float:
    return max(1.0, min(6.0, round(x * 2) / 2))


def objective_results(test: dict, responses: dict, routes: dict, transcripts: dict) -> dict:
    items = []
    repeats = []
    for sid, mkey, task in iter_tasks(test, routes):
        items += score_task(sid, mkey, task, responses.get(task["id"]))
        if task["type"] == "listen_and_repeat":
            for it in task["items"]:
                key = f"{task['id']}__{it['id']}"
                tr = transcripts.get(key, {})
                said = tr.get("text")
                acc = None if said is None else round(repeat_accuracy(it["text"], said, set(tr.get("low_confidence_words", []))), 3)
                repeats.append({"task_id": task["id"], "item_id": it["id"], "key": key, "target": it["text"],
                                "said": said, "accuracy": acc, "points": repeat_points(acc, len(norm_words(it["text"]))),
                                "clarity": tr.get("mean_word_prob"), "unclear": tr.get("low_confidence_words", [])})
    return {"items": items, "repeats": repeats}


def compute(test: dict, attempt: dict, objective: dict, grading: dict | None) -> dict:
    spec = load_spec()["scoring"]
    routes = attempt.get("routes", {})
    grading_tasks = (grading or {}).get("tasks", {})
    by_section = defaultdict(list)
    for it in objective["items"]:
        by_section[it["section"]].append(it)

    sections, notes = {}, []
    for sec in test["sections"]:
        sid = sec["id"]
        if sid in ("reading", "listening"):
            its = by_section[sid]
            p = sum(i["correct"] for i in its) / len(its) if its else 0
            route = routes.get(sid)
            lo, hi = spec["adaptive_band_range"].get(route, [1.0, 6.0])
            sections[sid] = {"band": half(lo + (hi - lo) * p), "raw": f"{sum(i['correct'] for i in its)}/{len(its)}",
                             "accuracy": round(p, 3), "route": route}
            continue

        weights = spec["weights"][sid]
        parts, partial = {}, False
        for _, _, task in iter_tasks({"sections": [sec]}):
            t = task["type"]
            if t == "build_sentence":
                its = [i for i in by_section[sid] if i["task_id"] == task["id"]]
                parts.setdefault(t, []).append(5 * sum(i["correct"] for i in its) / max(1, len(its)))
            elif t == "listen_and_repeat":
                reps = [r for r in objective["repeats"] if r["task_id"] == task["id"]]
                if any(r["accuracy"] is not None for r in reps):   # missing recordings count as 0 points
                    parts.setdefault(t, []).append(sum(r.get("points", 0) for r in reps) / len(task["items"]))
                else:
                    partial = True
            elif task["id"] in grading_tasks:
                parts.setdefault(t, []).append(float(grading_tasks[task["id"]]["score"]))
            else:
                partial = True
        if not parts:
            sections[sid] = {"band": None, "partial": True}
            notes.append(f"{sid}: not scored (missing transcription or Claude grading)")
            continue
        w = {t: weights.get(t, 1) for t in parts}
        avg5 = sum(w[t] * sum(v) / len(v) for t, v in parts.items()) / sum(w.values())
        sections[sid] = {"band": half(1 + avg5), "task_scores_0_5": {t: round(sum(v) / len(v), 2) for t, v in parts.items()},
                         "weights": {t: round(w[t] / sum(w.values()), 3) for t in parts},
                         "partial": partial}
        if partial:
            notes.append(f"{sid}: some tasks could not be graded; band based on the rest")

    table = {float(k): v for k, v in spec["band_to_30"].items()}
    cefr = {float(k): v for k, v in spec["cefr"].items()}
    for s in sections.values():
        if s.get("band") is not None:
            s["est_30"] = table[s["band"]]
            s["cefr"] = cefr[s["band"]]
    bands = [s["band"] for s in sections.values() if s.get("band") is not None]
    complete = test["mode"] == "full" and len(bands) == 4
    overall = half(sum(bands) / len(bands)) if bands else None
    summary = {
        "overall_band": overall if complete else None,
        "overall_cefr": cefr[overall] if complete else None,
        "est_total_120": sum(s["est_30"] for s in sections.values() if "est_30" in s) if complete else None,
        "sections": {k: {"band": v.get("band"), "est_30": v.get("est_30")} for k, v in sections.items()},
        "estimate_note": "Estimated from a practice test with approximate conversions; real scores can differ by ±0.5 band.",
    }
    return {"summary": summary, "sections": sections, "notes": notes}


def error_profile(objective: dict, grading: dict | None) -> dict:
    """Counts per taxonomy tag across objective misses and Claude-reported errors (used for trends)."""
    tags = Counter()
    skills = defaultdict(lambda: [0, 0])
    for it in objective["items"]:
        skills[it["skill"]][1] += 1
        if it["correct"]:
            skills[it["skill"]][0] += 1
        else:
            tags[it["skill"]] += 1
    for r in objective["repeats"]:
        if r["accuracy"] is not None and r["accuracy"] < 0.9:
            tags["speaking.repeat_accuracy"] += 1
    for g in (grading or {}).get("tasks", {}).values():
        for e in g.get("errors", []):
            tags[e["tag"]] += 1
        for q in g.get("questions", {}).values():
            for e in q.get("errors", []):
                tags[e["tag"]] += 1
    return {"error_tags": dict(tags.most_common()), "skills": {k: v for k, v in sorted(skills.items())}}


def _status(share: float, th: dict) -> str:
    return "met" if share >= th["met"] else "partly" if share >= th["partly"] else "not_met"


def _combine(statuses: list[str]) -> str:
    if all(s == "met" for s in statuses):
        return "met"
    if all(s == "not_met" for s in statuses):
        return "not_met"
    return "partly"


def goal_checks(test: dict, routes: dict, objective: dict, grading: dict | None) -> list[dict]:
    """Check every task type in the attempt against the goals in spec/toefl-2026.yaml.

    Objective criteria are computed from item accuracy; writing/speaking criteria come from Claude's
    per-criterion ratings in grading.json. Returns one entry per task type, in test order.
    """
    spec = load_spec()
    goals, th = spec["goals"], spec["goal_thresholds"]
    graded = (grading or {}).get("tasks", {})
    by_type: dict[str, dict] = {}
    for sid, _, task in iter_tasks(test, routes):
        by_type.setdefault(task["type"], {"section": sid, "task_ids": []})["task_ids"].append(task["id"])

    out = []
    for ttype, info in by_type.items():
        goal = goals.get(ttype)
        if not goal:
            continue
        items = [i for i in objective["items"] if i["task_type"] == ttype]
        criteria = []
        for cid, c in goal["criteria"].items():
            row = {"id": cid, "text": c["text"], "tip": c.get("tip", ""), "example": c.get("example", "")}
            if "skills" in c:
                its = [i for i in items if i["skill"] in c["skills"]]
                if its:
                    ok = sum(i["correct"] for i in its)
                    few = " (few questions, weak evidence)" if len(its) < 3 else ""
                    row.update(status=_status(ok / len(its), th), evidence=f"{ok}/{len(its)} correct{few}", source="objective")
                else:
                    row.update(status="not_tested", evidence="no questions of this kind in this attempt", source="objective")
            elif c.get("repeat") == "intelligibility":
                reps = [r for r in objective["repeats"] if r["task_id"] in info["task_ids"] and r.get("clarity") is not None]
                if reps:
                    share = sum(r["clarity"] for r in reps) / len(reps)
                    unclear = sorted({w for r in reps for w in r.get("unclear", [])})[:8]
                    row.update(status=_status(share, th), source="objective",
                               evidence=f"speech recogniser confidence {round(100 * share)}%"
                                        + (f"; unclear words: {', '.join(unclear)}" if unclear else ""))
                else:
                    row.update(status="not_tested", evidence="recordings not transcribed", source="objective")
            elif "repeat" in c:
                reps = [r for r in objective["repeats"] if r["task_id"] in info["task_ids"]]
                if c["repeat"] == "long":
                    reps = [r for t in info["task_ids"] for r in [x for x in reps if x["task_id"] == t][-3:]]
                accs = [r["accuracy"] for r in reps if r["accuracy"] is not None]
                if accs:
                    share = sum(accs) / len(reps)
                    row.update(status=_status(share, th), evidence=f"{round(100 * share)}% of words repeated correctly", source="objective")
                else:
                    row.update(status="not_tested", evidence="recordings not transcribed", source="objective")
            else:
                rated = [r for t in info["task_ids"] for r in graded.get(t, {}).get("criteria", []) if r["id"] == cid]
                if rated:
                    row.update(status=_combine([r["status"] for r in rated]),
                               evidence=" / ".join(r["evidence"] for r in rated), source="claude")
                    # Claude's personalised advice (built from the learner's own words) replaces the generic tip
                    if any(r.get("improve") for r in rated):
                        row["tip"] = " ".join(r["improve"] for r in rated if r.get("improve"))
                    if any(r.get("example") for r in rated):
                        row["example"] = " / ".join(r["example"] for r in rated if r.get("example"))
                else:
                    row.update(status="not_tested", evidence="not graded by Claude", source="claude")
            criteria.append(row)
        covered = {sk for c in goal["criteria"].values() for sk in c.get("skills", [])}
        if any("skills" in c for c in goal["criteria"].values()):     # safety net: no mistake goes unseen
            other = [i for i in items if i["skill"] not in covered]
            if other:
                ok = sum(i["correct"] for i in other)
                criteria.append({"id": "other_questions", "text": "Other question types: " + ", ".join(sorted({i["skill"] for i in other})),
                                 "status": _status(ok / len(other), th), "evidence": f"{ok}/{len(other)} correct", "source": "objective",
                                 "tip": "Review the explanation for each missed question below.", "example": ""})
        out.append({"task_type": ttype, "section": info["section"], "measures": goal["measures"], "criteria": criteria})
    return out
