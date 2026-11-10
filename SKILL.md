---
name: bpmn
description: Expert BPMN 2.0.2 process modelling. Investigates any written, visual or audio-transcript source (documents, SOPs, emails, interview transcripts, screenshots, whiteboard photos, flowcharts, swimlanes, existing BPMN) for explicit, observable and inferable processes, then produces conformant BPMN diagrams as PNG/SVG plus .bpmn XML validated against the official OMG XSD and the spec's structural rules, with soundness checks. Corrects and converts informal or malformed drawings into formal BPMN unless the user EXPLICITLY asks for an informal "pidgin" sketch. Supports Descriptive/Analytic/Executable/Full levels, hierarchy (sub-process, call activity, drill-down), collaboration, conversation and choreography. Use whenever the user mentions BPMN, process maps/models, swimlanes, workflows, as-is/to-be, SOP visualisation, or shares material describing how work flows, even without saying BPMN. Foundation for Lean/Six Sigma, ArchiMate, value-stream and APQC work.
---

# BPMN skill

Turns *any* source into a formally correct BPMN 2.0.2 model, then draws it. Correctness comes
from tools, not from memory: the model is written as BPMN XML, repaired by a normaliser,
checked by a validator, and drawn by a renderer that implements the notation rules.

**Be honest about the claim.** Conformance is a property of tools and of what they emit. Say
"validated against the official BPMN 2.0 XSD and the specification's structural rules" and
name the conformance level. Never say "100% certified". Validation proves the diagram is
well-formed BPMN; it cannot prove the process matches reality. That part rests on the evidence.

## Setup (once per session)

```bash
pip install lxml pillow cairosvg --break-system-packages -q     # usually present; cairosvg draws PNGs
python <skill-dir>/scripts/bpmn.py --help
```
`<skill-dir>` is the folder containing this file. Commands: `render`, `validate`, `normalize`,
`extract`, `info`. Source ingestion helper: `scripts/ingest.py`.

## Workflow

### 0. Decide what is being asked
Pick the mode from the request, ask a question only if the answer changes the model materially.

| User gives / wants | Mode | Read |
|---|---|---|
| a description, document, transcript, screenshots, "map this process" | **Discover and model** | `references/source-analysis.md` |
| an existing diagram (image, Visio-ish flowchart, BPMN file) to fix or convert | **Correct / convert** | `references/convert-and-correct.md` |
| explicitly "informal", "rough sketch", "pidgin", "don't need proper BPMN" | **Pidgin** (see below) | |
| "improve", "waste", "lean", "six sigma", "ArchiMate", "value stream", "APQC" | model first, then | `references/extensions/README.md` |

State the **purpose** and **conformance level** you will target. Default: *Analytic* for
business-facing models, *Descriptive* for a first high-level pass, *Executable* only if an
engine is named, *Full* when you need manual/script/business-rule tasks, event sub-processes,
compensation, conversations or choreography. See `references/conformance-and-levels.md`.

### 1. Ingest every source
`python scripts/ingest.py <file>... -o work/` extracts text from PDF, DOCX, PPTX, XLSX/CSV, HTML,
SRT/VTT, images (OCR plus tiles for large diagrams) and video (frames plus subtitles). Then **look at
images yourself** with `view`; OCR is only a helper.

**Audio / video with no transcript:** this environment has no speech-to-text. Say so, ask for a
transcript, or fetch one from a connected meeting tool (e.g. Granola, Teams) if available. Never
invent content from an audio file you could not hear.

### 2. Extract the process (evidence first)
Build an **evidence ledger** before modelling (`references/source-analysis.md` has the template):
every actor, activity, trigger, decision, outcome, exception, hand-off, message, data item and system,
each tagged **stated / observed / inferred / assumed** with a source pointer and confidence. Inferred
means a reasonable implication (e.g. a rejection path implied by "if it fails, we go back"). Assumed means
you filled a gap; list these as **open questions** for the user. Do not present assumptions as facts.

Resolve scope and hierarchy now: which process level is this (see `references/hierarchy-and-levels.md`),
what are the pool/participant boundaries, what triggers it and what ends it (named outcomes).

### 3. Author the BPMN XML (semantic model only)
Write `*.bpmn` with **semantic elements only**: no layout. The tools create the diagram layout.
Start from a template in `assets/templates/` and read `references/authoring-guide.md`
(skeleton, ordering rules, patterns, data associations). Essentials:

* One pool per participant organisation/system, lanes for roles/departments inside a pool. Other organisations
  you do not model internally are **black-box pools** (a participant with no `processRef`).
* **Sequence flow stays inside one pool and one process level; message flow crosses pools.** Never mix them.
* Events carry state: `Order received`, `Invoice paid`. Activities are verb + object: `Check order`.
  Exclusive gateways are questions with labelled outgoing flows and one `default`.
