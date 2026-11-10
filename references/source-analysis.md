# Discovering a process from any source

## The evidence ledger (build before modelling)
| ID | Element | Type | Detail | Evidence tag | Source | Confidence | Open question |
|---|---|---|---|---|---|---|---|
| E1 | Check order | activity | Sales clerk checks stock and credit | stated | SOP p.3 "the clerk verifies..." | high | |
| E2 | Order valid? | decision | outcome yes/no | stated | SOP p.3 | high | |
| E3 | Reminder after 7 days | timer boundary | non-interrupting | inferred | email "we chase after a week" | medium | does the process wait or end? |
Types: actor/pool, lane/role, activity, trigger, decision, outcome/end state, exception, hand-off/message, data item, system, rule, timing, volume.
**Tags**: *stated* (the source says it), *observed* (visible in a diagram/screen/recording), *inferred* (a reasonable implication you can quote the basis for), *assumed* (gap filled by you; always an open question). A model element with no ledger row is a defect.

## Reading by source type
**Documents, SOPs, policies, emails.** Look for verbs in sequence ("then", "after", "once"), conditionals ("if", "unless", "otherwise", "except"),
timing ("within 5 days", "weekly"), roles ("the manager approves"), hand-offs ("send to", "forwarded"), triggers ("when a request arrives"),
outcomes ("closed", "rejected"), systems ("in SAP"), artefacts (forms, reports). Passive voice hides the actor: record it as an open question.
Policy text often states rules without sequence; model rules as decisions, not as steps.

**Interview and meeting transcripts.** People narrate the happy path first and the exceptions later or only when pressed; people contradict
each other; they describe the as-is mixed with the to-be ("we should..."). Separate: current practice, pain points, aspirations (keep pain points for the
improvement layer, do not model aspirations as the as-is). Tag each claim with speaker and timestamp. When two speakers disagree, model the stated
policy and flag the variance. Ask for a transcript if only audio exists.

**Images and screenshots.** `view` the image; use OCR only as a helper. Identify: containers (pools/lanes/boxes), nodes (shape, text), connectors
(direction, line style, labels), and legends. Read left-to-right, top-to-bottom, then verify every arrow end. Large images: use the tiles from `ingest.py` and
stitch the reading. Record what is unreadable. For photographs of whiteboards, expect missing arrows and ambiguous handwriting; list uncertain labels.
**Reading a diagram image from this skill:** `bpmn.py extract image.png -o m.bpmn` recovers the exact model.

**Existing BPMN files.** `bpmn.py validate` and `info` first; then see `convert-and-correct.md`.

**Data and logs (CSV, event logs, tickets).** Derive the most frequent path and the variants (mark frequency); do not model every variant: model the dominant flow
and show exceptions where they matter. Timestamps give waiting vs processing time: keep them for the improvement layer.

**Screen recordings / video.** Frames show steps and systems; subtitles or a transcript give the rationale. Without a transcript, only tag *observed*.

## From evidence to model
1. Participants: who/what owns activities. Separate organisations and systems become pools; roles become lanes. Anything described only from the outside is a black-box pool.
2. Boundaries and triggers: what starts it (message, timer, manual, condition) and what ends it (name each outcome).
3. Main path first, then decisions, then exceptions (boundary events, error paths), then parallelism, loops, timers, messages.
4. Hierarchy: if a step is described in much more detail than its siblings, or owned by someone else, make it a sub-process or call activity (see `hierarchy-and-levels.md`).
5. Data and systems as data objects/stores or annotations only where the source gives them.
6. Check completeness with the ledger: every row is represented or explicitly out of scope; every element has a row.

## Typical inference traps
* "Sometimes", "usually" = decision with an unknown rule: keep the gateway, label the branches, flag the rule as open.
* "They check" without an outcome: ask what happens on failure; do not invent a rejection path silently (tag *assumed* if you add it).
* Parallelism claims ("at the same time") are rarely exact; confirm before using a parallel gateway.
* Loops ("until approved") need an exit condition and ideally a limit; flag if missing.
* Hand-offs between departments: sequence flow if the same organisation (lanes), message flow only across organisations/systems with independent processes.
