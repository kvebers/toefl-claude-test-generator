"""Offline end-to-end check (no browser, no Claude, no Whisper): builds a synthetic attempt on the sample
test with fake transcripts + a fake Claude grading, then runs scoring, report and trends in a temp folder.

usage: python tools/selftest.py [--keep]
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

TOOLS = Path(__file__).resolve().parent


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="toefl-selftest-"))
    os.environ["TOEFL_RESULTS_DIR"] = str(tmp)
    sys.path.insert(0, str(TOOLS))
    from common import LIBRARY_DIR, iter_tasks, load_json, save_json
    from validate import validate

    test = load_json(LIBRARY_DIR / "sample-mini" / "test.json")
    assert not validate(test)[0], "sample test invalid"
    routes = {"reading": "m2_hard", "listening": "m2_easy"}
    responses, transcripts, wrong = {}, {}, 0
    for sid, mkey, task in iter_tasks(test, routes):
        t = task["type"]
        if "questions" in task and "options" in task["questions"][0]:
            ans = {}
            for q in task["questions"]:              # every third answer wrong
                wrong += 1
                ans[q["id"]] = q["answer"] if wrong % 3 else (q["answer"] + 1) % len(q["options"])
            responses[task["id"]] = {"answers": ans}
        elif t == "complete_the_words":
            from common import gaps
            responses[task["id"]] = {"gaps": [m if i % 4 else m[:-1] for i, (_, m) in enumerate(gaps(task["text"]))]}
        elif t == "build_sentence":
            responses[task["id"]] = {"items": {it["id"]: (it["answer"] if i % 2 == 0 else it["chunks"]) for i, it in enumerate(task["items"])}}
        elif t in ("email", "academic_discussion"):
            responses[task["id"]] = {"text": "Dear Ms Chen, thank you for organise the event. I noticed there was not enough gloves. "
                                             "Maybe we can ask a local shop to donate some. Best regards, Alex"}
        elif t == "listen_and_repeat":
            for i, it in enumerate(task["items"]):
                words = it["text"].split()
                transcripts[f"{task['id']}__{it['id']}"] = {"text": " ".join(words if i < 4 else words[:-3]), "wpm": 120}
        elif t == "interview":
            for q in task["questions"]:
                transcripts[f"{task['id']}__{q['id']}"] = {"text": "I use my phone mostly for, um, messages and maps. It is very useful for me.",
                    "duration": 21.5, "speech_start": 1.2, "wpm": 95, "pauses": 6, "long_pauses": 2, "fillers": 3,
                    "mean_word_prob": 0.86, "low_confidence_words": []}

    def attempt(aid: str, score_shift: float):
        d = tmp / aid
        (d / "recordings").mkdir(parents=True)
        save_json(d / "test.json", test)
        save_json(d / "attempt.json", {"id": aid, "test_id": test["id"], "started": f"2026-10-{aid[6:8]}T10:00:00",
                                       "home_edition": True, "routes": routes})
        save_json(d / "responses.json", {"tasks": responses, "meta": {"routes": routes, "task_seconds": {}, "fullscreen_exits": 1}})
        save_json(d / "transcripts.json", transcripts)
        err = {"tag": "grammar.verb_form", "quote": "thank you for organise", "correction": "thank you for organising",
               "explanation": "After a preposition use the -ing form."}
        q_grades = {q["id"]: {"score": 2.5 + score_shift, "summary": "Short answer with long pauses.", "errors": [
            {"tag": "speaking.fluency.pauses", "quote": "for, um, messages", "correction": "for messaging", "explanation": "Avoid fillers."}],
            "model_answer": "Mostly my phone: I use it for messages, maps and studying vocabulary on the bus."}
            for q in test["sections"][3]["modules"]["m1"]["tasks"][1]["questions"]}
        save_json(d / "grading.json", {
            "tasks": {"w-email": {"score": 2.5 + score_shift, "summary": "Covers all points briefly.", "errors": [err],
                                  "dimensions": {"task_completion": "All bullets touched, thinly."}, "improved_version": "Dear Ms Chen, ..."},
                      "w-disc": {"score": 2 + score_shift, "summary": "Off-topic: the response is an email.", "errors": [
                          {"tag": "discourse.relevance", "quote": "Dear Ms Chen", "correction": "(answer the professor's question)",
                           "explanation": "The discussion task needs an opinion on lecture recordings."}]},
                      "s-interview": {"score": 2.5 + score_shift, "summary": "Answers are short.", "errors": [], "questions": q_grades}},
            "objective_patterns": "Most misses are inference questions.",
            "overall": {"summary": "Solid B1–B2 base.", "strengths": ["Clear reading of details"],
                        "priorities": [{"title": "Develop your answers", "why": "Interview answers use 21 of 45 seconds.",
                                        "how": ["Use the reason + example + result pattern"], "tags": ["discourse.development"],
                                        "practice_command": "make practice TASK=interview"}]}})
        return d

    py = sys.executable
    for aid, shift in (("20261020-100000_sample-mini", 0.0), ("20261022-100000_sample-mini", 1.0)):
        d = attempt(aid, shift)
        r = subprocess.run([py, str(TOOLS / "pipeline.py"), "grade", aid, "--no-claude", "--no-transcribe"], capture_output=True, text=True)
        print(r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "", r.stderr[-2000:])
        score = load_json(d / "score.json")
        print(f"  {aid}: overall {score['summary']['overall_band']}, ~{score['summary']['est_total_120']}/120, "
              f"bands { {k: v['band'] for k, v in score['sections'].items()} }")
        assert score["summary"]["overall_band"] is not None, "overall band missing"
        assert (d / "report.html").exists(), "report.html missing"
    r = subprocess.run([py, str(TOOLS / "trends.py"), "data"], capture_output=True, text=True)
    r2 = subprocess.run([py, str(TOOLS / "trends.py"), "render"], capture_output=True, text=True)
    print(r.stdout.strip(), r2.stdout.strip(), r.stderr[-1500:], r2.stderr[-1500:])
    assert (tmp / "trends" / "trends.html").exists(), "trends.html missing"
    print(f"SELFTEST OK, outputs in {tmp}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
