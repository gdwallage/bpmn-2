# Authoring guide: writing BPMN XML the tools can finish

Write **semantic XML only**. `bpmn.py render` normalises it, validates it, adds layout (DI) and draws it.
Namespace: `http://www.omg.org/spec/BPMN/20100524/MODEL` as the default namespace. Copy a file from `assets/templates/`.

## Skeleton
```xml
<definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL" id="Defs_1" name="Model name"
             targetNamespace="http://example.com/bpmn/model-name">
  <message id="Msg_1" name="Order"/>                     <!-- root elements: message, signal, error, escalation, dataStore -->
  <collaboration id="Col_1"> <participant .../> <messageFlow .../> </collaboration>
  <process id="Proc_1" name="..." isExecutable="false"> laneSet?, flow elements, then artifacts </process>
</definitions>
```
Every element needs a unique `id` (letters, digits, `_ - .`, starting with a letter or underscore). Ids are used for DI, so keep them
stable and readable (`Task_CheckOrder`). `render` generates ids for flows that lack one.

## Ordering the XSD enforces (the normaliser fixes these, but know them)
Inside `process` / `subProcess`: `documentation`, `laneSet`, then all flow elements (events, activities, gateways, `sequenceFlow`,
`dataObject`, `dataObjectReference`, `dataStoreReference`), then artifacts (`association`, `group`, `textAnnotation`).
Inside tasks: `documentation`, data associations, resource roles, loop characteristics. Inside events: data items, then event definitions.
`dataStore` is a **root** element (sibling of `process`); only `dataStoreReference` lives in a process. `BPMNDiagram` comes last.

## Collaboration and black-box pools
```xml
<collaboration id="Col_1">
  <participant id="P_Cust" name="Customer"/>                                 <!-- no processRef = black box -->
  <participant id="P_Co" name="Acme Ltd" processRef="Proc_Co"/>
  <messageFlow id="MF_1" name="Order" sourceRef="P_Cust" targetRef="Start_1" messageRef="Msg_Order"/>
</collaboration>
```
Lanes: `<laneSet><lane id name><flowNodeRef>Task_1</flowNodeRef>...</lane></laneSet>` placed first in the process; nested lanes use
`<childLaneSet>`. A process with lanes but no pool is wrapped in a participant automatically (N2).
Message flow endpoints: sender = send task / throw message event / end message event / any task; receiver = receive task /
message start or catch event / task; or the pool itself. A message event needs `<messageEventDefinition messageRef="..."/>`.

## Patterns (copy and adapt)
* **XOR decision**: `<exclusiveGateway id="G" name="Valid?" default="F_no"/>`, flows named `yes`/`no`; the default flow has no condition. Use `<conditionExpression>` (free text is fine at Descriptive/Analytic) when the rule is known.
* **Parallel fork/join**: `parallelGateway` split and `parallelGateway` join; do not join with an exclusive gateway.
* **Inclusive**: `inclusiveGateway` split with conditions, `inclusiveGateway` join.
* **Wait for message or timeout**: `eventBasedGateway` to `intermediateCatchEvent` (message) and `intermediateCatchEvent` (timer).
* **Timeout on a task**: `boundaryEvent attachedToRef="Task"` with `timerEventDefinition` (`cancelActivity="false"` keeps the task running).
* **Exception handling**: error boundary event on a sub-process, flow to recovery; error end event in the sub-process.
* **Loop**: back-edge through an XOR gateway, or `standardLoopCharacteristics` on the task.
* **Multi-instance**: `<multiInstanceLoopCharacteristics isSequential="false"/>`.
* **Reuse**: `<callActivity calledElement="Proc_Other"/>` with a separate top-level `process`.
* **Data**: `dataObject` + `dataObjectReference`; output: `<dataOutputAssociation><targetRef>DOR_1</targetRef></dataOutputAssociation>` inside the task;
  input: `<dataInputAssociation><sourceRef>DOR_1</sourceRef><targetRef>TASK_OR_PROPERTY</targetRef></dataInputAssociation>` (pointing at the task is repaired to a Property placeholder).
* **Annotation**: `textAnnotation` + `association`.
* **Documentation / provenance**: `<documentation>[stated] interview A, 00:12:30</documentation>` as the first child.

## Hints file (`--hints h.json`)
```json
{"expanded": {"SubProc_1": true, "SubProc_2": false},
 "groups": {"Group_1": ["Task_a", "Task_b", "Task_c"]}}
```
`expanded` overrides the automatic expand/collapse choice (auto expands a sub-process with up to 10 flow nodes). `groups` places a
declared `group` element (with optional `categoryValueRef`) around the named shapes. Unlisted groups are not drawn.

## Overlay file (`--overlay o.json`): colour and badges only (spec-permitted)
```json
{"elements": {"Task_1": {"fill": "#fde2e2", "badge": "NVA", "badge_fill": "#b00020", "note": "Waiting 2 d"}},
 "legend": [{"color": "#fde2e2", "label": "Non-value-adding"}]}
```
Keys per element: `fill`, `stroke`, `stroke_width`, `badge`, `badge_fill`, `badge_text`, `note`. The model and its meaning do not change.

## Layout behaviour and how to steer it
Left-to-right flow, main path kept straight (default flow or longest path), other branches fan out above/below, pools stacked,
message flows vertical. If a diagram is dense: collapse sub-processes (`--subprocess collapsed`), split the model, shorten labels.
Collapsed sub-processes with content get their own drill-down diagram (`<name>__<subprocess>.png`). Top-level processes outside
a collaboration (e.g. called processes) also get their own image. To control coordinates exactly, supply your own DI; complete DI is reused
as-is (`--relayout` ignores it).
Known limits: message flows between non-adjacent pools can cross intermediate pools; very dense models (30+ nodes per level) need decomposition.
