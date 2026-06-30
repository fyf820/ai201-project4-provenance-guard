# ai201-project4-provenance-guard

## Architecture

Provenance Guard is a Flask-based backend that accepts text submissions, runs them through a multi-signal attribution pipeline, returns a reader-facing transparency label, and preserves every decision in a structured audit log. The same core record is also used by the appeal workflow and the verified-human review flow.

### End-to-end submission flow

```text
Client / Platform
    |
    | POST /submit (raw text, optional metadata)
    v
Flask API
    |
    | validate payload
    v
Rate Limiter
    |
    | allow / reject request
    v
Submission Controller
    |
    | normalize text, create submission record
    v
Preprocessor
    |
    | cleaned text + simple features
    v
Detection Signals
    |--- LLM-based classification
    |--- Stylometric heuristics
    |--- Repetition / redundancy
    v
Ensemble Detector
    |
    | weighted score
    v
Confidence Scorer
    |
    | calibrated confidence
    v
Decision Classifier
    |
    | likely human / uncertain / likely AI
    v
Transparency Label Generator
    |
    | plain-language label text
    v
Audit Logger
    |
    | decision, score, signals, label, timestamp
    v
Database / Storage
    |
    | persisted submission + audit trail
    v
Response Serializer
    |
    | JSON response
    v
Platform UI
    |
    | shows label to reader
```

### Appeals flow

```text
Creator / Platform
    |
    | POST /appeal (content ID, reasoning, optional context)
    v
Flask API
    |
    | validate appeal request
    v
Appeal Handler
    |
    | update status -> under_review
    v
Human Reviewer Queue
    |
    | queue item with original label, confidence, signals, and appeal text
    v
Human Reviewer
    |
    | approve / deny appeal outcome
    v
Audit Logger
    |
    | original decision + appeal text + label + confidence
    v
Database / Storage
    |
    | persisted appeal record
    v
Response Serializer
    |
    | appeal confirmation
    v
Platform UI
    |
    | shows appeal status or review notes
```

### Provenance certificate flow

```text
Creator / Platform
    |
    | POST /verify-human (content ID, reasoning, optional supporting context)
    v
Flask API
    |
    | validate verification request
    v
Verification Handler
    |
    | mark pending human review
    v
Human Reviewer Queue
    |
    | queue item with original label, confidence, signals, and verification context
    v
Human Reviewer
    |
    | POST /verify-human/approve after reviewing evidence
    v
Audit Logger
    |
    | verification request + reviewer decision + credential status
    v
Database / Storage
    |
    | persisted credential record
    v
Platform UI
    |
    | shows verified-human badge if approved
```

### Core components

- Client / Platform Integration: sends submissions, appeals, and verification requests; displays the resulting label or badge.
- Flask API: receives requests and returns structured JSON responses.
- Rate Limiter: enforces submission quotas.
- Submission Controller: orchestrates the submission pipeline.
- Preprocessor: cleans text and extracts lightweight features.
- Detection Signals: compute independent evidence for AI-likeness.
- Ensemble Detector: combines signal outputs into one score.
- Confidence Scorer: turns the score into calibrated certainty.
- Decision Classifier: maps the score to human, uncertain, or AI.
- Transparency Label Generator: produces reader-facing label text.
- Appeal Handler: records creator objections and moves content to under_review.
- Verification Handler: routes verified-human requests to manual review.
- Audit Logger: records submissions, labels, appeals, and verification events.
- Database / Storage: persists submissions, decisions, appeals, and credentials.
- Response Serializer: formats the API response.
- Human Reviewer Queue: surfaces items that need manual review.
- Human Reviewer: makes the final decision on appeals and verified-human requests.

## Detection Signals

The attribution pipeline uses three distinct signals so the final decision does not depend on any single heuristic.

### 1. LLM-based classification - 50%
- What it measures: overall semantic coherence, voice consistency, and whether the text feels human-written, AI-generated, or uncertain.
- Output: a score from `0.0` to `1.0` representing AI-likelihood.
  - `0.0` means strongly human.
  - `1.0` means strongly AI-generated.
- Why this signal matters: it captures the broadest, most holistic view of the writing.

