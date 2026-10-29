"""Writing and speaking study guide (on request): structure, strategy, linking words, key phrases, core errors.

usage:
  python tools/study.py data [writing|speaking]   # results/study/study_data.json (input for /toefl-study)
  python tools/study.py check                     # validate results/study/study.json
  python tools/study.py render                    # results/study/study.html + study.pdf
"""
from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

from common import RESULTS_DIR, ROOT, load_json, load_spec, save_json
from report import env, html_to_pdf

OUT = RESULTS_DIR / "study"
TAXONOMY = ROOT / ".claude" / "skills" / "toefl-grade" / "error-taxonomy.md"
# Linking words by function, counted in every response so the guide can show what the learner already uses.
LINKERS = {
    "opinion": ["in my opinion", "in my view", "i believe", "i think", "i would argue", "from my perspective",
                "personally", "i strongly", "if i had to choose"],
    "addition": ["furthermore", "moreover", "in addition", "also", "what is more", "besides", "on top of that"],
    "contrast": ["however", "although", "even though", "whereas", "while", "on the other hand", "but",
                 "nevertheless", "despite", "unlike", "in contrast"],
    "cause_result": ["because", "since", "as a result", "therefore", "so", "this means", "that is why",
                     "consequently", "due to", "which leads to", "thanks to"],
    "example": ["for example", "for instance", "such as", "a good example", "the best example", "in my experience",
                "when i was", "last year", "once"],
    "sequence": ["first", "firstly", "second", "secondly", "finally", "then", "after that", "to begin with",
                 "the main reason"],
    "conclusion": ["in conclusion", "to sum up", "overall", "all in all", "that is why i", "for these reasons"],
    "email": ["i am writing to", "i'm writing to", "would it be possible", "i would appreciate", "could you",
              "i look forward", "thank you for", "best regards", "kind regards", "sincerely"],
}
REQUIRED = ["type", "structure_now", "structural_changes", "blueprint", "strategy", "linking_words", "key_phrases",
            "core_errors"]


def open_types() -> dict[str, str]:
    """Task types rated by Claude (criteria without `skills`/`repeat` keys) -> their section."""
    spec = load_spec()
    section_of = {t: s for s, sec in spec["sections"].items() for t in sec["tasks"]}
    return {t: section_of[t] for t, g in spec["goals"].items()
            if t in section_of and not any("skills" in c or "repeat" in c for c in g["criteria"].values())}


def linkers(text: str) -> dict[str, list[str]]:
    low = " " + re.sub(r"[^a-z' ]+", " ", text.lower()) + " "
    found = {}
    for func, words in LINKERS.items():
        hits = [w for w in words if f" {w} " in low]
        if hits:
            found[func] = hits
    return found


def shape(text: str) -> dict:
    paras = [p for p in re.split(r"\n\s*\n|\n", text.strip()) if p.strip()]
    sents = [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]
    words = len(text.split())
    return {"words": words, "paragraphs": len(paras), "sentences": len(sents),
            "avg_sentence_words": round(words / len(sents), 1) if sents else 0}


def errors(task: dict) -> list[dict]:
    out = list(task.get("errors", []))
    for q in (task.get("questions") or {}).values():
        out += q.get("errors", [])
    seen, uniq = set(), []          # interview task errors often repeat the per-question ones
    for e in out:
        if (e.get("tag"), e.get("quote")) not in seen:
            seen.add((e.get("tag"), e.get("quote")))
            uniq.append({k: e.get(k) for k in ("tag", "quote", "correction", "explanation")})
    return uniq


