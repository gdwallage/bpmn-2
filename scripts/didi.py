"""BPMN Diagram Interchange: read existing DI into Planes, write Planes as BPMNDiagram/BPMNPlane/
BPMNShape/BPMNEdge (clause 12.2)."""
from __future__ import annotations

import os
import sys

from lxml import etree

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bpmnlib import *  # noqa
from layout import Box, Shape, Edge, Plane


def _f(v, d=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def read_di(model: Model) -> list[Plane]:
    planes = []
    for d in model.diagrams():
        plane_el = d.find(q("BPMNPlane", BPMNDI_NS))
        if plane_el is None:
            continue
        root_id = local_id(plane_el.get("bpmnElement")) or ""
        root_el = model.get(root_id)
        kind = "process"
        if root_el is not None:
            kind = {"collaboration": "collaboration", "choreography": "choreography"}.get(ln(root_el), "process")
            if ln(root_el) in SUBPROCS:
                kind = "subprocess"
            if ln(root_el) == "collaboration" and not any(model.process_of_participant(p) is not None for p in kids(root_el, "participant")):
                kind = "conversation"
        name = d.get("name") or (root_el.get("name") if root_el is not None else None) or root_id
        pl = Plane(root_id, name, kind=kind)
        for sh in plane_el.iterchildren(q("BPMNShape", BPMNDI_NS)):
            ref = local_id(sh.get("bpmnElement"))
            el = model.get(ref)
            b = sh.find(q("Bounds", DC_NS))
            if b is None or el is None:
                continue
            key = ref
            band = sh.get("participantBandKind")
            if band:
                key = f"{local_id(sh.get('choreographyActivityShape'))}__{ref}"
            box = Box(_f(b.get("x")), _f(b.get("y")), _f(b.get("width")), _f(b.get("height")))
            s = Shape(key, box, ln(el), ref=ref)
            if sh.get("isExpanded") is not None:
                s.expanded = is_true(sh.get("isExpanded"))
            if sh.get("isHorizontal") is not None:
                s.horizontal = is_true(sh.get("isHorizontal"))
            if sh.get("isMarkerVisible") is not None:
                s.marker_visible = is_true(sh.get("isMarkerVisible"))
            if band:
                s.band = band
                s.parent = local_id(sh.get("choreographyActivityShape"))
                s.kind = "participantBand"
                if sh.get("isMessageVisible") is not None:
                    s.msg_visible = "initiating" if "non" not in band and is_true(sh.get("isMessageVisible")) else (
                        "non_initiating" if is_true(sh.get("isMessageVisible")) else None)
            lab = sh.find(q("BPMNLabel", BPMNDI_NS))
            if lab is not None:
                lb = lab.find(q("Bounds", DC_NS))
                if lb is not None:
                    s.label = Box(_f(lb.get("x")), _f(lb.get("y")), _f(lb.get("width")), _f(lb.get("height")))
            pl.shapes[key] = s
        for ed in plane_el.iterchildren(q("BPMNEdge", BPMNDI_NS)):
            ref = local_id(ed.get("bpmnElement"))
            wps = [(_f(w.get("x")), _f(w.get("y"))) for w in ed.iterchildren(q("waypoint", DI_NS))]
            if len(wps) < 2:
                continue
            e = Edge(ref, wps)
            lab = ed.find(q("BPMNLabel", BPMNDI_NS))
            if lab is not None:
                lb = lab.find(q("Bounds", DC_NS))
                if lb is not None:
                    e.label = Box(_f(lb.get("x")), _f(lb.get("y")), _f(lb.get("width")), _f(lb.get("height")))
            pl.edges[ref] = e
        planes.append(pl)
    return planes


def di_is_complete(model: Model, planes: list[Plane]) -> tuple[bool, list[str]]:
    """True if the main planes contain a shape for each flow node / pool / lane and an edge for each flow."""
    if not planes:
        return False, ["no diagram"]
    missing = []
    shown_s, shown_e = set(), set()
    for p in planes:
        for k, s in p.shapes.items():
            shown_s.add(s.ref or k)
        shown_e.update(p.edges.keys())
    # which planes exist for which roots?
    for pl in planes:
        root = model.get(pl.root_id)
        if root is None:
            continue
        scope = [root]
        if ln(root) == "collaboration":
            scope = [model.process_of_participant(p) for p in kids(root, "participant")]
            scope = [s for s in scope if s is not None]
            for p in kids(root, "participant"):
                if p.get("id") not in shown_s:
                    missing.append(p.get("id"))
            for mf in kids(root, "messageFlow"):
                if mf.get("id") not in shown_e:
                    missing.append(mf.get("id"))
        for proc in scope:
            if proc is None:
                continue
            for el in proc.iter():
                if not isinstance(el.tag, str) or ns_of(el) != BPMN_NS or el is proc:
                    continue
                n = ln(el)
                # children of collapsed sub-processes live in another plane
                p = el.getparent()
                hidden = False
                while p is not None and p is not proc:
                    if ln(p) in SUBPROCS:
                        sh = [s for s in pl.shapes.values() if (s.ref or s.id) == p.get("id")]
                        if sh and sh[0].expanded is False:
                            hidden = True
                    p = p.getparent()
                if hidden:
                    continue
                if n in FLOW_NODES | DATA_VISUAL | ARTIFACTS and el.get("id") not in shown_s:
                    missing.append(el.get("id"))
                if n in ("sequenceFlow", "association") and el.get("id") not in shown_e:
                    missing.append(el.get("id"))
    return (not missing), missing


def normalize_plane(pl: Plane, margin=20.0):
    """Shift so every coordinate is positive (DI requires positive bounds)."""
    b = pl.bounds()
    dx = margin - b.x if b.x < margin else 0
    dy = margin - b.y if b.y < margin else 0
    if not dx and not dy:
        return
    for s in pl.shapes.values():
        s.box = s.box.moved(dx, dy)
        if s.label:
            s.label = s.label.moved(dx, dy)
    for e in pl.edges.values():
        e.pts = [(x + dx, y + dy) for x, y in e.pts]
        if e.label:
            e.label = e.label.moved(dx, dy)


def write_di(model: Model, planes: list[Plane]):
    root = model.root
    for d in model.diagrams():
        root.remove(d)
    for i, pl in enumerate(planes, 1):
        normalize_plane(pl)
        dgm = etree.SubElement(root, q("BPMNDiagram", BPMNDI_NS))
        dgm.set("id", f"BPMNDiagram_{i}")
        if pl.name:
            dgm.set("name", pl.name)
        plane = etree.SubElement(dgm, q("BPMNPlane", BPMNDI_NS))
        plane.set("id", f"BPMNPlane_{i}")
        plane.set("bpmnElement", pl.root_id)
        for key, sh in pl.shapes.items():
            ref = sh.ref or key
            el = model.get(ref)
            if el is None:
                continue
            s = etree.SubElement(plane, q("BPMNShape", BPMNDI_NS))
            s.set("id", f"{key}_di")
            s.set("bpmnElement", ref)
            n = ln(el)
            if sh.band:
                s.set("participantBandKind", sh.band)
                s.set("choreographyActivityShape", f"{sh.parent}_di")
                if sh.msg_visible:
                    s.set("isMessageVisible", "true")
            if n in ("participant", "lane"):
                s.set("isHorizontal", "true")
            if n in SUBPROCS | {"callActivity", "subChoreography", "callChoreography"} and sh.expanded is not None:
                s.set("isExpanded", "true" if sh.expanded else "false")
            if n == "exclusiveGateway":
                s.set("isMarkerVisible", "true" if sh.marker_visible is not False else "false")
            b = etree.SubElement(s, q("Bounds", DC_NS))
            for k, v in (("x", sh.box.x), ("y", sh.box.y), ("width", sh.box.w), ("height", sh.box.h)):
                b.set(k, f"{v:.0f}" if abs(v - round(v)) < 0.01 else f"{v:.2f}")
            if sh.label is not None:
                lab = etree.SubElement(s, q("BPMNLabel", BPMNDI_NS))
                lb = etree.SubElement(lab, q("Bounds", DC_NS))
                for k, v in (("x", sh.label.x), ("y", sh.label.y), ("width", sh.label.w), ("height", sh.label.h)):
                    lb.set(k, f"{v:.0f}")
        for ref, ed in pl.edges.items():
            if model.get(ref) is None:
                continue
            e = etree.SubElement(plane, q("BPMNEdge", BPMNDI_NS))
            e.set("id", f"{ref}_di")
            e.set("bpmnElement", ref)
            for (x, y) in ed.pts:
                w = etree.SubElement(e, q("waypoint", DI_NS))
                w.set("x", f"{x:.0f}")
                w.set("y", f"{y:.0f}")
            if ed.label is not None:
                lab = etree.SubElement(e, q("BPMNLabel", BPMNDI_NS))
                lb = etree.SubElement(lab, q("Bounds", DC_NS))
                for k, v in (("x", ed.label.x), ("y", ed.label.y), ("width", ed.label.w), ("height", ed.label.h)):
                    lb.set(k, f"{v:.0f}")
    # make sure the prefixes are declared on the root for readability
    return model
