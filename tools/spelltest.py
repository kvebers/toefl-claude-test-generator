"""Offline check of the spelling trainer (no Claude): word extraction from grading.json, the Leitner schedule,
relapse after a later test, and the checker rejecting a misspelling that is not in the response.

usage: python tools/spelltest.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="toefl-spelltest-"))
os.environ["TOEFL_RESULTS_DIR"] = str(TMP)
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import load_json, save_json  # noqa: E402
import spelling  # noqa: E402
from pipeline import check_grading  # noqa: E402

TEXT = ("Ofcourse we are moving to a diffrent country. It does not make sence to wait. "
        "There are to many reasons and it is necesary. We can not stay.")


def attempt(aid: str, text: str, grading_task: dict) -> Path:
    d = TMP / aid
    d.mkdir(parents=True)
    save_json(d / "grading_input.json", {"writing": [{"task_id": "w-disc", "type": "academic_discussion", "response": text}],
                                         "speaking": []})
    save_json(d / "grading.json", {"scale": 6, "tasks": {"w-disc": {"score": 3, "summary": "s", **grading_task}},
                                   "overall": {"summary": "s", "strengths": [], "priorities": []}})
    return d


def main() -> int:
    err = lambda q, c, x="": {"tag": "lexis.spelling", "quote": q, "correction": c, "explanation": x}
    attempt("20261101-100000_t1", TEXT, {"errors": [
        err("moving to a diffrent country", "moving to a different country", "dif-fer-ent."),
        err("Ofcourse", "Of course,"),
        err("make sence", "make sense", "Also necesary -> necessary, 'cantry' (country)."),   # cantry is not in the text
        err("to many reasons", "too many reasons"),
        err("We can not stay.", "We cannot stay."),
        {"tag": "grammar.article", "quote": "a diffrent", "correction": "the different", "explanation": "x"}]})
    words = spelling.collect()
    want = {"different", "of course", "sense", "necessary", "too", "cannot"}
    assert set(words) == want, f"extracted {sorted(words)}, expected {sorted(want)}"
    assert words["different"]["wrong"] == ["diffrent"] and words["different"]["example"] == "moving to a different country"

    # second test: 'different' written correctly, 'sence' misspelt again via the complete misspellings list
    attempt("20261103-100000_t2", "A different idea. It makes no sence.",
            {"errors": [], "misspellings": [{"wrong": "sence", "right": "sense"}]})
    words = spelling.collect()
    assert words["sense"]["attempts"] == ["20261101-100000_t1", "20261103-100000_t2"]
    assert words["different"]["correct_since"] == 1

    s = spelling.summary()
    assert s["counts"]["to_practise"] == 6 and len(s["session"]) == 6
    r = spelling.record("different", ok=True, typed="different")
    assert r["box"] == 1 and r["status"] == "learning" and r["due"] == (date.today() + timedelta(days=1)).isoformat()
    r = spelling.record("too", ok=False, typed="to")
    assert r["box"] == 0 and r["status"] == "due"
    spelling.record("cannot", ignore=True)
    s = spelling.summary()
    by = {w["word"]: w for w in s["words"]}
    assert by["cannot"]["status"] == "ignored" and "cannot" not in s["session"] and "different" not in s["session"]

    p = load_json(spelling.PROGRESS)                    # pretend 'different' reached box 5 and is due
    p["words"]["different"].update(box=5, due=date.today().isoformat())
    save_json(spelling.PROGRESS, p)
    assert spelling.record("different", ok=True)["status"] == "learned"

    # a test taken after practice that misspells the word again sends it back to box 0
    attempt("29991231-100000_t3", "Still diffrent.", {"errors": [], "misspellings": [{"wrong": "diffrent", "right": "different"}]})
    w = next(w for w in spelling.summary()["words"] if w["word"] == "different")
    assert w["status"] == "relapsed" and w["box"] == 0, w

    try:
        spelling.record("notaword", ok=True)
        raise AssertionError("unknown word accepted")
    except KeyError:
        pass

    d = attempt("20261105-100000_t4", "Short text.", {"errors": [], "misspellings": [{"wrong": "invented", "right": "x"}]})
    problems = check_grading(d, load_json(d / "grading_input.json"))
    assert any("misspelling 'invented'" in x for x in problems), problems
    print(f"SPELLTEST OK ({len(by)} words, outputs in {TMP})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
