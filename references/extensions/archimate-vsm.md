# ArchiMate and value-stream thinking (stub: mapping + handoff)

## Handoff to the `archimate` skill (already installed in this environment)
Build the BPMN model first; then derive ArchiMate elements by id, never by retyping.
| BPMN | ArchiMate (business layer) | Note |
|---|---|---|
| process / sub-process / call activity (named unit) | Business Process | or Business Function when it is a stable capability grouping, not a flow |
| task | Business Process (detail) or Business Interaction when several roles collaborate | |
| start / intermediate / end event (named state or trigger) | Business Event | |
| lane (role) / pool (organisation) | Business Role / Business Actor | |
| message flow between pools | Triggering or Flow relationship; Business Interaction/Interface for the exchange | |
| data object | Business Object (or Data Object in the application layer) | |
| service / send / receive task automated by a system | Application Service / Application Process realising the business process | |
| data store | Data Object in an application component | |
| sequence flow | Triggering (control) or Flow (information/resource) relationship | |
Protocol: list the mapping as a table with BPMN id -> proposed ArchiMate type and relationship, ask the user to confirm the layer scope, then call the archimate skill with a JSON spec; store `archimate_id` in the sidecar. Check the archimate skill's own rules for permitted relationships.

## Value stream thinking (to be enriched)
* A value stream map needs: steps, lead time, process time, wait, %C&A (complete and accurate), inventory/queues, information flow. From BPMN: steps = tasks along the main path, waits = timers/receive tasks/queues, information flow = message flows and data.
* Keep value streams as a *separate view* that references BPMN ids; do not distort the BPMN diagram to look like a VSM.
* End-to-end value streams span several BPMN processes (pools or call activities): link them through the hierarchy sidecar.
