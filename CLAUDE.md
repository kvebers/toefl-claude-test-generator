# Project notes for Claude

- `spec/toefl-2026.yaml` is the single source of truth for task types, counts, timings, voices and score
  conversions. Never hard-code those elsewhere.
- Test JSON must pass `python tools/validate.py <id>`; grading JSON must pass `python tools/check_grading.py <dir>`.
- Error tags come only from `.claude/skills/toefl-grade/error-taxonomy.md` (append-only; trends depend on it).
- Answer keys must never be sent to the browser: the server uses `common.sanitize()`.
- `results/` and `tests/` are user data and git-ignored; shared tests live in `library/`.
- Run `make check` after changing scoring, reports or trends.
