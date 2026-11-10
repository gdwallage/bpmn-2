# Hierarchy, levels of abstraction and process frameworks

## Hierarchy inside BPMN
| Need | Use | Why |
|---|---|---|
| decompose locally, keep scope for events, show/hide detail | **sub-process** (embedded; collapsed with `+`, expanded, or drill-down diagram) | shares data and scope with its parent; boundary events and event sub-processes work on it |
| reusable or separately owned/maintained process | **call activity** (thick border) -> top-level `process` or global task | one definition, many callers; independent lifecycle |
| unit of work without further detail | **task** | |
| business transaction needing all-or-nothing or compensation | **transaction** sub-process (double border) | cancel and compensation semantics |
| unstructured set of activities done in any order | **ad-hoc** sub-process (`~`) | no start/end events inside |
| organisations interacting | **collaboration** (pools + message flows) | |
| the agreed interaction only (no internal behaviour) | **choreography** or **conversation** diagram | |
| who talks to whom about what, overview | **conversation** diagram | |

Rules: sequence flows never cross a sub-process boundary (connect to the sub-process, not its inner nodes); an expanded sub-process has its own start/end events (if
you use one, you need the other); a collapsed sub-process needs a drill-down diagram in the deliverable (`render --subprocess collapsed` creates them).

## Reading levels for a deliverable
Choose a level per audience and **keep each diagram to one level**; the same model can carry all of them via drill-down:
1. *Landscape / context* (not BPMN): value chain or process map; BPMN starts below it.
2. *Process overview*: collaboration with black-box pools or a short process with 5-9 collapsed sub-processes (Descriptive).
3. *Operational process*: tasks, gateways, key events, lanes (Descriptive/Analytic). The workhorse level.
4. *Detailed / exception* level: boundary events, messages, data (Analytic/Full), usually inside sub-processes.
5. *Executable*: technical attributes added by the engine's modeller (Executable subset).
Heuristic: 7-15 flow nodes per diagram; a sub-process with more than about 10 nodes should drill down.
A call activity target is a process of its own: give it its own image and name; `info` prints the outline.

## Mapping to a generic five-level process hierarchy (e.g. APQC PCF numbering)
| Hierarchy level | Typical name | BPMN construct |
|---|---|---|
| 1 | Category | outside BPMN (process landscape); a `collaboration`/`conversation` overview may reference it |
| 2 | Process group | outside BPMN or a top-level overview process whose steps are call activities |
| 3 | Process | a BPMN **process** (or collaboration); one diagram |
| 4 | Activity | sub-process / call activity / key task inside the process |
| 5 | Task | task (and detailed steps inside a sub-process) |
Carry the hierarchy identifier in `<documentation>` of the process or activity (for example `PCF 9.2.1`) or in the analysis sidecar, never in element ids
that tools may rewrite. **Do not assert framework numbering or names from memory**: follow `extensions/process-hierarchy-apqc.md`
(check the current version, record the version and retrieval date) before putting a hierarchy ID into a deliverable.
