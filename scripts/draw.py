"""SVG renderer implementing the BPMN 2.0.2 notation (clause 7.3 element catalogue, 10.x per-element
rules, 12.3 depiction library). Everything the spec says "MUST be drawn with ..." is encoded here:

  start event   single thin circle           intermediate  double thin circle     end event  single THICK circle
  task          thin rounded rect            call activity THICK border            transaction DOUBLE border
  event sub-pr. DOTTED rounded rect          non-interrupting events: DASHED circle(s)
  throwing event markers: dark fill          catching markers: unfilled
  sequence flow solid + solid arrowhead      message flow dashed + open circle start + open arrowhead
  association   dotted                       conditional flow from activity: mini-diamond; default flow: slash
  group         dash-dot rounded rect        text annotation: open bracket           conversation link: double line
"""
from __future__ import annotations

import html
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bpmnlib import *  # noqa
from layout import Box, Shape, Edge, Plane
from textutil import FONT_FAMILY, block, text_width

INK = "#1f1f1f"
PAPER = "#ffffff"
LIGHT = "#d9d9d9"
SW = 2.0
THICK = 4.5


def esc(s):
    return html.escape(str(s), quote=True)


def f(v):
    return f"{v:.1f}".rstrip("0").rstrip(".")


class Svg:
    def __init__(self, model: Model, plane: Plane, overlay=None, title=True, footer=None, show_messages=False):
        self.m = model
        self.pl = plane
        self.ov = (overlay or {}).get("elements", overlay or {}) if overlay else {}
        self.legend = (overlay or {}).get("legend") if overlay else None
        self.title = title
        self.footer = footer
        self.show_messages = show_messages
        self.layers = {k: [] for k in ("pool", "lane", "group", "sub", "node", "edge", "top", "label", "ov")}
        self.defs = []

    # ---- primitives -----------------------------------------------------------------------
    def add(self, layer, s):
        self.layers[layer].append(s)

    def style(self, el_id, fill=PAPER, stroke=INK, sw=SW, dash=None, extra=""):
        o = self.ov.get(el_id, {}) if isinstance(self.ov, dict) else {}
        fill = o.get("fill", fill)
        stroke = o.get("stroke", stroke)
        sw = o.get("stroke_width", sw)
        d = f' stroke-dasharray="{dash}"' if dash else ""
        return f'fill="{fill}" stroke="{stroke}" stroke-width="{f(sw)}"{d}{extra}'

    def text(self, layer, x, y, s, size=12, anchor="middle", weight="normal", fill=INK, rotate=None, italic=False):
        tr = f' transform="rotate({rotate} {f(x)} {f(y)})"' if rotate else ""
        st = ' font-style="italic"' if italic else ""
        self.add(layer, f'<text x="{f(x)}" y="{f(y)}" font-size="{size}" text-anchor="{anchor}" font-weight="{weight}" '
                        f'fill="{fill}"{st}{tr}>{esc(s)}</text>')

    def wrapped(self, layer, box: Box, s, size=12, valign="middle", pad=6, anchor="middle", lh=None):
        lh = lh or size * 1.2
        ls, tw, th = block(s, box.w - 2 * pad, size, lh)
        if valign == "middle":
            y0 = box.cy - th / 2
        elif valign == "top":
            y0 = box.y + pad
        else:
            y0 = box.b - th - pad
        x = box.cx if anchor == "middle" else box.x + pad
        for k, line in enumerate(ls):
            self.add(layer, f'<text x="{f(x)}" y="{f(y0 + k * lh + size * 0.88)}" font-size="{size}" '
                            f'text-anchor="{anchor}" fill="{INK}">{esc(line)}</text>')

    # ---- markers ------------------------------------------------------------------------------
    def envelope(self, cx, cy, w=20, h=14, filled=False):
        x, y = cx - w / 2, cy - h / 2
        fill = INK if filled else PAPER
        line = PAPER if filled else INK
        return (f'<rect x="{f(x)}" y="{f(y)}" width="{w}" height="{h}" fill="{fill}" stroke="{INK}" stroke-width="1.5"/>'
                f'<polyline points="{f(x)},{f(y)} {f(cx)},{f(cy + 1)} {f(x + w)},{f(y)}" fill="none" stroke="{line}" stroke-width="1.5"/>')

    def poly(self, pts, cx, cy, filled, sw=1.5, scale=1.0):
        p = " ".join(f"{f(cx + x * scale)},{f(cy + y * scale)}" for x, y in pts)
        return f'<polygon points="{p}" fill="{INK if filled else PAPER}" stroke="{INK}" stroke-width="{sw}" stroke-linejoin="round"/>'

    def event_marker(self, kind, cx, cy, filled, scale=1.0):
        s = scale
        if kind == "message":
            return self.envelope(cx, cy, 20 * s, 14 * s, filled)
        if kind == "timer":
            r = 10 * s
            out = f'<circle cx="{f(cx)}" cy="{f(cy)}" r="{f(r)}" fill="{PAPER}" stroke="{INK}" stroke-width="1.5"/>'
            for k in range(12):
                a = math.radians(k * 30)
                r1 = r - (3.2 if k % 3 == 0 else 1.8) * s
                out += (f'<line x1="{f(cx + r1 * math.sin(a))}" y1="{f(cy - r1 * math.cos(a))}" '
                        f'x2="{f(cx + r * math.sin(a))}" y2="{f(cy - r * math.cos(a))}" stroke="{INK}" stroke-width="1"/>')
            out += (f'<polyline points="{f(cx)},{f(cy - 7 * s)} {f(cx)},{f(cy)} {f(cx + 4.5 * s)},{f(cy + 3 * s)}" fill="none" '
                    f'stroke="{INK}" stroke-width="1.5" stroke-linecap="round"/>')
            return out
        if kind == "conditional":
            w, h = 14 * s, 18 * s
            x, y = cx - w / 2, cy - h / 2
            out = f'<rect x="{f(x)}" y="{f(y)}" width="{f(w)}" height="{f(h)}" fill="{PAPER}" stroke="{INK}" stroke-width="1.5"/>'
            for k in range(4):
                yy = y + 3.5 * s + k * 3.6 * s
                out += f'<line x1="{f(x + 2.5 * s)}" y1="{f(yy)}" x2="{f(x + w - 2.5 * s)}" y2="{f(yy)}" stroke="{INK}" stroke-width="1"/>'
            return out
        if kind == "link":
            pts = [(-9, -4), (1, -4), (1, -8.5), (10, 0), (1, 8.5), (1, 4), (-9, 4)]
            return self.poly(pts, cx, cy, filled, scale=s)
        if kind == "signal":
            return self.poly([(0, -9), (9.5, 8), (-9.5, 8)], cx, cy + 0.5, filled, scale=s)
        if kind == "escalation":
            return self.poly([(0, -10), (8.5, 9), (0, 3), (-8.5, 9)], cx, cy, filled, scale=s)
        if kind == "error":
            return self.poly([(-9, 8), (-4, -9), (1, 0), (5, -8), (9, 9), (2, -1), (-1, 6)], cx, cy, filled, scale=s)
        if kind == "cancel":
            pts = [(-9, -5), (-5, -9), (0, -4), (5, -9), (9, -5), (4, 0), (9, 5), (5, 9), (0, 4), (-5, 9), (-9, 5), (-4, 0)]
            return self.poly(pts, cx, cy, filled, scale=s)
        if kind == "compensation":
            return (self.poly([(-1, 0), (9, -7), (9, 7)], cx, cy, filled, scale=s) +
                    self.poly([(-11, 0), (-1, -7), (-1, 7)], cx, cy, filled, scale=s))
        if kind == "multiple":
            pts = [(10 * math.sin(math.radians(a)), -10 * math.cos(math.radians(a))) for a in range(0, 360, 72)]
            return self.poly(pts, cx, cy + 0.5, filled, scale=s)
        if kind == "parallelMultiple":
            t = 3.0
            pts = [(-t, -10), (t, -10), (t, -t), (10, -t), (10, t), (t, t), (t, 10), (-t, 10), (-t, t), (-10, t), (-10, -t), (-t, -t)]
            return self.poly(pts, cx, cy, filled, scale=s)
        if kind == "terminate":
            return f'<circle cx="{f(cx)}" cy="{f(cy)}" r="{f(11 * s)}" fill="{INK}" stroke="{INK}" stroke-width="1.5"/>'
        return ""

    def task_marker(self, kind, x, y):
        """Task type icon, anchored at the task's top-left corner (x, y)."""
        ox, oy = x + 8, y + 7
        if kind == "userTask":
            return (f'<g transform="translate({f(ox)},{f(oy)})" fill="{PAPER}" stroke="{INK}" stroke-width="1.4" stroke-linejoin="round">'
                    '<circle cx="9" cy="5" r="4.2"/><path d="M1,18 C1,11.5 4,10 9,10 C14,10 17,11.5 17,18 Z"/>'
                    '<path d="M6,10.5 L9,14 L12,10.5" fill="none"/></g>')
        if kind in ("sendTask", "receiveTask"):
            return self.envelope(ox + 9, oy + 8, 18, 12, filled=(kind == "sendTask"))
        if kind == "serviceTask":
            def gear(cx, cy, R, r, teeth=8):
                pts = []
                for k in range(teeth * 2):
                    a = math.pi * k / teeth
                    rr = R if k % 2 == 0 else R * 0.72
                    for da in (-0.17, 0.17) if k % 2 == 0 else (-0.2, 0.2):
                        pts.append((cx + rr * math.cos(a + da), cy + rr * math.sin(a + da)))
                p = " ".join(f"{f(a)},{f(b)}" for a, b in pts)
                return (f'<polygon points="{p}" fill="{PAPER}" stroke="{INK}" stroke-width="1.2" stroke-linejoin="round"/>'
                        f'<circle cx="{f(cx)}" cy="{f(cy)}" r="{f(r)}" fill="{PAPER}" stroke="{INK}" stroke-width="1.2"/>')
            return gear(ox + 7, oy + 7, 7.5, 2.6) + gear(ox + 15, oy + 15, 5.8, 2.0, 7)
        if kind == "manualTask":
            return (f'<g transform="translate({f(ox - 1)},{f(oy)})" fill="{PAPER}" stroke="{INK}" stroke-width="1.3" stroke-linejoin="round" stroke-linecap="round">'
                    '<path d="M3,12 L3,7.5 Q3,6 4.5,6 Q6,6 6,7.5 L6,3.5 Q6,2 7.5,2 Q9,2 9,3.5 L9,3 Q9,1.5 10.5,1.5 Q12,1.5 12,3 L12,4 Q12,2.8 13.4,2.8 Q15,2.8 15,4.3 L15,11 Q15,17 9.5,17 L8.5,17 Q5.5,17 4.2,14.5 Z"/></g>')
        if kind == "businessRuleTask":
            return (f'<g transform="translate({f(ox)},{f(oy + 1)})" stroke="{INK}" stroke-width="1.2">'
                    f'<rect x="0" y="0" width="18" height="15" fill="{PAPER}"/><rect x="0" y="0" width="18" height="4.5" fill="{LIGHT}"/>'
                    f'<line x1="0" y1="9.7" x2="18" y2="9.7"/><line x1="6" y1="4.5" x2="6" y2="15"/></g>')
        if kind == "scriptTask":
            return (f'<g transform="translate({f(ox)},{f(oy)})" fill="{PAPER}" stroke="{INK}" stroke-width="1.3" stroke-linejoin="round">'
                    '<path d="M5,1 L16,1 Q12,5 13,9 Q14,13 16,16 L7,16 Q3,16 2.5,13.5 Q4,13 4,11 Q4,7 5,1 Z"/>'
                    '<path d="M7,5 H12 M6.5,8 H12 M6.5,11 H11" fill="none"/></g>')
        return ""

    def bottom_markers(self, bx: Box, items):
        """items: list of marker names, centred as a group at the bottom of the shape."""
        if not items:
            return
        size, gap = 14, 4
        total = len(items) * size + (len(items) - 1) * gap
        x = bx.cx - total / 2
        y = bx.b - size - 5
        for it in items:
            cx, cy = x + size / 2, y + size / 2
            if it == "plus":
                self.add("node", f'<rect x="{f(x)}" y="{f(y)}" width="{size}" height="{size}" fill="{PAPER}" stroke="{INK}" stroke-width="1.5"/>'
                                 f'<path d="M{f(cx)},{f(y + 3)} V{f(y + size - 3)} M{f(x + 3)},{f(cy)} H{f(x + size - 3)}" stroke="{INK}" stroke-width="1.6" fill="none"/>')
            elif it == "loop":
                r = 5.2
                a0, a1 = math.radians(-50), math.radians(235)
                x0, y0 = cx + r * math.cos(a0), cy + r * math.sin(a0)
                x1, y1 = cx + r * math.cos(a1), cy + r * math.sin(a1)
                self.add("node", f'<path d="M{f(x0)},{f(y0)} A{r},{r} 0 1 0 {f(x1)},{f(y1)}" fill="none" stroke="{INK}" stroke-width="1.5"/>'
                                 f'<polygon points="{f(x1 - 2.8)},{f(y1 + 1.2)} {f(x1 + 3.8)},{f(y1 - 0.4)} {f(x1 - 0.2)},{f(y1 + 5.2)}" fill="{INK}" stroke="{INK}" stroke-width="1"/>')
            elif it == "mi_par":
                for k in range(3):
                    self.add("node", f'<rect x="{f(x + 1 + k * 4.5)}" y="{f(y + 1)}" width="2.6" height="{size - 2}" fill="{INK}"/>')
            elif it == "mi_seq":
                for k in range(3):
                    self.add("node", f'<rect x="{f(x + 1)}" y="{f(y + 1 + k * 4.5)}" width="{size - 2}" height="2.6" fill="{INK}"/>')
            elif it == "compensation":
                self.add("node", self.poly([(0, 0), (7, -5), (7, 5)], cx + 0.5, cy, False, sw=1.3, scale=0.95) +
                         self.poly([(-7.5, 0), (-0.5, -5), (-0.5, 5)], cx + 0.5, cy, False, sw=1.3, scale=0.95))
            elif it == "adhoc":
                self.add("node", f'<path d="M{f(x + 1)},{f(cy + 1)} Q{f(x + 3.5)},{f(cy - 5)} {f(cx)},{f(cy)} T{f(x + size - 1)},{f(cy - 1)}" '
                                 f'fill="none" stroke="{INK}" stroke-width="2"/>')
            x += size + gap

    # ---- shapes -------------------------------------------------------------------------------
    def overlay_badge(self, key, bx: Box):
        o = self.ov.get(key) if isinstance(self.ov, dict) else None
        if not o or not o.get("badge"):
            return
        txt = str(o["badge"])
        w = max(18, text_width(txt, 10, True) + 10)
        x = bx.r - w + 6
        y = bx.y - 9
        self.add("ov", f'<rect x="{f(x)}" y="{f(y)}" width="{f(w)}" height="16" rx="8" fill="{o.get("badge_fill", "#b00020")}" '
                       f'stroke="{PAPER}" stroke-width="1.5"/>'
                       f'<text x="{f(x + w / 2)}" y="{f(y + 11.5)}" font-size="10" font-weight="bold" text-anchor="middle" fill="{o.get("badge_text", "#ffffff")}">{esc(txt)}</text>')

    def draw_shape(self, key, sh: Shape):
        m = self.m
        ref = sh.ref or key
        el = m.get(ref)
        if el is None:
            return
        n = ln(el)
        bx = sh.box
        if n == "participant":
            self.pool(el, sh)
        elif n == "lane":
            self.lane(el, sh)
        elif n in TASKS:
            self.task(el, sh)
        elif n in SUBPROCS or n == "callActivity":
            self.activity_box(el, sh)
        elif n in EVENTS:
            self.event(el, sh)
        elif n in GATEWAYS:
            self.gateway(el, sh)
        elif n in ("dataObjectReference", "dataObject", "dataInput", "dataOutput"):
            self.data_object(el, sh)
        elif n in ("dataStoreReference", "dataStore"):
            self.data_store(el, sh)
        elif n == "textAnnotation":
            self.annotation(el, sh)
        elif n == "group":
            self.group(el, sh)
        elif n in CONV_NODES:
            self.conversation(el, sh)
        elif n in CHOREO_ACTS:
            self.choreo_activity(key, el, sh)
        elif n == "participant" or sh.band:
            pass
        self.overlay_badge(ref, bx)

    # pools / lanes
    def pool(self, el, sh):
        bx = sh.box
        st = self.style(el.get("id"), fill="#ffffff")
        self.add("pool", f'<rect x="{f(bx.x)}" y="{f(bx.y)}" width="{f(bx.w)}" height="{f(bx.h)}" {st}/>')
        self.add("pool", f'<line x1="{f(bx.x + 30)}" y1="{f(bx.y)}" x2="{f(bx.x + 30)}" y2="{f(bx.b)}" stroke="{INK}" stroke-width="{SW}"/>')
        nm = el.get("name") or ""
        ls, tw, th = block(nm, bx.h - 8, 13, 15)
        for k, line in enumerate(ls):
            xx = bx.x + 15 + (k - (len(ls) - 1) / 2) * 15
            self.text("pool", xx, bx.cy, line, 13, rotate=-90, weight="bold")
        pm = el.find(q("participantMultiplicity"))
        if pm is not None and _int(pm.get("maximum"), 1) > 1:
            cx = bx.x + 30 + (bx.w - 30) / 2
            for k in range(3):
                self.add("pool", f'<rect x="{f(cx - 7 + k * 5)}" y="{f(bx.b - 16)}" width="2.6" height="11" fill="{INK}"/>')

    def lane(self, el, sh):
        bx = sh.box
        st = self.style(el.get("id"), fill="none")
        self.add("lane", f'<rect x="{f(bx.x)}" y="{f(bx.y)}" width="{f(bx.w)}" height="{f(bx.h)}" {st}/>')
        self.add("lane", f'<line x1="{f(bx.x + 30)}" y1="{f(bx.y)}" x2="{f(bx.x + 30)}" y2="{f(bx.b)}" stroke="{INK}" stroke-width="{SW}"/>')
        nm = el.get("name") or ""
        ls, tw, th = block(nm, bx.h - 14, 12, 14)
        for k, line in enumerate(ls):
            yy = bx.cy
            xx = bx.x + 15 + (k - (len(ls) - 1) / 2) * 14
            self.text("lane", xx, yy + 0, line, 12, rotate=-90)

    # activities
    def task(self, el, sh):
        n = ln(el)
        bx = sh.box
        o_stroke = SW
        extra_borders = ""
        if is_true(el.get("isForCompensation")) and False:
            pass
        st = self.style(el.get("id"))
        self.add("node", f'<rect x="{f(bx.x)}" y="{f(bx.y)}" width="{f(bx.w)}" height="{f(bx.h)}" rx="10" {st}/>')
        mk = self.task_marker(n, bx.x, bx.y)
        if mk:
            self.add("node", mk)
        pad_l = 6
        tb = Box(bx.x + (22 if mk else 0) * 0, bx.y + (14 if mk else 0), bx.w, bx.h - (14 if mk else 0) - 14 * (1 if self.bottom_items(el) else 0))
        self.wrapped("node", Box(bx.x, bx.y + (6 if mk else 0), bx.w, bx.h - (6 if mk else 0) - (12 if self.bottom_items(el) else 0)),
                     el.get("name") or "", 12)
        self.bottom_markers(bx, self.bottom_items(el))
        self.label_overlay_note(el, bx)

    def bottom_items(self, el, collapsed=False):
        items = []
        lc, mi = el.find(q("standardLoopCharacteristics")), el.find(q("multiInstanceLoopCharacteristics"))
        if lc is not None:
            items.append("loop")
        if mi is not None:
            items.append("mi_seq" if is_true(mi.get("isSequential")) else "mi_par")
        if is_true(el.get("isForCompensation")):
            items.append("compensation")
        if ln(el) == "adHocSubProcess":
            items.append("adhoc")
        return items

    def activity_box(self, el, sh):
        n = ln(el)
        bx = sh.box
        expanded = bool(sh.expanded)
        esp = self.m.is_event_subprocess(el)
        sid = el.get("id")
        if esp:
            st = self.style(sid, dash="2 4.5", extra=' stroke-linecap="round"')
        elif n == "callActivity":
            st = self.style(sid, sw=THICK)
        else:
            st = self.style(sid)
        layer = "sub" if expanded else "node"
        self.add(layer, f'<rect x="{f(bx.x)}" y="{f(bx.y)}" width="{f(bx.w)}" height="{f(bx.h)}" rx="10" {st}/>')
        if n == "transaction":
            self.add(layer, f'<rect x="{f(bx.x + 3.5)}" y="{f(bx.y + 3.5)}" width="{f(bx.w - 7)}" height="{f(bx.h - 7)}" rx="7" '
                            f'fill="none" stroke="{INK}" stroke-width="{SW}"/>')
        items = self.bottom_items(el)
        if expanded:
            nm = el.get("name") or ""
            ls, tw, th = block(nm, bx.w - 24, 12, 14.4)
            for k, line in enumerate(ls):
                self.add("label", f'<text x="{f(bx.cx)}" y="{f(bx.y + 16 + k * 14.4)}" font-size="12" font-weight="bold" '
                                  f'text-anchor="middle" fill="{INK}">{esc(line)}</text>')
            self.bottom_markers(bx, items)
        else:
            mk = ""
            if n == "callActivity":
                tgt = self.m.get(el.get("calledElement")) if el.get("calledElement") else None
                if tgt is not None and ln(tgt).startswith("global") and ln(tgt) != "globalTask":
                    mk = self.task_marker(ln(tgt).replace("global", "").replace("Task", "Task").lower().replace("usertask", "userTask")
                                          .replace("manualtask", "manualTask").replace("scripttask", "scriptTask")
                                          .replace("businessruletask", "businessRuleTask"), bx.x, bx.y)
            if mk:
                self.add("node", mk)
            self.wrapped("node", Box(bx.x, bx.y + (6 if mk else 0), bx.w, bx.h - 18), el.get("name") or "", 12)
            if esp:
                # collapsed event sub-process shows its start event as a small marker top-left
                st_ev = [c for c in kids(el) if ln(c) == "startEvent"]
                if st_ev:
                    trig = self.m.event_trigger(st_ev[0])
                    dash = None if self.m.is_interrupting(st_ev[0]) else "3 2"
                    self.add("node", f'<circle cx="{f(bx.x + 16)}" cy="{f(bx.y + 16)}" r="9" fill="{PAPER}" stroke="{INK}" stroke-width="1.5"'
                                     + (f' stroke-dasharray="{dash}"' if dash else "") + "/>")
                    self.add("node", self.event_marker(trig, bx.x + 16, bx.y + 16, False, 0.45))
            pre = items + ["plus"]
            # markers order per spec: loop/mi/compensation then + (adhoc to the right of +)
            order = [i for i in pre if i not in ("plus", "adhoc")] + ["plus"] + [i for i in pre if i == "adhoc"]
            self.bottom_markers(bx, order)
        self.label_overlay_note(el, bx)

    def label_overlay_note(self, el, bx):
        o = self.ov.get(el.get("id")) if isinstance(self.ov, dict) else None
        if o and o.get("note"):
            self.add("ov", f'<text x="{f(bx.x)}" y="{f(bx.b + 12)}" font-size="9.5" fill="#7a0010">{esc(o["note"])}</text>')

    # events
    def event(self, el, sh):
        n = ln(el)
        bx = sh.box
        cx, cy, r = bx.cx, bx.cy, bx.w / 2
        trig = self.m.event_trigger(el)
        throwing = n in THROW_EVENTS
        interrupting = self.m.is_interrupting(el)
        in_esp = False
        dash = None if interrupting else "5 3"
        sid = el.get("id")
        if n == "startEvent":
            self.add("node", f'<circle cx="{f(cx)}" cy="{f(cy)}" r="{f(r - 1)}" {self.style(sid, dash=dash)}/>')
        elif n == "endEvent":
            self.add("node", f'<circle cx="{f(cx)}" cy="{f(cy)}" r="{f(r - 2)}" {self.style(sid, sw=THICK)}/>')
        else:
            layer = "top" if n == "boundaryEvent" else "node"
            self.add(layer, f'<circle cx="{f(cx)}" cy="{f(cy)}" r="{f(r - 1)}" {self.style(sid, dash=dash)}/>')
            self.add(layer, f'<circle cx="{f(cx)}" cy="{f(cy)}" r="{f(r - 4.6)}" fill="none" stroke="{self.ov.get(sid, {}).get("stroke", INK)}" stroke-width="{SW}"'
                            + (f' stroke-dasharray="{dash}"' if dash else "") + "/>")
        if trig != "none":
            layer = "top" if n == "boundaryEvent" else "node"
            filled = throwing and trig not in ("parallelMultiple",)
            if trig == "terminate":
                filled = True
            self.add(layer, self.event_marker(trig, cx, cy, filled, scale=0.82 if n in ("intermediateCatchEvent", "intermediateThrowEvent", "boundaryEvent") else 0.9))
        if sh.label is not None and (el.get("name") or ""):
            self.event_label(el, sh)

    def event_label(self, el, sh):
        nm = el.get("name")
        ls, tw, th = block(nm, sh.label.w, 11, 13.2)
        left = ln(el) == "boundaryEvent"
        gw = ln(el) in GATEWAYS
        shifted = (not gw) and not left and abs(sh.label.cx - sh.box.cx) > 20
        left = left or shifted
        for k, line in enumerate(ls):
            x = sh.label.x if left else (sh.label.r if gw else sh.label.cx)
            anc = "start" if left else ("end" if gw else "middle")
            self.add("label", f'<text x="{f(x)}" y="{f(sh.label.y + 10 + k * 13.2)}" font-size="11" text-anchor="{anc}" fill="{INK}">{esc(line)}</text>')

    # gateways
    def gateway(self, el, sh):
        n = ln(el)
        bx = sh.box
        cx, cy = bx.cx, bx.cy
        st = self.style(el.get("id"))
        self.add("node", f'<polygon points="{f(cx)},{f(bx.y)} {f(bx.r)},{f(cy)} {f(cx)},{f(bx.b)} {f(bx.x)},{f(cy)}" {st} stroke-linejoin="miter"/>')
        k = 1.0
        if n == "exclusiveGateway":
            if sh.marker_visible is not False:
                self.add("node", f'<path d="M{f(cx - 9)},{f(cy - 9)} L{f(cx + 9)},{f(cy + 9)} M{f(cx - 9)},{f(cy + 9)} L{f(cx + 9)},{f(cy - 9)}" '
                                 f'stroke="{INK}" stroke-width="4.5" fill="none"/>')
        elif n == "inclusiveGateway":
            self.add("node", f'<circle cx="{f(cx)}" cy="{f(cy)}" r="11.5" fill="none" stroke="{INK}" stroke-width="3.2"/>')
        elif n == "parallelGateway":
            self.add("node", f'<path d="M{f(cx - 12)},{f(cy)} H{f(cx + 12)} M{f(cx)},{f(cy - 12)} V{f(cy + 12)}" stroke="{INK}" stroke-width="4.5" fill="none"/>')
        elif n == "complexGateway":
            self.add("node", f'<path d="M{f(cx - 12)},{f(cy)} H{f(cx + 12)} M{f(cx)},{f(cy - 12)} V{f(cy + 12)} '
                             f'M{f(cx - 8.5)},{f(cy - 8.5)} L{f(cx + 8.5)},{f(cy + 8.5)} M{f(cx - 8.5)},{f(cy + 8.5)} L{f(cx + 8.5)},{f(cy - 8.5)}" '
                             f'stroke="{INK}" stroke-width="3" fill="none"/>')
        elif n == "eventBasedGateway":
            inst = is_true(el.get("instantiate"))
            par = (el.get("eventGatewayType") or "Exclusive").lower() == "parallel"
            self.add("node", f'<circle cx="{f(cx)}" cy="{f(cy)}" r="11.5" fill="none" stroke="{INK}" stroke-width="1.5"/>')
            if not inst:
                self.add("node", f'<circle cx="{f(cx)}" cy="{f(cy)}" r="8.8" fill="none" stroke="{INK}" stroke-width="1.5"/>')
            if inst and par:
                self.add("node", self.event_marker("parallelMultiple", cx, cy, False, 0.62))
            else:
                self.add("node", self.event_marker("multiple", cx, cy, False, 0.62))
        if sh.label is not None and el.get("name"):
            self.event_label(el, sh)

    # data
    def data_object(self, el, sh):
        bx = sh.box
        fold = 10
        st = self.style(el.get("id"))
        self.add("node", f'<path d="M{f(bx.x)},{f(bx.y)} H{f(bx.r - fold)} L{f(bx.r)},{f(bx.y + fold)} V{f(bx.b)} H{f(bx.x)} Z" {st} stroke-linejoin="round"/>')
        self.add("node", f'<path d="M{f(bx.r - fold)},{f(bx.y)} V{f(bx.y + fold)} H{f(bx.r)}" fill="none" stroke="{INK}" stroke-width="1.5"/>')
        n = ln(el)
        ref = el
        if n == "dataObjectReference":
            d = self.m.get(el.get("dataObjectRef"))
            coll = d is not None and is_true(d.get("isCollection"))
        else:
            coll = is_true(el.get("isCollection"))
        if coll:
            for k in range(3):
                self.add("node", f'<rect x="{f(bx.cx - 7 + k * 5)}" y="{f(bx.b - 13)}" width="2.6" height="10" fill="{INK}"/>')
        if n in ("dataInput", "dataOutput"):
            filled = n == "dataOutput"
            self.add("node", f'<polygon points="{f(bx.x + 4)},{f(bx.y + 5)} {f(bx.x + 11)},{f(bx.y + 5)} {f(bx.x + 11)},{f(bx.y + 2)} {f(bx.x + 17)},{f(bx.y + 8)} '
                             f'{f(bx.x + 11)},{f(bx.y + 14)} {f(bx.x + 11)},{f(bx.y + 11)} {f(bx.x + 4)},{f(bx.y + 11)}" '
                             f'fill="{INK if filled else PAPER}" stroke="{INK}" stroke-width="1.2"/>')
        # dataObjectReference whose dataObject is an input/output? (Cl.10.4: visualised Data Input / Output carry an arrow)
        if sh.label is not None:
            lab = el.get("name") or ""
            ds = el.find(q("dataState"))
            lines = [lab] + ([f"[{ds.get('name')}]"] if ds is not None and ds.get("name") else [])
            yy = bx.y + 14
            for t in lines:
                for line in block(t, 70, 11, 13.2)[0]:
                    self.add("label", f'<text x="{f(bx.r + 6)}" y="{f(yy)}" font-size="11" text-anchor="start" fill="{INK}">{esc(line)}</text>')
                    yy += 13.2

    def data_store(self, el, sh):
        bx = sh.box
        w, h, x, y = bx.w, bx.h, bx.x, bx.y
        st = self.style(el.get("id"))
        self.add("node", f'<path d="M{f(x)},{f(y + 7)} C{f(x)},{f(y - 2.5)} {f(x + w)},{f(y - 2.5)} {f(x + w)},{f(y + 7)} '
                         f'V{f(y + h - 7)} C{f(x + w)},{f(y + h + 2.5)} {f(x)},{f(y + h + 2.5)} {f(x)},{f(y + h - 7)} Z" {st}/>')
        self.add("node", f'<path d="M{f(x)},{f(y + 7)} C{f(x)},{f(y + 16.5)} {f(x + w)},{f(y + 16.5)} {f(x + w)},{f(y + 7)} '
                         f'M{f(x)},{f(y + 13)} C{f(x)},{f(y + 22.5)} {f(x + w)},{f(y + 22.5)} {f(x + w)},{f(y + 13)}" fill="none" stroke="{INK}" stroke-width="1.5"/>')
        if sh.label is not None:
            for k, line in enumerate(block(el.get("name") or "", sh.label.w, 11, 13.2)[0]):
                self.add("label", f'<text x="{f(sh.label.cx)}" y="{f(sh.label.y + 10 + k * 13.2)}" font-size="11" text-anchor="middle" fill="{INK}">{esc(line)}</text>')

    # artifacts
    def annotation(self, el, sh):
        bx = sh.box
        self.add("node", f'<rect x="{f(bx.x)}" y="{f(bx.y)}" width="{f(bx.w)}" height="{f(bx.h)}" fill="none" stroke="none"/>')
        self.add("node", f'<path d="M{f(bx.x + 14)},{f(bx.y)} H{f(bx.x)} V{f(bx.b)} H{f(bx.x + 14)}" fill="none" stroke="{INK}" stroke-width="1.6"/>')
        txt = text_of(el.find(q("text")))
        ls, tw, th = block(txt, bx.w - 14, 11, 13.2)
        y0 = bx.cy - th / 2
        for k, line in enumerate(ls):
            self.add("node", f'<text x="{f(bx.x + 8)}" y="{f(y0 + k * 13.2 + 9.8)}" font-size="11" fill="{INK}">{esc(line)}</text>')

    def group(self, el, sh):
        bx = sh.box
        self.add("group", f'<rect x="{f(bx.x)}" y="{f(bx.y)}" width="{f(bx.w)}" height="{f(bx.h)}" rx="9" fill="none" stroke="{INK}" '
                          f'stroke-width="1.8" stroke-dasharray="10 4 2 4"/>')
        cv = self.m.get(el.get("categoryValueRef")) if el.get("categoryValueRef") else None
        if cv is not None and cv.get("value"):
            self.add("label", f'<text x="{f(bx.cx)}" y="{f(bx.y + 15)}" font-size="11" font-weight="bold" text-anchor="middle" fill="{INK}">{esc(cv.get("value"))}</text>')

    # conversation
    def hexagon(self, bx: Box):
        x, y, w, h = bx.x, bx.y, bx.w, bx.h
        d = h / 2
        return f"{f(x + d * 0.7)},{f(y)} {f(x + w - d * 0.7)},{f(y)} {f(x + w)},{f(y + d)} {f(x + w - d * 0.7)},{f(y + h)} {f(x + d * 0.7)},{f(y + h)} {f(x)},{f(y + d)}"

    def conversation(self, el, sh):
        n = ln(el)
        bx = sh.box
        thick = n == "callConversation"
        self.add("node", f'<polygon points="{self.hexagon(bx)}" {self.style(el.get("id"), sw=THICK if thick else 1.8)} stroke-linejoin="round"/>')
        if n == "subConversation" or (n == "callConversation" and self._calls_collaboration(el)):
            self.bottom_markers(bx, ["plus"])
        if sh.label is not None and el.get("name"):
            self.event_label(el, sh)

    def _calls_collaboration(self, el):
        t = self.m.get(el.get("calledCollaborationRef")) if el.get("calledCollaborationRef") else None
        return t is not None and ln(t) == "collaboration"

    # choreography
    def choreo_bands(self, key, el, sh):
        """Participant band shapes belonging to this activity (separate BPMNShapes per spec 12.3.2)"""
        return [s for k, s in self.pl.shapes.items() if s.band and s.parent == key]

    def choreo_activity(self, key, el, sh):
        n = ln(el)
        bx = sh.box
        thick = n == "callChoreography"
        self.add("node", f'<rect x="{f(bx.x)}" y="{f(bx.y)}" width="{f(bx.w)}" height="{f(bx.h)}" rx="10" fill="{PAPER}" '
                         f'stroke="{INK}" stroke-width="{THICK if thick else SW}"/>')
        bands = self.choreo_bands(key, el, sh)
        for b in bands:
            pe = self.m.get(b.ref)
            ini = "non" not in (b.band or "")
            bb = b.box
            rtop = "top" in b.band
            rx = 10
            if rtop:
                path = f"M{f(bb.x)},{f(bb.b)} V{f(bb.y + rx)} Q{f(bb.x)},{f(bb.y)} {f(bb.x + rx)},{f(bb.y)} H{f(bb.r - rx)} Q{f(bb.r)},{f(bb.y)} {f(bb.r)},{f(bb.y + rx)} V{f(bb.b)} Z"
            elif "bottom" in b.band:
                path = f"M{f(bb.x)},{f(bb.y)} V{f(bb.b - rx)} Q{f(bb.x)},{f(bb.b)} {f(bb.x + rx)},{f(bb.b)} H{f(bb.r - rx)} Q{f(bb.r)},{f(bb.b)} {f(bb.r)},{f(bb.b - rx)} V{f(bb.y)} Z"
            else:
                path = f"M{f(bb.x)},{f(bb.y)} H{f(bb.r)} V{f(bb.b)} H{f(bb.x)} Z"
            self.add("node", f'<path d="{path}" fill="{PAPER if ini else LIGHT}" stroke="{INK}" stroke-width="{SW}"/>')
            self.wrapped("node", bb, (pe.get("name") if pe is not None else "") or "", 11, pad=4)
            if b.msg_visible:
                self.choreo_message(b, ini, rtop)
        # name band
        if bands:
            ys = sorted(bands, key=lambda s: s.box.y)
            top_h = sum(b.box.h for b in bands if "top" in b.band)
            bot_h = sum(b.box.h for b in bands if "bottom" in b.band)
            nb = Box(bx.x, bx.y + top_h, bx.w, bx.h - top_h - bot_h)
        else:
            nb = bx
        self.wrapped("node", nb, el.get("name") or "", 12)
        items = self.bottom_items(el)
        if n in ("subChoreography",):
            items = items + ["plus"] if sh.expanded is not True else items
        elif n == "callChoreography" and sh.expanded is not True:
            items = items + ["plus"]
        if items:
            self.bottom_markers(Box(nb.x, nb.y, nb.w, nb.h + 4), items)

    def choreo_message(self, band: Shape, initiating: bool, top: bool):
        bb = band.box
        cx = bb.cx
        cy = bb.y - 18 if top else bb.b + 18
        self.add("node", f'<line x1="{f(cx)}" y1="{f(bb.y if top else bb.b)}" x2="{f(cx)}" y2="{f(cy + (7 if top else -7))}" stroke="{INK}" stroke-width="1" stroke-dasharray="2 2"/>')
        fill = PAPER if initiating else LIGHT
        x, y = cx - 10, cy - 7
        self.add("node", f'<rect x="{f(x)}" y="{f(y)}" width="20" height="14" fill="{fill}" stroke="{INK}" stroke-width="1.5"/>'
                         f'<polyline points="{f(x)},{f(y)} {f(cx)},{f(cy + 1)} {f(x + 20)},{f(y)}" fill="none" stroke="{INK}" stroke-width="1.5"/>')

    # ---- edges --------------------------------------------------------------------------------
    @staticmethod
    def path_d(pts):
        return "M" + " L".join(f"{f(x)},{f(y)}" for x, y in pts)

    def arrow_filled(self, p_from, p_to, color=INK):
        (x1, y1), (x2, y2) = p_from, p_to
        a = math.atan2(y2 - y1, x2 - x1)
        L, W = 10.5, 4.6
        bx, by = x2 - L * math.cos(a), y2 - L * math.sin(a)
        px, py = -math.sin(a) * W, math.cos(a) * W
        return f'<polygon points="{f(x2)},{f(y2)} {f(bx + px)},{f(by + py)} {f(bx - px)},{f(by - py)}" fill="{color}" stroke="{color}" stroke-width="1" stroke-linejoin="round"/>'

    def arrow_open_tri(self, p_from, p_to):
        (x1, y1), (x2, y2) = p_from, p_to
        a = math.atan2(y2 - y1, x2 - x1)
        L, W = 11, 5
        bx, by = x2 - L * math.cos(a), y2 - L * math.sin(a)
        px, py = -math.sin(a) * W, math.cos(a) * W
        return f'<polygon points="{f(x2)},{f(y2)} {f(bx + px)},{f(by + py)} {f(bx - px)},{f(by - py)}" fill="{PAPER}" stroke="{INK}" stroke-width="1.5" stroke-linejoin="round"/>'

    def arrow_v(self, p_from, p_to):
        (x1, y1), (x2, y2) = p_from, p_to
        a = math.atan2(y2 - y1, x2 - x1)
        L, W = 9, 4.6
        bx, by = x2 - L * math.cos(a), y2 - L * math.sin(a)
        px, py = -math.sin(a) * W, math.cos(a) * W
        return f'<polyline points="{f(bx + px)},{f(by + py)} {f(x2)},{f(y2)} {f(bx - px)},{f(by - py)}" fill="none" stroke="{INK}" stroke-width="1.5" stroke-linejoin="round"/>'

    def draw_edge(self, ref, ed: Edge):
        m = self.m
        el = m.get(ref)
        if el is None:
            return
        n = ln(el)
        pts = ed.pts
        col = self.ov.get(ref, {}).get("stroke", INK) if isinstance(self.ov, dict) else INK
        if n == "sequenceFlow":
            pts2 = list(pts)
            self.add("edge", f'<path d="{self.path_d(pts2)}" fill="none" stroke="{col}" stroke-width="{SW}" stroke-linejoin="round"/>')
            self.add("edge", self.arrow_filled(pts2[-2], pts2[-1], col))
            src = m.get(el.get("sourceRef"))
            if src is not None:
                if el.find(q("conditionExpression")) is not None and ln(src) in ACTIVITIES:
                    self.add("edge", self.mini_diamond(pts2[0], pts2[1]))
                if src.get("default") == el.get("id"):
                    self.add("edge", self.slash(pts2[0], pts2[1]))
        elif n == "messageFlow":
            self.add("edge", f'<path d="{self.path_d(pts)}" fill="none" stroke="{col}" stroke-width="{SW}" stroke-dasharray="9 6" stroke-linejoin="round"/>')
            self.add("edge", f'<circle cx="{f(pts[0][0])}" cy="{f(pts[0][1])}" r="4.2" fill="{PAPER}" stroke="{INK}" stroke-width="1.5"/>')
            self.add("edge", self.arrow_open_tri(pts[-2], pts[-1]))
            if self.show_messages and el.get("messageRef"):
                best = max(zip(pts, pts[1:]), key=lambda s: abs(s[0][0] - s[1][0]) + abs(s[0][1] - s[1][1]))
                mx, my = (best[0][0] + best[1][0]) / 2, (best[0][1] + best[1][1]) / 2
                self.add("edge", self.envelope(mx, my, 18, 12, False))
        elif n in ("association", "dataInputAssociation", "dataOutputAssociation"):
            self.add("edge", f'<path d="{self.path_d(pts)}" fill="none" stroke="{col}" stroke-width="1.6" stroke-dasharray="1.5 4.2" stroke-linecap="round"/>')
            dirn = (el.get("associationDirection") or "None") if n == "association" else "One"
            if dirn in ("One", "Both"):
                self.add("edge", self.arrow_v(pts[-2], pts[-1]))
            if dirn == "Both":
                self.add("edge", self.arrow_v(pts[1], pts[0]))
        elif n == "conversationLink":
            self.add("edge", f'<path d="{self.path_d(pts)}" fill="none" stroke="{INK}" stroke-width="5" stroke-linejoin="round"/>')
            self.add("edge", f'<path d="{self.path_d(pts)}" fill="none" stroke="{PAPER}" stroke-width="2" stroke-linejoin="round"/>')
        else:
            self.add("edge", f'<path d="{self.path_d(pts)}" fill="none" stroke="{INK}" stroke-width="{SW}"/>')
        nm = el.get("name")
        if nm and ed.label is not None and n in ("sequenceFlow", "messageFlow", "conversationLink", "association"):
            ls, tw, th = block(nm, max(ed.label.w, 60), 11, 13.2)
            lb = ed.label
            self.add("label", f'<rect x="{f(lb.x - 2)}" y="{f(lb.y - 1)}" width="{f(tw + 6)}" height="{f(len(ls) * 13.2 + 2)}" fill="{PAPER}" fill-opacity="0.85"/>')
            for k, line in enumerate(ls):
                self.add("label", f'<text x="{f(lb.x + 1)}" y="{f(lb.y + 9 + k * 13.2)}" font-size="11" fill="{INK}">{esc(line)}</text>')

    def mini_diamond(self, p0, p1):
        (x1, y1), (x2, y2) = p0, p1
        a = math.atan2(y2 - y1, x2 - x1)
        L, W = 11, 4.2
        ux, uy = math.cos(a), math.sin(a)
        px, py = -uy, ux
        pts = [(x1, y1), (x1 + ux * L / 2 + px * W, y1 + uy * L / 2 + py * W), (x1 + ux * L, y1 + uy * L), (x1 + ux * L / 2 - px * W, y1 + uy * L / 2 - py * W)]
        return f'<polygon points="{" ".join(f(a_) + "," + f(b_) for a_, b_ in pts)}" fill="{PAPER}" stroke="{INK}" stroke-width="1.5" stroke-linejoin="round"/>'

    def slash(self, p0, p1):
        (x1, y1), (x2, y2) = p0, p1
        a = math.atan2(y2 - y1, x2 - x1)
        ux, uy = math.cos(a), math.sin(a)
        px, py = -uy, ux
        cx, cy = x1 + ux * 13, y1 + uy * 13
        # slash tilted ~60 degrees from the line
        t = math.radians(60)
        dx, dy = math.cos(a + t) * 6.5, math.sin(a + t) * 6.5
        return f'<line x1="{f(cx - dx)}" y1="{f(cy - dy)}" x2="{f(cx + dx)}" y2="{f(cy + dy)}" stroke="{INK}" stroke-width="2"/>'

    # ---- assemble -----------------------------------------------------------------------------
    def render(self) -> str:
        pl = self.pl
        # draw order: larger containers first so children sit on top
        def area(s):
            return s.box.w * s.box.h
        keys = list(pl.shapes.keys())
        # bands are drawn by their activity
        keys = [k for k in keys if not pl.shapes[k].band]
        for k in keys:
            self.draw_shape(k, pl.shapes[k])
        for ref, ed in pl.edges.items():
            self.draw_edge(ref, ed)
        b = pl.bounds()
        pad = 28
        W = b.r + pad
        H = b.b + pad + (18 if self.footer else 0)
        extra = []
        if self.title and pl.name:
            extra.append(f'<text x="18" y="20" font-size="14" font-weight="bold" fill="{INK}">{esc(pl.name)}</text>')
        if self.legend:
            y = b.b + pad + 4
            extra.append(f'<text x="18" y="{f(y)}" font-size="11" font-weight="bold" fill="{INK}">Legend</text>')
            for k, it in enumerate(self.legend):
                yy = y + 8 + k * 18
                extra.append(f'<rect x="18" y="{f(yy)}" width="14" height="12" rx="2" fill="{it.get("color", "#ccc")}" stroke="{INK}" stroke-width="1"/>'
                             f'<text x="38" y="{f(yy + 10)}" font-size="11" fill="{INK}">{esc(it.get("label", ""))}</text>')
            H += 26 + 18 * len(self.legend)
        if self.footer:
            extra.append(f'<text x="18" y="{f(H - 8)}" font-size="9.5" fill="#777">{esc(self.footer)}</text>')
        body = []
        for layer in ("pool", "lane", "group", "sub", "node", "edge", "top", "label", "ov"):
            body += self.layers[layer]
        body += extra
        return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{f(W)}" height="{f(H)}" viewBox="0 0 {f(W)} {f(H)}" '
                f'font-family="{FONT_FAMILY}">\n<rect width="{f(W)}" height="{f(H)}" fill="#ffffff"/>\n' + "\n".join(body) + "\n</svg>\n")


def _int(v, d=0):
    try:
        return int(v)
    except (TypeError, ValueError):
        return d
