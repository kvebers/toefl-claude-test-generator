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
**complete_the_words**: one academic-style paragraph of 70–100 words (3 per full test: 2 in module 1, 1 in module 2). Leave the first sentence intact.
From the second sentence, damage every second word: keep the first half of its letters (round up),
mark the missing half in brackets: `exa[mple]`, `o[f]`, `bi[rds]`. One-letter words are skipped.
Exactly 10 gaps. Missing parts must be uniquely recoverable from context and spelling.

**daily_life**: short real-world text (easier: 15–50 words, harder: up to 150 words), in sets of 2 or 3 questions: email, notice, menu, schedule, ad, text
message, form, social post. Set `text.genre`. 2–3 questions: detail, inference, purpose.

**academic_passage**: 150–200 words (ETS maximum is about 200), title, 2–3 paragraphs, introductory textbook register.
5 questions mixing detail, vocabulary-in-context ("The word X in paragraph N is closest in meaning to"),
inference, purpose/rhetorical function, negative factual (NOT/EXCEPT).

## Listening
Balance accents across the test: US, Canadian, British and Australian voices (see `voices` in the spec),
and both genders. Scripts must sound spoken: contractions, short sentences, occasional self-correction or "um" in
conversations (not in announcements). Assign voices from the spec (`male_1`, `female_2`, `narrator`,
...). Use two different-gender voices in conversations. `speaker` is a role label ("Student",
"Professor", "Employee").

**choose_response**: one brief natural utterance of at most about six stressed syllables (question,
request, complaint, suggestion, indirect statement), e.g. "Do you know if the lab's open tonight?". 4 written reply options; the right one is pragmatically appropriate, distractors repeat
words from the prompt, answer a different question, or are grammatically fine but socially wrong.
Prompt text: "Choose the best response."

**conversation**: 35–100 words in 4–8 short turns, campus or everyday service setting, a problem and a resolution. 2 questions
(gist/detail/next action/inference). Provide `context`.

**announcement**: 35–100 words, single speaker, campus/workplace/public. 2 questions.

**academic_talk**: 150–250 words (ETS maximum is 250) by a professor (may include one brief student question as a separate
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
7 sentences, all said by the same voice, growing from one simple clause (4–5 words) to sentences with
compound verbs, dependent or relative clauses and complex noun phrases (16–20 words). Use natural contractions. `response_sec`: the
spec's `listen_and_repeat.response_sec` range, the low end for the shortest rising to the high end for the longest. Natural, useful sentences, no tongue twisters or rare names.

**interview**: one topic, a friendly `intro` (1–2 sentences), 4 questions that go from brief factual answers to
opinion, explanation, prediction and narration (e.g. describe -> tell about a time -> compare/predict -> opinion
on a broader issue). Topics may come from everyday life or familiar academic areas (life sciences, history, business). Each answerable in 45 s. Questions do not depend on previous answers. `answer_sec` 45,
`voice` "interviewer".
