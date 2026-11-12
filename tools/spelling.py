"""Spelling tracker and trainer: every misspelt word from graded writing, practised with spaced repetition.

Words come from grading.json: the `misspellings` list (complete, newer gradings) and the `lexis.spelling`
errors, whose quotes are often whole phrases and whose explanations list extra words ("sence -> sense").
A pair is kept only if the wrong form really occurs in the learner's response.

Practice follows Look, Say, Cover, Write, Check with Leitner boxes: a word moves up one box each time it is
spelt right from memory and waits longer before the next review; a miss sends it back to box 0. A word that
is misspelt again in a later test also goes back to box 0.

usage:
  python tools/spelling.py           # table of tracked words
  python tools/spelling.py json      # the same data as JSON (what the web app shows)
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date, datetime, timedelta
from difflib import SequenceMatcher

from common import RESULTS_DIR, load_json, save_json

PROGRESS = RESULTS_DIR / "spelling" / "progress.json"
INTERVALS = {1: 1, 2: 3, 3: 7, 4: 14, 5: 30}   # box -> days until the next review
LEARNED = 6                                      # spelt right from memory in box 5 (about 8 weeks in)
SESSION = 10                                     # words per practice session
WORD = re.compile(r"[A-Za-z]+(?:['’][A-Za-z]+)*")
# "sence -> sense", "'activly' (actively)", "'ofline' for 'offline'", "'themselfs' should be 'themselves'"
HINTS = [re.compile(r"\b([A-Za-z']+)\s*(?:->|→)\s*([A-Za-z']+)"),
         re.compile(r"'([A-Za-z]+)'\s*\(([A-Za-z]+)\)"),
         re.compile(r"'([A-Za-z]+)' (?:for|should be) '([A-Za-z]+)'")]


def similar(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower(), autojunk=False).ratio()


def is_pair(wrong: str, right: str, text: str) -> bool:
    """A real misspelling: differs beyond letter case, looks like the right word, and occurs in the response."""
    if wrong.lower() == right.lower() or len(right) < 2 or similar(wrong, right) < 0.6:
        return False
    return re.search(rf"(?<![A-Za-z]){re.escape(wrong)}(?![A-Za-z])", text, re.I) is not None


def pairs_from_error(e: dict, text: str) -> list[tuple[str, str]]:
    """Word pairs inside one lexis.spelling error: aligned quote/correction words, then hints in the explanation."""
    q, c = WORD.findall(e.get("quote") or ""), WORD.findall(e.get("correction") or "")
    out = []
    ops = SequenceMatcher(None, [w.lower() for w in q], [w.lower() for w in c], autojunk=False).get_opcodes()
    for op, i1, i2, j1, j2 in ops:
        if op != "replace":
            continue
        a, b = q[i1:i2], c[j1:j2]
        if len(a) == len(b):
            out += zip(a, b)
        elif "".join(a).lower() == "".join(b).lower() or similar("".join(a), "".join(b)) >= 0.85:
            out.append((" ".join(a), " ".join(b)))       # split or merged word: "Ofcourse" / "can not"
        else:                                            # rewritten phrase: keep the closest word pairs only
            for w in a:
                best = max(b, key=lambda x: similar(w, x))
                if similar(w, best) >= 0.75:
                    out.append((w, best))
    for rx in HINTS:
        out += rx.findall(e.get("explanation") or "")
    return [(w, r) for w, r in out if is_pair(w, r, text)]


def attempt_time(aid: str) -> datetime:
    return datetime.strptime(aid[:15], "%Y%m%d-%H%M%S")


def collect() -> dict[str, dict]:
    """Tracked words keyed by the correct spelling (lower case), oldest attempt first."""
    words: dict[str, dict] = {}
    responses = []                                       # (attempt, text) of every graded writing response
    for gi in sorted(RESULTS_DIR.glob("*/grading_input.json")):
        d = gi.parent
        if not (d / "grading.json").exists():
            continue
        gin, grading = load_json(gi), load_json(d / "grading.json")
        for item in gin.get("writing", []):
            text = item.get("response") or ""
            responses.append((d.name, text))
            g = grading.get("tasks", {}).get(item["task_id"], {})
            found = [(m.get("wrong", ""), m.get("right", ""), None, None) for m in g.get("misspellings", [])
                     if is_pair(m.get("wrong", ""), m.get("right", ""), text)]
            for e in g.get("errors", []):
                if e.get("tag") == "lexis.spelling":
                    found += [(w, r, e, len(WORD.findall(e.get("correction") or ""))) for w, r in pairs_from_error(e, text)]
            for wrong, right, err, n in found:
                w = words.setdefault(right.lower(), {"word": right.lower(), "wrong": {}, "attempts": [], "tip": None, "example": None})
                w["wrong"][wrong.lower()] = w["wrong"].get(wrong.lower(), 0) + 1
                if d.name not in w["attempts"]:
                    w["attempts"].append(d.name)
                if err:                                  # the newest tip and example sentence win
                    w["tip"] = err.get("explanation") or w["tip"]
                    if n and n > 1:
                        w["example"] = err["correction"]
    for key, w in words.items():                         # later tests where the word was written correctly
        last = w["attempts"][-1]
        right = re.compile(rf"(?<![A-Za-z]){re.escape(key)}(?![A-Za-z])", re.I)
        w["correct_since"] = len({a for a, t in responses if a > last and right.search(t)})
        w["wrong"] = sorted(w["wrong"], key=lambda x: -w["wrong"][x])
    return words


def load_progress() -> dict:
    return load_json(PROGRESS) if PROGRESS.exists() else {"words": {}}


def state(w: dict, p: dict, today: date) -> dict:
    """Merge practice progress into a tracked word: box, status and next review date."""
    box, due = p.get("box", 0), p.get("due")
    relapsed = bool(p.get("last")) and attempt_time(w["attempts"][-1]) > datetime.fromisoformat(p["last"])
    if relapsed:                                         # misspelt in a test taken after the last practice
        box, due = 0, None
    if p.get("ignored"):
        status = "ignored"
    elif box >= LEARNED:
        status = "learned"
    elif relapsed:
        status = "relapsed"
    elif not p.get("reviews"):
        status = "new"
    else:
        status = "due" if not due or date.fromisoformat(due) <= today else "learning"
    return {**w, "box": box, "due": due, "status": status, "reviews": len(p.get("reviews", [])),
            "right_first_time": sum(r["ok"] for r in p.get("reviews", []))}


def summary(today: date | None = None) -> dict:
    today = today or date.today()
    prog = load_progress()["words"]
    words = [state(w, prog.get(k, {}), today) for k, w in collect().items()]
    rank = {"relapsed": 0, "due": 1, "new": 2, "learning": 3, "learned": 4, "ignored": 5}
    words.sort(key=lambda w: (rank[w["status"]], w["due"] or "", -len(w["attempts"]), w["word"]))
    session = [w for w in words if w["status"] in ("relapsed", "due", "new")][:SESSION]
    upcoming = sorted(w["due"] for w in words if w["status"] == "learning")
    count = lambda *s: sum(w["status"] in s for w in words)
    return {"words": words, "session": [w["word"] for w in session], "next_review": upcoming[0] if upcoming else None,
            "counts": {"tracked": count("relapsed", "due", "new", "learning", "learned"), "learned": count("learned"),
                       "to_practise": count("relapsed", "due", "new"), "learning": count("learning"),
                       "ignored": count("ignored")},
            "boxes": LEARNED, "intervals": INTERVALS}


def record(word: str, ok: bool | None = None, typed: str = "", ignore: bool | None = None) -> dict:
    """Store one practice result (the first try of a session) or hide/unhide a word."""
    key = word.lower()
    tracked = collect()
    if key not in tracked:
        raise KeyError(f"'{word}' is not a tracked word")
    data = load_progress()
    p = data["words"].setdefault(key, {"box": 0, "reviews": []})
    if ignore is not None:
        p["ignored"] = bool(ignore)
    if ok is not None:
        now = datetime.now()
        if p.get("last") and attempt_time(tracked[key]["attempts"][-1]) > datetime.fromisoformat(p["last"]):
            p["box"] = 0                                 # relapsed: start again
        p["box"] = min(p.get("box", 0) + 1, LEARNED) if ok else 0
        p["due"] = (now.date() + timedelta(days=INTERVALS[p["box"]])).isoformat() if 0 < p["box"] < LEARNED \
            else None if p["box"] >= LEARNED else now.date().isoformat()
        p["last"] = now.isoformat(timespec="seconds")
        p["reviews"].append({"t": p["last"], "ok": bool(ok), "typed": typed[:60]})
    save_json(PROGRESS, data)
    return state(tracked[key], p, date.today())


def main() -> None:
    s = summary()
    if sys.argv[1:2] == ["json"]:
        print(json.dumps(s, ensure_ascii=False, indent=1))
        return
    c = s["counts"]
    print(f"{c['tracked']} words tracked: {c['to_practise']} to practise, {c['learning']} waiting for review, "
          f"{c['learned']} learned" + (f", {c['ignored']} hidden" if c["ignored"] else ""))
    print(f"{'word':<18}{'you wrote':<26}{'tests':>6}  {'status':<10}next review")
    for w in s["words"]:
        print(f"{w['word']:<18}{', '.join(w['wrong'])[:25]:<26}{len(w['attempts']):>6}  {w['status']:<10}{w['due'] or ''}")
    print("Practise them on the start page (make serve), Spelling trainer.")


if __name__ == "__main__":
    main()
