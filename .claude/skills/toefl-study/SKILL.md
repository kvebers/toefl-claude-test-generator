---
name: toefl-study
description: Write an easy-to-read TOEFL study guide for writing and speaking from all past responses: how the learner's structure changed between tests, a blueprint and strategy per task type, linking words, key phrases, core errors and a spelling list. Use for "/toefl-study [writing|speaking]".
---

# Writing and speaking study guide

The graded reports list every mistake per attempt. This guide is the opposite: short, reusable material to
study from, built on patterns across all attempts. Write for a learner who will print it and keep it next to
them while practising.

1. Run `python tools/study.py data $ARGUMENTS` (`$ARGUMENTS` is empty, `writing` or `speaking`). It writes
   `results/study/study_data.json`: every writing response and interview transcript (oldest first) with
   scores, goal statuses, graded errors, word/paragraph/sentence counts, linking words found per response
   (`linkers`, from `linker_bank`) and per task type totals (`per_type`).
2. Read `results/study/study_data.json` in full. Read the responses themselves, not only the error lists:
   the structure is in the text.
3. Write `results/study/study.json`:
   ```json
   {
     "generated": "YYYY-MM-DD",
     "summary": "3-4 sentences: how the writing/speaking structure has developed, the single biggest structural gap",
     "top_three": ["the three changes with the biggest expected score gain, one sentence each"],
     "types": [
       {
         "type": "academic_discussion",
         "title": "Academic discussion",
         "structure_now": "2-4 sentences: the shape the learner actually uses now (cite counts: paragraphs, words, where the example sits)",
         "structural_changes": [{"when": "2026-10-23 → 2026-10-28", "change": "what changed in the structure or strategy, with evidence", "effect": "helped | no change | hurt"}],
         "blueprint": [{"part": "Position", "purpose": "answer the professor's exact question", "template": "In my view, ... because ...", "length": "1 sentence"}],
         "strategy": ["timed step-by-step plan for the task, e.g. 'Minute 0-1: ...'"],
         "linking_words": [{"function": "Contrast", "you_use": ["however"], "add": ["whereas", "unlike"], "avoid": ["but (to start a sentence)"], "example": "Unlike Daniel, I think ..."}],
         "key_phrases": [{"phrase": "What neither of my classmates mentioned is ...", "when": "to signal your new contribution"}],
         "core_errors": [{"pattern": "Missing article before singular nouns", "tag": "grammar.article", "count": 10,
                          "examples": [{"wrong": "change battery", "right": "change the battery"}],
                          "rule": "plain-English rule", "drill": "one concrete 5-minute drill"}],
         "spelling": [{"wrong": "necesary", "right": "necessary", "tip": "one c, two s"}],
         "model": {"prompt": "short restatement of a past prompt", "parts": [{"part": "Position", "text": "model sentence(s) following the blueprint"}]}
       }
     ],
     "checklist": ["6-10 yes/no checks to run in the last minute of a writing task or before speaking"]
   }
   ```
   - One entry in `types` per task type in `per_type`, writing types first. `spelling` only for writing types.
   - `structural_changes` compares attempts with each other (first vs later, before vs after a change in
     approach): paragraphing, length, where the opinion and example appear, use of classmates' ideas, how
     interview answers open and close. Only claim changes the responses show.
   - `blueprint` follows the category goals in `spec/toefl-2026.yaml` (`goals.<type>.criteria`) and fits the
     task's time and length from the spec. 4-6 parts. Templates are sentence frames with `...` gaps, not
     whole answers.
   - `linking_words`: 5-7 functions. `you_use` only lists words in `per_type.<type>.linker_use`; `add` gives
     2-4 better or missing ones; `avoid` names overused or misused ones with evidence.
   - `key_phrases`: 8-12, specific to the task type, written at a band 5-6 level.
   - `core_errors`: 4-6 patterns, most frequent and most score-relevant first. `tag` must come from
     `.claude/skills/toefl-grade/error-taxonomy.md`. Examples are the learner's own words (shortened) and
     the fix. Group single errors into patterns; do not copy the per-attempt error list.
   - `spelling`: every misspelt word in the writing responses (graded `lexis.spelling` errors plus any the
     graders missed), deduplicated, with a short memory tip.
   - `model`: build it on a past prompt the learner answered, using the blueprint and the phrases above.
   - Keep sentences short and concrete. This is a study sheet, not a report.
4. Run `python tools/study.py check` and fix every problem until it prints OK.
5. Run `python tools/study.py render` and reply with the PDF path and a 2-line summary.

## Writing style
Never use em dashes (the long dash) in any text you write: test content, explanations, feedback or
summaries. Use a comma, colon, full stop or brackets instead.
