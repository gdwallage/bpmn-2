#!/usr/bin/env python3
"""BPMN 2.0.2 validator: official XSD + structural rules from the specification + conformance
level classification + (optional) token-game soundness analysis.

Usage:  validate_bpmn.py model.bpmn [--level descriptive|analytic|executable] [--soundness]
                         [--no-style] [--no-xsd] [--json]
Exit codes: 0 = no errors, 1 = errors found, 2 = unreadable / not BPMN.

Every error-severity rule cites the clause of OMG formal/2013-12-09 it comes from. Warnings are
modelling-quality findings (spec "SHOULD"/RECOMMENDED, or widely accepted style) and never block
a conformance claim; info items are observations.
"""
from __future__ import annotations

import argparse
import itertools
import json
import os
import sys
from collections import defaultdict, deque
from dataclasses import dataclass, asdict

from lxml import etree

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bpmnlib import *  # noqa

XSD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "xsd")

START_OK = {"none", "message", "timer", "conditional", "signal", "multiple", "parallelMultiple"}
START_ESP_OK = {"message", "timer", "error", "escalation", "compensation", "conditional", "signal",
                "multiple", "parallelMultiple"}
END_OK = {"none", "message", "escalation", "error", "cancel", "compensation", "signal", "terminate",
          "multiple"}
INT_THROW_OK = {"none", "message", "escalation", "link", "compensation", "signal", "multiple"}
INT_CATCH_OK = {"message", "timer", "conditional", "link", "signal", "multiple", "parallelMultiple"}
BOUNDARY_OK = {"message", "timer", "escalation", "error", "cancel", "compensation", "conditional",
               "signal", "multiple", "parallelMultiple"}
EVENT_GATEWAY_TARGET_TRIGGERS = {"message", "signal", "timer", "conditional", "multiple"}


@dataclass
class Issue:
    sev: str          # error | warning | info
    code: str
    msg: str
    el: str | None = None
    clause: str | None = None

    def __str__(self):
        loc = f" [{self.el}]" if self.el else ""
        cl = f" (spec {self.clause})" if self.clause else ""
        return f"{self.sev.upper():7} {self.code}{loc}: {self.msg}{cl}"


