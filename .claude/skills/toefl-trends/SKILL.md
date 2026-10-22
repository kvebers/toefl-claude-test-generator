---
name: toefl-trends
description: Analyse the learner's TOEFL practice history (scores and error types over time), estimate their current level and write a study plan into the progress PDF. Use for "/toefl-trends".
---

# Progress analysis

1. Run `python tools/trends.py data` (creates `results/trends/trends.json` and charts).
2. Read `results/trends/trends.json`. For the 3 most recent attempts also skim `results/<attempt>/grading.json`
   (`overall` and task `summary` fields only) for qualitative evidence.
3. Write `results/trends/analysis.json`:
   ```json
   {
     "summary": "4-6 sentences: trajectory per section, what changed, what didn't",
     "predicted_band": 4.5,
     "predicted_total_120": 88,
     "confidence": "low|medium|high (based on number of full tests and score spread)",
     "improving": ["short evidence-based items, cite tags and numbers"],
     "persistent": ["weaknesses that have not improved, with numbers"],
     "plan": [ {"when": "Days 1-2", "what": "concrete drill", "command": "make practice TASK=..."} ]
   }
   ```
   - Prediction: weight recent full tests most; treat practice-set section bands as weaker evidence.
     If fewer than 2 full tests, say so and set confidence `low`.
   - Plan: 5–7 entries covering ~2 weeks, ending with a full test (`make test`). Prioritise by expected
     score gain: the lowest section and the most frequent persistent tags first.
   - Use only numbers present in the data; never invent attempts.
4. Run `python tools/trends.py render` and reply with the PDF path and a 2-line summary.

## Writing style
Never use em dashes (the long dash) in any text you write: test content, explanations, feedback or
summaries. Use a comma, colon, full stop or brackets instead.
