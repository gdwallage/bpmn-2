#!/usr/bin/env python3
"""Deterministic BPMN repairs applied before validation/rendering.

Each repair is behaviour-preserving and is reported in a change log so the author can
mention it. Nothing here guesses at process semantics.

  N1  reorder children into the order the BPMN XSD demands (flow elements before artifacts,
      BPMNDiagram last, laneSet first, eventDefinitions after data items ...)
  N2  wrap a process that has lanes but no pool in a collaboration + participant
  N3  data associations that point at an activity/event get an item-aware placeholder
      (Property '__targetRef_placeholder'), as the metamodel requires (Table 2.1 note a)
  N4  intermediateCatchEvent without any event definition -> intermediateThrowEvent (none)
  N5  ensure every flow element / flow has an id; targetNamespace; exporter attributes
  N6  drop incoming/outgoing lists that contradict the actual sequence flows (they are optional)
"""
from __future__ import annotations

import os
import sys

from lxml import etree

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bpmnlib import *  # noqa


def _rank_fn(order):
    idx = {n: i for i, n in enumerate(order)}

    def rank(el):
        n = ln(el)
        if ns_of(el) != BPMN_NS:
            return idx.get("__foreign__", len(order))
        return idx.get(n, idx.get("__other__", len(order)))
    return rank


FLOW_ELEMENT_NAMES = sorted(FLOW_NODES | {"sequenceFlow", "dataObject", "dataObjectReference",
                                          "dataStoreReference", "callChoreography"})
ARTIFACT_NAMES = ["association", "group", "textAnnotation"]

CONTAINER_ORDER = (["documentation", "extensionElements", "auditing", "monitoring", "property", "laneSet"]
                   + ["__flow__"] + ["__artifact__"]
                   + ["performer", "humanPerformer", "potentialOwner", "resourceRole",
                      "correlationSubscription", "supports"])
SUBPROCESS_ORDER = (["documentation", "extensionElements", "incoming", "outgoing", "ioSpecification", "property",
                     "dataInputAssociation", "dataOutputAssociation", "resourceRole", "performer",
                     "humanPerformer", "potentialOwner", "standardLoopCharacteristics",
                     "multiInstanceLoopCharacteristics", "laneSet", "__flow__", "__artifact__"])
ACTIVITY_ORDER = ["documentation", "extensionElements", "incoming", "outgoing", "ioSpecification", "property",
                  "dataInputAssociation", "dataOutputAssociation", "resourceRole", "performer", "humanPerformer",
                  "potentialOwner", "standardLoopCharacteristics", "multiInstanceLoopCharacteristics",
                  "rendering", "script"]
EVENT_ORDER = ["documentation", "extensionElements", "incoming", "outgoing", "property", "dataInput",
               "dataInputAssociation", "dataOutput", "dataOutputAssociation", "inputSet", "outputSet",
               "__eventdef__"]
GATEWAY_ORDER = ["documentation", "extensionElements", "incoming", "outgoing"]
COLLAB_ORDER = ["documentation", "extensionElements", "participant", "messageFlow", "__artifact__",
                "conversation", "subConversation", "callConversation", "conversationAssociation",
                "participantAssociation", "messageFlowAssociation", "correlationKey", "choreographyRef",
                "conversationLink"]
LANE_ORDER = ["documentation", "extensionElements", "partitionElement", "flowNodeRef", "childLaneSet"]
FLOW_ORDER = ["documentation", "extensionElements", "conditionExpression"]


def _class_rank(order):
    base = {n: i for i, n in enumerate(order)}
    flow_i = base.get("__flow__")
    art_i = base.get("__artifact__")
    ev_i = base.get("__eventdef__")

    def rank(el):
        if ns_of(el) != BPMN_NS:
            return len(order) + 1 if ln(el) else len(order) + 2
        n = ln(el)
        if n in base:
            return base[n]
        if flow_i is not None and (n in FLOW_NODES or n in ("sequenceFlow", "dataObject", "dataObjectReference",
                                                              "dataStoreReference", "callChoreography")):
            return flow_i
        if art_i is not None and n in ARTIFACT_NAMES:
            return art_i
        if ev_i is not None and (n in EVENT_DEF_TAGS or n == "eventDefinitionRef"):
            return ev_i
        return len(order)
    return rank


