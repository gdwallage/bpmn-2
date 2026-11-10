# Notation and semantics catalogue (synthesised from cl. 7.3, 8, 9, 10; clause numbers in brackets)

## Flow objects
**Events** (circle). Position decides outline: *start* single thin, *intermediate* double thin, *end* single thick [10.5.2-4].
Catching markers unfilled, throwing markers dark-filled [7.5]. Non-interrupting start/boundary events use a dashed outline.

| Trigger | Start | Intermediate catch (normal flow) | Intermediate throw | Boundary | End |
|---|---|---|---|---|---|
| none | yes (not in event sub-process) | n/a | yes (`intermediateThrowEvent`, no definition) | no | yes |
| message | yes | yes | yes | yes | yes |
| timer | yes | yes | no | yes | no |
| conditional | yes | yes | no | yes | no |
| link | no | yes (target of a jump) | yes (source of a jump) | no | no |
| signal | yes | yes | yes | yes | yes |
| escalation | event sub-process only | no | yes | yes | yes |
| error | event sub-process only | no | no | yes (always interrupting) | yes |
| cancel | no | no | no | transaction boundary only | transaction only |
| compensation | event sub-process only | no | yes | yes (no outgoing sequence flow; association to handler) | yes |
| multiple / parallel multiple | yes | yes | multiple only | yes | multiple only |
| terminate | no | no | no | no | yes |
Boundary events attach to an activity, have no incoming flow and one or more outgoing flows. Event sub-process start events
need a trigger (none is invalid) and the sub-process has no incoming/outgoing sequence flow [10.3.5].

**Activities** (rounded rectangle). Task types and markers: none, user (person), service (gears), send (filled envelope),
receive (empty envelope), manual (hand), business rule (table), script (scroll). Sub-process: collapsed shows a `+` marker,
expanded shows its content. Call activity: **thick border**, `+` when collapsed. Transaction: **double border**. Event
sub-process: **dotted border**. Ad-hoc: `~` marker, contains activities only (no start/end events). Loop marker (circular
arrow), multi-instance parallel (three vertical bars) or sequential (three horizontal bars), compensation (double rewind
triangles); markers sit grouped at bottom centre [10.3, 12.3.2].

**Gateways** (diamond). Exclusive (X optional, but be consistent), inclusive (O), parallel (+), complex (*), event-based
(double circle with pentagon; single circle when it instantiates). A gateway must split or merge. Conditional flows never
leave a parallel or event gateway [10.6].

## Connecting objects
| Object | Line | Rules |
|---|---|---|
| Sequence flow | solid, solid arrowhead | same pool and same process level; never crosses a pool or sub-process boundary [7.6.1]. From an activity a conditional flow gets a mini-diamond, a default flow a slash |
| Message flow | dashed, open circle at start, open arrowhead | connects two *different* pools or their flow objects; never gateways, data, or two objects of one pool [9.4]. Sender = end/throw event or task, receiver = start/catch event or task |
| Association | dotted | links artifacts/annotations; arrowhead shows direction; compensation association to a handler |
| Data association | dotted with arrow | data object/store to activity or event |
| Conversation link | double line | participant to conversation node |

## Swimlanes
Pool = participant (rectangle, label in left band); lanes subdivide a pool and sit inside it; a black-box pool has no process;
at most one pool per diagram may omit its boundary; multi-instance pool carries three vertical bars at bottom centre [9.3].

## Data and artifacts
Data object (page with folded corner; collection = three vertical bars; data input = unfilled block arrow, data output = filled),
data store (cylinder), text annotation (open bracket), group (dash-dot rounded rectangle, labelled by category value; does not affect flow).

## Conversation and choreography
Conversation = hexagon, sub-conversation adds `+`, call conversation thick border. Choreography task = rounded rectangle with
**participant bands** (initiator unshaded, other participants light fill) and the task name between; exactly two participants
for a task, two or more for a sub-choreography; initiator of an activity must have taken part in the previous one [11.5.6].

## Semantics worth remembering (cl. 10, 13)
* Multiple outgoing sequence flows from an *activity* mean parallel paths; multiple incoming flows mean an uncontrolled merge.
* Each start event creates its own process instance. A process with an end event must have a start event and vice versa.
* A process instance completes only when no token remains; terminate end events kill all other paths.
* Event-based gateway: first event wins, others are withdrawn. Targets only catch events / receive tasks; targets have no other incoming flow.
* Error events always interrupt; escalation can be non-interrupting. Escalation/error propagate to the nearest enclosing catcher.
* Compensation undoes completed work in reverse order; handler activities sit outside normal flow.
* Spec quirk: cl. 10.3.5 lists event sub-process start triggers without timer, but its own depiction table (12.16) includes a timer event sub-process. The
  validator allows timer.