class Validator:
    def __init__(self, model: Model, level=None, style=True, soundness=False, xsd=True):
        self.m = model
        self.level = level
        self.style = style
        self.soundness = soundness
        self.use_xsd = xsd
        self.issues: list[Issue] = []

    # ------------------------------------------------------------------------------------------
    def add(self, sev, code, msg, el=None, clause=None):
        if isinstance(el, etree._Element):
            el = el.get("id") or ln(el)
        self.issues.append(Issue(sev, code, msg, el, clause))

    def err(self, code, msg, el=None, clause=None):
        self.add("error", code, msg, el, clause)

    def warn(self, code, msg, el=None, clause=None):
        self.add("warning", code, msg, el, clause)

    def info(self, code, msg, el=None, clause=None):
        self.add("info", code, msg, el, clause)

    def nm(self, el):
        n = el.get("name")
        return f"'{n}'" if n else f"<{ln(el)}>"

    # ------------------------------------------------------------------------------------------
    def run(self):
        m = self.m
        if ln(m.root) != "definitions" or ns_of(m.root) != BPMN_NS:
            self.err("X001", "Root element must be bpmn:definitions in namespace " + BPMN_NS, None, "8.2.1")
            return self.issues
        self.check_basics()
        if self.use_xsd:
            self.check_xsd()
        self.check_references()
        self.check_di()
        for proc in m.of("process", "subProcess", "adHocSubProcess", "transaction"):
            self.check_container(proc)
        self.check_events()
        self.check_gateways()
        self.check_activities()
        self.check_collaboration()
        self.check_data_and_artifacts()
        self.check_choreography()
        self.check_graph_hygiene()
        if self.style:
            self.check_style()
        if self.soundness:
            self.check_soundness()
        if self.level:
            self.check_level()
        return self.issues

    # ---- 1. basics ---------------------------------------------------------------------------
    def check_basics(self):
        m = self.m
        if not m.root.get("targetNamespace"):
            self.err("X002", "bpmn:definitions requires a targetNamespace attribute", m.root, "8.2.1 / XSD")
        for d in sorted(set(m.duplicate_ids)):
            self.err("X020", f"Duplicate id '{d}' (ids must be unique in the file)", d, "8.3.1")
        if not list(m.of("process", "choreography", "collaboration")):
            self.err("X003", "File contains no process, collaboration or choreography", None, "10.1")

    def check_xsd(self):
        path = os.path.join(XSD_DIR, "BPMN20.xsd")
        if not os.path.exists(path):
            self.info("X010", "Official XSD not found next to the scripts; schema check skipped")
            return
        try:
            schema = etree.XMLSchema(etree.parse(path))
        except Exception as e:  # pragma: no cover
            self.info("X010", f"Could not load XSD ({e}); schema check skipped")
            return
        doc = self.m.root.getroottree()
        if not schema.validate(doc):
            seen = set()
            lines = {}
            for el in self.m.root.iter():
                if isinstance(el.tag, str) and el.get("id") and el.sourceline:
                    lines[el.sourceline] = el.get("id")
            for e in schema.error_log:
                msg = e.message
                for pfx in ("{" + BPMN_NS + "}", "{" + BPMNDI_NS + "}", "{" + DC_NS + "}", "{" + DI_NS + "}"):
                    msg = msg.replace(pfx, "")
                key = (e.line, msg)
                if key in seen:
                    continue
                seen.add(key)
                near = None
                for ln_ in range(e.line, max(0, e.line - 6), -1):
                    if ln_ in lines:
                        near = lines[ln_]
                        break
                self.err("X011", f"XSD: {msg} (line {e.line})", near, "15.3 / BPMN20.xsd")
                if len(seen) >= 25:
                    self.info("X012", "More than 25 schema errors; showing the first 25 only")
                    break

    # ---- 2. references -----------------------------------------------------------------------
    def check_references(self):
        m = self.m
        ref_attrs = {
            "sequenceFlow": ["sourceRef", "targetRef"], "messageFlow": ["sourceRef", "targetRef"],
            "association": ["sourceRef", "targetRef"], "boundaryEvent": ["attachedToRef"],
            "participant": ["processRef"], "dataObjectReference": ["dataObjectRef"],
            "dataStoreReference": ["dataStoreRef"], "conversationLink": ["sourceRef", "targetRef"],
        }
        for tag, attrs in ref_attrs.items():
            for el in m.of(tag):
                for a in attrs:
                    v = el.get(a)
                    if v is None:
                        if tag in ("sequenceFlow", "messageFlow", "association", "boundaryEvent", "conversationLink") or \
                                (tag == "dataObjectReference" and a == "dataObjectRef" and False):
                            self.err("R001", f"{tag} is missing required attribute {a}", el, "8.4 / XSD")
                        continue
                    if m.get(v) is None:
                        self.err("R002", f"{tag}.{a}='{v}' does not resolve to any element", el, "8.3 / XSD")
        for el in m.of(*ACTIVITIES, "exclusiveGateway", "inclusiveGateway", "complexGateway"):
            d = el.get("default")
            if d and m.get(d) is None:
                self.err("R002", f"default='{d}' does not resolve to a sequence flow", el, "8.4.13")
        for el in m.of("flowNodeRef"):
            if m.get(text_of(el)) is None:
                self.err("R002", f"lane flowNodeRef '{text_of(el)}' does not resolve", el.getparent(), "10.8")
        for tag in ("dataInputAssociation", "dataOutputAssociation"):
            for el in m.of(tag):
                for c in kids(el, "sourceRef", "targetRef"):
                    if m.get(text_of(c)) is None:
                        self.err("R002", f"{tag}/{ln(c)} '{text_of(c)}' does not resolve", el, "10.4.1")
        for tag, attr in (("messageEventDefinition", "messageRef"), ("signalEventDefinition", "signalRef"),
                          ("errorEventDefinition", "errorRef"), ("escalationEventDefinition", "escalationRef")):
            for el in m.of(tag):
                v = el.get(attr)
                if v and m.get(v) is None:
                    self.err("R002", f"{tag}.{attr}='{v}' does not resolve", el.getparent(), "8.4 / 10.5.5")
        for el in m.of("incoming", "outgoing"):
            if m.get(text_of(el)) is None:
                self.err("R002", f"{ln(el)} reference '{text_of(el)}' does not resolve", el.getparent(), "8.4.7")
        # incoming/outgoing consistency (optional elements, but wrong values are misleading)
        for node in m.of(*FLOW_NODES):
            nid = node.get("id")
            inc = {text_of(c) for c in kids(node, "incoming")}
            out = {text_of(c) for c in kids(node, "outgoing")}
            real_in = {sf.get("id") for sf in m.flows_to(nid)}
            real_out = {sf.get("id") for sf in m.flows_from(nid)}
            if inc and inc != real_in:
                self.warn("R003", "incoming list does not match the sequence flows that target this node", node, "8.4.7")
            if out and out != real_out:
                self.warn("R003", "outgoing list does not match the sequence flows from this node", node, "8.4.7")
        for sf in m.of("sequenceFlow"):
            for a in ("sourceRef", "targetRef"):
                t = m.get(sf.get(a))
                if t is not None and ln(t) not in FLOW_NODES:
                    self.err("F004", f"sequence flow {a} points to <{ln(t)}>; sequence flows connect flow nodes "
                                     "(events, activities, gateways) only", sf, "7.6.1 / 8.4.1")

    # ---- 3. diagram interchange --------------------------------------------------------------
    def check_di(self):
        m = self.m
        diagrams = m.diagrams()
        if not diagrams:
            self.info("D001", "No BPMN DI (diagram layout) in the file; render_bpmn will compute a layout and write it.")
            return
        for d in diagrams:
            plane = d.find(q("BPMNPlane", BPMNDI_NS))
            if plane is None:
                self.err("D002", "BPMNDiagram without BPMNPlane", d, "12.2")
                continue
            root_ref = plane.get("bpmnElement")
            if root_ref and m.get(root_ref) is None:
                self.err("D003", f"BPMNPlane.bpmnElement='{root_ref}' not found", plane, "12.2.3.2")
            shown = set()
            shape_bounds = {}
            for sh in plane.iterchildren(q("BPMNShape", BPMNDI_NS)):
                ref = sh.get("bpmnElement")
                if ref is None or m.get(ref) is None:
                    self.err("D003", f"BPMNShape references missing element '{ref}'", sh, "12.2.3.3")
                    continue
                shown.add(ref)
                b = sh.find(q("Bounds", DC_NS))
                if b is None:
                    self.err("D004", f"BPMNShape for '{ref}' has no dc:Bounds", sh, "12.2.3.3")
                else:
                    try:
                        x, y, w, h = (float(b.get(k)) for k in ("x", "y", "width", "height"))
                        if w <= 0 or h <= 0:
                            self.err("D004", f"BPMNShape for '{ref}' has non-positive size", sh, "12.2.3.3")
                        shape_bounds[ref] = (x, y, w, h)
                    except (TypeError, ValueError):
                        self.err("D004", f"BPMNShape for '{ref}' has non-numeric bounds", sh, "12.2.3.3")
            for ed in plane.iterchildren(q("BPMNEdge", BPMNDI_NS)):
                ref = ed.get("bpmnElement")
                if ref is None or m.get(ref) is None:
                    self.err("D003", f"BPMNEdge references missing element '{ref}'", ed, "12.2.3.5")
                    continue
                shown.add(ref)
                wps = list(ed.iterchildren(q("waypoint", DI_NS)))
                if len(wps) < 2:
                    self.err("D004", f"BPMNEdge for '{ref}' needs at least 2 di:waypoint", ed, "12.2.3.5")
                    continue
                el = m.get(ref)
                if ln(el) in ("sequenceFlow", "messageFlow") and len(wps) >= 2:
                    for end, wp, a in ((0, wps[0], "sourceRef"), (-1, wps[-1], "targetRef")):
                        tid = local_id(el.get(a))
                        if tid in shape_bounds:
                            x, y, w, h = shape_bounds[tid]
                            px, py = float(wp.get("x")), float(wp.get("y"))
                            dx = max(x - px, 0, px - (x + w))
                            dy = max(y - py, 0, py - (y + h))
                            if (dx * dx + dy * dy) ** 0.5 > 12:
                                self.warn("D005", f"waypoint {'start' if end == 0 else 'end'} is {((dx*dx+dy*dy)**0.5):.0f}px "
                                                  f"away from the {a.replace('Ref','')} shape (edge looks detached)", ref, "12.2.3.5")
            # completeness
            if root_ref:
                root = m.get(root_ref)
                expected = self._expected_shapes(root)
                miss = [i for i in expected if i not in shown]
                if miss:
                    self.warn("D006", f"{len(miss)} element(s) have no shape/edge in plane '{root_ref}': "
                                      + ", ".join(miss[:8]) + (" ..." if len(miss) > 8 else ""), plane, "12.3")

    def _expected_shapes(self, root):
        ids = []
        m = self.m
        scope = [root]
        if ln(root) == "collaboration":
            scope = [root] + [m.process_of_participant(p) for p in kids(root, "participant")
                              if m.process_of_participant(p) is not None]
            ids += [p.get("id") for p in kids(root, "participant")]
            ids += [mf.get("id") for mf in kids(root, "messageFlow")]
        if ln(root) in SUBPROCS | {"process"}:
            pass
        for proc in scope:
            if proc is None:
                continue
            for el in proc.iter():
                if not isinstance(el.tag, str) or ns_of(el) != BPMN_NS:
                    continue
                n = ln(el)
                if el is not proc and n in SUBPROCS and not self._shape_expanded(el):
                    # collapsed sub-process: its children live in another plane
                    pass
                if n in FLOW_NODES | DATA_VISUAL | ARTIFACTS | {"sequenceFlow", "association", "lane"}:
                    if el.get("id") and self._inside_visible(el, proc):
                        ids.append(el.get("id"))
                if n in ("dataInputAssociation", "dataOutputAssociation") and False:
                    pass
        return ids

    def _shape_expanded(self, sp):
        for sh in self.m.root.iter(q("BPMNShape", BPMNDI_NS)):
            if sh.get("bpmnElement") == sp.get("id"):
                v = sh.get("isExpanded")
                if v is not None:
                    return is_true(v)
        return False

    def _inside_visible(self, el, proc):
        """True when `el` is not hidden inside a collapsed sub-process."""
        p = el.getparent()
        while p is not None and p is not proc:
            if ln(p) in SUBPROCS and not self._shape_expanded(p):
                return False
            p = p.getparent()
        return True

    # ---- 4. containers: start/end/flows -----------------------------------------------------
    def check_container(self, proc):
        m = self.m
        pid = proc.get("id")
        nodes = m.flow_nodes(proc)
        node_ids = {n.get("id") for n in nodes}
        in_esp = m.is_event_subprocess(proc)
        flows = m.sequence_flows(proc)

        starts = [n for n in nodes if ln(n) == "startEvent"]
        ends = [n for n in nodes if ln(n) == "endEvent"]
        if ends and not starts:
            self.err("F007", "End event present but no start event at this process level", proc, "10.5.2")
        if starts and not ends:
            self.err("F007", "Start event present but no end event at this process level", proc, "10.5.3")
        if ln(proc) == "adHocSubProcess" and (starts or ends):
            self.err("F017", "Ad-hoc sub-process must not contain start or end events", proc, "10.3.5")
        if in_esp:
            if len(starts) != 1:
                self.err("F016", f"Event sub-process must have exactly one start event (found {len(starts)})", proc, "10.3.5")
        for sf in flows:
            s, t = sf.get("sourceRef"), sf.get("targetRef")
            sn, tn = m.get(s), m.get(t)
            if sn is None or tn is None:
                continue
            for end, node in (("source", sn), ("target", tn)):
                if node.get("id") not in node_ids and ln(node) in FLOW_NODES:
                    # find where it is
                    self.err("F001", f"sequence flow {end} '{node.get('id')}' is not in the same process/sub-process "
                                     f"('{pid}') as the flow. Sequence flows cannot cross pool or sub-process boundaries "
                                     "(use message flow between pools; connect to the sub-process itself, not its children)",
                             sf, "7.6.1")
            if ln(sn) == "endEvent":
                self.err("F002", "end event cannot be the source of a sequence flow", sf, "10.5.3")
            if ln(tn) == "startEvent":
                self.err("F003", "start event cannot be the target of a sequence flow", sf, "10.5.2")
            if ln(tn) == "boundaryEvent":
                self.err("F009", "boundary event cannot be the target of a sequence flow", sf, "10.5.4")
            if ln(sn) == "intermediateCatchEvent" and m.event_trigger(sn) == "link":
                pass
            if sn.get("id") == tn.get("id"):
                self.warn("F030", "sequence flow loops from a node directly to itself", sf, "10.3")
            for node in (sn, tn):
                if m.is_event_subprocess(node):
                    self.err("F016", "event sub-process must not have incoming or outgoing sequence flows", sf, "10.3.5")
            for node in (sn, tn):
                if ln(node) in ACTIVITIES and is_true(node.get("isForCompensation")):
                    self.err("F015", "a compensation activity must not be connected by sequence flows", sf, "10.3 / 10.7")
            cond = sf.find(q("conditionExpression"))
            if cond is not None:
                if ln(sn) in ("parallelGateway", "eventBasedGateway"):
                    self.err("F013", f"conditional sequence flow out of a {ln(sn)} (parallel and event-based "
                                     "gateways cannot carry conditions)", sf, "8.4.13 / 10.6.6")
                if ln(sn) == "startEvent":
                    self.err("F019", "outgoing sequence flows of a start event must not have a condition", sf, "10.5.2")
                if ln(sn) in ACTIVITIES:
                    outs = [x for x in m.flows_from(sn.get("id"))]
                    if len(outs) < 2:
                        self.err("F014", "a conditional flow leaving an activity needs at least one other outgoing flow "
                                         "(otherwise the condition is meaningless)", sf, "8.4.13")
                if sn.get("default") == sf.get("id"):
                    self.err("F013", "the default flow must not have a condition expression", sf, "8.4.13")

    # ---- 5. events ---------------------------------------------------------------------------
    def check_events(self):
        m = self.m
        link_throw, link_catch = defaultdict(list), defaultdict(list)
        for ev in m.of(*EVENTS):
            n = ln(ev)
            if n == "implicitThrowEvent":
                continue
            trig = m.event_trigger(ev)
            nid = ev.get("id")
            ins, outs = m.flows_to(nid), m.flows_from(nid)
            cont = m.container_of(ev)
            in_esp = cont is not None and m.is_event_subprocess(cont) and ev.getparent() is cont
            if n == "startEvent":
                ok = START_ESP_OK if in_esp else START_OK
                if trig not in ok:
                    code = "F011"
                    if in_esp and trig == "none":
                        self.err(code, "an event sub-process start event must have a trigger; 'none' is not allowed",
                                 ev, "10.3.5 / 10.5.5")
                    else:
                        self.err(code, f"start event cannot have a '{trig}' trigger{' in an event sub-process' if in_esp else ''}",
                                 ev, "10.5.2")
                if ins:
                    self.err("F003", "start event must not have incoming sequence flows", ev, "10.5.2")
                if not outs:
                    self.err("F005", "start event must be the source of at least one sequence flow", ev, "10.5.2")
                if not in_esp and not m.is_interrupting(ev) and trig in ("none",):
                    self.warn("F011", "non-interrupting only makes sense for start events of event sub-processes", ev, "10.5.2")
                if m.event_triggers(ev).count("compensation") and cont is not None and ln(cont) == "process":
                    self.err("F011", "compensation start event may not be used in a top-level process", ev, "10.5.5")
                if in_esp and trig == "compensation" and False:
                    pass
            elif n == "endEvent":
                if trig not in END_OK:
                    self.err("F011", f"end event cannot have a '{trig}' result", ev, "10.5.3")
                if trig == "cancel" and not (cont is not None and ln(cont) == "transaction"):
                    self.err("F018", "cancel end event may only be used inside a transaction sub-process", ev, "10.5.5")
                if not ins:
                    self.err("F006", "end event must be the target of at least one sequence flow", ev, "10.5.3")
                if outs:
                    self.err("F002", "end event must not have outgoing sequence flows", ev, "10.5.3")
                mfs = [mf for mf in m.of("messageFlow") if local_id(mf.get("sourceRef")) == nid]
                if mfs and trig not in ("message", "multiple"):
                    self.err("F021", "end event with outgoing message flow must have a message (or multiple) result", ev, "10.5.3")
                if len(mfs) > 1 and trig != "multiple":
                    self.err("F021", "end event with more than one outgoing message flow must have a 'multiple' result", ev, "10.5.3")
            elif n == "boundaryEvent":
                host = m.get(ev.get("attachedToRef"))
                if trig not in BOUNDARY_OK:
                    self.err("F010", f"boundary event cannot have a '{trig}' trigger", ev, "10.5.4")
                if host is not None:
                    if ln(host) not in ACTIVITIES:
                        self.err("F010", "boundary event must be attached to an activity", ev, "10.5.4")
                    elif trig == "cancel" and ln(host) != "transaction":
                        self.err("F018", "cancel boundary event may only be attached to a transaction sub-process", ev, "10.5.4")
                    elif m.is_event_subprocess(host):
                        self.err("F010", "boundary events cannot be attached to an event sub-process", ev, "10.5.4")
                if ins:
                    self.err("F009", "boundary event must not have incoming sequence flows", ev, "10.5.4")
                if trig == "compensation":
                    if outs:
                        self.err("F009", "compensation boundary event must not have outgoing sequence flows "
                                         "(use an association to the compensation activity)", ev, "10.5.4")
                    assoc = [a for a in m.of("association") if local_id(a.get("sourceRef")) == nid]
                    if not assoc:
                        self.warn("F009", "compensation boundary event has no association to a compensation activity", ev, "10.7.1")
                elif not outs:
                    self.err("F009", "boundary event must have at least one outgoing sequence flow", ev, "10.5.4")
                if not m.is_interrupting(ev) and trig in ("error", "cancel", "compensation"):
                    self.err("F010", f"a {trig} boundary event is always interrupting; remove cancelActivity='false'", ev, "10.5.4")
            elif n in ("intermediateCatchEvent", "intermediateThrowEvent"):
                if n == "intermediateCatchEvent":
                    if trig == "none":
                        self.warn("F011", "intermediateCatchEvent without an event definition; a 'none' intermediate event is an "
                                          "intermediateThrowEvent", ev, "10.5.4")
                    elif trig not in INT_CATCH_OK:
                        self.err("F011", f"a catching intermediate event in normal flow cannot be '{trig}'"
                                         + (" (it is only valid as a boundary event)" if trig in ("error", "cancel", "compensation", "escalation") else ""),
                                 ev, "10.5.4 / 10.5.5")
                else:
                    if trig not in INT_THROW_OK:
                        self.err("F011", f"a throwing intermediate event cannot be '{trig}'", ev, "10.5.4")
                if not ins:
                    if not (n == "intermediateCatchEvent" and trig == "link"):
                        self.err("F008", "intermediate event in normal flow must have an incoming sequence flow", ev, "10.5.4")
                if not outs:
                    if not (n == "intermediateThrowEvent" and trig == "link"):
                        self.err("F008", "intermediate event in normal flow must have an outgoing sequence flow", ev, "10.5.4")
                if trig == "link":
                    if ins and outs:
                        self.err("F012", "a link event must not be both a target and a source of sequence flows", ev, "10.5.4")
                    name = (ev.get("name") or "").strip()
                    ld = ev.find(q("linkEventDefinition"))
                    if not name and ld is not None:
                        name = (ld.get("name") or "").strip()
                    if not name:
                        self.err("F012", "link event needs a name to be matched with its counterpart", ev, "10.5.4")
                    (link_throw if n == "intermediateThrowEvent" else link_catch)[(cont.get("id") if cont is not None else "", name)].append(ev)
                mfs_in = [mf for mf in m.of("messageFlow") if local_id(mf.get("targetRef")) == nid]
                mfs_out = [mf for mf in m.of("messageFlow") if local_id(mf.get("sourceRef")) == nid]
                if mfs_in and mfs_out:
                    self.err("F021", "a message intermediate event may have an incoming OR an outgoing message flow, not both", ev, "10.5.4")
            # throw/catch hygiene for data (info only)
        for key, evs in link_throw.items():
            if key not in link_catch:
                for ev in evs:
                    self.err("F012", f"throwing link '{key[1]}' has no matching catching link with the same name", ev, "10.5.4")
        for key, evs in link_catch.items():
            if len(evs) > 1:
                for ev in evs[1:]:
                    self.err("F012", f"more than one catching link named '{key[1]}' (a throwing link needs exactly one target)", ev, "10.5.4")
            if key not in link_throw:
                for ev in evs:
                    self.warn("F012", f"catching link '{key[1]}' is never thrown", ev, "10.5.4")

    # ---- 6. gateways -------------------------------------------------------------------------
    def check_gateways(self):
        m = self.m
        for g in m.of(*GATEWAYS):
            n, gid = ln(g), g.get("id")
            ins, outs = m.flows_to(gid), m.flows_from(gid)
            if len(ins) <= 1 and len(outs) <= 1 and (ins or outs):
                self.err("F013", f"{n} {self.nm(g)} neither splits nor merges (needs multiple incoming or multiple "
                                 "outgoing sequence flows)", g, "10.6.1")
            d = (g.get("gatewayDirection") or "Unspecified").lower()
            if d == "converging" and (len(ins) < 2 or len(outs) > 1):
                self.err("F013", "gatewayDirection='Converging' requires multiple incoming and at most one outgoing flow", g, "10.6.1")
            if d == "diverging" and (len(outs) < 2 or len(ins) > 1):
                self.err("F013", "gatewayDirection='Diverging' requires multiple outgoing and at most one incoming flow", g, "10.6.1")
            if d == "mixed" and (len(ins) < 2 or len(outs) < 2):
                self.err("F013", "gatewayDirection='Mixed' requires multiple incoming and multiple outgoing flows", g, "10.6.1")
            df = g.get("default")
            if df:
                dflow = m.get(df)
                if dflow is not None and local_id(dflow.get("sourceRef")) != gid:
                    self.err("F013", "default flow must be an outgoing flow of the same gateway", g, "8.4.13")
                if n in ("parallelGateway", "eventBasedGateway"):
                    self.err("F013", f"{n} cannot have a default flow", g, "8.4.13")
            if n == "eventBasedGateway":
                self.check_event_gateway(g, ins, outs)

    def check_event_gateway(self, g, ins, outs):
        m = self.m
        if len(outs) < 2:
            self.err("F020", "event-based gateway must have two or more outgoing sequence flows", g, "10.6.6")
        kinds = set()
        for sf in outs:
            if sf.find(q("conditionExpression")) is not None:
                self.err("F020", "outgoing flows of an event-based gateway must not have a condition", sf, "10.6.6")
            t = m.get(sf.get("targetRef"))
            if t is None:
                continue
            tn = ln(t)
            if tn == "receiveTask":
                kinds.add("receiveTask")
                if any(True for b in m.of("boundaryEvent") if local_id(b.get("attachedToRef")) == t.get("id")):
                    self.err("F020", "a receive task after an event-based gateway must not have boundary events", t, "10.6.6")
            elif tn == "intermediateCatchEvent":
                trig = m.event_trigger(t)
                if trig not in EVENT_GATEWAY_TARGET_TRIGGERS:
                    self.err("F020", f"event-based gateway target cannot be a '{trig}' intermediate event "
                                     "(valid: message, signal, timer, conditional, multiple)", t, "10.6.6")
                if trig == "message":
                    kinds.add("messageEvent")
            else:
                self.err("F020", f"event-based gateway target must be an intermediate catch event or a receive task, not <{tn}>",
                         t, "10.6.6")
            if len(m.flows_to(t.get("id"))) > 1:
                self.err("F020", "targets of an event-based gateway must not have other incoming sequence flows", t, "10.6.6")
        if {"receiveTask", "messageEvent"} <= kinds:
            self.err("F020", "event-based gateway mixes receive tasks and message events; use one kind only", g, "10.6.6")
        if g.get("eventGatewayType", "Exclusive").lower() == "parallel" and not is_true(g.get("instantiate")):
            self.err("F020", "eventGatewayType='Parallel' requires instantiate='true'", g, "10.6.6")

    # ---- 7. activities -----------------------------------------------------------------------
    def check_activities(self):
        m = self.m
        for a in m.of(*ACTIVITIES):
            n, aid = ln(a), a.get("id")
            if is_true(a.get("isForCompensation")):
                assoc = [x for x in m.of("association") if local_id(x.get("targetRef")) == aid]
                if not assoc:
                    self.warn("F015", "compensation activity is not the target of a compensation association", a, "10.7.1")
            df = a.get("default")
            if df:
                dflow = m.get(df)
                if dflow is not None and local_id(dflow.get("sourceRef")) != aid:
                    self.err("F013", "default flow must be an outgoing flow of the same activity", a, "8.4.13")
            if n == "callActivity":
                ce = a.get("calledElement")
                if ce is None:
                    self.warn("F024", "call activity without calledElement (nothing is being called)", a, "10.3.6")
                else:
                    tgt = m.get(ce)
                    if tgt is None:
                        self.info("F024", f"calledElement '{ce}' is not defined in this file (treated as an external reference)", a, "10.3.6")
                    elif ln(tgt) not in ("process", "globalTask", "globalUserTask", "globalManualTask",
                                         "globalScriptTask", "globalBusinessRuleTask", "choreography", "collaboration"):
                        self.err("F024", f"calledElement points to <{ln(tgt)}>; must be a process or global task", a, "10.3.6")
            if n in SUBPROCS and not m.is_event_subprocess(a):
                if n == "adHocSubProcess" and not list(kids(a, *ACTIVITIES)):
                    self.warn("F017", "ad-hoc sub-process contains no activities", a, "10.3.5")
            if m.is_event_subprocess(a) and a.getparent() is not None and ln(a.getparent()) not in PROCESS_CONTAINERS:
                self.err("F016", "event sub-process must be nested directly in a process or sub-process", a, "10.3.5")
            if n == "transaction":
                pass
            lc, mi = a.find(q("standardLoopCharacteristics")), a.find(q("multiInstanceLoopCharacteristics"))
            if lc is not None and mi is not None:
                self.err("F025", "loop and multi-instance characteristics are mutually exclusive", a, "10.3.8")

    # ---- 8. collaboration / pools / lanes / message flows -----------------------------------
    def check_collaboration(self):
        m = self.m
        for col in m.collaborations():
            parts = list(kids(col, "participant"))
            pids = {p.get("id") for p in parts}
            for p in parts:
                pr = p.get("processRef")
                if pr and m.get(pr) is not None and ln(m.get(pr)) != "process":
                    self.err("F022", "participant.processRef must point to a process", p, "9.3")
                if self.style and not p.get("name"):
                    self.warn("S010", "participant (pool) has no name", p, "9.3")
            seen_proc = defaultdict(list)
            for p in parts:
                if p.get("processRef"):
                    seen_proc[local_id(p.get("processRef"))].append(p)
            for k, v in seen_proc.items():
                if len(v) > 1:
                    self.warn("F022", f"{len(v)} participants reference the same process '{k}'", v[1], "9.3")
            for mf in kids(col, "messageFlow"):
                self.check_message_flow(mf, col)
        for proc in m.processes():
            part = m.participant_of(proc)
            for ls in proc.iterchildren(q("laneSet")):
                self.check_lanes(proc, ls)
            if list(kids(proc, "laneSet")) and part is None:
                self.warn("F023", "process has lanes but no participant (pool); wrap it in a collaboration so the lanes sit "
                                  "inside a pool (render_bpmn does this automatically)", proc, "9.3 / 10.8")

    def check_lanes(self, proc, ls):
        m = self.m
        assigned = defaultdict(list)

        def walk(lset, depth=0):
            for lane in kids(lset, "lane"):
                if self.style and not lane.get("name"):
                    self.warn("S010", "lane has no name", lane, "10.8")
                for fr in kids(lane, "flowNodeRef"):
                    t = m.get(text_of(fr))
                    if t is not None:
                        if m.container_of(t) is not proc:
                            self.err("F023", f"lane references '{t.get('id')}' which is not a flow node of this process level", lane, "10.8")
                        assigned[text_of(fr)].append(lane.get("id"))
                child = lane.find(q("childLaneSet"))
                if child is not None:
                    walk(child, depth + 1)
        walk(ls)
        # a node in a parent and a child lane is expected; flag nodes with no lane at all
        top_nodes = [n.get("id") for n in m.flow_nodes(proc) if ln(n) != "boundaryEvent" and not m.is_event_subprocess(n)]
        miss = [i for i in top_nodes if i not in assigned]
        if miss:
            self.warn("F023", f"{len(miss)} flow node(s) are not assigned to any lane: " + ", ".join(miss[:8]), proc, "10.8")

    def check_message_flow(self, mf, col):
        m = self.m
        s, t = m.get(mf.get("sourceRef")), m.get(mf.get("targetRef"))
        if s is None or t is None:
            return

        def pool_of(el):
            if ln(el) == "participant":
                return el
            return m.participant_of(el)
        ps, pt = pool_of(s), pool_of(t)
        if ps is not None and pt is not None and ps is pt:
            self.err("F021", "a message flow must connect two separate pools; it cannot connect objects inside the same pool "
                             "(use a sequence flow)", mf, "9.4")
        if ps is None or pt is None:
            self.err("F021", "message flow endpoints must be a pool/participant or a flow object inside a pool", mf, "9.4")
        for role, node in (("source", s), ("target", t)):
            n = ln(node)
            if n in GATEWAYS or n in DATA_REFS or n in ARTIFACTS or n == "lane":
                self.err("F021", f"message flow {role} cannot be a <{n}>", mf, "7.6.2")
            elif n in EVENTS:
                trig = m.event_trigger(node)
                if trig not in ("message", "multiple", "parallelMultiple"):
                    self.err("F021", f"message flow {role} is a {n} with trigger '{trig}'; it must be a message (or multiple) event", mf, "10.5")
                if role == "source" and n in ("startEvent", "intermediateCatchEvent", "boundaryEvent"):
                    self.err("F021", f"message flow cannot leave a catching event ({n}); a sender is an end event, throwing intermediate event or task", mf, "10.5.2 / 10.5.4")
                if role == "target" and n in ("endEvent", "intermediateThrowEvent"):
                    self.err("F021", f"message flow cannot enter a throwing event ({n}); a receiver is a start event, catching intermediate event or task", mf, "10.5.3 / 10.5.4")
            elif n in ("sendTask",) and role == "target":
                self.warn("F021", "message flow targets a send task; use a receive task or another receiving element", mf, "10.3.3")
            elif n == "receiveTask" and role == "source":
                self.warn("F021", "message flow leaves a receive task; use a send task or another sending element", mf, "10.3.3")

    # ---- 9. data and artifacts ---------------------------------------------------------------
    def check_data_and_artifacts(self):
        m = self.m
        for tag in ("dataInputAssociation", "dataOutputAssociation"):
            for da in m.of(tag):
                for c in kids(da, "targetRef" if tag == "dataInputAssociation" else "sourceRef"):
                    t = m.get(text_of(c))
                    if t is not None and ln(t) in ACTIVITIES | EVENTS:
                        self.warn("DA01", f"{tag} points at the {ln(t)} itself. The metamodel requires an item-aware target "
                                          "(Property, DataInput or DataOutput); the skill's normaliser fixes this automatically.",
                                  da, "10.4.1 / Table 2.1 note a")
        for a in m.of("association"):
            s, t = m.get(a.get("sourceRef")), m.get(a.get("targetRef"))
            if s is None or t is None:
                continue
            d = (a.get("associationDirection") or "None")
            if ln(s) in ("textAnnotation", "group") and ln(t) in ("textAnnotation",):
                self.warn("A001", "association between two text annotations is unusual", a, "8.4.1")
        for g in m.of("group"):
            if not g.get("categoryValueRef") and self.style:
                self.info("A002", "group without categoryValueRef has no visible label", g, "8.4.1")

    # ---- 10. choreography / conversation (structural essentials) -----------------------------
    def check_choreography(self):
        m = self.m
        for ct in m.of("choreographyTask", "subChoreography", "callChoreography"):
            parts = [text_of(c) for c in kids(ct, "participantRef")]
            if ln(ct) == "choreographyTask" and len(parts) != 2:
                self.err("C001", f"choreography task involves exactly two participants (found {len(parts)})", ct, "11.5.1")
            if ln(ct) == "subChoreography" and len(parts) < 2:
                self.err("C001", "sub-choreography needs two or more participants", ct, "11.5.2")
            ini = ct.get("initiatingParticipantRef")
            if ini is None:
                self.err("C002", "choreography activity needs initiatingParticipantRef", ct, "11.5.1")
            elif parts and local_id(ini) not in [local_id(p) for p in parts]:
                self.err("C002", "initiatingParticipantRef must be one of the activity's participantRefs", ct, "11.5.1")
        for cl in m.of("conversationLink"):
            s, t = m.get(cl.get("sourceRef")), m.get(cl.get("targetRef"))
            if s is not None and t is not None:
                ok = (ln(s) == "participant" and ln(t) in CONV_NODES) or (ln(t) == "participant" and ln(s) in CONV_NODES)
                if not ok:
                    self.err("C003", "a conversation link connects a participant with a conversation node", cl, "9.5.6")

    # ---- 11. graph hygiene (reachability) ----------------------------------------------------
    def _container_graph(self, proc):
        m = self.m
        nodes = {n.get("id"): n for n in m.flow_nodes(proc)}
        succ = defaultdict(set)
        for sf in m.sequence_flows(proc):
            s, t = local_id(sf.get("sourceRef")), local_id(sf.get("targetRef"))
            if s in nodes and t in nodes:
                succ[s].add(t)
        # boundary events act as extra edges host -> event
        for n in list(nodes.values()):
            if ln(n) == "boundaryEvent":
                h = local_id(n.get("attachedToRef"))
                if h in nodes:
                    succ[h].add(n.get("id"))
        # link events: throw -> catch of the same name
        def link_name(n):
            nme = (n.get("name") or "").strip()
            if not nme:
                ld = n.find(q("linkEventDefinition"))
                nme = (ld.get("name") or "").strip() if ld is not None else ""
            return nme
        throws, catches = defaultdict(list), defaultdict(list)
        for n in nodes.values():
            if ln(n) in ("intermediateThrowEvent", "intermediateCatchEvent") and m.event_trigger(n) == "link":
                (throws if ln(n) == "intermediateThrowEvent" else catches)[link_name(n)].append(n.get("id"))
        for nme, tids in throws.items():
            for tid in tids:
                for c in catches.get(nme, []):
                    succ[tid].add(c)
        return nodes, succ

    def check_graph_hygiene(self):
        m = self.m
        for proc in m.of("process", "subProcess", "adHocSubProcess", "transaction"):
            if m.is_event_subprocess(proc) and False:
                continue
            nodes, succ = self._container_graph(proc)
            if len(nodes) < 2:
                continue
            ids = set(nodes)
            has_in = {t for s in succ for t in succ[s]}
            starts = [i for i, n in nodes.items() if ln(n) == "startEvent"]
            roots = starts or [i for i in ids if i not in has_in and ln(nodes[i]) != "boundaryEvent"]
            # event sub-process children are their own containers, not part of this graph
            ignore = {i for i, n in nodes.items() if m.is_event_subprocess(n) or is_true(n.get("isForCompensation"))}
            ignore |= {i for i, n in nodes.items() if ln(n) == "intermediateCatchEvent" and m.event_trigger(n) == "link"}
            seen = set()
            dq = deque(roots)
            # catching link events are legitimate entry points
            dq.extend(i for i, n in nodes.items() if ln(n) == "intermediateCatchEvent" and m.event_trigger(n) == "link")
            while dq:
                x = dq.popleft()
                if x in seen:
                    continue
                seen.add(x)
                dq.extend(succ[x])
            for i in sorted(ids - seen - ignore):
                if ln(nodes[i]) == "boundaryEvent":
                    continue
                self.warn("P004", f"{ln(nodes[i])} {self.nm(nodes[i])} is not reachable from any start of this process level", nodes[i], "10.5.2 (instantiation)")
            ends = {i for i, n in nodes.items() if ln(n) == "endEvent" or not succ[i]}
            rev = defaultdict(set)
            for s in succ:
                for t in succ[s]:
                    rev[t].add(s)
            can = set()
            dq = deque(ends)
            while dq:
                x = dq.popleft()
                if x in can:
                    continue
                can.add(x)
                dq.extend(rev[x])
            for i in sorted(ids - can - ignore):
                if ln(nodes[i]) == "boundaryEvent":
                    continue
                self.warn("P005", f"{ln(nodes[i])} {self.nm(nodes[i])} cannot reach an end of this process level (endless loop)", nodes[i], "10.5.3")

    # ---- 12. style ---------------------------------------------------------------------------
    def check_style(self):
        m = self.m
        for n in m.of(*ACTIVITIES):
            if not n.get("name") and not m.is_event_subprocess(n):
                self.warn("S001", f"{ln(n)} has no name", n, "recommended style")
        for g in m.of("exclusiveGateway", "inclusiveGateway", "eventBasedGateway"):
            outs = m.flows_from(g.get("id"))
            if len(outs) > 1:
                if not g.get("name") and ln(g) != "eventBasedGateway":
                    self.warn("S003", f"{ln(g)} splits the flow but has no name (name it as the question being decided)", g, "recommended style")
                if ln(g) != "eventBasedGateway":
                    df = g.get("default")
                    unlabeled = [sf for sf in outs if not sf.get("name") and sf.find(q("conditionExpression")) is None and sf.get("id") != df]
                    if len(unlabeled) > 0 and len(outs) - (1 if df else 0) >= 1:
                        if len(unlabeled) == len(outs) or len(unlabeled) > 0:
                            self.warn("S003", f"{len(unlabeled)} outgoing flow(s) of {self.nm(g)} have neither a label nor a condition", g, "recommended style")
                    if ln(g) == "exclusiveGateway" and g.get("name") and not g.get("name").strip().endswith("?"):
                        self.info("S005", f"decision {self.nm(g)} is not phrased as a question", g, "recommended style")
        unnamed = [ev for ev in m.of("startEvent", "endEvent") if not ev.get("name")]
        if unnamed:
            self.info("S006", f"{len(unnamed)} start/end event(s) have no name ("
                              + ", ".join(e.get("id") or ln(e) for e in unnamed[:6]) + (" ..." if len(unnamed) > 6 else "")
                              + "); name events after the state they represent, e.g. 'Order received'", unnamed[0], "recommended style")
        for proc in m.of("process"):
            if not proc.get("name") and not m.participant_of(proc):
                self.warn("S008", "process has no name", proc, "recommended style")
            nodes = m.flow_nodes(proc)
            starts_none = [n for n in nodes if ln(n) == "startEvent" and m.event_trigger(n) == "none"]
            if len(starts_none) > 1:
                self.warn("S007", f"{len(starts_none)} none start events at one level: each start event creates its own independent "
                                  "process instance (use one start or distinct triggers)", proc, "10.5.2")
        for cont in list(m.of("process")) + list(m.of(*SUBPROCS)):
            nodes = m.flow_nodes(cont)
            cnt = len([n for n in nodes if ln(n) != "boundaryEvent"])
            if cnt > 30:
                self.warn("S004", f"{cnt} flow nodes at one level: too dense to read; decompose into sub-processes / call activities", cont, "recommended style")
            elif cnt > 20:
                self.info("S004", f"{cnt} flow nodes at one level; consider decomposing (about 7-15 per level reads best)", cont, "recommended style")
            names = defaultdict(list)
            for n in nodes:
                if ln(n) in ACTIVITIES and n.get("name"):
                    names[n.get("name").strip().lower()].append(n)
            for k, v in names.items():
                if len(v) > 1:
                    self.warn("S002", f"{len(v)} activities share the name '{v[0].get('name')}' in this level (duplicates are ambiguous; "
                                      "if it is the same work reused, use one call activity)", v[1], "recommended style")
        # exclusive gateway marker consistency (DI)
        flags = [sh.get("isMarkerVisible") for sh in m.root.iter(q("BPMNShape", BPMNDI_NS))
                 if m.get(sh.get("bpmnElement")) is not None and ln(m.get(sh.get("bpmnElement"))) == "exclusiveGateway"]
        if flags and len(set(flags)) > 1:
            self.warn("S009", "exclusive gateways are drawn inconsistently (some with the X marker, some without)", None, "10.6.2")

    # ---- 13. soundness (token game) ----------------------------------------------------------
    def check_soundness(self, limit=20000):
        m = self.m
        analysed = 0
        for proc in m.of("process", "subProcess", "adHocSubProcess", "transaction"):
            if ln(proc) == "adHocSubProcess":
                continue
            nodes = {n.get("id"): n for n in m.flow_nodes(proc) if ln(n) != "boundaryEvent"}
            flows = [sf for sf in m.sequence_flows(proc) if local_id(sf.get("sourceRef")) in nodes and local_id(sf.get("targetRef")) in nodes]
            if len(nodes) < 3 or not flows:
                continue
            if any(ln(n) == "complexGateway" for n in nodes.values()):
                self.info("P010", "complex gateway present: soundness analysis skipped for this level", proc)
                continue
            analysed += 1
            self._soundness_one(proc, nodes, flows, limit)
        if not analysed:
            self.info("P010", "soundness analysis: nothing to analyse (no process level with 3+ nodes)")

    def _soundness_one(self, proc, nodes, flows, limit):
        m = self.m
        eidx = {sf.get("id"): i for i, sf in enumerate(flows)}
        out_e = defaultdict(list)
        in_e = defaultdict(list)
        for sf in flows:
            out_e[local_id(sf.get("sourceRef"))].append(eidx[sf.get("id")])
            in_e[local_id(sf.get("targetRef"))].append(eidx[sf.get("id")])
        tgt = [local_id(sf.get("targetRef")) for sf in flows]
        src = [local_id(sf.get("sourceRef")) for sf in flows]

        # link events: treat throw -> catch jumps as virtual edges
        catch_by_name = {}
        for i, n in nodes.items():
            if ln(n) == "intermediateCatchEvent" and m.event_trigger(n) == "link":
                nme = (n.get("name") or "").strip()
                catch_by_name[nme] = i
        jump = {}
        for i, n in nodes.items():
            if ln(n) == "intermediateThrowEvent" and m.event_trigger(n) == "link":
                nme = (n.get("name") or "").strip()
                if nme in catch_by_name:
                    jump[i] = catch_by_name[nme]

        def kind(i):
            n = nodes[i]
            t = ln(n)
            if t == "parallelGateway":
                return "AND"
            if t in ("exclusiveGateway", "eventBasedGateway"):
                return "XOR"
            if t == "inclusiveGateway":
                return "OR"
            if t == "endEvent":
                return "END"
            return "ACT"

        # successors for OR-join reachability
        succ = defaultdict(set)
        for sf in flows:
            succ[local_id(sf.get("sourceRef"))].add(local_id(sf.get("targetRef")))
        for t, c in jump.items():
            succ[t].add(c)

        def reach_from_edges(marking_edges, avoid):
            seen = set()
            dq = deque(tgt[e] for e in marking_edges)
            while dq:
                x = dq.popleft()
                if x in seen or x == avoid:
                    continue
                seen.add(x)
                dq.extend(succ[x])
            return seen

        start_ids = [i for i, n in nodes.items() if ln(n) == "startEvent"]
        entries = []
        if start_ids:
            for s in start_ids:
                entries.append([e for e in out_e[s]])
        else:
            roots = [i for i in nodes if not in_e[i] and i not in jump.values()]
            entries.append([e for r in roots for e in out_e[r]] or [])
        results = {"deadlock": [], "unsafe": [], "nocomplete": False}
        for ei, entry in enumerate(entries):
            init = tuple(sorted(entry))
            start = {e: 0 for e in range(len(flows))}
            marking0 = defaultdict(int)
            for e in init:
                marking0[e] += 1

            def freeze(mk):
                return tuple(sorted((e, c) for e, c in mk.items() if c))

            seen = {freeze(marking0): None}
            dq = deque([dict(marking0)])
            completed = False
            deadlock_state = None
            unsafe_edge = None
            explored = 0
            truncated = False
            while dq:
                mk = dq.popleft()
                explored += 1
                if explored > limit:
                    self.info("P010", f"soundness analysis truncated after {limit} states in '{proc.get('id')}' (result inconclusive)", proc)
                    truncated = True
                    break
                succs = []
                total = sum(mk.values())
                if total == 0:
                    completed = True
                    continue
                for i, n in nodes.items():
                    k = kind(i)
                    ins, outs = in_e[i], out_e[i]
                    firings = []  # list of (consume edges, produce edges)
                    if k == "AND":
                        if ins and all(mk.get(e, 0) > 0 for e in ins):
                            firings.append((ins, outs))
                    elif k == "OR":
                        avail = [e for e in ins if mk.get(e, 0) > 0]
                        if avail:
                            if len(ins) > 1:
                                rest = {e for e in ins if e not in avail}
                                others = {e: c for e, c in mk.items() if c and e not in avail}
                                # an OR-join waits while any token elsewhere can still reach one of its empty inputs
                                upstream = reach_from_edges(list(others), i)
                                wait = any(src[e] in upstream for e in rest)
                                if wait:
                                    continue
                            subsets = [outs] if len(outs) <= 1 else [list(c) for r in range(1, len(outs) + 1)
                                                                    for c in itertools.combinations(outs, r)][:32]
                            for sub in subsets:
                                firings.append((avail, sub))
                    elif k in ("XOR", "ACT"):
                        for e in ins:
                            if mk.get(e, 0) > 0:
                                if k == "XOR":
                                    if len(outs) <= 1:
                                        firings.append(([e], outs))
                                    else:
                                        for o in outs:
                                            firings.append(([e], [o]))
                                else:
                                    cond = [sf for sf in flows if sf.get("id") and local_id(sf.get("sourceRef")) == i and sf.find(q("conditionExpression")) is not None]
                                    dflt = n.get("default")
                                    if len(outs) > 1 and (cond or dflt):
                                        for r in range(1, len(outs) + 1):
                                            for c in itertools.combinations(outs, r):
                                                firings.append(([e], list(c)))
                                    else:
                                        firings.append(([e], outs))
                    elif k == "END":
                        for e in ins:
                            if mk.get(e, 0) > 0:
                                if ln(n) == "endEvent" and m.event_trigger(n) == "terminate":
                                    firings.append(([e], "TERMINATE"))
                                else:
                                    firings.append(([e], []))
                    # link jumps and start events (never target of flows)
                    for cons, prod in firings:
                        nm = dict(mk)
                        for e in cons:
                            nm[e] -= 1
                        if prod == "TERMINATE":
                            nm = {}
                        else:
                            if i in jump:
                                # a throwing link re-emits on the catching link's outgoing flows
                                prod = out_e[jump[i]]
                            for e in prod:
                                nm[e] = nm.get(e, 0) + 1
                        nm = {e: c for e, c in nm.items() if c}
                        succs.append(nm)
                if not succs:
                    deadlock_state = mk
                    break_ = True
                    results["deadlock"].append((ei, mk))
                    continue
                for nm in succs:
                    fz = freeze(nm)
                    if fz in seen:
                        continue
                    seen[fz] = True
                    if any(c > 1 for c in nm.values()) and unsafe_edge is None:
                        unsafe_edge = [e for e, c in nm.items() if c > 1][0]
                        results["unsafe"].append((ei, unsafe_edge, nm))
                    dq.append(nm)
            if not completed and not results["deadlock"] and not truncated:
                results["nocomplete"] = True
        label = proc.get("name") or proc.get("id")
        seen_dead = set()
        for ei, mk in results["deadlock"][:3]:
            where = ", ".join(sorted({self.nm(nodes[tgt[e]]) for e, c in mk.items() if c}))
            key = where
            if key in seen_dead:
                continue
            seen_dead.add(key)
            self.warn("P001", f"possible DEADLOCK in '{label}': a token can get stuck waiting at {where} "
                              "(typically a parallel/inclusive join that not all branches reach, e.g. an exclusive split joined by a parallel join)",
                      proc, "13.4 (execution semantics)")
        for ei, e, mk in results["unsafe"][:2]:
            self.warn("P002", f"possible LACK OF SYNCHRONISATION in '{label}': two tokens can sit on flow '{flows[e].get('id')}' "
                              f"(→ {self.nm(m.get(flows[e].get('targetRef')))}); typically parallel branches merged by an exclusive "
                              "merge / uncontrolled merge", flows[e], "13.4 / 10.3 note")
        if results["nocomplete"]:
            self.warn("P003", f"no execution path of '{label}' reaches completion (endless loop?)", proc, "13.2")

    # ---- 14. conformance level --------------------------------------------------------------
    def check_level(self):
        if self.level == "full":
            return
        allowed = LEVELS.get(self.level)
        if allowed is None:
            self.err("L000", f"unknown level '{self.level}'")
            return
        kinds = element_kinds(self.m)
        for k, ids in sorted(kinds.items()):
            if k not in allowed:
                self.err("L001", f"'{k}' ({len(ids)}x, e.g. {ids[0]}) is outside the {LEVEL_LABEL[self.level]} sub-class; "
                                 f"simplify it or choose a higher level", ids[0], "2.2.2")


