"""Automatic layout for BPMN 2.0 models without diagram interchange (DI).

Produces `Plane` objects (shapes with absolute bounds, edges with waypoints) that
`draw.py` renders and `didi.py` serialises as BPMNDiagram / BPMNPlane / BPMNShape / BPMNEdge.

Layout style (Cl. 7.6 recommendation): sequence flow runs left -> right, message flows are
vertical (90 degrees to the sequence flows), pools are stacked top to bottom.
"""
from __future__ import annotations

import math
import os
import sys
from collections import defaultdict
from dataclasses import dataclass, field

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bpmnlib import *  # noqa
from textutil import block, wrap, text_width

# geometry constants ---------------------------------------------------------------------------
TASK_W, TASK_H = 100, 80
EVENT_D = 36
GW_D = 50
DATA_W, DATA_H = 36, 50
STORE_W, STORE_H = 50, 50
COL_GAP = 64
ROW_GAP = 34
LANE_PAD = 22
X0 = 28
POOL_HDR = 30
LANE_HDR = 30
MIN_LANE_H = 110
SP_PAD = 22
SP_HDR = 6
POOL_GAP = 56
BLACKBOX_H = 84
LABEL_W = 92
OFFS = [0, 1, -1, 2, -2, 3, -3, 4, -4]


@dataclass
class Box:
    x: float
    y: float
    w: float
    h: float

    @property
    def cx(self): return self.x + self.w / 2
    @property
    def cy(self): return self.y + self.h / 2
    @property
    def r(self): return self.x + self.w
    @property
    def b(self): return self.y + self.h

    def moved(self, dx, dy): return Box(self.x + dx, self.y + dy, self.w, self.h)

    def inflate(self, d): return Box(self.x - d, self.y - d, self.w + 2 * d, self.h + 2 * d)

    def hits(self, o: "Box") -> bool:
        return not (self.r <= o.x or o.r <= self.x or self.b <= o.y or o.b <= self.y)


@dataclass
class Shape:
    id: str
    box: Box
    kind: str = ""
    expanded: bool | None = None
    horizontal: bool | None = None
    marker_visible: bool | None = None
    label: Box | None = None
    band: str | None = None        # choreography participant band kind
    msg_visible: str | None = None
    ref: str | None = None          # bpmnElement id when different from the dict key
    parent: str | None = None       # choreography activity shape id (participant bands)


@dataclass
class Edge:
    id: str
    pts: list
    label: Box | None = None


@dataclass
class Plane:
    root_id: str
    name: str
    shapes: dict = field(default_factory=dict)
    edges: dict = field(default_factory=dict)
    kind: str = "process"          # process | collaboration | choreography | conversation | subprocess
    order: list = field(default_factory=list)   # draw-order hint: ids of shapes in document order

    def bounds(self):
        xs, ys, xe, ye = [], [], [], []
        for s in self.shapes.values():
            xs.append(s.box.x); ys.append(s.box.y); xe.append(s.box.r); ye.append(s.box.b)
            if s.label:
                xs.append(s.label.x); ys.append(s.label.y); xe.append(s.label.r); ye.append(s.label.b)
        for e in self.edges.values():
            for (x, y) in e.pts:
                xs.append(x); ys.append(y); xe.append(x); ye.append(y)
            if e.label:
                xs.append(e.label.x); ys.append(e.label.y); xe.append(e.label.r); ye.append(e.label.b)
        if not xs:
            return Box(0, 0, 100, 100)
        return Box(min(xs), min(ys), max(xe) - min(xs), max(ye) - min(ys))


@dataclass
class Opts:
    subprocess: str = "auto"       # auto | expanded | collapsed
    hints: dict = field(default_factory=dict)
    max_auto_expand: int = 10
    show_messages: bool = False


# ------------------------------------------------------------------------------------------------
class Ctx:
    def __init__(self, model: Model, opts: Opts):
        self.m = model
        self.o = opts
        self.extra_planes: list[Plane] = []     # drill-down planes for collapsed sub-processes
        self.warnings: list[str] = []

    def inner_count(self, sp) -> int:
        return len([n for n in kids(sp) if ln(n) in FLOW_NODES])

    def is_expanded(self, sp) -> bool:
        m = self.m
        if self.inner_count(sp) == 0:
            return False
        forced = self.o.hints.get("expanded", {})
        if sp.get("id") in forced:
            return bool(forced[sp.get("id")])
        if m.is_event_subprocess(sp):
            return self.o.subprocess != "collapsed"
        pol = self.o.subprocess
        if pol == "expanded":
            return True
        if pol == "collapsed":
            return False
        return self.inner_count(sp) <= self.o.max_auto_expand


def label_box_below(cx, bottom, text, w=LABEL_W, size=11):
    ls, tw, th = block(text, w, size, size * 1.2)
    return Box(cx - w / 2, bottom + 4, w, th)


