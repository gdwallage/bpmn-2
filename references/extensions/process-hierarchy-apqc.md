# Standard process hierarchies, APQC PCF first (stub: refresh protocol and mapping)

Goal (from the project brief): the skill must know, understand and **refresh** standard process hierarchy models such as the APQC Process Classification Framework (PCF).

## What to carry in memory (verify before use)
Structure: five levels (Category, Process group, Process, Activity, Task), numbered hierarchically (for example `9.2.1`), a cross-industry framework (13 categories: 1 Develop vision and strategy, 2 Develop and manage products and services, 3 Market and sell, 4 Deliver physical products,
5 Deliver services, 6 Manage customer service, 7 Human capital, 8 Information technology, 9 Financial resources, 10 Assets, 11 Risk/compliance/resiliency, 12 External relationships, 13 Business capabilities) plus industry-specific versions.
**This list is from training knowledge and may be out of date; it is a pointer, not a source.**

## Refresh protocol (do this before putting any PCF id or name in a deliverable)
1. `web_search` for the current APQC PCF cross-industry version and the industry variant required (query: "APQC Process Classification Framework latest version"); open apqc.org pages.
2. Record **framework, version, retrieval date, URL** in the analysis sidecar `framework_versions` and in the deliverable footnote.
3. If the full framework is a download behind a form, ask the user to supply the file (xlsx/pdf); ingest with `scripts/ingest.py`; do not reconstruct numbering from memory.
4. If the user's organisation uses an adapted hierarchy, use theirs as master and map to PCF ids in the sidecar.
5. Re-check on every new engagement or when the version is older than 12 months; note changes (added, merged, renumbered processes) in a change log.
6. Other frameworks to treat the same way when asked: ITIL 4 value stream, eTOM (TM Forum), SCOR, BIAN (banking), ACORD (insurance), COBIT, Value Chain (Porter). Always check the current edition.

## Mapping to BPMN
See `../hierarchy-and-levels.md` (levels 3 to 5 become BPMN process / sub-process or call activity / task; levels 1-2 are navigation structure).
Where to store ids: `<documentation>` text `Hierarchy: APQC PCF v<version> 9.2.1 Process accounts payable`, and `hierarchy_id` in the sidecar.
Suggested to-do for the extension owner: a `hierarchy.json` per framework version (id, name, parent, level) cached next to the skill, a validator that checks a model's hierarchy ids exist in that cache, and a roll-up view generator (process landscape diagram listing child BPMN diagrams).