def _sort_children(el, order, log, label):
    rank = _class_rank(order)
    chs = [c for c in el.iterchildren() if isinstance(c.tag, str)]
    if not chs:
        return
    keyed = sorted(enumerate(chs), key=lambda t: (rank(t[1]), t[0]))
    new = [c for _, c in keyed]
    if new != chs:
        # keep comments/PIs attached by simply moving only element children
        tails = [c.tail for c in chs]
        for c in chs:
            el.remove(c)
        for c, t in zip(new, tails):
            el.append(c)
            c.tail = t
        log.append(f"N1 reordered children of {label} into schema order")


def normalize(model: Model, exporter="BPMN 2.0 Standard Skill") -> list[str]:
    log: list[str] = []
    root = model.root
    if ln(root) != "definitions":
        return log

    # N5 attributes
    if not root.get("targetNamespace"):
        root.set("targetNamespace", "http://example.com/bpmn/" + slug(root.get("name") or "model", "model"))
        log.append("N5 added missing targetNamespace")
    if not root.get("exporter"):
        root.set("exporter", exporter)
        root.set("exporterVersion", SKILL_VERSION)

    # N5 ids
    for el in list(root.iter()):
        if not isinstance(el.tag, str) or ns_of(el) != BPMN_NS or el.get("id"):
            continue
        n = ln(el)
        if n in FLOW_ELEMENTS_ALL or n in ("participant", "lane", "messageFlow", "collaboration", "process",
                                             "message", "dataStore", "property", "dataInputAssociation",
                                             "dataOutputAssociation", "conversationLink"):
            prefix = {"sequenceFlow": "Flow", "messageFlow": "MessageFlow", "participant": "Participant",
                      "lane": "Lane", "laneSet": "LaneSet", "dataInputAssociation": "DataInputAssociation",
                      "dataOutputAssociation": "DataOutputAssociation", "conversationLink": "ConversationLink"}.get(n, n[0].upper() + n[1:])
            nid = new_id(model, prefix)
            el.set("id", nid)
            model.by_id[nid] = el
            log.append(f"N5 generated id {nid} for <{n}>")

    # N4 intermediate catch without definition
    for ev in list(model.of("intermediateCatchEvent")):
        if not model.event_triggers(ev) and not is_true(ev.get("parallelMultiple")):
            ev.tag = q("intermediateThrowEvent")
            log.append(f"N4 {ev.get('id')}: intermediateCatchEvent without trigger converted to intermediateThrowEvent (none)")

    # N6 inconsistent incoming/outgoing
    for node in list(model.of(*FLOW_NODES)):
        nid = node.get("id")
        inc = {text_of(c) for c in kids(node, "incoming")}
        out = {text_of(c) for c in kids(node, "outgoing")}
        if (inc and inc != {sf.get("id") for sf in model.flows_to(nid)}) or \
           (out and out != {sf.get("id") for sf in model.flows_from(nid)}):
            for c in list(kids(node, "incoming", "outgoing")):
                node.remove(c)
            log.append(f"N6 {nid}: removed inconsistent incoming/outgoing lists")

    # N3 data associations
    for tag in ("dataInputAssociation", "dataOutputAssociation"):
        for da in list(model.of(tag)):
            owner = da.getparent()
            if owner is None:
                continue
            if tag == "dataInputAssociation":
                t = da.find(q("targetRef"))
                tgt = model.get(text_of(t)) if t is not None else None
                if t is None or (tgt is not None and ln(tgt) in ACTIVITIES | EVENTS):
                    pid = new_id(model, "Property")
                    prop = etree.SubElement(owner, q("property"))
                    prop.set("id", pid)
                    prop.set("name", "__targetRef_placeholder")
                    model.by_id[pid] = prop
                    if t is None:
                        t = etree.SubElement(da, q("targetRef"))
                    t.text = pid
                    log.append(f"N3 {owner.get('id')}: data input association retargeted to item-aware Property {pid}")
            else:
                for s in list(kids(da, "sourceRef")):
                    src = model.get(text_of(s))
                    if src is not None and ln(src) in ACTIVITIES | EVENTS:
                        da.remove(s)
                        log.append(f"N3 {owner.get('id')}: dropped non-item-aware sourceRef from data output association")

    # N2 process with lanes but no participant
    collabs = model.collaborations()
    for proc in model.processes():
        if list(kids(proc, "laneSet")) and model.participant_of(proc) is None:
            if collabs:
                col = collabs[0]
                created = False
            else:
                col = etree.Element(q("collaboration"))
                col.set("id", new_id(model, "Collaboration"))
                model.by_id[col.get("id")] = col
                root.insert(list(root).index(proc), col)
                collabs = [col]
                created = True
            part = etree.SubElement(col, q("participant"))
            pid = new_id(model, "Participant")
            part.set("id", pid)
            part.set("name", proc.get("name") or "Process")
            if created and not col.get("name"):
                col.set("name", proc.get("name") or "Process")
            part.set("processRef", proc.get("id"))
            model.by_id[pid] = part
            log.append(f"N2 process {proc.get('id')} has lanes: wrapped in {'a new collaboration' if created else 'collaboration ' + col.get('id')} "
                       f"with participant {pid}")

    # N1 ordering
    for col in model.collaborations():
        _sort_children(col, COLLAB_ORDER, log, f"collaboration {col.get('id')}")
    for el in list(root.iter()):
        if not isinstance(el.tag, str) or ns_of(el) != BPMN_NS:
            continue
        n = ln(el)
        label = f"<{n}> {el.get('id') or ''}".strip()
        if n == "process":
            _sort_children(el, CONTAINER_ORDER, log, label)
        elif n in SUBPROCS:
            _sort_children(el, SUBPROCESS_ORDER, log, label)
        elif n in ACTIVITIES:
            _sort_children(el, ACTIVITY_ORDER, log, label)
        elif n in EVENTS:
            _sort_children(el, EVENT_ORDER, log, label)
        elif n in GATEWAYS:
            _sort_children(el, GATEWAY_ORDER, log, label)
        elif n == "lane":
            _sort_children(el, LANE_ORDER, log, label)
        elif n == "sequenceFlow":
            _sort_children(el, FLOW_ORDER, log, label)
    # definitions: imports, extensions, root elements, diagrams last
    chs = [c for c in root.iterchildren() if isinstance(c.tag, str)]

    def drank(c):
        n = ln(c)
        if ns_of(c) == BPMNDI_NS:
            return 3
        if n == "import":
            return 0
        if n == "extension":
            return 1
        if n == "relationship":
            return 4
        return 2
    new = [c for _, c in sorted(enumerate(chs), key=lambda t: (drank(t[1]), t[0]))]
    if new != chs:
        tails = [c.tail for c in chs]
        for c in chs:
            root.remove(c)
        for c, t in zip(new, tails):
            root.append(c)
            c.tail = t
        log.append("N1 reordered definitions children (root elements before BPMNDiagram)")
    return log


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="Normalise a BPMN file (schema order + deterministic repairs).")
    ap.add_argument("file")
    ap.add_argument("-o", "--out", required=True)
    a = ap.parse_args(argv)
    m = Model.parse(a.file)
    log = normalize(m)
    etree.ElementTree(m.root).write(a.out, xml_declaration=True, encoding="UTF-8", pretty_print=True)
    print("\n".join(log) if log else "nothing to normalise")
    return 0


if __name__ == "__main__":
    sys.exit(main())
