# Lean and Six Sigma on top of a BPMN model (stub: contract + starting checklists)

**Precondition**: a validated as-is model (`validate --soundness` clean) and an analysis sidecar for any measured data. Measurements beat opinions; mark estimates.

## What the core gives you
Element ids, hierarchy (sub-processes / call activities), lanes (who), message flows (hand-offs between organisations), data/systems annotations, timers and waits, loops (rework), exception paths (defects).

## Starting checklists (to be enriched by the owner of this extension)
* **Lean waste (TIMWOODS)** to BPMN signals: Transport = hand-offs across lanes/pools; Inventory = queues before tasks (wait timers, receive tasks); Motion = system switching (user tasks across systems); Waiting = timer/message catch events, approvals; Over-production = parallel tasks whose output is unused; Over-processing = duplicate checks (duplicate names, serial approvals); Defects = rework loops, error boundary events; Skills = tasks routed to the wrong role.
* **Value classification** per activity: value-adding (customer would pay), business-value-adding (required), non-value-adding. Record in the sidecar, show with overlay colours and a legend.
* **Flow metrics**: cycle time, wait time, process cycle efficiency (value-adding time / lead time), first-pass yield, rolled throughput yield (product of step yields), takt vs cycle time, WIP.
* **DMAIC mapping**: Define = scope, trigger, outcomes, SIPOC derived from pools/messages/data; Measure = sidecar metrics; Analyse = bottlenecks, rework loops, handoff counts, variants; Improve = to-be model, error-proofing, automation candidates (manual to service task); Control = KPIs on events (start/end) and timers, SLAs as timer boundary events.
* **Tools to wire in later**: SIPOC table, spaghetti/hand-off count, Pareto of pain points, FMEA on exception paths, simulation inputs (probabilities on flows, durations on tasks).

## Output conventions
Improvement overlay image + a table of findings (element id, finding, evidence, estimated effect, confidence). Never present a projected saving as a fact without data.
