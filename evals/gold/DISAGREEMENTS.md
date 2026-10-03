# Gold label decisions for `note_extract` (scorer `notes-1`)

The gold in `note_extract.jsonl` was hand-labelled from the definitions in
`petpulse/llm/prompts/note_extract.v1.md`, not from any model or fake output. `urgent` and
`needs_review` follow the code rules in `petpulse.services.notes.decide` applied to the
labelled facts. These are the cases where a second labeller could reasonably disagree, and
the call made:

| case | question | call | why |
|------|----------|------|-----|
| f02 | "collapsed on the walk": MEDICAL or MIXED? | MEDICAL | The walk is where it happened, not a routine-care report. |
| f04 | "got into the chocolate cake and ate a big slice": MEDICAL or MIXED? | MEDICAL | Toxin ingestion is the fact; "ate" is not a meal report. |
| m03 | vet visit plus prescribed drops: MEDICAL or MIXED? | MEDICAL | Prescribed treatment is part of the medical event, not scheduled medication. |
| m06 | diarrhea three times: is this `blood`/`repeated_vomiting`? | no flag, MEDICAL | Neither flag's definition covers diarrhea. |
| n03 | "the vet said it was not a seizure": MEDICAL or OTHER? | MEDICAL, seizure denied | Reports a vet's assessment of an episode. |
| a01 | "maybe some blood in his stool": MEDICAL or MIXED? | MEDICAL, blood ambiguous | The stool is mentioned only as where the possible blood was. |
| a02 | "not sure if he ate any of the raisins": ambiguous or denied? | ambiguous | "Not sure" is uncertainty, not a denial. |
| i02 | injection text names a seizure | no flag | The seizure is only in an instruction aimed at the model. |
| h01 | sarcastic "threw up for the third time" | repeated_vomiting present | Third time = more than once, whatever the tone. |
| h02 | "red streaks in what he brought up again" | blood present, repeated_vomiting present | Indirect wording for blood in vomit; "again" = more than once. |
| h03 | "He's been weird today." | OTHER, no review | Too vague for a category, long enough to read: not UNKNOWN. |

Hard cases (`h*`) are expected to fail with the keyword fake. A live-model run is the only
evaluation of extraction quality; the fake run is a pipeline test.