# ------------------------------------------------------------------------------------------------
def summarise(model: Model):
    kinds = element_kinds(model)
    minlvl = minimum_level(kinds.keys())
    exec_ok = set(kinds) <= EXECUTABLE
    counts = {"processes": len(model.processes()), "participants": len(list(model.participants())),
              "activities": len(list(model.of(*ACTIVITIES))), "events": len(list(model.of(*EVENTS))),
              "gateways": len(list(model.of(*GATEWAYS))), "sequenceFlows": len(list(model.of("sequenceFlow"))),
              "messageFlows": len(list(model.of("messageFlow"))), "diagrams": len(model.diagrams())}
    return {"minimum_level": minlvl, "minimum_level_label": LEVEL_LABEL[minlvl], "within_executable_subset": exec_ok,
            "counts": counts}


def validate_file(path, level=None, style=True, soundness=False, xsd=True):
    try:
        model = Model.parse(path)
    except etree.XMLSyntaxError as e:
        return None, [Issue("error", "X000", f"Not well-formed XML: {e}")], None
    v = Validator(model, level=level, style=style, soundness=soundness, xsd=xsd)
    issues = v.run()
    summ = summarise(model) if ln(model.root) == "definitions" else None
    return model, issues, summ


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file")
    ap.add_argument("--level", choices=["descriptive", "analytic", "executable", "full"], help="require the model to stay inside this conformance sub-class")
    ap.add_argument("--soundness", action="store_true", help="token-game deadlock / lack-of-synchronisation analysis")
    ap.add_argument("--no-style", action="store_true", help="hide style findings")
    ap.add_argument("--no-xsd", action="store_true", help="skip the official XSD check")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    model, issues, summ = validate_file(a.file, a.level, not a.no_style, a.soundness, not a.no_xsd)
    errors = [i for i in issues if i.sev == "error"]
    if a.json:
        print(json.dumps({"summary": summ, "issues": [asdict(i) for i in issues]}, indent=2))
    else:
        for i in issues:
            print(i)
        print()
        if summ:
            c = summ["counts"]
            print(f"Elements: {c['processes']} process(es), {c['participants']} pool(s), {c['activities']} activities, "
                  f"{c['events']} events, {c['gateways']} gateways, {c['sequenceFlows']} sequence flows, {c['messageFlows']} message flows")
            print(f"Minimum conformance sub-class needed: {summ['minimum_level_label']}"
                  + ("  | inside Common Executable subset" if summ["within_executable_subset"] else ""))
        w = len([i for i in issues if i.sev == "warning"])
        print(f"RESULT: {'INVALID' if errors else 'VALID'}  ({len(errors)} error(s), {w} warning(s))")
    if model is None:
        return 2
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