# ------------------------------------------------------------------------------------------------
class ContainerLayout:
    """Layout of one process level (process, sub-process or choreography)."""

    def __init__(self, ctx: Ctx, container, lanes=True):
        self.ctx = ctx
        self.m = ctx.m
        self.c = container
        self.use_lanes = lanes
        self.shapes: dict[str, Shape] = {}
        self.edges: dict[str, Edge] = {}
        self.lane_bands: list[dict] = []
        self.w = 0.0
        self.h = 0.0
        self.sub: dict[str, "ContainerLayout"] = {}
        self.is_choreo = ln(container) in ("choreography", "subChoreography")

    # ---- sizes ------------------------------------------------------------------------------
    @staticmethod
    def annotation_size(d):
        txt = text_of(d.find(q("text")))
        ls, tw, th = block(txt, 150, 11, 13.2)
        return min(160, max(80, tw + 16)), max(30, th + 12)

    def label_of(self, n) -> str:
        t = n.get("name") or ""
        if ln(n) == "dataObjectReference":
            ds = n.find(q("dataState"))
            if ds is not None and ds.get("name"):
                t = f"{t}\n[{ds.get('name')}]"
        return t

    def node_size(self, n):
        k = ln(n)
        if k in EVENTS:
            return EVENT_D, EVENT_D
        if k in GATEWAYS:
            return GW_D, GW_D
        if k == "choreographyTask":
            return 150, 96
        if k in ("subChoreography", "callChoreography"):
            return 170, 110
        if k in SUBPROCS or k == "callActivity" or k in TASKS:
            if n.get("id") in self.sub:
                s = self.sub[n.get("id")]
                return max(s.w, 200), max(s.h, 120)
            nm = n.get("name") or ""
            ls, tw, th = block(nm, TASK_W - 14, 12, 14.4)
            if len(ls) > 4:
                return 150, TASK_H + (10 if len(ls) > 5 else 0)
            if len(ls) > 3 or tw > TASK_W - 16 and len(nm) > 36:
                return 130, TASK_H
            return TASK_W, TASK_H
        return TASK_W, TASK_H

    # ---- main ---------------------------------------------------------------------------------
    def run(self):
        m, c = self.m, self.c
        all_nodes = [n for n in kids(c) if ln(n) in FLOW_NODES]
        self.boundaries = [n for n in all_nodes if ln(n) == "boundaryEvent"]
        self.esps = [n for n in all_nodes if m.is_event_subprocess(n)]
        self.nodes = [n for n in all_nodes if ln(n) != "boundaryEvent" and not m.is_event_subprocess(n)]
        self.flows = list(kids(c, "sequenceFlow"))
        self.node_by_id = {n.get("id"): n for n in self.nodes}
        self.b_by_id = {n.get("id"): n for n in self.boundaries}

        # sub-process contents
        for n in self.nodes:
            if ln(n) in SUBPROCS and self.ctx.is_expanded(n):
                cl = ContainerLayout(self.ctx, n, lanes=False)
                cl.run()
                self.sub[n.get("id")] = cl
            elif ln(n) in SUBPROCS and self.ctx.inner_count(n) > 0:
                self.ctx.extra_planes.append(self._drilldown_plane(n))
        self.esp_layouts = []
        for e in self.esps:
            cl = ContainerLayout(self.ctx, e, lanes=False)
            cl.run()
            self.esp_layouts.append((e, cl))

        self.size = {n.get("id"): self.node_size(n) for n in self.nodes}
        for b in self.boundaries:
            self.size[b.get("id")] = (EVENT_D, EVENT_D)

        self._lanes()
        self._graph()
        self._ranks()
        self._rows()
        self._coords()
        self._artifacts()
        self._route()
        self._finish()
        return self

    # ---- drill-down plane for a collapsed sub-process ---------------------------------------
    def _drilldown_plane(self, sp):
        cl = ContainerLayout(self.ctx, sp, lanes=False)
        cl.run()
        pl = Plane(sp.get("id"), sp.get("name") or sp.get("id"), kind="subprocess")
        cl.emit(pl, 40, 40, with_container_shape=False)
        return pl

    # ---- lanes --------------------------------------------------------------------------------
    def _lanes(self):
        m = self.m
        self.lane_of: dict[str, str] = {}
        self.lane_tree = []
        if not self.use_lanes or ln(self.c) != "process":
            return
        ls = self.c.find(q("laneSet"))
        if ls is None:
            return

        def walk(lset, depth):
            out = []
            for lane in kids(lset, "lane"):
                node = {"id": lane.get("id"), "name": lane.get("name") or "", "depth": depth, "children": [], "refs": []}
                for fr in kids(lane, "flowNodeRef"):
                    node["refs"].append(text_of(fr))
                ch = lane.find(q("childLaneSet"))
                if ch is not None:
                    node["children"] = walk(ch, depth + 1)
                out.append(node)
            return out
        self.lane_tree = walk(ls, 0)
        leaves = []

        def collect(nodes):
            for n in nodes:
                if n["children"]:
                    collect(n["children"])
                else:
                    leaves.append(n)
        collect(self.lane_tree)
        self.leaf_lanes = leaves
        for lf in leaves:
            for r in lf["refs"]:
                self.lane_of.setdefault(r, lf["id"])
        # nodes referenced only by a parent lane -> first leaf below it
        def first_leaf(n):
            return first_leaf(n["children"][0]) if n["children"] else n

        def assign_parent_refs(nodes):
            for n in nodes:
                if n["children"]:
                    fl = first_leaf(n)
                    for r in n["refs"]:
                        self.lane_of.setdefault(r, fl["id"])
                    assign_parent_refs(n["children"])
        assign_parent_refs(self.lane_tree)
        if any(n.get("id") not in self.lane_of for n in self.nodes):
            self.leaf_lanes.append({"id": None, "name": "", "depth": 0, "children": [], "refs": [], "synthetic": True})
        for b in self.boundaries:
            h = local_id(b.get("attachedToRef"))
            if h in self.lane_of:
                self.lane_of[b.get("id")] = self.lane_of[h]

    def lane_key(self, i):
        return self.lane_of.get(i) if self.lane_tree else None

    # ---- graph, ranks, rows -------------------------------------------------------------------
    def _graph(self):
        m = self.m
        self.ids = [n.get("id") for n in self.nodes]
        bids = [b.get("id") for b in self.boundaries]
        known = set(self.ids) | set(bids)
        self.layout_edges = []   # (u, v, w, drawn_flow_id or None)
        for sf in self.flows:
            s, t = local_id(sf.get("sourceRef")), local_id(sf.get("targetRef"))
            if s in known and t in known and s != t:
                self.layout_edges.append((s, t, 1, sf.get("id")))
        for b in self.boundaries:
            h = local_id(b.get("attachedToRef"))
            if h in self.node_by_id:
                self.layout_edges.append((h, b.get("id"), 0, None))
        for a in m.of("association"):
            s, t = local_id(a.get("sourceRef")), local_id(a.get("targetRef"))
            if s in self.b_by_id and t in self.node_by_id and is_true(self.node_by_id[t].get("isForCompensation")):
                self.layout_edges.append((s, t, 1, None))
        self.all_ids = self.ids + bids
        self.doc_index = {i: k for k, i in enumerate(self.all_ids)}

    def _ranks(self):
        ids = self.all_ids
        succ = defaultdict(list)
        pred = defaultdict(list)
        for u, v, w, _ in self.layout_edges:
            succ[u].append((v, w))
            pred[v].append((u, w))
        roots = [i for i in ids if not pred[i]] + ids
        color, back, post = {}, set(), []
        for r in roots:
            if r in color:
                continue
            stack = [(r, iter(succ[r]))]
            color[r] = 1
            while stack:
                u, it = stack[-1]
                advanced = False
                for v, w in it:
                    if v not in color:
                        color[v] = 1
                        stack.append((v, iter(succ[v])))
                        advanced = True
                        break
                    elif color[v] == 1:
                        back.add((u, v))
                if not advanced:
                    color[u] = 2
                    post.append(u)
                    stack.pop()
        self.back = back
        rank = {i: 0 for i in ids}
        for u in reversed(post):
            for v, w in succ[u]:
                if (u, v) in back:
                    continue
                if rank[v] < rank[u] + w:
                    rank[v] = rank[u] + w
        self.rank = rank
        self.succ_nb = defaultdict(list)
        self.pred_nb = defaultdict(list)
        for u, v, w, _ in self.layout_edges:
            if (u, v) in back:
                continue
            if v not in [x for x in self.succ_nb[u]]:
                self.succ_nb[u].append(v)
            if u not in self.pred_nb[v]:
                self.pred_nb[v].append(u)
        # depth to sink (longest path) for main-branch choice
        depth = {i: 0 for i in ids}
        for u in post:  # post order: successors first
            for v in self.succ_nb[u]:
                depth[u] = max(depth[u], depth[v] + 1)
        self.depth = depth

    def _ordered_succ(self, u):
        sl = list(self.succ_nb[u])
        if len(sl) <= 1:
            return sl
        node = self.node_by_id.get(u)
        main = None
        if node is not None and node.get("default"):
            sf = self.m.get(node.get("default"))
            if sf is not None:
                t = local_id(sf.get("targetRef"))
                if t in sl:
                    main = t
        if main is None:
            main = max(sl, key=lambda v: (self.depth[v], -self.doc_index[v]))
        rest = sorted([v for v in sl if v != main], key=lambda v: self.doc_index[v])
        return [main] + rest

    def _rows(self):
        order = sorted(self.all_ids, key=lambda i: (self.rank[i], self.doc_index[i]))
        row: dict[str, int] = {}
        occ = defaultdict(set)
        host_of_b = {b.get("id"): local_id(b.get("attachedToRef")) for b in self.boundaries}
        b_index = defaultdict(list)
        for b in self.boundaries:
            b_index[local_id(b.get("attachedToRef"))].append(b.get("id"))
        for v in order:
            if v in host_of_b:
                h = host_of_b[v]
                row[v] = row.get(h, 0)
                continue
            lane = self.lane_key(v)
            preds = [u for u in self.pred_nb[v] if u in row]
            sign = 0
            if not preds:
                pref = 0
            else:
                cands = []
                for u in preds:
                    if u in host_of_b:
                        h = host_of_b[u]
                        base = row.get(h, 0) + 1 + b_index[h].index(u)
                        off = 0
                        sib = self._ordered_succ(u)
                        if len(sib) > 1:
                            off = sib.index(v)
                        cands.append(base + off)
                        sign = 1
                        continue
                    if self.lane_key(u) != lane:
                        base = 0
                    else:
                        base = row[u]
                    off = 0
                    sib = self._ordered_succ(u)
                    if len(sib) > 1:
                        off = OFFS[min(sib.index(v), len(OFFS) - 1)]
                        if off:
                            sign = 1 if off > 0 else -1
                    cands.append(base + off)
                pref = int(math.floor(sum(cands) / len(cands) + 0.49))
            key = (self.rank[v], lane)
            r = pref
            if r in occ[key]:
                step = 1
                while True:
                    order_try = [r + step, r - step] if sign >= 0 else [r - step, r + step]
                    done = False
                    for t in order_try:
                        if t not in occ[key]:
                            r = t
                            done = True
                            break
                    if done:
                        break
                    step += 1
            occ[key].add(r)
            row[v] = r
        self.row = row

    # ---- coordinates ---------------------------------------------------------------------------
    def _attached(self):
        """artifacts / data objects associated with nodes of this container"""
        m = self.m
        c = self.c
        self.data_top = defaultdict(list)     # node id -> [data/annotation elements placed above]
        self.data_bottom = defaultdict(list)  # node id -> [data stores placed below]
        self.placed_artifacts = {}
        refs = {el.get("id"): el for el in kids(c) if ln(el) in DATA_VISUAL | ARTIFACTS}
        self.art_elems = refs
        # data associations
        self.data_assocs = []   # (assoc element, node element, data element, direction 'in'|'out')
        for n in list(self.nodes) + list(self.boundaries):
            for da in kids(n, "dataInputAssociation"):
                for s in kids(da, "sourceRef"):
                    d = m.get(text_of(s))
                    if d is not None and d.get("id") in refs:
                        self.data_assocs.append((da, n, d, "in"))
            for da in kids(n, "dataOutputAssociation"):
                for t in kids(da, "targetRef"):
                    d = m.get(text_of(t))
                    if d is not None and d.get("id") in refs:
                        self.data_assocs.append((da, n, d, "out"))
        # plain associations (text annotations, compensation)
        self.assocs = []
        for a in kids(c, "association"):
            s, t = m.get(a.get("sourceRef")), m.get(a.get("targetRef"))
            if s is not None and t is not None:
                self.assocs.append((a, s, t))
        # decide where each artifact sits
        placed = {}
        for da, n, d, dirn in self.data_assocs:
            did = d.get("id")
            if did in placed:
                continue
            nid = n.get("id")
            host = nid
            if nid in self.b_by_id:
                host = local_id(self.b_by_id[nid].get("attachedToRef"))
            placed[did] = host
            if ln(d) == "dataStoreReference":
                self.data_bottom[host].append(d)
            else:
                self.data_top[host].append(d)
        for a, s, t in self.assocs:
            art, other = (s, t) if ln(s) in ARTIFACTS else ((t, s) if ln(t) in ARTIFACTS else (None, None))
            if art is None or art.get("id") in placed or ln(art) == "group":
                continue
            oid = other.get("id")
            if oid in self.b_by_id:
                oid = local_id(self.b_by_id[oid].get("attachedToRef"))
            if oid in self.node_by_id:
                placed[art.get("id")] = oid
                self.data_top[oid].append(art)
        self.art_host = placed

    def _coords(self):
        self._attached()
        # column widths
        ranks = sorted({self.rank[i] for i in self.ids}) if self.ids else []
        col_w = defaultdict(float)
        for i in self.ids:
            col_w[self.rank[i]] = max(col_w[self.rank[i]], self.size[i][0])
        # annotations widen nothing; they float above
        xl = {}
        cur = X0
        for r in range(0, (max(ranks) + 1) if ranks else 0):
            xl[r] = cur
            cur += col_w.get(r, EVENT_D) + COL_GAP
        self.xl, self.col_w = xl, col_w
        content_w = (cur - COL_GAP) + X0 if ranks else 2 * X0
        # rows per lane
        lanes = self.leaf_lanes if self.lane_tree else [{"id": None, "name": "", "depth": 0, "children": [], "refs": []}]
        self.lane_rows = {}
        y_cursor = 0.0
        self.boxes: dict[str, Box] = {}
        lane_geom = {}
        for lane in lanes:
            lid = lane["id"]
            members = [i for i in self.ids if self.lane_key(i) == lid]
            rows = sorted({self.row[i] for i in members})
            rowinfo = []
            for r in rows:
                nodes_r = [i for i in members if self.row[i] == r]
                inner = max(self.size[i][1] for i in nodes_r)
                over = 0
                for i in nodes_r:
                    n = self.node_by_id[i]
                    if ln(n) in EVENTS and n.get("name"):
                        lh = block(n.get("name"), LABEL_W, 11, 13.2)[2]
                        over = max(over, self.size[i][1] / 2 + 4 + lh - inner / 2)
                top = 0
                bottom = max(0, over)
                for i in nodes_r:
                    if self.data_top.get(i):
                        top = max(top, 0)
                        hh = 0
                        for d in self.data_top[i]:
                            hh = max(hh, (self.annotation_size(d)[1] if ln(d) == "textAnnotation" else DATA_H) + 18)
                        top = max(top, hh)
                    if self.data_bottom.get(i):
                        bottom = max(bottom, STORE_H + 18)
                rowinfo.append({"row": r, "inner": inner, "top": top, "bottom": bottom})
            lane_top = y_cursor
            cur_y = lane_top + LANE_PAD
            centers = {}
            for k, ri in enumerate(rowinfo):
                cur_y += ri["top"]
                centers[ri["row"]] = cur_y + ri["inner"] / 2
                cur_y += ri["inner"] + ri["bottom"]
                if k < len(rowinfo) - 1:
                    cur_y += ROW_GAP
            content_bottom = cur_y + LANE_PAD
            lane_h = max(content_bottom - lane_top, MIN_LANE_H if self.lane_tree else 0)
            shift = (lane_h - (content_bottom - lane_top)) / 2 if self.lane_tree else 0
            for r in centers:
                centers[r] += shift
            lane_geom[lid] = (lane_top, lane_top + lane_h)
            y_cursor = lane_top + lane_h
            for i in members:
                wd, ht = self.size[i]
                cx = xl[self.rank[i]] + col_w[self.rank[i]] / 2
                cy = centers[self.row[i]]
                self.boxes[i] = Box(cx - wd / 2, cy - ht / 2, wd, ht)
        self.lane_geom = lane_geom
        self.content_w = content_w
        self.content_h = y_cursor
        # boundary events
        by_host = defaultdict(list)
        for b in self.boundaries:
            by_host[local_id(b.get("attachedToRef"))].append(b)
        for h, bl in by_host.items():
            if h not in self.boxes:
                continue
            hb = self.boxes[h]
            n = len(bl)
            for k, b in enumerate(bl):
                cx = hb.x + hb.w * (k + 1) / (n + 1)
                self.boxes[b.get("id")] = Box(cx - EVENT_D / 2, hb.b - EVENT_D / 2, EVENT_D, EVENT_D)
        # lane order for bands
        self.lane_bands = []

        def bands(nodes):
            res = []
            for nd in nodes:
                if nd["children"]:
                    ch = bands(nd["children"])
                    y0, y1 = ch[0]["y0"], ch[-1]["y1"]
                    res.append({"id": nd["id"], "name": nd["name"], "depth": nd["depth"], "y0": y0, "y1": y1})
                    res += ch
                else:
                    y0, y1 = lane_geom.get(nd["id"], (0, 0))
                    res.append({"id": nd["id"], "name": nd["name"], "depth": nd["depth"], "y0": y0, "y1": y1})
            return res

        def nest_order(nodes):
            # parent before children, siblings in order
            res = []
            for nd in nodes:
                if nd["children"]:
                    ch = nest_order(nd["children"])
                    y0 = min(b["y0"] for b in ch)
                    y1 = max(b["y1"] for b in ch)
                    res.append({"id": nd["id"], "name": nd["name"], "depth": nd["depth"], "y0": y0, "y1": y1})
                    res += ch
                else:
                    y0, y1 = lane_geom.get(nd["id"], (0, 0))
                    res.append({"id": nd["id"], "name": nd["name"], "depth": nd["depth"], "y0": y0, "y1": y1})
            return res
        if self.lane_tree:
            self.lane_bands = [b for b in nest_order(self.lane_tree)]
            self.max_depth = max(b["depth"] for b in self.lane_bands) + 1
        else:
            self.max_depth = 0

    # ---- artifacts ----------------------------------------------------------------------------
    def _artifacts(self):
        self.art_boxes: dict[str, Box] = {}
        placed_rects: list[Box] = []
        for host, items in list(self.data_top.items()) + list(self.data_bottom.items()):
            hb = self.boxes.get(host)
            if hb is None:
                continue
            is_bottom = items and ln(items[0]) == "dataStoreReference"
            k = 0
            for d in items:
                did = d.get("id")
                if did in self.art_boxes:
                    continue
                if ln(d) == "textAnnotation":
                    w, h = self.annotation_size(d)
                    desired_x = hb.cx + 12
                    y = hb.y - 20 - h - (0)
                    # annotation sits above the node; leave room for event labels etc.
                    bx = Box(desired_x, y, w, h)
                elif ln(d) == "dataStoreReference":
                    bx = Box(hb.cx - STORE_W / 2 + (k * (STORE_W + 14)), hb.b + 16, STORE_W, STORE_H)
                else:
                    bx = Box(hb.cx - DATA_W - 4 + (k * (DATA_W + 14)), hb.y - 18 - DATA_H, DATA_W, DATA_H)
                # shift right until it does not collide with earlier artifacts
                tries = 0
                while any(bx.inflate(6).hits(p) for p in placed_rects) and tries < 40:
                    bx = Box(bx.x + 24, bx.y, bx.w, bx.h)
                    tries += 1
                placed_rects.append(bx)
                self.art_boxes[did] = bx
                k += 1
        # artifacts not placed (e.g. group, unattached annotations/data) -> park top-left area
        floating = [el for el in self.art_elems.values() if el.get("id") not in self.art_boxes and ln(el) != "group"]
        fx = X0
        for d in floating:
            if ln(d) == "textAnnotation":
                aw, ah = self.annotation_size(d)
                bx = Box(fx, self.content_h + 10, aw, ah)
            elif ln(d) == "dataStoreReference":
                bx = Box(fx, self.content_h + 10, STORE_W, STORE_H)
            else:
                bx = Box(fx, self.content_h + 10, DATA_W, DATA_H)
            fx += bx.w + 20
            self.art_boxes[d.get("id")] = bx
            self.content_h = max(self.content_h, bx.b + 16)

    # ---- routing ------------------------------------------------------------------------------
    def _obstacles(self, ignore=()):
        res = []
        for i, b in self.boxes.items():
            if i in ignore or i in self.b_by_id:
                continue
            res.append((i, b))
        for i, b in self.art_boxes.items():
            res.append((i, b))
        return res

    @staticmethod
    def _seg_box(p, q_, b: Box) -> bool:
        x1, y1 = p
        x2, y2 = q_
        sb = Box(min(x1, x2), min(y1, y2), abs(x2 - x1), abs(y2 - y1))
        bb = Box(b.x + 1.5, b.y + 1.5, b.w - 3, b.h - 3)
        if sb.w == 0:
            sb = Box(sb.x - 0.01, sb.y, 0.02, sb.h)
        if sb.h == 0:
            sb = Box(sb.x, sb.y - 0.01, sb.w, 0.02)
        return sb.hits(bb)

    def _clear(self, pts, ignore):
        obs = self._obstacles(ignore)
        for a, b in zip(pts, pts[1:]):
            for i, bx in obs:
                if self._seg_box(a, b, bx):
                    return False
        return True

    def _channel_y(self, x1, x2, near_y, ignore, prefer_down=True):
        obs = self._obstacles(ignore)
        lo, hi = min(x1, x2), max(x1, x2)
        step = 14
        for k in range(0, 60):
            for sgn in ((1, -1) if prefer_down else (-1, 1)):
                y = near_y + sgn * (k * step)
                ok = True
                for i, bx in obs:
                    if bx.y - 4 <= y <= bx.b + 4 and not (bx.r < lo or bx.x > hi):
                        ok = False
                        break
                if ok:
                    return y
        return near_y + 200

    def _route(self):
        m = self.m
        self.flow_count_in = defaultdict(int)
        used_exit = set()
        for sf in self.flows:
            sid, tid = local_id(sf.get("sourceRef")), local_id(sf.get("targetRef"))
            if sid not in self.boxes or tid not in self.boxes:
                continue
            S, T = self.boxes[sid], self.boxes[tid]
            sn = self.node_by_id.get(sid)
            if sn is None:
                sn = self.b_by_id.get(sid)
            tn = self.node_by_id.get(tid)
            s_is_gw = ln(sn) in GATEWAYS
            t_is_gw = ln(tn) in GATEWAYS
            s_is_b = sid in self.b_by_id
            host = local_id(sn.get("attachedToRef")) if s_is_b else None
            ignore = {sid, tid} | ({host} if host else set())
            rs, rt = self.rank.get(sid, 0), self.rank.get(tid, 0)
            back = (sid, tid) in self.back or rt < rs
            pts = None
            sy, ty = S.cy, T.cy
            cands = []
            if s_is_b:
                if T.cy > S.b + 6:
                    cands.append([(S.cx, S.b), (S.cx, ty), (T.x, ty)] if T.x > S.cx + 4 else [(S.cx, S.b), (S.cx, ty - 0), (T.cx, ty)])
                cands.append([(S.cx, S.b), (S.cx, S.b + 22), (T.x - 14, S.b + 22), (T.x - 14, ty), (T.x, ty)])
            elif back or rt == rs:
                if rt == rs and sid != tid and not back:
                    # same column, different rows: vertical connection
                    if T.cy > S.cy:
                        if abs(S.cx - T.cx) < 1:
                            cands.append([(S.cx, S.b), (T.cx, T.y)])
                        else:
                            mid = S.b + (T.y - S.b) / 2
                            cands.append([(S.cx, S.b), (S.cx, mid), (T.cx, mid), (T.cx, T.y)])
                    else:
                        if abs(S.cx - T.cx) < 1:
                            cands.append([(S.cx, S.y), (T.cx, T.b)])
                        else:
                            mid = T.b + (S.y - T.b) / 2
                            cands.append([(S.cx, S.y), (S.cx, mid), (T.cx, mid), (T.cx, T.b)])
                else:
                    ch = self._channel_y(min(S.cx, T.cx), max(S.cx, T.cx), max(S.b, T.b) + 24, ignore, True)
                    # a back edge to the same row goes below; if target is gateway enter from bottom
                    cands.append([(S.cx, S.b), (S.cx, ch), (T.cx, ch), (T.cx, T.b)])
            else:
                if abs(sy - ty) < 1:
                    cands.append([(S.r, sy), (T.x, ty)])
                mx = (S.r + T.x) / 2 if rt - rs == 1 else T.x - COL_GAP / 2
                elbow = [(S.r, sy), (mx, sy), (mx, ty), (T.x, ty)]
                v_exit = [(S.cx, S.y if ty < sy else S.b), (S.cx, ty), (T.x, ty)]
                v_entry = [(S.r, sy), (T.cx, sy), (T.cx, T.b if sy > ty else T.y)]
                if abs(sy - ty) >= 1:
                    side = (sid, ty < sy)
                    if s_is_gw and side in used_exit:
                        s_is_gw = False
                    elif s_is_gw:
                        used_exit.add(side)
                    if s_is_gw and not t_is_gw:
                        cands += [v_exit, elbow]
                    elif t_is_gw and not s_is_gw:
                        cands += [v_entry if rt - rs >= 1 else elbow, elbow]
                    elif s_is_gw and t_is_gw:
                        cands += [v_exit, v_entry, elbow]
                    else:
                        cands += [elbow]
                # channel detour
                chy = self._channel_y(S.r, T.x, S.b + 22 if ty >= sy else S.y - 22, ignore, ty >= sy)
                cands.append([(S.r, sy), (S.r + 16, sy), (S.r + 16, chy), (T.x - 16, chy), (T.x - 16, ty), (T.x, ty)])
            for c in cands:
                if self._clear(c, ignore):
                    pts = c
                    break
            if pts is None:
                pts = cands[-1]
            pts = _dedupe(pts)
            self.edges[sf.get("id")] = Edge(sf.get("id"), pts, self._flow_label(sf, pts))
        # data associations and associations
        for da, n, d, dirn in self.data_assocs:
            nid = n.get("id")
            nb = self.boxes.get(nid)
            db = self.art_boxes.get(d.get("id"))
            if nb is None or db is None:
                continue
            a, b = (db, nb) if dirn == "in" else (nb, db)
            self.edges[da.get("id") or f"da_{nid}_{d.get('id')}"] = Edge(da.get("id"), self._straight(a, b))
        for a, s, t in self.assocs:
            sb = self.boxes.get(s.get("id"))
            if sb is None:
                sb = self.art_boxes.get(s.get("id"))
            tb = self.boxes.get(t.get("id"))
            if tb is None:
                tb = self.art_boxes.get(t.get("id"))
            if sb is None or tb is None:
                continue
            self.edges[a.get("id")] = Edge(a.get("id"), self._straight(sb, tb))

    def _straight(self, A: Box, B: Box):
        """Straight connector between boxes, orthogonal when they are nearly aligned."""
        if abs(A.cx - B.cx) < 2 or (A.x < B.r and B.x < A.r and abs(A.cx - B.cx) < 40):
            x = (max(A.x, B.x) + min(A.r, B.r)) / 2 if (A.x < B.r and B.x < A.r) else A.cx
            if A.cy < B.cy:
                return [(x, A.b), (x, B.y)]
            return [(x, A.y), (x, B.b)]
        if A.b <= B.y or B.b <= A.y:
            # diagonal between vertical neighbours: leave from centre sides
            if A.cy < B.cy:
                return [(A.cx, A.b), (B.cx, B.y)]
            return [(A.cx, A.y), (B.cx, B.b)]
        if A.cx < B.cx:
            return [(A.r, A.cy), (B.x, B.cy)]
        return [(A.x, A.cy), (B.r, B.cy)]

    def _flow_label(self, sf, pts):
        name = sf.get("name")
        if not name:
            return None
        ls, tw, th = block(name, 110, 11, 13.2)
        (x1, y1), (x2, y2) = pts[0], pts[1]
        if abs(y1 - y2) < 1:           # horizontal first segment: label above, near the start
            lx = min(x1, x2) + 6 if x2 > x1 else x1 - tw - 6
            return Box(lx, y1 - th - 3, tw + 2, th)
        # vertical first segment: label to the right, near the start
        ly = y1 + 4 if y2 > y1 else y1 - th - 4
        return Box(x1 + 6, ly, tw + 2, th)

    # ---- finish -------------------------------------------------------------------------------
    def _finish(self):
        # sub-process contents + event sub-processes
        ys = [self.content_h]
        xs = [self.content_w]
        for e in self.edges.values():
            for (x, y) in e.pts:
                ys.append(y + 14)
                xs.append(x + 14)
            if e.label:
                ys.append(e.label.b + 6)
                xs.append(e.label.r + 6)
        for b in self.art_boxes.values():
            ys.append(b.b + 12)
            xs.append(b.r + 12)
        self.h = max(ys)
        self.w = max(xs)
        # event sub-processes go below the main flow
        cur_y = self.h + 10
        self.esp_pos = {}
        for e, cl in self.esp_layouts:
            self.esp_pos[e.get("id")] = Box(X0, cur_y, cl.w, cl.h)
            cur_y += cl.h + 20
            self.w = max(self.w, X0 + cl.w + 20)
        if self.esp_layouts:
            self.h = cur_y
        # a lane-less container never grows below content; lane container: last lane stretches to h
        if self.lane_bands and self.leaf_lanes:
            last = self.leaf_lanes[-1]["id"]
            ly0, ly1 = self.lane_geom[last]
            if self.h > ly1:
                self.lane_geom[last] = (ly0, self.h)
                for b in self.lane_bands:
                    if b["y1"] == ly1:
                        b["y1"] = self.h
            self.h = max(self.h, ly1)

    def _bands(self, plane, n, sh):
        """Participant bands are separate BPMNShapes (Cl. 12.3.2). Initiator on top, others below."""
        parts = [local_id(text_of(c)) for c in kids(n, "participantRef")]
        ini = local_id(n.get("initiatingParticipantRef"))
        if not parts:
            return
        order = ([ini] if ini in parts else []) + [p for p in parts if p != ini]
        bh = 22
        bottoms = order[1:]
        bx = sh.box
        y = bx.y
        has_msg = bool(list(kids(n, "messageFlowRef")))
        for i, pid in enumerate(order):
            if i == 0:
                kind, yy = "top_initiating" if pid == ini else "top_non_initiating", bx.y
            else:
                j = i - 1
                yy = bx.b - bh * (len(bottoms) - j)
                if j == len(bottoms) - 1:
                    kind = "bottom_initiating" if pid == ini else "bottom_non_initiating"
                else:
                    kind = "middle_initiating" if pid == ini else "middle_non_initiating"
            key = f"{n.get('id')}__{pid}"
            b = Shape(key, Box(bx.x, yy, bx.w, bh), "participantBand", ref=pid, parent=n.get("id"), band=kind)
            if has_msg and i == 0:
                b.msg_visible = "initiating"
            plane.shapes[key] = b

    # ---- emit into a plane ----------------------------------------------------------------------
    def emit(self, plane: Plane, ox: float, oy: float, with_container_shape=True, lane_x0=None, lane_w=None):
        """Copy this layout into `plane`, translated by (ox, oy). Lanes use lane_x0/lane_w."""
        m = self.m
        # lanes
        for b in self.lane_bands:
            x = ox + (lane_x0 if lane_x0 is not None else 0) + b["depth"] * LANE_HDR
            w = (lane_w if lane_w is not None else self.w) - b["depth"] * LANE_HDR
            plane.shapes[b["id"]] = Shape(b["id"], Box(x, oy + b["y0"], w, b["y1"] - b["y0"]), "lane", horizontal=True)
        # sub-processes first so they sit under their children
        for n in self.nodes + self.boundaries:
            nid = n.get("id")
            bx = self.boxes.get(nid)
            if bx is None:
                continue
            k = ln(n)
            sh = Shape(nid, bx.moved(ox, oy), k)
            if k in SUBPROCS:
                sh.expanded = nid in self.sub
            if k == "exclusiveGateway":
                sh.marker_visible = True
            if k in EVENTS and n.get("name") and k != "boundaryEvent":
                sh.label = label_box_below(sh.box.cx, sh.box.b, n.get("name"))
            elif k in GATEWAYS and n.get("name"):
                ls_, tw_, th_ = block(n.get("name"), LABEL_W, 11, 13.2)
                sh.label = Box(sh.box.cx - LABEL_W - 2, sh.box.y - 4 - th_, LABEL_W, th_)
            if k == "boundaryEvent" and n.get("name"):
                sh.label = Box(sh.box.r + 3, sh.box.b - 8, 70, 13.2 * len(block(n.get("name"), 70, 11, 13.2)[0]))
            plane.shapes[nid] = sh
            if k in CHOREO_ACTS:
                self._bands(plane, n, sh)
            if nid in self.sub:
                inner = self.sub[nid]
                inner.emit(plane, sh.box.x + SP_PAD * 0 + (sh.box.w - inner.w) / 2,
                           sh.box.y + (sh.box.h - inner.h) / 2, with_container_shape=False)
        for eid, pos in self.esp_pos.items():
            en = self.m.get(eid)
            sh = Shape(eid, Box(pos.x + ox, pos.y + oy, pos.w, pos.h), ln(en), expanded=True)
            plane.shapes[eid] = sh
            cl = dict((e.get("id"), c) for e, c in self.esp_layouts)[eid]
            cl.emit(plane, pos.x + ox, pos.y + oy, with_container_shape=False)
        for did, bx in self.art_boxes.items():
            el = m.get(did)
            sh = Shape(did, bx.moved(ox, oy), ln(el))
            if ln(el) in DATA_VISUAL and el.get("name"):
                sh.label = label_box_below(sh.box.cx, sh.box.b, self.label_of(el), w=80)
            plane.shapes[did] = sh
        for eid, ed in self.edges.items():
            plane.edges[eid] = Edge(eid, [(x + ox, y + oy) for x, y in ed.pts],
                                    ed.label.moved(ox, oy) if ed.label else None)


