# Conformance and levels (paraphrased from OMG BPMN 2.0.2, clause 2; the project file formal-13-12-09)

## What "conformant" can honestly mean here
The spec grants conformance to *software* that fully meets a conformance type. This skill's claim is narrower and checkable:
the **model** validates against the official XSD, passes the structural rules of cl. 7.6, 8-11 listed in
`structural-rules.md`, and the **image** follows the notation rules (cl. 7.5, 10.x, 12.3). Say exactly that.
Process-execution and BPEL conformance (cl. 2.3, 2.4, 13, 14) concern engines, not drawings.

## Four conformance types in the spec
1. Process Modeling (process, collaboration, conversation diagrams)  2. Process Execution  3. BPEL Process Execution
4. Choreography Modeling. A tool need not support all. This skill covers 1 and 4 (drawing/validating) and can emit
an executable-ready skeleton, but it does not run models.

## Process Modeling sub-classes (cl. 2.2.2, Tables 2.1 to 2.4): the "levels"
| Level | Intent | Elements (summary) |
|---|---|---|
| **Descriptive** | visible, high-level flowcharting for analysts | pools, lanes, unconditional sequence flow, message flow, exclusive and parallel gateway, task / user / service task, sub-process (collapsed or expanded), call activity, data object, data store reference, text annotation, associations, none start, none end |
| **Analytic** (includes Descriptive; about half of the full set) | richer business analysis | + message / timer / signal / conditional start, message / terminate / signal / error / escalation end, conditional and default flows, send and receive task, loop and multi-instance, inclusive and event-based gateway, link events, intermediate message / timer / signal / conditional / escalation (throw) events, boundary message / timer / error / signal / conditional (and non-interrupting variants; escalation boundary only non-interrupting), group, documentation |
| **Common Executable** (a different subset, *not* a superset of Analytic) | tool emits executable models | sequence flows (all kinds), expanded sub-process, exclusive / parallel / event-based gateway, none start/end, user / service task, call activity, data object, message start/end, terminate end, intermediate message catch/throw, intermediate timer catch, boundary error, loop and multi-instance, plus supporting data, message, error, operation structures. Data types XSD, service interfaces WSDL, data access XPath |
| **Full** | everything | + manual / script / business-rule task, ad-hoc sub-process, transaction, event sub-process, complex gateway, compensation, cancel, multiple / parallel-multiple events, conversations, choreography |

`validate` prints the *minimum* sub-class a model needs and `--level` fails if it exceeds a target. The element sets
live in `scripts/bpmnlib.py` (`DESCRIPTIVE`, `ANALYTIC`, `EXECUTABLE`). Known literal reading: Table 2.2 lists no
non-interrupting message/timer *start* events and no interrupting escalation boundary, so those count as Full.

## Choosing a level
* First pass for stakeholders, or little evidence: **Descriptive**. Move up only when a real behaviour needs it
  (timeouts, message waits, exceptions, parallel joins with conditions).
* Business process documentation, process improvement baselines: **Analytic**.
* Handover to an engine: **Executable** *subset*, then add engine specifics (implementation, ioSpecification, expressions)
  in the engine's modeller. Say that the skeleton is not deployed or tested.
* Complex exception handling (compensation, transactions, event sub-processes), conversations, choreography: **Full**.

## Visual-conformance rules the renderer enforces (cl. 2.2.3, 7.5)
Fills and colours are free, except throwing-event markers must be dark-filled; line styles may change only where they
do not clash with a line style the spec assigns (sequence = solid, message = dashed, association = dotted, group = dash-dot,
event outline weight, thick call activity, double transaction, dotted event sub-process). Extensions (markers, colours,
new artifacts) are allowed if they never change a specified shape. Overlays in this skill use colour and badges only.
