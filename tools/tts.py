"""Pre-render every spoken line of a test to MP3 so playback is identical on every attempt.

usage: python tools/tts.py <test_id> [--engine edge|browser]

Writes <test_dir>/audio/<hash>.mp3 and audio/manifest.json:
    { "<clip_key>": [ {"file": "ab12.mp3" | null, "voice": "en-US-GuyNeural", "speaker": "...", "text": "..."} ] }
Clip keys: <task_id> for listening tasks, <task_id>__<item_id> for Listen & Repeat,
<task_id>__intro / <task_id>__<question_id> for the interview.
`file: null` means the browser falls back to the Web Speech API (offline / --engine browser).
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import sys

from common import AUDIO_TYPES, find_test_dir, iter_tasks, latest_test_id, load_json, load_spec, save_json


def clips(test: dict, voices: dict) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    line = lambda speaker, voice, text: {"speaker": speaker, "voice": voices.get(voice, voice), "text": text}
    for _, _, task in iter_tasks(test):
        if task["type"] in AUDIO_TYPES:
            out[task["id"]] = [line(l["speaker"], l["voice"], l["text"]) for l in task["audio"]]
        elif task["type"] == "listen_and_repeat":
            for it in task["items"]:
                out[f"{task['id']}__{it['id']}"] = [line("Speaker", it["voice"], it["text"])]
        elif task["type"] == "interview":
            v = task.get("voice", "interviewer")
            out[f"{task['id']}__intro"] = [line("Interviewer", v, task["intro"])]
            for q in task["questions"]:
                out[f"{task['id']}__{q['id']}"] = [line("Interviewer", v, q["text"])]
    return out


async def render(manifest: dict, audio_dir, concurrency: int = 4) -> None:
    import edge_tts

    sem = asyncio.Semaphore(concurrency)

    async def one(entry: dict):
        name = hashlib.sha1(f"{entry['voice']}|{entry['text']}".encode()).hexdigest()[:16] + ".mp3"
        path = audio_dir / name
        if not path.exists():
            async with sem:
                try:
                    await edge_tts.Communicate(entry["text"], entry["voice"]).save(str(path))
                except Exception as e:  # network / voice errors -> browser fallback for this line
                    print(f"  tts failed ({e.__class__.__name__}): {entry['text'][:50]}", file=sys.stderr)
                    path.unlink(missing_ok=True)
                    return
        entry["file"] = name

    await asyncio.gather(*(one(e) for lines in manifest.values() for e in lines))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("test_id", nargs="?")
    ap.add_argument("--engine", choices=["edge", "browser"], default="edge")
    a = ap.parse_args()
    test_dir = find_test_dir(a.test_id or latest_test_id())
    test = load_json(test_dir / "test.json")
    manifest = clips(test, load_spec()["voices"])
    for lines in manifest.values():
        for e in lines:
            e["file"] = None
    audio_dir = test_dir / "audio"
    audio_dir.mkdir(exist_ok=True)
    n = sum(len(v) for v in manifest.values())
    if a.engine == "edge":
        try:
            print(f"Rendering {n} lines with edge-tts -> {audio_dir}")
            asyncio.run(render(manifest, audio_dir))
        except ImportError:
            print("edge-tts not installed; using browser speech. `pip install edge-tts` for real voices.")
    save_json(audio_dir / "manifest.json", manifest)
    mp3 = sum(1 for v in manifest.values() for e in v if e["file"])
    print(f"Audio ready: {mp3}/{n} lines as MP3, the rest via browser speech.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
