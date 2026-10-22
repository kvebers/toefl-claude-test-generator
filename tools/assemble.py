"""Merge per-section parts written by parallel generator subagents into tests/<id>/test.json.

usage: python tools/assemble.py <test_id> --title "..." [--mode full|practice] [--difficulty mixed] [--description "..."]
Reads tests/<id>/parts/<section>.json (each a section object: {"id": "reading", "modules": {...}}), orders them
per the spec, writes test.json and validates it.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date

from common import TESTS_DIR, load_json, load_spec, save_json
from validate import validate


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("test_id")
    ap.add_argument("--title", required=True)
    ap.add_argument("--mode", default="full", choices=["full", "practice"])
    ap.add_argument("--difficulty", default="mixed")
    ap.add_argument("--description", default="")
    ap.add_argument("--author", default="claude")
    a = ap.parse_args()
    d = TESTS_DIR / a.test_id
    parts = {p.stem: load_json(p) for p in sorted((d / "parts").glob("*.json"))}
    if not parts:
        sys.exit(f"no parts in {d / 'parts'}")
    order = load_spec()["order"]
    test = {"id": a.test_id, "title": a.title, "format": "toefl-ibt-2026", "mode": a.mode,
            "created": date.today().isoformat(), "author": a.author, "difficulty": a.difficulty,
            "description": a.description,
            "sections": [parts[s] for s in order if s in parts]}
    errors, warnings = validate(test)
    for w in warnings:
        print("WARN ", w)
    for e in errors:
        print("ERROR", e)
    save_json(d / "test.json", test)
    print(f"Wrote {d / 'test.json'}" + (" (INVALID, fix the parts and re-run)" if errors else ""))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
