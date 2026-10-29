"""Shared paths, loaders and objective-scoring helpers used by the server and the CLI tools."""
from __future__ import annotations

import copy
import difflib
import json
import math
import os
import re
import threading
import time
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


LIMIT_MARKERS = ("hit your session limit", "usage limit", "rate limit")


# Headless runs load only this project's settings, no MCP servers and only the tools the skills use. Without
# this every turn of every run (and every subagent) carries ~45k tokens of user plugins, MCP tools and unused
# built-in tools instead of ~19k. Keep in sync with CLAUDE_LEAN in the Makefile.
CLAUDE_LEAN = ["--setting-sources", "project,local", "--strict-mcp-config",
               "--tools", "Read,Write,Edit,Glob,Grep,Agent,Skill,Bash,PowerShell"]


def claude_env() -> dict:
    """Environment for headless Claude runs: no claude.ai connectors (Gmail, Drive, Docs...)."""
    return {**os.environ, "ENABLE_CLAUDEAI_MCP_SERVERS": "false"}


def usage_limit_message(log_text: str) -> str | None:
    """The Claude Code line that says the plan's usage limit was reached, if any."""
    for line in log_text.splitlines():
        if any(m in line.lower() for m in LIMIT_MARKERS):
            return line.strip()
    return None


def load_json(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save_json(path: Path, data) -> None:
    """Write atomically (temp file + rename) so a concurrent reader never sees a half-written file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    for attempt in range(20):
        try:
            return os.replace(tmp, path)
        except PermissionError:     # Windows: the target is open in another process for a moment
            if attempt == 19:
                raise
            time.sleep(0.05)


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


def last_attempts() -> dict:
    """test_id -> its most recent graded attempt from results/index.jsonl (date, overall and section bands)."""
    index = RESULTS_DIR / "index.jsonl"
    rows = [json.loads(l) for l in index.read_text(encoding="utf-8").splitlines() if l.strip()] if index.exists() else []
    return {r["test_id"]: {"date": r.get("date"), "overall_band": r.get("overall_band"), "bands": r.get("bands", {})}
            for r in rows}     # later rows overwrite earlier ones


def list_tests() -> list[dict]:
    out, seen, last = [], set(), last_attempts()
    for source, base in (("local", TESTS_DIR), ("library", LIBRARY_DIR)):
        for f in sorted(base.glob("*/test.json"), key=lambda f: f.stat().st_mtime):
            try:
                t = load_json(f)
            except (json.JSONDecodeError, OSError):
                continue
            if t["id"] in seen:     # a published test is also in tests/; find_test_dir uses that copy
                continue
            seen.add(t["id"])
            out.append({
                "id": t["id"], "title": t.get("title", t["id"]), "mode": t.get("mode"), "source": source,
                "created": t.get("created"), "author": t.get("author"), "difficulty": t.get("difficulty"),
                "description": t.get("description", ""),
                "sections": [s["id"] for s in t.get("sections", [])],
                "task_types": list(dict.fromkeys(task["type"] for _, _, task in iter_tasks(t))),
                "audio_ready": (f.parent / "audio" / "manifest.json").exists(),
                "last": last.get(t["id"]),
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
    if 1100 <= n <= 2099 and not 2000 <= n <= 2009:      # years are read in pairs: 1930 -> nineteen thirty
        lo = n % 100
        return _num_words(n // 100) + (["hundred"] if lo == 0 else ["oh", _ONES[lo]] if lo < 10 else _num_words(lo))
    return [str(n)]


_NEG_STEMS = {"wo": "will", "ca": "can", "sha": "shall"}
_CONTRACTIONS = {"'ll": "will", "'re": "are", "'ve": "have", "'m": "am"}   # 's and 'd are ambiguous, kept as is


def norm_words(s: str) -> list[str]:
    """Lower-case words with digits spelled out and contractions expanded, so Whisper's "10" matches a
    spoken "ten" and its "has not" / "we will" match "hasn't" / "we'll" (it writes the same audio either way)."""
    out = []
    for w in re.findall(r"[a-z0-9']+", s.lower().replace("’", "'")):
        if w.isdigit():
            out += _num_words(int(w))
        elif w[:-1].isdigit() and w[-1] == "s":             # decades: 1930s -> nineteen thirties
            *head, last = _num_words(int(w[:-1]))
            out += head + [last[:-1] + "ies" if last.endswith("y") else last + "s"]
        elif w.endswith("n't"):
            out += [_NEG_STEMS.get(w[:-3], w[:-3]), "not"]
        elif w == "cannot":
            out += ["can", "not"]
        elif (c := next((c for c in _CONTRACTIONS if w.endswith(c) and len(w) > len(c)), None)):
            out += [w[:-len(c)], _CONTRACTIONS[c]]
        else:
            out.append(w)
    return out


FILLERS = {"uh", "um", "er", "erm", "ah", "eh", "hmm", "mm", "uhm"}


def repeat_errors(target: str, said: str, unclear: set[str] | None = None) -> float:
    """Word errors in a Listen & Repeat answer: missing, changed and added words, as the official task
    asks for a word-for-word repetition. Fillers and restarts ("twice, uh, twice") are not counted.

    Words Whisper was unsure of (`unclear`) count as half an error: Whisper tends to "clean up" unclear
    speech into the expected word, so full credit would flatter the speaker.
    """
    t = norm_words(target)
    s = []
    for w in norm_words(said):
        if w in FILLERS or (s and s[-1] == w and f"{w} {w}" not in " ".join(t)):
            continue
        s.append(w)
    unclear = {w for u in (unclear or ()) for w in norm_words(u)}
    errors = 0.0
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, t, s, autojunk=False).get_opcodes():
        if op == "equal":
            errors += sum(0.5 for w in t[i1:i2] if w in unclear)
        else:   # replace / delete / insert: each target word lost or extra word said is one error
            errors += max(i2 - i1, j2 - j1)
    return errors


def repeat_accuracy(target: str, said: str, unclear: set[str] | None = None) -> float:
    """Share of the sentence repeated correctly (1 - errors per target word, floored at 0)."""
    n = len(norm_words(target))
    return max(0.0, 1 - repeat_errors(target, said, unclear) / n) if n else 0.0


def repeat_points(errors: float | None, n_words: int) -> int:
    """Per-sentence rating 0-5 from the number of word errors, so short and long sentences are judged alike:
    word-perfect 5, one slip 4, two or three 3, more but at least half right 2, any attempt 1.
    `errors` is None when there is no recording; half errors (unclear words) round down, so a single
    word Whisper was unsure of does not cost a point but two of them do."""
    if errors is None or not n_words:
        return 0
    e = math.ceil(errors - 0.5)
    return 5 if e == 0 else 4 if e == 1 else 3 if e <= 3 else 2 if e <= n_words / 2 else 1


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
