# Extension space

The core skill guarantees a *valid, evidence-backed BPMN model with stable element ids*. Everything below builds on that.
Status: **core implemented**; extension modules are **stubs with a defined contract**, to be enriched.

| Extension | File | Status |
|---|---|---|
| Lean / Six Sigma improvement | `improvement-lean-sixsigma.md` | stub: contract and starting checklists |
| ArchiMate and value-stream thinking | `archimate-vsm.md` | stub: mapping and handoff protocol |
| Standard process hierarchies (APQC PCF etc.) | `process-hierarchy-apqc.md` | stub: refresh protocol, level mapping |

## Contract between core and extensions
1. **Stable ids.** Never renumber ids when improving a model; extensions key their data by element id.
2. **Analysis sidecar** `<model>.analysis.json` (created by an extension, optional):
```json
{"model": "order-to-cash.bpmn", "framework_versions": {"apqc_pcf": {"version": "...", "retrieved": "YYYY-MM-DD", "source": "url"}},
 "elements": {"Task_Check": {"cycle_time_min": 12, "wait_time_min": 240, "volume_per_week": 300, "fte": 1.5, "error_rate_pct": 4,
                              "value_class": "NVA|BVA|VA", "waste": ["waiting", "defects"], "pain": "Re-keying of data",
                              "system": "SAP", "owner": "Sales ops", "hierarchy_id": "9.2.1", "archimate_id": "id-..."}},
 "flows": {"Flow_3": {"probability": 0.8}},
 "notes": []}
```
All keys are optional and extensible. Values are facts from evidence or measured data (tag them `[stated]`, `[observed]`, `[assumed]` in `notes`).
3. **Overlays, not edits.** Visualise analysis with `bpmn.py render --overlay` (fill colour, outline, badge, note; see `authoring-guide.md`). The spec permits colour and
extra markers (cl. 2.2.3) as long as specified shapes and line styles are unchanged, so overlays do not break conformance.
4. **To-be models are new files** (`as-is`, `to-be`) linked by ids and documented changes; never overwrite the as-is.
5. Improvement proposals must reference ledger evidence or measurements; label estimates as such.
6. If improvement changes control flow, re-run `validate --soundness` and show the diff.
