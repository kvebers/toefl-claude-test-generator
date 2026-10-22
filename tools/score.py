"""Turn objective results + Claude's grading into section bands, CEFR and an estimated 0–120 score.

All conversions are ESTIMATES driven by spec/toefl-2026.yaml -> scoring. Edit the spec, not this file.
"""
from __future__ import annotations

from collections import Counter, defaultdict

from common import iter_tasks, load_spec, repeat_accuracy, score_task


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
                said = transcripts.get(key, {}).get("text")
                repeats.append({"task_id": task["id"], "item_id": it["id"], "key": key, "target": it["text"],
                                "said": said, "accuracy": None if said is None else round(repeat_accuracy(it["text"], said), 3)})
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
                acc = [r["accuracy"] for r in objective["repeats"] if r["task_id"] == task["id"] and r["accuracy"] is not None]
                if acc:
                    parts.setdefault(t, []).append(5 * sum(acc) / len(task["items"]))
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
