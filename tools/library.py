"""Save, share and load tests.

usage:
  python tools/library.py list
  python tools/library.py publish <test_id> [--author NAME]   # tests/<id> -> library/<id> (commit it / open a PR to share)
  python tools/library.py import <file.json>                  # load a test someone shared -> tests/<id>
  python tools/library.py export <test_id> [out.json]         # single-file copy to send to someone
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys

from common import LIBRARY_DIR, ROOT, TESTS_DIR, find_test_dir, list_tests, load_json, save_json
from validate import validate


def check(test: dict) -> None:
    errors, warnings = validate(test)
    for w in warnings:
        print("WARN ", w)
    if errors:
        for e in errors:
            print("ERROR", e)
        sys.exit("Test is invalid; not saved.")


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    p = sub.add_parser("publish")
    p.add_argument("test_id")
    p.add_argument("--author")
    p = sub.add_parser("import")
    p.add_argument("file")
    p = sub.add_parser("export")
    p.add_argument("test_id")
    p.add_argument("out", nargs="?")
    a = ap.parse_args()

    if a.cmd == "list":
        for t in list_tests():
            print(f"{t['source']:8} {t['id']:42} {t['mode']:9} {','.join(s[0].upper() for s in t['sections']):8} "
                  f"{'audio' if t['audio_ready'] else 'no-audio':9} taken {t['attempts']}x  {t['title']}")
    elif a.cmd == "publish":
        test = load_json(find_test_dir(a.test_id) / "test.json")
        if a.author:
            test["author"] = a.author
        check(test)
        dest = LIBRARY_DIR / test["id"]
        if dest.exists():
            sys.exit(f"library/{test['id']} already exists. Rename the test id first.")
        save_json(dest / "test.json", test)
        print(f"Published to library/{test['id']}/test.json (audio is re-rendered locally, not committed).")
        print(f"Share it: git add library/{test['id']} && git commit -m \"Add test {test['id']}\", then open a PR.")
    elif a.cmd == "import":
        test = load_json(a.file)
        check(test)
        base, n = test["id"], 1
        while (TESTS_DIR / test["id"]).exists() or (LIBRARY_DIR / test["id"]).exists():
            n += 1
            test["id"] = f"{base}-{n}"
        save_json(TESTS_DIR / test["id"] / "test.json", test)
        print(f"Imported as tests/{test['id']}; rendering audio…")
        subprocess.run([sys.executable, str(ROOT / "tools" / "tts.py"), test["id"]], check=False)
        print(f"Take it with: make take ID={test['id']}")
    elif a.cmd == "export":
        src = find_test_dir(a.test_id) / "test.json"
        out = a.out or str(ROOT / "exports" / f"{a.test_id}.json")
        (ROOT / "exports").mkdir(exist_ok=True)
        shutil.copyfile(src, out)
        print(f"Exported to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