### 2. Stylometric heuristics - 25%
- What it measures: sentence-length variance, type-token ratio, punctuation density, repetition rate, and average sentence complexity.
- Output: a score from `0.0` to `1.0` representing AI-likelihood.
- Implementation:
  - The detector lowercases the text and extracts words using a simple word regex.
  - It splits the text into sentences and counts the number of words in each sentence.
  - It computes sentence-length variance. Lower variance increases `regularity_score` because highly uniform sentence structure can look machine-like.
  - It computes type-token ratio, which is the number of unique words divided by total words. Lower vocabulary variety increases `diversity_score`.
  - It computes repeated-word ratio, punctuation density, and first-person pronoun ratio.
  - It counts generic AI-style phrases such as `it is important to note`, `transformative paradigm shift`, `ethical implications`, `responsible deployment`, `comprehensive`, `scalable`, and `future iterations`.
  - It computes `polished_formality_score` when the text has longer sentences, little or no first-person voice, high type-token ratio, and low punctuation density.
- Internal metric meanings:
  - `regularity_score`: higher when sentence lengths are unusually uniform.
  - `diversity_score`: higher when vocabulary diversity is lower.
  - `repetition_score`: higher when words repeat more often.
  - `punctuation_score`: higher when punctuation density is high.
  - `generic_phrase_score`: higher when the text contains known polished AI-style phrases.
  - `first_person_inverse`: higher when the text has little personal voice.
  - `polished_formality_score`: higher when the text is formal, smooth, and impersonal.
- AI-likelihood is computed as:

  `ai_likelihood = (`
  `    0.18 * regularity_score`
  `    + 0.15 * diversity_score`
  `    + 0.12 * repetition_score`
  `    + 0.08 * punctuation_score`
  `    + 0.27 * generic_phrase_score`
  `    + 0.10 * first_person_inverse`
  `    + 0.10 * polished_formality_score`
  `)`

- Why this signal matters: it captures structural writing patterns that are hard to see from semantic analysis alone. It is especially useful for separating casual, irregular writing from polished, generic, impersonal writing. It is kept as a supporting signal because some human writing, such as academic work or formal essays, can also be polished and impersonal.

### 3. Repetition / redundancy signal - 25%
- What it measures: repeated phrases, near-duplicate sentences, n-gram reuse, and overly uniform phrasing.
- Output: a score from `0.0` to `1.0` representing AI-likelihood.
- Implementation:
  - The detector normalizes sentences by lowercasing them and keeping only word tokens.
  - It computes `sentence_duplication_score` from the ratio of repeated normalized sentences.
  - It builds 2-grams and 3-grams from the text and computes how often those short phrases repeat.
  - It computes `structural_redundancy_score` by boosting repeated n-gram reuse, because near-duplicate AI sentences often repeat phrase shapes without being exact sentence copies.
  - It computes `immediate_repeat_ratio` for back-to-back repeated words.
  - It reuses the generic AI phrase list to compute `boilerplate_score`, which captures repeated or formulaic AI-style language even when the exact sentences are not duplicated.
- Internal metric meanings:
  - `sentence_duplication_score`: higher when full normalized sentences repeat.
  - `repeated_ngram_score`: higher when 2-word or 3-word phrases recur.
  - `structural_redundancy_score`: a stronger version of n-gram repetition used to catch near-duplicate sentence structure.
  - `boilerplate_score`: higher when the text contains generic AI-style wording.
  - `immediate_repeat_ratio`: higher when the same word appears back-to-back.
- AI-likelihood is computed by taking the strongest redundancy cue:

  `ai_likelihood = max(sentence_duplication_score, structural_redundancy_score, boilerplate_score * 0.75, immediate_repeat_ratio)`

- Why this signal matters: it detects internal pattern reuse that often appears in generated text. The detector uses `max(...)` instead of averaging because a single strong redundancy pattern should be visible rather than diluted by the other metrics. This makes it more useful as an independent check alongside the LLM and stylometric signals.

### Combining the signals

Each signal returns a continuous score rather than a binary flag. The raw signal outputs are first normalized onto the same `0.0` to `1.0` AI-likelihood scale, then combined as a weighted average:

