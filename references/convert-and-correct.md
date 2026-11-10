# Correcting and converting process drawings into formal BPMN

Default behaviour for any attempted process drawing (flowchart, "BPMN-ish" diagram, Visio/PowerPoint export, hand sketch,
tool export with errors): **convert to correct BPMN**. Only skip that when the user EXPLICITLY asks for an informal "pidgin" sketch.

## Procedure
1. **Transcribe faithfully** what was drawn (nodes, text, connectors, direction, lanes). Do not fix anything yet. Put the transcription in the ledger as *observed*.
2. **Classify** each construct with the table below.
3. **Build the BPMN XML**, then `bpmn.py validate`; fix every error. Keep the author's names unless they break naming rules; improve names and say so.
4. **Resolve ambiguity** by keeping the author's reading and listing a question; never silently reinterpret.
5. **Deliver a conversion log**: for every change, `original -> BPMN -> rule/reason`. Also say what was *kept* and what is *unclear*.

## Mapping: informal constructs to BPMN
| Drawn as | Becomes | Note |
|---|---|---|
| oval / rounded "Start", "Begin" | start event (none) | name it after the trigger state; if the text says "email received" use a message start |
| oval "End", "Stop", "Finish" | end event (none) | one per distinct outcome; "Stop" for abnormal termination can be an error or terminate end |
| rectangle / process box | task | choose user / service / manual / script / send / receive when the text shows who or what performs it (see below) |
| rectangle with double side bars (subroutine / predefined process) | call activity (reused) or sub-process (local) | |
| diamond "decision?" | exclusive gateway | question as label; flows labelled; one default |
| diamond with "AND"/"+" or fork bar | parallel gateway | needs matching join |
| "OR (any of)" | inclusive gateway | matching inclusive join |
| parallelogram (input/output) | data object (if a document/data), or a send/receive/user task if it is an action | |
| document / multi-document | data object (collection if multi) | |
| cylinder / database | data store reference | |
| hourglass, clock, "wait 3 days" | intermediate timer catch event, or timer boundary if it limits a task | |
| envelope, "send email" | send task (or message end/throw event if it ends/throws) | |
| "wait for reply / approval email" | receive task or intermediate message catch event | |
| connector circle with letter / off-page reference | sequence flow if on the same page; link event pair only if truly needed | |
| swimlane label = department/role | lane | |
| swimlane label = company/system | pool (participant) | |
| arrow between lanes of one organisation | sequence flow | |
| arrow between different organisations | message flow (dashed), sender and receiver must be tasks/events/pools | |
| note box with dashed line | text annotation + association | |
| dashed box grouping steps | group (visual) or sub-process (if it is a unit of work with its own scope) | |
| arrow labelled with a condition leaving a task | gateway after the task (clearer), or a conditional flow from the task | |

## Typical errors and corrections
| Found | Rule | Correction |
|---|---|---|
| sequence arrow crossing from one pool/organisation to another | F001 | message flow between pools, with a message name |
| message flow between two lanes of the same pool | F021 | sequence flow |
| decision shape with one outgoing arrow, or a gateway used just as a connector | F013 | remove it, or add the missing branch |
| several arrows leaving a task meaning "choose one" | semantics: parallel | insert an exclusive gateway |
| several arrows entering a task from alternative paths meant "wait for all" | semantics: uncontrolled merge | insert a parallel join |
| XOR split closed by an AND join | P001 deadlock | XOR join |
| AND split closed by an XOR merge | P002 | AND join |
| end event with an outgoing arrow, start event with an incoming arrow | F002, F003 | remove / restructure; for repeat use a loop to a task |
| no start or no end | F007 | add them; name outcomes |
| two start events that both join into an AND join | S007 / semantics | each start creates its own instance; use one start, or an event-based/parallel start deliberately |
| task text "Approved?" (a question on an activity) | style | a decision belongs in a gateway; task is "Review request" |
| activity names as nouns ("Invoice") or states | style S001-ish | verb + object ("Issue invoice"); events carry states ("Invoice issued") |
| lanes for systems and roles mixed | modelling | roles as lanes; systems as pools/participants or annotations |
| huge flat diagram | S004 | decompose into sub-processes / call activities |
| gateway labels missing, flows unlabelled | S003 | question on gateway, answers on flows |

## Task type selection
Human with a screen/work list: user task. Automated system step: service task. Physical or offline work: manual task. Script/rule execution:
script / business rule task. Sends/receives a message to/from another participant: send / receive task. Unknown: plain task (Descriptive-safe).

## Pidgin (informal) requests
Only on explicit request ("quick informal sketch", "pidgin", "doesn't need to be proper BPMN"). Produce a flowchart-style picture with ordinary boxes and arrows
(Graphviz / Mermaid / Visualizer), avoid BPMN shapes, add the banner "Informal process sketch, not BPMN", keep the evidence ledger, and offer to convert.
Do not draw things that look like BPMN but break its rules.
