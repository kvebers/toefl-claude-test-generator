"""Shared paths, loaders and objective-scoring helpers used by the server and the CLI tools."""
from __future__ import annotations

import copy
import difflib
import json
import os
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
TESTS_DIR = ROOT / "tests"          # your own generated / imported tests (git-ignored)
LIBRARY_DIR = ROOT / "library"      # shared tests, committed so others can reuse them
RESULTS_DIR = Path(os.environ.get("TOEFL_RESULTS_DIR") or ROOT / "results")  # attempts, reports, trends (git-ignored)
SPEC_PATH = ROOT / "spec" / "toefl-2026.yaml"
SCHEMA_PATH = ROOT / "schemas" / "test.schema.json"

MCQ_TYPES = {"daily_life", "academic_passage", "choose_response", "conversation", "announcement", "academic_talk"}
AUDIO_TYPES = {"choose_response", "conversation", "announcement", "academic_talk"}
GAP_RE = re.compile(r"([A-Za-z'-]*)\[([A-Za-z'-]+)\]")


def load_json(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save_json(path: Path, data) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def load_spec() -> dict:
    return yaml.safe_load(SPEC_PATH.read_text(encoding="utf-8"))


# ---------------------------------------------------------------- test discovery

def find_test_dir(test_id: str) -> Path:
    for base in (TESTS_DIR, LIBRARY_DIR):
        d = base / test_id
        if (d / "test.json").exists():
            return d
    raise FileNotFoundError(f"No test '{test_id}' in tests/ or library/")


def latest_test_id() -> str:
    dirs = [p.parent for p in TESTS_DIR.glob("*/test.json")] or [p.parent for p in LIBRARY_DIR.glob("*/test.json")]
    if not dirs:
        raise FileNotFoundError("No tests found. Run `make test` or `make practice TASK=...` first.")
    return max(dirs, key=lambda d: (d / "test.json").stat().st_mtime).name


def next_untaken_test_id() -> str:
    """Oldest test you have never attempted (your own tests first, then the library)."""
    untaken = [t for t in list_tests() if t["attempts"] == 0 and t["mode"] == "full"]
    if not untaken:
        raise FileNotFoundError("Every full test has been taken. Run `make test` or `make bank N=5` for new ones.")
    return untaken[0]["id"]


def attempt_counts(test: dict) -> dict:
    full = partial = 0
    for a in RESULTS_DIR.glob(f"*_{test['id']}/attempt.json"):
        secs = load_json(a).get("sections")
        if secs and len(secs) < len(test.get("sections", [])):
            partial += 1
        else:
            full += 1
    return {"attempts": full, "section_attempts": partial}


def list_tests() -> list[dict]:
    out = []
    for source, base in (("local", TESTS_DIR), ("library", LIBRARY_DIR)):
        for f in sorted(base.glob("*/test.json"), key=lambda f: f.stat().st_mtime):
            try:
                t = load_json(f)
            except (json.JSONDecodeError, OSError):
                continue
            out.append({
                "id": t["id"], "title": t.get("title", t["id"]), "mode": t.get("mode"), "source": source,
                "created": t.get("created"), "author": t.get("author"), "difficulty": t.get("difficulty"),
                "description": t.get("description", ""),
                "sections": [s["id"] for s in t.get("sections", [])],
                "audio_ready": (f.parent / "audio" / "manifest.json").exists(),
                **attempt_counts(t),
            })
    return out


# ---------------------------------------------------------------- iteration

def iter_tasks(test: dict, modules: dict | None = None):
    """Yield (section_id, module_key, task). `modules` maps section -> chosen m2 route to skip the other."""
    for sec in test["sections"]:
        for mkey, module in sec["modules"].items():
            if modules is not None and mkey.startswith("m2_") and modules.get(sec["id"]) != mkey:
                continue
            for task in module["tasks"]:
                yield sec["id"], mkey, task


def gaps(text: str) -> list[tuple[str, str]]:
    """'mig[ration]' -> [('mig', 'ration')]"""
    return GAP_RE.findall(text)


def sanitize(test: dict) -> dict:
    """Copy of the test with every answer key removed, safe to send to the browser."""
    t = copy.deepcopy(test)
    for _, _, task in iter_tasks(t):
        for q in task.get("questions", []):
            q.pop("answer", None)
            q.pop("explanation", None)
            q.pop("skill", None)
        if task["type"] == "complete_the_words":
            segs, pos, n = [], 0, 0
            for m in GAP_RE.finditer(task["text"]):
                segs.append({"t": task["text"][pos:m.start()]})
                segs.append({"gap": n, "prefix": m.group(1), "len": len(m.group(2))})
                pos, n = m.end(), n + 1
            segs.append({"t": task["text"][pos:]})
            task["segments"] = segs
            del task["text"]
        if task["type"] == "build_sentence":
            for it in task["items"]:
                it.pop("answer", None)
                it.pop("explanation", None)
                it.pop("skill", None)
    return t


# ---------------------------------------------------------------- objective scoring

_ONES = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split()
_TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()


def _num_words(n: int) -> list[str]:
    if n < 20:
        return [_ONES[n]]
    if n < 100:
        return [_TENS[n // 10]] + ([_ONES[n % 10]] if n % 10 else [])
    return [str(n)]


def norm_words(s: str) -> list[str]:
    """Lower-case words with digits spelled out, so Whisper's "10" matches a spoken "ten"."""
    out = []
    for w in re.findall(r"[a-z0-9']+", s.lower()):
        out += _num_words(int(w)) if w.isdigit() else [w]
    return out


def repeat_accuracy(target: str, said: str) -> float:
    """Share of target words reproduced in order (Listen & Repeat)."""
    t, s = norm_words(target), norm_words(said)
    if not t:
        return 0.0
    matched = sum(b.size for b in difflib.SequenceMatcher(None, t, s, autojunk=False).get_matching_blocks())
    return matched / len(t)


def score_task(section: str, module: str, task: dict, resp: dict | None) -> list[dict]:
    """Objective item results for one task (empty for human-rated tasks)."""
    resp = resp or {}
    out = []
    base = {"section": section, "module": module, "task_id": task["id"], "task_type": task["type"]}
    if task["type"] in MCQ_TYPES:
        given = resp.get("answers", {})
        for q in task["questions"]:
            g = given.get(q["id"])
            out.append({**base, "item_id": q["id"], "prompt": q["prompt"], "skill": q["skill"],
                        "given": q["options"][g] if isinstance(g, int) and 0 <= g < len(q["options"]) else None,
                        "expected": q["options"][q["answer"]], "correct": g == q["answer"],
                        "explanation": q["explanation"]})
    elif task["type"] == "complete_the_words":
        given = resp.get("gaps", [])
        for i, (prefix, missing) in enumerate(gaps(task["text"])):
            g = (given[i] if i < len(given) else "") or ""
            out.append({**base, "item_id": f"gap{i + 1}", "prompt": f"{prefix}___", "skill": "reading.vocabulary.form",
                        "given": prefix + g, "expected": prefix + missing,
                        "correct": g.strip().lower() == missing.lower(), "explanation": ""})
    elif task["type"] == "build_sentence":
        given = resp.get("items", {})
        for it in task["items"]:
            g = given.get(it["id"]) or []
            sentence = lambda parts: " ".join(x for x in [it.get("start", ""), *parts, it.get("end", "")] if x)
            out.append({**base, "item_id": it["id"], "prompt": it["prompt"], "skill": it["skill"],
                        "given": sentence(g) if g else None, "expected": sentence(it["answer"]),
                        "correct": [c.strip().lower() for c in g] == [c.strip().lower() for c in it["answer"]],
                        "explanation": it.get("explanation", "")})
    return out


def score_module(section: str, module_key: str, module: dict, responses: dict) -> float:
    items = [r for task in module["tasks"] for r in score_task(section, module_key, task, responses.get(task["id"]))]
    return sum(r["correct"] for r in items) / len(items) if items else 0.0