`ensemble_ai_score = (0.50 * llm_score) + (0.25 * stylometric_score) + (0.25 * repetition_score)`

The LLM signal receives the highest weight because it captures semantic meaning, voice, and overall authorship impression across the whole submission. Stylometric and repetition signals are weighted evenly as supporting checks because they measure concrete text properties, but either one can produce false positives for certain human writing styles such as poetry, formal essays, or intentionally repetitive creative work.

## Uncertainty representation

The system treats `0.5` as the uncertainty midpoint.

Calibration maps the raw ensemble score into a confidence value that reflects how far the prediction is from that midpoint:

`confidence = max(ensemble_ai_score, 1 - ensemble_ai_score)`

That means:
- A confidence score of `0.6` means the system is only moderately confident and the decision is still relatively close to the uncertainty boundary.
- A confidence score of `0.9` means the system is much more certain and the label should be much stronger.

Thresholds:
- `0.00 to 0.34` of `ensemble_ai_score` -> likely human
- `0.35 to 0.64` of `ensemble_ai_score` -> uncertain
- `0.65 to 1.00` of `ensemble_ai_score` -> likely AI

This design makes borderline cases visible instead of forcing a false binary answer. A score near `0.51` should surface as uncertain, while a score near `0.95` should produce a strong label.

## Transparency label

The reader-facing label uses plain language, a short explanation, and a confidence percentage so non-technical users can understand both the result and how sure the system is.

The label variants are:

- High-confidence AI: `Likely AI-generated. This post appears to have been created with AI tools. Confidence: {confidence}%`
- High-confidence human: `Likely human-written. This post appears to have been written by a person. Confidence: {confidence}%`
- Uncertain: `Uncertain. We cannot tell with confidence whether this post was written by a person or by AI. Confidence: {confidence}%`

Label rules:
- Show `Likely human-written` when `ensemble_ai_score < 0.35`
- Show `Uncertain` when `0.35 <= ensemble_ai_score <= 0.64`
- Show `Likely AI-generated` when `ensemble_ai_score > 0.65`

The confidence percentage is shown as the system's certainty about the chosen label, not as a raw AI-likelihood score. This keeps the label readable while still exposing meaningful uncertainty.

## Appeals workflow

Creators can appeal a classification if they believe their work was misclassified.

### Request
- The original creator of the content, or an authenticated account acting on their behalf if the platform supports delegated moderation support.
- Appeals are only allowed for submissions that already have a classification result.

### What the appeal includes
- The content ID being challenged.
- The creator's reasoning for the appeal.
- Optional supporting context, such as draft notes or a brief explanation of style or authorship.
- The original label is attached to the appeal so the reviewer can see what was shown to the user.
- The original audit log entry, including the confidence score, signals used, combined score, and any prior appeal history, is included for review context.

### Human review
- A reviewer checks the original content, the original label, the confidence score, the signal breakdown, and the creator's reasoning.
- The reviewer can confirm the original decision or mark the item as needing further manual follow-up.
- The appeal enters a human review queue and the content status is set to `under_review` while it waits.

### What the system does when an appeal is received
- Accepts `POST /appeal`.
- Validates that the appeal refers to an existing classified submission.
- Updates the content status to `under_review`.
- Stores the appeal text alongside the original decision in the audit log, including the original label, confidence score, signals used, and appeal metadata.
- Does not automatically re-run classification.
- Only updates the final outcome if a human reviewer approves a change after review.
- Returns a confirmation response that the appeal was received and the item is under review.

### What the human reviewer sees
- The original content and its current status.
- The original attribution result.
- The confidence score and transparency label that were shown to the user.
- The signal breakdown used to reach the original decision.
- The creator's appeal statement.
- The audit history for the submission, including the original decision and the appeal event.

### Outcome
- If the reviewer upholds the original decision, the content stays under review history only and no label change is required.
- If the reviewer decides the classification should be reconsidered later, the system can record that note without automatically re-running detection.

### Appeal flow

`POST /appeal` -> `status update` -> `audit log` -> `response`

