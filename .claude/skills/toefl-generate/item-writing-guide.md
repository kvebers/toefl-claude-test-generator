# Item-writing guide (TOEFL iBT 2026 format)

General rules
- Everything original: invented people, places, studies. Real-world facts in academic texts must be
  accurate and uncontroversial (textbook-level science, history, social science, arts).
- Topics: no politics, religion, violence, medical advice, culturally narrow knowledge. Campus life,
  work, daily errands, nature, technology, history, arts, economics, psychology.
- Each MC question has exactly one defensible answer. Distractors are plausible: they reuse words from
  the text, state something true but irrelevant, reverse a relationship, or overgeneralise.
  Keep options similar in length; avoid "all/none of the above".
- Spread correct answers evenly across positions A–D (validator warns otherwise).
- Every MC question needs `skill` (taxonomy tag) and a one-sentence `explanation` quoting/pointing to the evidence.
- Difficulty: module 1 = mixed B1–C1. `m2_easy` = mostly A2–B2 (shorter texts, literal questions).
  `m2_hard` = B2–C2 (denser texts, inference, purpose, rhetorical function, idiomatic speech).

Skill tags for MC questions
reading.detail, reading.main_idea, reading.inference, reading.vocabulary, reading.purpose,
reading.negative_factual, reading.cause_effect, reading.reference, reading.vocabulary.form,
listening.detail, listening.main_idea, listening.inference, listening.purpose, listening.attitude,
listening.response, listening.organization, grammar.word_order, grammar.tense, grammar.agreement,
grammar.comparatives, grammar.questions, grammar.clauses

## Reading
**complete_the_words**: one academic-style paragraph of 70–100 words. Leave the first sentence intact.
From the second sentence, damage every second word: keep the first half of its letters (round up),
mark the missing half in brackets: `exa[mple]`, `o[f]`, `bi[rds]`. One-letter words are skipped.
Exactly 10 gaps. Missing parts must be uniquely recoverable from context and spelling.

**daily_life**: short real-world text (40–150 words): email, notice, menu, schedule, ad, text
message, form, social post. Set `text.genre`. 2–3 questions: detail, inference, purpose.

**academic_passage**: 180–230 words, title, 2–3 paragraphs, introductory textbook register.
5 questions mixing detail, vocabulary-in-context ("The word X in paragraph N is closest in meaning to"),
inference, purpose/rhetorical function, negative factual (NOT/EXCEPT).

## Listening
Scripts must sound spoken: contractions, short sentences, occasional self-correction or "um" in
conversations (not in announcements). Assign voices from the spec (`male_1`, `female_2`, `narrator`,
...). Use two different-gender voices in conversations. `speaker` is a role label ("Student",
"Professor", "Employee").

**choose_response**: one natural utterance (question, request, complaint, suggestion, indirect
statement). 4 written reply options; the right one is pragmatically appropriate, distractors repeat
words from the prompt, answer a different question, or are grammatically fine but socially wrong.
Prompt text: "Choose the best response."

**conversation**: 6–10 turns, campus or everyday service setting, a problem and a resolution. 2 questions
(gist/detail/next action/inference). Provide `context`.

**announcement**: 60–110 words, single speaker, campus/workplace/public. 2 questions.

**academic_talk**: 250–350 words by a professor (may include one brief student question as a separate
line). Clear structure: topic, definition, example, contrast/implication. 4 questions: main idea, detail,
purpose of an example, inference/attitude.

## Writing
**build_sentence**: 10 items per real test. `prompt` is something one person says; the learner builds
the reply. 4–7 `chunks` (single words or short phrases), shuffled, plus optional fixed `start`/`end`
(e.g. end "."). Exactly one grammatical ordering. Test word order: indirect questions, adverb placement,
auxiliaries, relative clauses, comparatives, phrasal verbs. `chunks` must be a permutation of `answer`
and NOT already in answer order. Add `skill` (grammar.*) and an `explanation`.

**email**: a realistic situation (neighbour, landlord, manager, professor, club organiser, company),
`to`, `subject`, exactly 3 `bullets` the email must cover (e.g. explain / describe / request / suggest).
`time_sec` 420.

**academic_discussion**: course name, professor post (2–4 sentences ending in an open question), two
student posts (2–3 sentences each) taking different positions so the learner can add a new idea.
`time_sec` 600.

## Speaking
**listen_and_repeat**: one `setting` (guide training, new-employee orientation, lab assistant...).
7 sentences, all said by the same voice, growing from 4–5 words to 16–20 words. `response_sec`: 6 for
the shortest rising to 12 for the longest. Natural, useful sentences, no tongue twisters or rare names.

**interview**: one topic, a friendly `intro` (1–2 sentences), 4 questions that go from personal and
concrete to abstract and opinion-based (experience -> describe -> compare -> opinion on a broader
issue). Each answerable in 45 s. Questions do not depend on previous answers. `answer_sec` 45,
`voice` "interviewer".
