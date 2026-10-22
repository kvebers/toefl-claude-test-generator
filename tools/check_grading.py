"""Check results/<attempt>/grading.json against the schema and grading_input.json (used by the toefl-grade skill).

usage: python tools/check_grading.py results/<attempt_id>
"""
import sys
from pathlib import Path

from common import ROOT, load_json
from pipeline import check_grading

d = Path(sys.argv[1])
d = d if d.is_absolute() else ROOT / d
errors = check_grading(d, load_json(d / "grading_input.json"))
print("\n".join(errors) if errors else "OK")
sys.exit(1 if errors else 0)