Arrow labels:
- `POST /appeal`: raw appeal payload, including content ID and creator reasoning
- `status update`: content status changes from `classified` to `under_review`
- `audit log`: original decision, original label, signal scores, combined score, confidence score, and appeal text are recorded together
- `response`: confirmation that the appeal was received and the item is queued for human review

This flow keeps the original decision visible, preserves accountability, and gives the reviewer enough context to make a manual judgment without retraining or reclassification.

## Provenance certificate

Creators can earn a verified-human credential through an additional human review step.

### Request
- The content ID to be verified.
- The creator's reasoning for why the content should be treated as human-written.
- Optional supporting context, such as draft history, notes, or authorship background.

### Human review
- A reviewer checks the content, the original attribution result, and the creator's proof or context.
- The reviewer decides whether the creator should receive a verified-human credential.
- The verification request enters a human review queue and the content status is set to `under_review` while it waits.

### What the human reviewer queue contains
- Pending verification requests waiting for manual review.
- The content ID, creator reasoning, and optional supporting context for each request.
- The original attribution result, confidence score, and transparency label.
- Any prior appeals or review notes tied to the same submission.

### What the human reviewer sees
- The original content and attribution result.
- The confidence score and transparency label.
- The creator's verification statement and supporting context.
- The audit history for the content, including any prior appeals or review notes.
- The verification queue item and its current `under_review` state.

### Outcome
- If approved, the creator receives a `Verified human` credential.
- If denied, the content keeps its existing attribution status and no credential is shown.
- The reviewer decision is recorded in the audit log and the queue item is closed.

### What the system does
- Accepts a verification request for a specific submission.
- Marks the submission as pending human verification.
- Sends the request to a human reviewer.
- Stores the request in the audit log alongside the original content and attribution result.
- Does not automatically change the attribution label unless the reviewer approves the credential.
- Only updates the verified-human credential if a human reviewer approves the request after review.
- Accepts `POST /verify-human/approve` from a reviewer to approve a pending request.
- When approved, stores `credential_status: approved`, `badge_text: Verified human`, and `display_badge: true`.

### How it is displayed on content
- Approved content shows a visible badge such as `Verified human` or `Verified human by review`.
- The badge should appear near the transparency label so readers can distinguish platform verification from the AI detection result.
- The badge only indicates that a human reviewer confirmed the creator's provenance claim; it does not replace the attribution label.

Approved credential response example:

```json
{
  "credential_status": "approved",
  "badge_text": "Verified human",
  "display_badge": true,
  "standard_transparency_label": "Likely human-written. This post appears to have been written by a person. Confidence: 81%"
}
```

### Verification flow

`POST /verify-human` -> `human review queue` -> `POST /verify-human/approve` -> `audit log` -> `credential response`

Arrow labels:
- `POST /verify-human`: content ID, creator reasoning, and optional supporting context
- `human review queue`: reviewer checks the submission and provenance claim
- `POST /verify-human/approve`: reviewer ID and optional review notes
- `audit log`: verification request, reviewer decision, and credential status are recorded
- `credential response`: approved response, plus the visible badge state

## Analytics dashboard

The dashboard will present a simple operational view of how the system is behaving over time.

### Metrics to show
- Detection pattern distribution: the ratio of `likely AI`, `likely human`, and `uncertain` verdicts.
- Appeal rate: the percentage of classified submissions that are appealed by creators.
- Appeal overturn rate: the percentage of appeals that result in a changed decision or credential outcome after human review.
- Human review rate: the percentage of appealed or flagged items that receive a human review.

### Why these metrics matter
- Detection pattern distribution shows whether the system is leaning too heavily toward one label.
- Appeal rate shows how often creators disagree with the result.
- Appeal overturn rate shows whether the system is producing too many mistaken classifications.
- Human review rate shows how much of the workflow is being handled by people rather than automation.

### Dashboard behavior
- Each metric should be visible as a simple count, percentage, or ratio.
- The dashboard should use audit log data so the numbers reflect the same events stored for submissions and appeals.
- The view should be lightweight and easy to scan, not a full analytics suite.

## Anticipated edge cases