* Every split needs a matching join of the same kind (XOR/XOR, AND/AND, OR/OR) unless paths end separately.
* Prefer one start event per trigger type; name end events by outcome.
* Keep each level readable: about 7 to 15 flow nodes. Push detail down into sub-processes or call activities.
* Record provenance in `<documentation>` (e.g. `[inferred] from interview 2, 14:05`). Assumptions get `[assumed]`.

### 4. Render, validate, look, fix (loop until clean)
```bash
python scripts/bpmn.py render model.bpmn -o /mnt/user-data/outputs/<name> --soundness
```
This normalises, validates (official XSD + spec rules + soundness), computes layout where DI is missing,
and writes `<name>.png`, `<name>.svg`, `<name>.bpmn` (the last carries complete DI and opens in Camunda
Modeler, bpmn.io, Signavio, etc.). Hierarchical models also write one image per drill-down diagram.
* **Errors block output.** Fix the model, never use `--force` to ship. `references/structural-rules.md`
  explains every rule code and how to fix it.
* **Warnings must be read.** `P001/P002` (deadlock / lack of synchronisation) are real modelling bugs;
  style warnings (`S...`) are judgement calls you may justify.
* **Always `view` the PNG** before delivering: check overlaps, unreadable labels, crossing lines. Fixes go
  in the model (split into sub-processes, rename, reorder) or in options: `--subprocess collapsed|expanded`,
  `--hints h.json` (see authoring guide), `--scale 3` for sharper bitmaps.
* Level control: add `--level descriptive|analytic|executable` to fail if the model uses elements outside it.

Other commands: `validate model.bpmn --soundness --json`, `info model.bpmn` (structure and hierarchy
outline), `extract image.png -o model.bpmn` (recover the model embedded in any image this skill made),
`normalize in.bpmn -o out.bpmn`.

### 5. Deliver
Use `present_files` for the PNG (and `.bpmn` / `.svg` if wanted). In the message give:
1. what the diagram shows (one or two sentences) and the **conformance level**;
2. the validation result in one line ("valid against the OMG XSD, 0 errors, soundness clean");
3. **assumptions and open questions** from the ledger that affect correctness (short list);
4. anything normalised or corrected (for conversions: the change log, see `convert-and-correct.md`);
5. what could come next (decompose a step, add an improvement overlay, ArchiMate view).
Keep the evidence ledger as a file only if it is long; otherwise summarise it.

## Modes in brief

**Correct / convert.** Transcribe the attempt faithfully first (what was drawn, not what was meant), then
map each construct to BPMN using the catalogue in `references/convert-and-correct.md`, fix rule violations,
and deliver a **conversion log** listing every change and why. If intent is ambiguous, keep the author's
reading, flag the question, never silently reinterpret.

**Pidgin (informal) mode.** Only when the user explicitly asks for an informal or non-formal sketch. Draw a
plain flowchart-style picture (Graphviz `dot`, Mermaid or the Visualizer) that does **not** use BPMN
shapes, so it cannot be mistaken for BPMN, with a visible banner "Informal process sketch, not BPMN".
Still build the evidence ledger. Offer to formalise it afterwards. Never produce BPMN-looking
shapes with non-BPMN meaning.

**Hierarchy and levels.** Show a level as collapsed sub-processes/call activities with separate drill-down
diagrams (`--subprocess collapsed`). Use a **call activity** for reusable or separately owned processes and a
**sub-process** for local decomposition and for scoping events (boundary events, event sub-processes).
See `references/hierarchy-and-levels.md`, which also covers mapping to process-classification frameworks.

**Improvement and other frameworks.** Model the as-is correctly first; improvement analysis (Lean waste,
Six Sigma DMAIC, bottlenecks) works on top of a valid model through **overlays and the analysis sidecar**
(`references/extensions/README.md`). Overlays use only colour and badges, which the spec permits (cl. 2.2.3),
so the diagram stays conformant. ArchiMate handoff goes to the `archimate` skill.

## Hard rules
* Never ship a model with validation errors. Never claim certification.
* Never draw a process element you cannot trace to evidence or list as an assumption.
* Never use BPMN notation with non-BPMN meaning, and never produce informal output unless explicitly asked.
* Do not copy text from the OMG documents into deliverables; cite clause numbers. The reference files
  here are paraphrased syntheses of the project's standards.
* When the project files are available, `/mnt/project/formal-13-12-09.pdf` is plain text despite its extension
  (`sed 's/\r$//'`, then `grep -n`); use it to confirm a rule. Rule bullets are marked with the control
  character U+008B in that file.
