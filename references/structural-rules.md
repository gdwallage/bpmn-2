# Validator rule index (what each code means and how to fix it)

Severity: **error** = violates a MUST in the spec or the XSD (blocks `render`); **warning** = likely modelling defect or
SHOULD; **info** = observation. Clause numbers refer to OMG formal/2013-12-09.

| Code | Meaning | Typical fix |
|---|---|---|
| X001-X003 | root not `bpmn:definitions`, no `targetNamespace`, nothing modelled | fix the skeleton |
| X010-X012 | official XSD (BPMN20.xsd) violation; message names the element and line | usually element order (artifacts after flow elements; `laneSet` first; `BPMNDiagram` last). `normalize` fixes order |
| X020 | duplicate id | rename |
| R001-R003 | missing/dangling reference; `incoming`/`outgoing` contradicting the flows | point to an existing id, or delete the optional lists |
| F001 | sequence flow crosses a pool or sub-process boundary [7.6.1] | message flow between pools; connect to the sub-process, not its children |
| F002-F003 | flow leaves an end event / enters a start event [10.5.2-3] | remove or re-target the flow |
| F004 | sequence flow to a non-flow-node (data, artifact) | use an association |
| F005-F007 | start without outgoing, end without incoming, start without end at a level [10.5.2-3] | complete the path |
| F008 | intermediate event needs in and out flow (links excepted) [10.5.4] | wire it into the flow |
| F009-F010 | boundary-event rules: no incoming, needs outgoing (compensation: association), attach to activity, valid trigger | re-model the exception path |
| F011 | trigger not allowed in that position (e.g. timer end, error catch in normal flow) | see the table in `notation-catalogue.md` |
| F012 | link events: not both in and out; every throw needs one catch of the same name | name them consistently |
| F013 | gateway neither splits nor merges, bad `gatewayDirection`, default flow misuse, condition on parallel/event gateway [10.6.1, 8.4.13] | remove the gateway, or fix flows |
| F014 | conditional flow out of an activity needs a sibling flow | add the alternative, or use a gateway |
| F015-F016 | compensation activity wired into normal flow; event sub-process wired or without exactly one start | detach / fix start |
| F017-F018 | ad-hoc contains start/end; cancel used outside a transaction | move events out; use a transaction |
| F019 | condition on a start-event flow | remove |
| F020 | event-based gateway targets/conditions invalid [10.6.6] | targets: catch events or receive tasks, no mixing |
| F021 | message flow endpoints invalid: same pool, gateway/data endpoint, wrong event direction [9.4, 10.5] | re-point; use sequence flow inside one pool |
| F022-F024 | pool/process references; lane membership; call activity target | fix reference; assign nodes to lanes |
| F025, F030 | loop plus multi-instance; flow to itself | choose one |
| D001-D006 | diagram interchange missing, detached edges, missing shapes | `render` computes DI when absent or incomplete |
| C001-C003 | choreography/conversation structure | two participants per task; initiator among them |
| DA01 | data association aims at the activity, not an item-aware element | `normalize` inserts a Property placeholder |
| S001-S010 | style: unnamed activities/gateways/events, duplicate names, density, inconsistent X marker, single start per trigger | rename / decompose |
| P001 | possible deadlock (e.g. exclusive split joined by parallel join) | match split and join types |
| P002 | possible lack of synchronisation (parallel split merged by exclusive merge) | use a parallel join |
| P003-P005 | no completion path; unreachable node; node cannot reach an end | fix flows |
| L001 | element outside requested `--level` | simplify or raise the level |

Soundness (`--soundness`) is a bounded token game (20 000 states) per process level: exceptions and event sub-processes
are not interleaved, complex gateways are skipped, data-dependent loops are treated as possible. A clean result means "no
structural deadlock found", not "proven correct".