The system will handle some content types poorly because the signals can confuse style with authorship.

- A poem or lyric with heavy repetition, short lines, and simple vocabulary may look AI-generated even when it was clearly written by a human.
- A polished essay written by a strong human writer who naturally uses formal, consistent phrasing may score as AI-like because the stylometric signal sees low variance and high regularity.
- AI-generated text that a human has lightly edited for tone or grammar may look more human than it really is, because the edits can reduce repetition and make the writing style less uniform.
- Text written by a non-native speaker may be flagged as uncertain or AI-like if sentence structure and vocabulary patterns differ from the training assumptions behind the heuristics.
- Very short submissions, such as a title, tagline, or one-paragraph blurb, may not contain enough signal for a reliable score, so the system should lean toward uncertainty.

These edge cases are important because they show where the score is measuring style signals rather than true authorship, which is why the appeal flow and uncertainty label are both necessary.

## AI Tool Plan

### M3 (submission endpoint + first signal)
I'll give my architecture and detection signals section, ask it use Flask app skeleton to build the submission endpoint and first signal. Then writing tests to make sure it works.

### M4 (second signal + confidence scoring)
I'll give it my architecture, uncertainty representation, and detection signals section, ask ai to build second and third signals and confidence scoring system. I'll check if the confidence score works and vary meaningfully between clearly AI and clearly human text with my edge cases.

### M5 (production layer)
I'll give my architecture, uncertainty representation, appeal flow, Provenance certificate and analytics dashboard to ask it generate those features. I'll verify if the label variants are aligned with design and confidence, appeal and certification works correctly, and dashboard shows correct data. 

## Known Limitation
- Formal human writing may be misclassified as AI-generated.

The system may incorrectly score polished academic essays, professional blog posts, technical explanations, or writing by a very formal human author as AI-like. This happens because the stylometric signal rewards features such as smooth sentence structure, low emotional/personal language, generic formal phrasing, and consistent tone. Those features can appear in AI-generated text, but they can also be completely normal for human writers in academic or professional contexts.

- Lightly edited AI-generated text may be misclassified as human or uncertain.

If someone generates text with AI and then edits it to add personal details, vary the sentence structure, and remove repeated phrases, the stylometric and repetition signals may become less suspicious. The LLM signal may still catch some semantic patterns, but the final ensemble could land in the uncertain range instead of likely AI.

## Rate limiting

The `/submit` endpoint uses Flask-Limiter with this limit:

```text
10 submissions per minute; 100 submissions per day per client IP
```

I chose `10 per minute` as the short-term limit because a real writer manually submitting poems, blog posts, or story excerpts is unlikely to submit more than 10 separate pieces in one minute. That still allows quick demos and normal retry behavior, but it blocks a simple script from flooding the detector endpoint.

I chose `100 per day` as the longer-term limit because a creative platform user might submit several drafts or posts over a day, but 100 daily attribution requests from one IP is already much higher than normal individual writing behavior. The daily limit protects the Groq-backed detector from repeated automated use while still being generous for a class project or demo.

For local development, the limiter uses in-memory storage:

```python
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[],
    storage_uri="memory://",
)
```

The submit route applies the limit directly:

```python
@api.post("/submit")
@limiter.limit("10 per minute;100 per day")
def submit():
    ...
```

I tested rate limiting by sending 12 rapid requests to `/submit`, which is more than the `10 per minute` quota:

```
201
201
201
201
201
201
201
201
201
201
429
429
```

Successful `/submit` responses are `201 Created`, not `200`, so this is the expected passing pattern: the first 10 requests are allowed, and requests 11 and 12 are blocked with `429`.

## Generated Audit Log Entries

I generated fresh structured audit evidence from four saved sample submissions:

- clearly AI-generated
- clearly human-written
- borderline formal human writing
- borderline lightly edited AI output

The project saves this evidence in two files:

- `audit_log.jsonl`: JSON Lines audit log used by the app
- `audit_log_examples.json`: pretty-printed copy for README/demo review

