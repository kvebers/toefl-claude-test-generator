---
name: toefl-practice
description: Create a focused TOEFL practice set for one section or task type, targeted at the learner's weak spots from past results. Use for "/toefl-practice <task|section|weakest> [count] [easy|medium|hard]", e.g. "/toefl-practice interview", "/toefl-practice weakest".
---

# Targeted practice

1. Resolve the target from `$ARGUMENTS`:
   - a task type from `spec/toefl-2026.yaml` (e.g. `interview`, `email`, `academic_talk`, `build_sentence`),
   - a section (`reading`, `listening`, `writing`, `speaking`) → a mini module with every task type of that section,
   - `weakest` (or nothing) → read `results/index.jsonl` (last 5 rows): pick the task type behind the most
     frequent `error_tags` and the lowest `skills` accuracy / `task_scores`. Say in one line what you picked and why.
2. If history exists, collect the learner's top error tags and the topics already used in their recent tests
   (`results/*/test.json` titles/topics) so you pick fresh topics and **design items that exercise those
   weaknesses** (e.g. many `reading.inference` questions; build-sentence items on `grammar.word_order`;
   interview questions that require comparing and justifying).
3. Generate the set by following `.claude/skills/toefl-generate/SKILL.md` in practice mode
   (steps 1, 3–7), with difficulty from the arguments, default `medium`, or one step above the learner's
   latest band for that section (band ≤3 → easy, 3.5–4.5 → medium, ≥5 → hard).
4. Finish with: `Ready: make take ID=<id>`.

## Writing style
Never use em dashes (the long dash) in any text you write: test content, explanations, feedback or
summaries. Use a comma, colon, full stop or brackets instead.