def _dedupe(pts):
    out = [pts[0]]
    for p in pts[1:]:
        if abs(p[0] - out[-1][0]) < 0.01 and abs(p[1] - out[-1][1]) < 0.01:
            continue
        out.append(p)
    # drop collinear middle points
    res = [out[0]]
    for i in range(1, len(out) - 1):
        a, b, c = res[-1], out[i], out[i + 1]
        if (abs(a[0] - b[0]) < 0.01 and abs(b[0] - c[0]) < 0.01) or (abs(a[1] - b[1]) < 0.01 and abs(b[1] - c[1]) < 0.01):
            continue
        res.append(b)
    res.append(out[-1])
    return res


# ------------------------------------------------------------------------------------------------
class Layouter:
    def __init__(self, model: Model, opts: Opts | None = None):
        self.m = model
        self.o = opts or Opts()
        self.ctx = Ctx(model, self.o)

    def run(self) -> list[Plane]:
        m = self.m
        planes: list[Plane] = []
        in_collab = set()
        for col in m.collaborations():
            for p in kids(col, "participant"):
                if p.get("processRef"):
                    in_collab.add(local_id(p.get("processRef")))
        for col in m.collaborations():
            planes.append(self._collaboration(col))
        for proc in m.processes():
            if proc.get("id") in in_collab:
                continue
            planes.append(self._process_plane(proc))
        for ch in m.choreographies():
            planes.append(self._process_plane(ch, kind="choreography"))
        planes += self.ctx.extra_planes
        # groups: placed around the members named in hints {"groups": {"Group_1": ["Task_a", "Task_b"]}}
        for gid, members in (self.o.hints.get("groups") or {}).items():
            if m.get(gid) is None:
                self.ctx.warnings.append(f"hints: group '{gid}' is not in the model")
                continue
            for pl in planes:
                boxes = [pl.shapes[x].box for x in members if x in pl.shapes]
                if boxes:
                    x0 = min(b.x for b in boxes) - 14; y0 = min(b.y for b in boxes) - 26
                    x1 = max(b.r for b in boxes) + 14; y1 = max(b.b for b in boxes) + 30
                    pl.shapes[gid] = Shape(gid, Box(x0, y0, x1 - x0, y1 - y0), "group")
                    break
        return planes

    # ---- a single process ---------------------------------------------------------------------
    def _process_plane(self, proc, kind="process"):
        cl = ContainerLayout(self.ctx, proc, lanes=False)
        cl.run()
        pl = Plane(proc.get("id"), proc.get("name") or proc.get("id"), kind=kind)
        cl.emit(pl, 40, 40)
        return pl

    # ---- collaboration ------------------------------------------------------------------------
    def _collaboration(self, col):
        m = self.m
        parts = list(kids(col, "participant"))
        pl = Plane(col.get("id"), col.get("name") or self.m.root.get("name") or col.get("id"), kind="collaboration")
        has_proc = any(m.process_of_participant(p) is not None for p in parts)
        conv = [c for c in kids(col, *CONV_NODES)]
        if not has_proc and (conv or parts):
            return self._conversation(col, pl, parts, conv)
        layouts = {}
        for p in parts:
            proc = m.process_of_participant(p)
            if proc is not None:
                cl = ContainerLayout(self.ctx, proc, lanes=True)
                cl.run()
                layouts[p.get("id")] = cl
        max_depth = max([cl.max_depth for cl in layouts.values()] + [0])
        hdr = POOL_HDR + LANE_HDR * max_depth
        inner_w = max([cl.w for cl in layouts.values()] + [300])
        pool_w = hdr + inner_w
        x0, y = 40, 40
        pool_boxes = {}
        for p in parts:
            cl = layouts.get(p.get("id"))
            if cl is not None:
                h = max(cl.h, 100)
                # pools that have lanes: lanes occupy the full pool height
                pb = Box(x0, y, pool_w, h)
                pl.shapes[p.get("id")] = Shape(p.get("id"), pb, "participant", horizontal=True)
                pool_boxes[p.get("id")] = pb
                cl.emit(pl, x0 + hdr - (0), y, lane_x0=-(hdr - POOL_HDR), lane_w=pool_w - POOL_HDR + 0)
                # (lane bands drawn relative to pool inner edge)
                y += h + POOL_GAP
            else:
                pb = Box(x0, y, pool_w, BLACKBOX_H)
                pl.shapes[p.get("id")] = Shape(p.get("id"), pb, "participant", horizontal=True)
                pool_boxes[p.get("id")] = pb
                y += BLACKBOX_H + POOL_GAP
        # message flows
        self._message_flows(col, pl, pool_boxes)
        return pl

    def _message_flows(self, col, pl: Plane, pool_boxes):
        m = self.m
        gap_used = defaultdict(int)
        tgt_used = defaultdict(int)
        for mf in kids(col, "messageFlow"):
            sid, tid = local_id(mf.get("sourceRef")), local_id(mf.get("targetRef"))
            S = pl.shapes.get(sid)
            T = pl.shapes.get(tid)
            if S is None or T is None:
                continue
            sb, tb = S.box, T.box
            s_pool = pool_boxes.get(sid)
            t_pool = pool_boxes.get(tid)
            sp_box = s_pool or self._pool_of(pl, sid, pool_boxes)
            tp_box = t_pool or self._pool_of(pl, tid, pool_boxes)
            if sp_box is None or tp_box is None:
                continue
            down = tp_box.y > sp_box.y
            # x position: keep the flow vertical where possible
            if t_pool is not None:
                lo, hi = tb.x + 20, tb.r - 20
                sx = sb.cx
                tx = min(max(sx, lo), hi) + 14 * tgt_used[tid]
                tgt_used[tid] += 1
            elif s_pool is not None:
                lo, hi = sb.x + 20, sb.r - 20
                tx = tb.cx
                sx = min(max(tx, lo), hi) + 14 * tgt_used[sid]
                tgt_used[sid] += 1
            else:
                sx, tx = sb.cx, tb.cx
            sy = sb.b if down else sb.y
            ty = tb.y if down else tb.b
            obst = [x.box for k_, x in pl.shapes.items() if x.kind in (FLOW_NODES | DATA_VISUAL | ARTIFACTS)
                    and k_ not in (sid, tid)]

            def clear(pp):
                for a_, b_ in zip(pp, pp[1:]):
                    for ob in obst:
                        if ContainerLayout._seg_box(a_, b_, ob):
                            return False
                return True
            key = (round(min(sp_box.b, tp_box.b)), round(max(sp_box.y, tp_box.y)))
            ym = (sp_box.b + tp_box.y) / 2 if down else (tp_box.b + sp_box.y) / 2
            ym += (gap_used[key] % 5 - 2) * 7
            gap_used[key] += 1
            cands = []
            if abs(sx - tx) < 1:
                cands.append([(sx, sy), (tx, ty)])
            else:
                cands.append([(sx, sy), (sx, ym), (tx, ym), (tx, ty)])
            # slide the vertical run across the overlap of the two x-ranges looking for a clear line
            if t_pool is None and s_pool is None:
                lo, hi = max(sb.x + 8, tb.x + 8), min(sb.r - 8, tb.r - 8)
            elif t_pool is not None:
                lo, hi = max(sb.x + 8, tb.x + 20), min(sb.r - 8, tb.r - 20)
            else:
                lo, hi = max(tb.x + 8, sb.x + 20), min(tb.r - 8, sb.r - 20)
            if lo <= hi:
                for k_ in range(0, 12):
                    for sg in (1, -1):
                        xx = (sx if t_pool is not None or s_pool is not None else sb.cx) + sg * k_ * 8
                        xx = tx if (s_pool is not None and t_pool is None) else xx
                        if lo <= xx <= hi:
                            cands.insert(1 if k_ else 0, [(xx, sy), (xx, ty)])
            # approach the target node from the side through the column gap
            gx_t = tb.x - COL_GAP / 2
            if t_pool is None:
                ey = tb.y + min(16, tb.h / 3)
                cands.append([(gx_t, sy), (gx_t, ey), (tb.x, ey)] if s_pool is not None else
                             [(sx, sy), (sx, ym), (gx_t, ym), (gx_t, ey), (tb.x, ey)])
            elif s_pool is None:
                gx_s = sb.x - COL_GAP / 2
                cands.append([(gx_s, ty), (gx_s, sb.cy), (sb.x, sb.cy)][::-1] if False else [(sb.x, sb.cy), (gx_s, sb.cy), (gx_s, ty)])
            pts = next((c for c in cands if clear(c)), cands[0])
            pts = _dedupe(pts)
            label = None
            if mf.get("name"):
                ls, tw, th = block(mf.get("name"), 120, 11, 13.2)
                (x1, y1), (x2, y2) = pts[0], pts[1]
                label = Box(x1 + 6, (y1 + y2) / 2 - th / 2 if abs(x1 - x2) < 1 else y1 + 4, tw + 2, th)
            for end_id, (ex, ey) in ((sid, pts[0]), (tid, pts[-1])):
                es = pl.shapes.get(end_id)
                if es is not None and es.kind in EVENTS and es.label is not None and abs(ey - es.box.b) < 2:
                    es.label = Box(es.box.cx + 8, es.label.y, 70, es.label.h)
            pl.edges[mf.get("id")] = Edge(mf.get("id"), pts, label)

    def _pool_of(self, pl, nid, pool_boxes):
        el = self.m.get(nid)
        part = self.m.participant_of(el)
        return pool_boxes.get(part.get("id")) if part is not None else None

    # ---- conversation diagram -----------------------------------------------------------------
    def _conversation(self, col, pl, parts, conv):
        m = self.m
        n_conv = len(conv)
        left = parts[0::2]
        right = parts[1::2]
        px_l, px_r = 40, 40 + 240 + 160 * 1
        cx = 40 + 150
        row_h = 120
        rows = max(len(left), len(right), n_conv, 1)
        W_P, H_P = 130, 70
        left_x = 40
        mid_x = left_x + W_P + 170
        right_x = mid_x + 120 + 170
        for i, p in enumerate(left):
            pl.shapes[p.get("id")] = Shape(p.get("id"), Box(left_x, 40 + i * row_h, W_P, H_P), "participant", horizontal=True)
        for i, p in enumerate(right):
            pl.shapes[p.get("id")] = Shape(p.get("id"), Box(right_x, 40 + i * row_h, W_P, H_P), "participant", horizontal=True)
        for i, c in enumerate(conv):
            pl.shapes[c.get("id")] = Shape(c.get("id"), Box(mid_x, 40 + i * row_h + 5, 70, 60), ln(c))
            if c.get("name"):
                pl.shapes[c.get("id")].label = label_box_below(mid_x + 35, 40 + i * row_h + 65, c.get("name"), w=110)
        for cl in kids(col, "conversationLink"):
            s, t = pl.shapes.get(local_id(cl.get("sourceRef"))), pl.shapes.get(local_id(cl.get("targetRef")))
            if not s or not t:
                continue
            a, b = (s, t) if s.box.cx < t.box.cx else (t, s)
            pl.edges[cl.get("id")] = Edge(cl.get("id"), [(a.box.r, a.box.cy), (b.box.x, b.box.cy)] if abs(a.box.cy - b.box.cy) < 2
                                          else [(a.box.r, a.box.cy), ((a.box.r + b.box.x) / 2, a.box.cy), ((a.box.r + b.box.x) / 2, b.box.cy), (b.box.x, b.box.cy)]
                                          if a.box.r < b.box.x else [(a.box.cx, a.box.b), (b.box.cx, b.box.y)])
        pl.kind = "conversation"
        return pl


def layout_model(model: Model, opts: Opts | None = None):
    lo = Layouter(model, opts)
    planes = lo.run()
    return planes, lo.ctx.warnings