Each submission entry includes `timestamp`, `content_id`, `attribution`, `confidence`, `llm_score`, `stylometric_score`, `repetition_score`, `status`, and `appeal_filed`. The appeal entry includes the creator's reasoning, `status: "under_review"`, `appeal_filed: true`, and the original decision snapshot.

```
[
  {
    "event_type": "submission_created",
    "timestamp": "2026-06-30T08:56:17.403Z",
    "content_id": "cnt_711511d0c8f9",
    "creator_id": "audit-example-ai",
    "attribution": "likely_ai",
    "combined_score": 0.7636,
    "confidence": 0.7636,
    "label": "Likely AI-generated. This post appears to have been created with AI tools. Confidence: 76%",
    "llm_score": 0.9,
    "stylometric_score": 0.5044,
    "repetition_score": 0.75,
    "status": "classified",
    "appeal_filed": false
  },
  {
    "event_type": "submission_created",
    "timestamp": "2026-06-30T08:56:17.405Z",
    "content_id": "cnt_0dd8590a6b43",
    "creator_id": "audit-example-human",
    "attribution": "likely_human",
    "combined_score": 0.089,
    "confidence": 0.911,
    "label": "Likely human-written. This post appears to have been written by a person. Confidence: 91%",
    "llm_score": 0.1,
    "stylometric_score": 0.156,
    "repetition_score": 0.0,
    "status": "classified",
    "appeal_filed": false
  },
  {
    "event_type": "appeal_received",
    "timestamp": "2026-06-30T08:56:17.409Z",
    "content_id": "cnt_b0a6fc61f6f1",
    "creator_id": "audit-example-formal-human",
    "appeal_reasoning": "I wrote this myself in a formal academic style. Please review the original classification because polished human writing can look AI-like.",
    "creator_reasoning": "I wrote this myself in a formal academic style. Please review the original classification because polished human writing can look AI-like.",
    "status": "under_review",
    "original_decision": {
      "attribution": "likely_human",
      "combined_score": 0.284,
      "confidence": 0.716,
      "label": "Likely human-written. This post appears to have been written by a person. Confidence: 72%",
      "llm_score": 0.45,
      "stylometric_score": 0.2361,
      "repetition_score": 0.0
    },
    "appeal_count": 1,
    "appeal_filed": true
  }
]
```

## Spec Reflection

The spec helped me generate the appeals workflow successfully. I put my planning into the AI, and it generated the `/appeal` endpoint, status update, and audit log flow smoothly. That part passed tests right away because the spec clearly described what needed to happen: capture the creator's reasoning, update the content status to `under_review`, log the appeal alongside the original classification decision, and return a confirmation response.

However, I struggled when I used the spec to implement the detection signals. The first versions of the stylometric heuristics and repetition / redundancy signal did not work well: the scores were too low for polished AI-style examples, and the repetition detector was too conservative. I had to tune the formulas, add more AI-style phrase checks, make the repetition detector more aggressive, and change the final detector weighting to `50%` LLM, `25%` stylometric, and `25%` repetition. This diverged from my first plan, but it made the final system work better.

## AI Usage

I used AI to help implement the stylometric heuristics and repetition / redundancy signal. I directed the AI to create Python-based detectors that would measure sentence-length variance, vocabulary diversity, punctuation density, repeated phrases, near-duplicate sentences, and n-gram reuse. The AI produced working detector functions, but the first version did not score the samples well: polished AI-style paragraphs were too low, and the repetition detector was too conservative. I revised the output by asking the AI to test more examples, compare casual human writing against polished AI-style writing, add more generic AI phrase checks, make the repetition formula more aggressive, and update the final ensemble weighting to `50%` LLM, `25%` stylometric, and `25%` repetition.

I also used AI to help design the Provenance certificate workflow. I directed the AI to make it similar to the appeals workflow: submit a `content_id`, include the creator's reasoning, send the request to human review, update the content status to `under_review`, and write the request to the audit log. The AI produced the first workflow structure and endpoint plan. I revised and overrode the part after human review because I did not want the system to automatically award a `Verified human` badge. Instead, I kept the credential as `pending_review` with `display_badge: false` until a human reviewer approves it. This better matches the purpose of a provenance certificate because the badge should come from human verification, not automatic classification.
