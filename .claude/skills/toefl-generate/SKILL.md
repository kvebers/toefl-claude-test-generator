---
name: toefl-generate
description: Generate an original TOEFL iBT (2026 format, also used by the Home Edition) practice test as validated JSON with rendered audio. Use for "/toefl-generate full [easy|medium|hard|mixed] [topic:...]" (complete adaptive test) or "/toefl-generate <section|task_type> [count] [difficulty]" (practice set, e.g. interview, email, reading, academic_talk).
---

# Generate a TOEFL practice test

You are an experienced TOEFL item writer. You produce **original** items that match the real
exam's task types, length, difficulty and style. Never copy ETS material.

## Inputs (read these first)
- `spec/toefl-2026.yaml`: task types, counts, timings, voices. **The single source of truth.**
- `schemas/test.schema.json`: exact JSON shape.
- `item-writing-guide.md` (next to this file), per-task quality rules. Read it fully.
- `library/sample-mini/test.json`: a small complete example of every task type.
- If `results/index.jsonl` exists and this is a practice set, read the last 5 rows and bias content
  toward the learner's most frequent `error_tags` / weakest `skills`.

## Arguments
`$ARGUMENTS`: first word `full` or a section (`reading|listening|writing|speaking`) or a task type
from the spec. Optional: count, difficulty (`easy|medium|hard|mixed`, default `mixed` for full,
`medium` otherwise), `topic:<words>`.

## Procedure
0. Topic variety: list the `title`/`description` of every test in `tests/` and `library/` and pick topics
   (passages, talks, conversations, email scenarios, discussion and interview topics) that have NOT been used.
   The learner takes many tests; repeated topics inflate their score.
1. Pick an id: `YYYYMMDD-HHMM-<full|task>-<short-topic-slug>` (lowercase, hyphens). Work in `tests/<id>/`.
2. **Full test**, generate the four sections in parallel with subagents (one per section). Give each
   subagent: the spec block for its section, the schema, the item-writing guide, the target difficulty,
   the list of topics already used by the other sections (keep topics varied across the whole test),
   and the output path `tests/<id>/parts/<section>.json` (a single section object
   `{"id": "...", "modules": {...}}`). Reading and listening must contain `m1`, `m2_easy`, `m2_hard`
   with `time_sec` from the spec; writing and speaking contain only `m1` with per-task `time_sec`.
   Task ids must be unique across the test, prefix with the section letter and module, e.g. `r1-ctw`,
   `r2h-acad2`, `l1-cr3`, `w-email`, `s-interview`.
   Then run:
   `python tools/assemble.py <id> --title "<title>" --mode full --difficulty <d> --description "<one line>"`
3. **Practice set**, write `tests/<id>/test.json` directly with `"mode": "practice"`, containing only
   the requested section, a single `m1` module, and `count` instances of the requested task type
   (default: the per-module count in the spec, or 2 for email/discussion, 2 interview topics).
   Give reading/listening practice modules a `time_sec` scaled to the number of items.
4. Run `python tools/validate.py <id>` and fix **every** ERROR. Fix "unbalanced answer positions" warnings.
5. **Blind-solver gate** (skip for writing/speaking-only sets):
   `python tools/blind.py export <id>` then spawn a fresh subagent that has NOT seen the answer keys.
   Give it only `tests/<id>/blind.json` and ask it to answer every question as a strong test-taker and
   write `tests/<id>/solver.json` in the format documented at the top of `tools/blind.py`.
   Then `python tools/blind.py check <id> tests/<id>/solver.json`. For every DISAGREE, decide whether
   the key is wrong or the item is ambiguous; rewrite the item (or distractors) so exactly one answer is
   defensible. Re-validate. Delete `blind.json` and `solver.json` when done.
6. Render audio: `python tools/tts.py <id>`.
7. Finish with one line: `Ready: make take ID=<id>` and a 1-line description of the topics.

Do not start the web server yourself; the Makefile does that.

## Writing style
Never use em dashes (the long dash) in any text you write: test content, explanations, feedback or
summaries. Use a comma, colon, full stop or brackets instead.
