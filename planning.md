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
    | approve / deny verified-human credential
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

### 1. LLM-based classification - 45%
- What it measures: overall semantic coherence, voice consistency, and whether the text feels human-written, AI-generated, or uncertain.
- Output: a score from `0.0` to `1.0` representing AI-likelihood.
  - `0.0` means strongly human.
  - `1.0` means strongly AI-generated.
- Why this signal matters: it captures the broadest, most holistic view of the writing.

### 2. Stylometric heuristics - 30%
- What it measures: sentence-length variance, type-token ratio, punctuation density, repetition rate, and average sentence complexity.
- Output: a score from `0.0` to `1.0` representing AI-likelihood.
- Why this signal matters: it captures structural writing patterns that are hard to see from semantic analysis alone.

### 3. Repetition / redundancy signal - 25%
- What it measures: repeated phrases, near-duplicate sentences, n-gram reuse, and overly uniform phrasing.
- Output: a score from `0.0` to `1.0` representing AI-likelihood.
- Why this signal matters: it detects internal pattern reuse that often appears in generated text.

### Combining the signals

Each signal returns a continuous score rather than a binary flag. The raw signal outputs are first normalized onto the same `0.0` to `1.0` AI-likelihood scale, then combined as a weighted average:

`ensemble_ai_score = (0.45 * llm_score) + (0.30 * stylometric_score) + (0.25 * repetition_score)`

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

### How it is displayed on content
- Approved content shows a visible badge such as `Verified human` or `Verified human by review`.
- The badge should appear near the transparency label so readers can distinguish platform verification from the AI detection result.
- The badge only indicates that a human reviewer confirmed the creator's provenance claim; it does not replace the attribution label.

### Verification flow

`POST /verify-human` -> `human review` -> `audit log` -> `credential response`

Arrow labels:
- `POST /verify-human`: content ID, creator reasoning, and optional supporting context
- `human review`: reviewer checks the submission and provenance claim
- `audit log`: verification request, reviewer decision, and credential status are recorded
- `credential response`: approved or denied response, plus the visible badge state

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