def collect(section: str | None) -> dict:
    types = open_types()
    entries = []
    for gi in sorted(RESULTS_DIR.glob("*/grading_input.json")):
        d = gi.parent
        if not (d / "grading.json").exists():
            continue
        gin, grading = load_json(gi), load_json(d / "grading.json")
        date = d.name[:8]
        for sec in ("writing", "speaking"):
            if section and sec != section:
                continue
            for item in gin.get(sec, []):
                if item.get("type") not in types:
                    continue
                g = grading.get("tasks", {}).get(item["task_id"], {})
                e = {"attempt_id": d.name, "date": f"{date[:4]}-{date[4:6]}-{date[6:]}", "task_id": item["task_id"],
                     "type": item["type"], "section": sec, "score": g.get("score"),
                     "criteria": {c["id"]: c["status"] for c in g.get("criteria", [])}, "errors": errors(g)}
                if sec == "writing":
                    text = item.get("response") or ""
                    e.update(prompt=item.get("prompt"), response=text, **shape(text), linkers=linkers(text),
                             improved_version=g.get("improved_version"))
                else:
                    qs = []
                    for q in item.get("questions", []):
                        tr = q.get("transcript") or {}
                        gq = (g.get("questions") or {}).get(q["id"], {})
                        text = tr.get("text") or ""
                        qs.append({"id": q["id"], "question": q["text"], "transcript": text,
                                   "duration": tr.get("duration"), "wpm": tr.get("wpm"), "fillers": tr.get("fillers"),
                                   "long_pauses": tr.get("long_pauses"), "words": len(text.split()),
                                   "linkers": linkers(text), "score": gq.get("score"),
                                   "model_answer": gq.get("model_answer")})
                    e.update(topic=item.get("topic"), questions=qs)
                entries.append(e)
    per_type = {}
    for t in sorted({e["type"] for e in entries}):
        es = [e for e in entries if e["type"] == t]
        texts = [e.get("response") or " ".join(q["transcript"] for q in e.get("questions", [])) for e in es]
        used = Counter(w for tx in texts for ws in linkers(tx).values() for w in ws)
        tags = Counter(x["tag"] for e in es for x in e["errors"])
        per_type[t] = {"section": types[t], "responses": len(es), "scores": [e["score"] for e in es],
                       "linker_use": dict(used.most_common()), "error_tags": dict(tags.most_common()),
                       "spelling": [x for e in es for x in e["errors"] if x["tag"] == "lexis.spelling"]}
    return {"section": section or "all", "attempts": len({e["attempt_id"] for e in entries}),
            "per_type": per_type, "entries": entries, "linker_bank": LINKERS}


def build_data(section: str | None) -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    data = collect(section)
    save_json(OUT / "study_data.json", data)
    print(f"Wrote {OUT / 'study_data.json'} ({len(data['entries'])} responses, {data['attempts']} attempts, "
          f"types: {', '.join(data['per_type']) or 'none'})")
    return data


def check() -> list[str]:
    p = OUT / "study.json"
    if not p.exists():
        return [f"{p} missing"]
    s, probs = load_json(p), []
    known = set(re.findall(r"^- ([a-z_.]+):", TAXONOMY.read_text(encoding="utf-8"), re.M))
    types = open_types()
    for k in ("summary", "types"):
        if not s.get(k):
            probs.append(f"missing '{k}'")
    for i, t in enumerate(s.get("types", [])):
        where = f"types[{i}] ({t.get('type')})"
        if t.get("type") not in types:
            probs.append(f"{where}: unknown type, expected one of {sorted(types)}")
        probs += [f"{where}: missing '{k}'" for k in REQUIRED if not t.get(k)]
        for e in t.get("core_errors", []):
            if e.get("tag") not in known:
                probs.append(f"{where}: core error tag '{e.get('tag')}' is not in error-taxonomy.md")
            if not e.get("examples"):
                probs.append(f"{where}: core error '{e.get('pattern')}' needs examples (wrong/right)")
        for b in t.get("blueprint", []):
            if not (b.get("part") and b.get("template")):
                probs.append(f"{where}: every blueprint step needs 'part' and 'template'")
    text = p.read_text(encoding="utf-8")
    if "—" in text:
        probs.append("study.json contains an em dash; use a comma, colon or brackets instead")
    return probs


def render() -> None:
    data = load_json(OUT / "study_data.json") if (OUT / "study_data.json").exists() else build_data(None)
    guide = load_json(OUT / "study.json") if (OUT / "study.json").exists() else None
    html = OUT / "study.html"
    html.write_text(env().get_template("study.html.j2").render(d=data, s=guide), encoding="utf-8")
    pdf = OUT / "study.pdf"
    pdf.unlink(missing_ok=True)
    print(f"Wrote {pdf if html_to_pdf(html, pdf) else html}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "data"
    if cmd == "data":
        build_data(sys.argv[2] if len(sys.argv) > 2 else None)
    elif cmd == "check":
        problems = check()
        print("\n".join(problems) if problems else "OK")
        sys.exit(1 if problems else 0)
    else:
        render()
