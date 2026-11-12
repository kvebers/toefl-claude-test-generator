# Scoring rubrics (0-6)

These are this project's own descriptors, modelled on the public description of what TOEFL raters
reward. The 0-6 scale matches the section bands (a task score of 4.5 reads like a band of 4.5).
Half points are allowed. Score the *response*, not the person.

## Write an Email
Dimensions: task completion · organisation · language use · register/tone

| Score | Descriptor |
|---|---|
| 6 | All three points fully and clearly addressed. Well organised with smooth connections. Wide, precise vocabulary and varied, accurate grammar; at most one or two minor slips. Tone fully appropriate to the reader (polite request, formal/informal as the situation needs). |
| 5 | All three points well addressed. Clear organisation with good connections. Good range and control; a few minor errors that never obscure meaning. Tone appropriate. |
| 4 | All points addressed, one possibly less developed. Clear organisation. Adequate range; some errors that do not obscure meaning. Tone mostly appropriate. |
| 3 | Points mostly addressed but one is vague or thin. Understandable organisation. Limited range and noticeable errors that occasionally obscure meaning. Tone may slip. |
| 2 | One point missing or the purpose is unclear. Weak organisation. Frequent errors; meaning is often unclear. Tone may be inappropriate. |
| 1 | Very little relevant content; errors make most of it hard to follow. |
| 0 | No response, copied the prompt, off-topic, or not English. |

## Write for an Academic Discussion
Dimensions: relevance & contribution · development & support · language use · coherence

| Score | Descriptor |
|---|---|
| 6 | Directly answers the professor's question and adds a new idea beyond the classmates' posts. Clear position, well explained with reasons and specific examples. Varied, precise vocabulary and syntax; almost no errors. |
| 5 | Relevant, clear and new contribution, well supported with a reason and an example. Easy to follow. Good range; a few minor errors. |
| 4 | Relevant, clear contribution with adequate support. Easy to follow. Some errors that do not affect meaning. |
| 3 | Relevant but partly underdeveloped, generic, or mostly repeats a classmate. Some lapses in coherence; noticeable errors and limited range. |
| 2 | Weak or partly off-topic contribution, little explanation. Frequent errors that obscure meaning. |
| 1 | Barely related or very short; language makes it hard to understand. |
| 0 | No response, copied text, off-topic, or not English. |

Length note: under ~80 words rarely earns above 3.5; length alone never earns a high score.

## Take an Interview (per question)
Dimensions: task fulfilment · fluency & delivery (from metrics) · language use · coherence

| Score | Descriptor |
|---|---|
| 6 | Fully answers the question with relevant detail/examples, well connected. Fluent: steady pace (~110-160 wpm), few long pauses or fillers. Wide, accurate vocabulary and grammar. Uses most of the 45 seconds. |
| 5 | Answers well with clear detail. Mostly fluent, occasional hesitation. Good range with minor errors. Uses most of the time. |
| 4 | Answers the question with some detail. Some hesitation or fillers. Adequate control; errors rarely affect meaning. |
| 3 | Answers the question but with limited development or partly generic content. Noticeable pauses/fillers or a slow pace. Errors and limited range, meaning still clear. |
| 2 | Partial or unclear answer, very short (under ~20 s of speech). Frequent hesitation. Errors often obscure meaning. |
| 1 | A few relevant words or phrases only. |
| 0 | No response or unrelated. |

Delivery evidence available: `wpm`, `pauses` (>0.5 s), `long_pauses` (>1.5 s), `fillers`, `duration`
vs `answer_sec`, `speech_start` (late start = hesitation), `mean_word_prob` and `low_confidence_words`
(possible pronunciation problems, mention only as "may have been unclear").

## Listen and Repeat
Scored automatically from word accuracy (in pipeline), 0-6 per sentence. Only comment on patterns,
e.g. dropping function words, struggling once sentences exceed ~12 words.
