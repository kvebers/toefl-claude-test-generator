"""Transcribe speaking recordings with faster-whisper and compute simple fluency metrics.

usage: python tools/transcribe.py <attempt_dir>      (WHISPER_MODEL env, default small.en)

Writes transcripts.json: { "<key>": {text, duration, wpm, pauses, long_pauses, fillers, mean_word_prob} }.
Claude cannot hear audio, so pronunciation is only approximated via Whisper's word confidence.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from common import save_json

FILLERS = {"um", "uh", "erm", "er", "ah", "hmm", "mm"}


def metrics(words: list) -> dict:
    if not words:
        return {"duration": 0, "wpm": 0, "pauses": 0, "long_pauses": 0, "fillers": 0, "mean_word_prob": None}
    span = max(0.1, float(words[-1].end - words[0].start))
    gaps = [float(b.start - a.end) for a, b in zip(words, words[1:])]   # Whisper gives numpy floats
    tokens = [re.sub(r"[^a-z']", "", w.word.lower()) for w in words]
    return {
        "duration": round(float(words[-1].end), 1),
        "speech_start": round(float(words[0].start), 1),
        "wpm": int(round(60 * len(words) / span)),
        "pauses": int(sum(g > 0.5 for g in gaps)),
        "long_pauses": int(sum(g > 1.5 for g in gaps)),
        "fillers": int(sum(t in FILLERS for t in tokens)),
        "mean_word_prob": round(float(sum(w.probability for w in words)) / len(words), 3),
        "low_confidence_words": [w.word.strip() for w in words if w.probability < 0.5][:15],
    }


def transcribe(attempt_dir: Path) -> dict:
    recs = sorted(p for p in (attempt_dir / "recordings").glob("*") if p.suffix in (".webm", ".ogg", ".wav", ".m4a", ".mp3"))
    out = {}
    if not recs:
        return out
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        msg = "faster-whisper not installed (pip install faster-whisper)"
        return {p.stem: {"error": msg} for p in recs}
    model = WhisperModel(os.environ.get("WHISPER_MODEL", "small.en"), device="cpu", compute_type="int8")
    for p in recs:
        try:
            segments, _ = model.transcribe(str(p), language="en", word_timestamps=True, vad_filter=False,
                                           initial_prompt="Um, uh, so, I mean, like, you know.")  # keeps fillers
            segments = list(segments)
            words = [w for s in segments for w in (s.words or [])]
            out[p.stem] = {"text": " ".join(s.text.strip() for s in segments).strip(), **metrics(words)}
        except Exception as e:  # corrupt/empty recording
            out[p.stem] = {"error": f"{e.__class__.__name__}: {e}"}
        print(f"  {p.stem}: {out[p.stem].get('text', out[p.stem].get('error'))[:70]}")
    return out


if __name__ == "__main__":
    d = Path(sys.argv[1])
    save_json(d / "transcripts.json", transcribe(d))
