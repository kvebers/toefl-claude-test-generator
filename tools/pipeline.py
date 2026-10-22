"""Grade an attempt end to end: transcribe -> objective scoring -> Claude grading -> bands -> PDF report.

usage:
  python tools/pipeline.py grade <attempt_id|latest> [--no-claude] [--no-transcribe] [--force]
  python tools/pipeline.py report <attempt_id|latest>        # re-render report only

Claude is called headless through the Claude Code CLI (`claude -p "/toefl-grade ..."`), so it uses
your Claude subscription / login. Set CLAUDE_BIN to override the executable.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path

import jsonschema

from common import RESULTS_DIR, ROOT, iter_tasks, load_json, load_spec, save_json, usage_limit_message
from score import compute, error_profile, goal_checks, objective_results

GRADING_SCHEMA = ROOT / "schemas" / "grading.schema.json"
CRITERION_POINTS = {"met": 4.5, "partly": 3.0, "not_met": 1.5}   # rough 0-5 score a criterion status implies


def status(d: Path, stage: str, **extra):
    save_json(d / "status.json", {"stage": stage, "updated": datetime.now().isoformat(timespec="seconds"), **extra})
    print(f"[{stage}]", flush=True)


def resolve(aid: str) -> Path:
    if aid == "latest":
        dirs = sorted(p.parent for p in RESULTS_DIR.glob("*/attempt.json"))
        if not dirs:
            sys.exit("no attempts in results/")
        return dirs[-1]
    d = RESULTS_DIR / aid
    if not (d / "attempt.json").exists():
        sys.exit(f"no attempt {aid}")
    return d


def grading_input(d: Path, test: dict, attempt: dict, responses: dict, transcripts: dict, objective: dict) -> dict:
    routes = attempt.get("routes", {})
    goals = load_spec()["goals"]
    crit = lambda t: [{"id": k, "text": v["text"]} for k, v in goals[t]["criteria"].items() if "skills" not in v and "repeat" not in v]
    writing, speaking = [], []
    secs = responses.get("meta", {}).get("task_seconds", {})
    for sid, _, task in iter_tasks(test, routes):
        resp = responses.get("tasks", {}).get(task["id"], {})
        if task["type"] in ("email", "academic_discussion"):
            prompt = {k: task[k] for k in ("scenario", "to", "subject", "bullets", "course", "professor", "students") if k in task}
            text = resp.get("text", "")
            writing.append({"task_id": task["id"], "type": task["type"], "measures": goals[task["type"]]["measures"],
                            "criteria_to_rate": crit(task["type"]), "prompt": prompt, "response": text,
                            "word_count": len(text.split()), "seconds_used": secs.get(task["id"]),
                            "time_limit_sec": task.get("time_sec")})
        elif task["type"] == "interview":
            speaking.append({"task_id": task["id"], "type": "interview", "measures": goals["interview"]["measures"],
                             "criteria_to_rate": crit("interview"), "topic": task["topic"], "answer_sec": task["answer_sec"],
                             "questions": [{"id": q["id"], "text": q["text"],
                                            "transcript": transcripts.get(f"{task['id']}__{q['id']}", {"error": "no recording"})}
                                           for q in task["questions"]]})
        elif task["type"] == "listen_and_repeat":
            speaking.append({"task_id": task["id"], "type": "listen_and_repeat", "scored_objectively": True,
                             "items": [r for r in objective["repeats"] if r["task_id"] == task["id"]]})
    misses = [{k: i[k] for k in ("section", "task_type", "item_id", "prompt", "given", "expected", "skill")}
              for i in objective["items"] if not i["correct"]]
    by_sec = {}
    for i in objective["items"]:
        c, n = by_sec.get(i["section"], (0, 0))
        by_sec[i["section"]] = (c + i["correct"], n + 1)
    index = RESULTS_DIR / "index.jsonl"
    history = [json.loads(l) for l in index.read_text(encoding="utf-8").splitlines() if l.strip()][-5:] if index.exists() else []
    return {
        "attempt_id": d.name, "test_id": attempt["test_id"], "mode": test["mode"],
        "writing": writing, "speaking": speaking,
        "objective_summary": {k: f"{c}/{n}" for k, (c, n) in by_sec.items()},
        "objective_misses": misses,
        "objective_goals": [{**g, "criteria": [c for c in g["criteria"] if c["source"] == "objective"]}
                            for g in goal_checks(test, routes, objective, None)
                            if any(c["source"] == "objective" for c in g["criteria"])],
        "history": [h for h in history if h.get("attempt_id") != d.name],
        "output_file": str(d / "grading.json"),
        "schema_file": "schemas/grading.schema.json",
    }


def run_claude(d: Path) -> None:
    claude = os.environ.get("CLAUDE_BIN") or shutil.which("claude")
    if not claude:
        raise RuntimeError("Claude Code CLI not found (install it or set CLAUDE_BIN), or re-run with --no-claude")
    inside = d.resolve().is_relative_to(ROOT)
    folder = d.resolve().relative_to(ROOT).as_posix() if inside else str(d.resolve())
    cmd = [claude, "-p", f"/toefl-grade {folder}", "--permission-mode", "acceptEdits",
           *([] if inside else ["--add-dir", str(d.resolve())]),
           "--allowedTools", "Read", "Write", "Edit", "Glob", "Grep", "Bash(python tools/check_grading.py:*)"]
    if os.environ.get("CLAUDE_MODEL"):
        cmd += ["--model", os.environ["CLAUDE_MODEL"]]
    with open(d / "claude.log", "w", encoding="utf-8") as log:
        subprocess.run(cmd, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, timeout=1800, check=False)
    if limit := usage_limit_message((d / "claude.log").read_text(encoding="utf-8", errors="replace")):
        raise RuntimeError(f"Claude usage limit reached ({limit}). Your answers are saved; "
                           f"run `make grade ID={d.name}` after the reset.")


def check_grading(d: Path, gin: dict) -> list[str]:
    path = d / "grading.json"
    if not path.exists():
        return ["grading.json was not written"]
    try:
        g = load_json(path)
    except json.JSONDecodeError as e:
        return [f"invalid JSON: {e}"]
    errs = [f"/{'/'.join(map(str, e.path))}: {e.message[:160]}"
            for e in jsonschema.Draft202012Validator(load_json(GRADING_SCHEMA)).iter_errors(g)]
    needed = [w["task_id"] for w in gin["writing"]] + [s["task_id"] for s in gin["speaking"] if s["type"] == "interview"]
    errs += [f"missing grade for task {t}" for t in needed if t not in g.get("tasks", {})]
    for item in gin["writing"] + [x for x in gin["speaking"] if x["type"] == "interview"]:
        rated = {c.get("id") for c in g.get("tasks", {}).get(item["task_id"], {}).get("criteria", [])}
        missing = [c["id"] for c in item.get("criteria_to_rate", []) if c["id"] not in rated]
        if missing:
            errs.append(f"task {item['task_id']}: criteria not rated: {', '.join(missing)}")
        crit = g.get("tasks", {}).get(item["task_id"], {}).get("criteria", [])
        for c in crit:
            if c.get("status") in ("partly", "not_met") and not (c.get("improve") and c.get("example")):
                errs.append(f"task {item['task_id']}: criterion {c.get('id')} is {c.get('status')} but has no improve/example")
        if crit and not missing:
            implied = sum(CRITERION_POINTS.get(c.get("status"), 0) for c in crit) / len(crit)
            given = g["tasks"][item["task_id"]].get("score", 0)
            if abs(given - implied) > 1.0:
                errs.append(f"task {item['task_id']}: score {given} contradicts its criteria (they imply about "
                            f"{implied:.1f}); re-check the criteria or the score")
    return errs


def update_index(d: Path, test: dict, attempt: dict, score: dict, profile: dict, goals: list) -> None:
    index = RESULTS_DIR / "index.jsonl"
    rows = [json.loads(l) for l in index.read_text(encoding="utf-8").splitlines() if l.strip()] if index.exists() else []
    rows = [r for r in rows if r["attempt_id"] != d.name]
    rows.append({"attempt_id": d.name, "test_id": attempt["test_id"], "mode": test["mode"],
                 "date": attempt.get("started", "")[:10], "home_edition": attempt.get("home_edition", False),
                 "overall_band": score["summary"]["overall_band"], "est_total_120": score["summary"]["est_total_120"],
                 "bands": {k: v["band"] for k, v in score["sections"].items()},
                 "task_scores": {k: v.get("task_scores_0_5") for k, v in score["sections"].items() if v.get("task_scores_0_5")},
                 "routes": attempt.get("routes", {}), **profile,
                 "goals": {g["task_type"]: {c["id"]: c["status"] for c in g["criteria"]} for g in goals}})
    rows.sort(key=lambda r: r["attempt_id"])
    index.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def grade(d: Path, use_claude: bool, do_transcribe: bool, force: bool) -> None:
    test, attempt = load_json(d / "test.json"), load_json(d / "attempt.json")
    responses = load_json(d / "responses.json") if (d / "responses.json").exists() else {"tasks": {}}
    routes = attempt.get("routes") or responses.get("meta", {}).get("routes", {})
    attempt["routes"] = routes

    tpath = d / "transcripts.json"
    if do_transcribe and (force or not tpath.exists()):
        status(d, "transcribing")
        from transcribe import transcribe
        save_json(tpath, transcribe(d))
    transcripts = load_json(tpath) if tpath.exists() else {}

    status(d, "objective")
    objective = objective_results(test, responses.get("tasks", {}), routes, transcripts)
    save_json(d / "objective.json", objective)
    gin = grading_input(d, test, attempt, responses, transcripts, objective)
    save_json(d / "grading_input.json", gin)

    grading = None
    if use_claude and (force or check_grading(d, gin)):
        status(d, "claude")
        (d / "grading.json").unlink(missing_ok=True)
        run_claude(d)
        if errs := check_grading(d, gin):
            print("grading.json problems, asking Claude to fix:", errs[:5])
            save_json(d / "grading_errors.json", errs)
            run_claude(d)
    if (d / "grading.json").exists() and not check_grading(d, gin):
        grading = load_json(d / "grading.json")
    elif use_claude:
        print("WARNING: no valid Claude grading; writing/speaking bands will be partial. See claude.log")

    status(d, "scoring")
    score = compute(test, attempt, objective, grading)
    profile = error_profile(objective, grading)
    goals = goal_checks(test, routes, objective, grading)
    save_json(d / "score.json", {**score, **profile, "goals": goals})
    update_index(d, test, attempt, score, profile, goals)

    status(d, "report")
    from report import render
    render(d)
    status(d, "done")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["grade", "report"])
    ap.add_argument("attempt")
    ap.add_argument("--no-claude", action="store_true")
    ap.add_argument("--no-transcribe", action="store_true")
    ap.add_argument("--force", action="store_true", help="redo transcription and Claude grading")
    a = ap.parse_args()
    d = resolve(a.attempt)
    try:
        if a.cmd == "report":
            from report import render
            print(render(d))
        else:
            grade(d, not a.no_claude, not a.no_transcribe, a.force)
            print(f"Done: {d / 'report.pdf' if (d / 'report.pdf').exists() else d / 'report.html'}")
    except Exception as e:
        traceback.print_exc()
        status(d, "error", error=f"{e.__class__.__name__}: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
