#!/usr/bin/env python3
"""BPMN 2.0.2 skill command line.

  bpmn.py render   model.bpmn -o out/name [--formats png,svg,bpmn] [--overlay o.json] [--hints h.json]
                              [--subprocess auto|expanded|collapsed] [--relayout] [--scale 2]
                              [--level descriptive|analytic|executable] [--soundness] [--no-title] [--footer]
  bpmn.py validate model.bpmn [--level L] [--soundness] [--json]
  bpmn.py normalize model.bpmn -o fixed.bpmn
  bpmn.py extract  image.png|svg -o recovered.bpmn      (models embedded by `render`)
  bpmn.py info     model.bpmn                           (structure, hierarchy outline, level)

`render` = normalise -> validate (XSD + spec rules) -> layout (only when DI is missing/incomplete) ->
SVG + PNG in BPMN notation -> .bpmn with complete DI.  Errors block output unless --force.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import zlib
from datetime import date

from lxml import etree

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bpmnlib import *  # noqa
from normalize import normalize
from validate_bpmn import Validator, summarise, Issue
from layout import Opts, layout_model
from didi import read_di, di_is_complete, write_di
from draw import Svg

META_KEY = "bpmn-model"


# ------------------------------------------------------------------------------------------------
def rebuild_root(model: Model):
    """Re-create <definitions> with the standard prefixes declared (bpmndi, dc, di, xsi) while keeping
    every prefix the author already declared (QName-valued attributes need them)."""
    old = model.root
    nsmap = dict(old.nsmap)
    for pfx, uri in (("bpmndi", BPMNDI_NS), ("dc", DC_NS), ("di", DI_NS), ("xsi", XSI_NS)):
        if uri not in nsmap.values():
            nsmap[pfx] = uri
    if BPMN_NS not in nsmap.values():
        nsmap[None] = BPMN_NS
    new = etree.Element(old.tag, nsmap=nsmap)
    for k, v in old.attrib.items():
        new.set(k, v)
    new.text = old.text
    for c in list(old):
        new.append(c)
    model.root = new
    return model


def serialize(model: Model) -> bytes:
    rebuild_root(model)
    return etree.tostring(model.root, xml_declaration=True, encoding="UTF-8", pretty_print=True)


def embed_png(path: str, xml: bytes):
    try:
        from PIL import Image, PngImagePlugin
    except Exception:
        return False
    img = Image.open(path)
    info = PngImagePlugin.PngInfo()
    info.add_text(META_KEY, base64.b64encode(zlib.compress(xml, 9)).decode("ascii"))
    info.add_text("bpmn-skill", f"bpmn-skill {SKILL_VERSION}; BPMN 2.0.2")
    img.save(path, pnginfo=info)
    return True


def svg_with_meta(svg: str, xml: bytes) -> str:
    blob = base64.b64encode(zlib.compress(xml, 9)).decode("ascii")
    meta = f'<metadata id="{META_KEY}" data-encoding="zlib+base64">{blob}</metadata>\n'
    i = svg.index(">") + 1
    return svg[:i] + "\n" + meta + svg[i:]


def to_png(svg: str, out: str, scale: float):
    try:
        import cairosvg
        cairosvg.svg2png(bytestring=svg.encode("utf-8"), write_to=out, scale=scale)
        return True
    except ImportError:
        pass
    except Exception as e:  # pragma: no cover
        print(f"  cairosvg failed: {e}", file=sys.stderr)
    for tool in ("rsvg-convert",):
        import shutil, subprocess
        if shutil.which(tool):
            subprocess.run([tool, "-z", str(scale), "-o", out], input=svg.encode(), check=False)
            return os.path.exists(out)
    return False


def load_json(path):
    if not path:
        return None
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


# ------------------------------------------------------------------------------------------------
EXPORTER = "BPMN 2.0 Standard Skill"


def cmd_render(a):
    model = Model.parse(a.file)
    # DI written by this skill is disposable (the semantic model may have changed since); DI from another tool,
    # or hand-written DI, is the author's layout and is kept.
    skill_made_di = model.root.get("exporter") == EXPORTER
    log = normalize(model)
    for l in log:
        print("normalised:", l)
    v = Validator(model, level=a.level, style=True, soundness=a.soundness, xsd=True)
    # XSD must see the normalised tree; serialise->reparse so line numbers/ordering match what we will write
    issues = v.run()
    errors = [i for i in issues if i.sev == "error"]
    warns = [i for i in issues if i.sev == "warning"]
    for i in issues:
        if i.sev in ("error", "warning") or a.verbose:
            print(i)
    summ = summarise(model)
    if errors and not a.force:
        print(f"\nBLOCKED: {len(errors)} validation error(s). Fix the model (or use --force to render anyway).")
        return 1

    opts = Opts(subprocess=a.subprocess, hints=load_json(a.hints) or {})
    keep = a.keep_layout or not skill_made_di
    existing = [] if (a.relayout or not keep) else read_di(model)
    if model.diagrams() and not existing and not a.relayout:
        print('layout: DI in the file was produced by this skill earlier -> recomputing (use --keep-layout to reuse it)')
    ok, missing = di_is_complete(model, existing) if existing else (False, [])
    if existing and ok:
        planes = existing
        print(f"layout: using the diagram interchange (DI) in the file ({len(planes)} diagram(s))")
    else:
        if existing and not ok:
            print(f"layout: existing DI is incomplete ({len(missing)} element(s) without a shape/edge) -> computing a full layout")
        planes, lwarn = layout_model(model, opts)
        for w in lwarn:
            print("layout:", w)
        write_di(model, planes)
        print(f"layout: computed {len(planes)} diagram(s)")
    overlay = load_json(a.overlay)
    base = a.out
    os.makedirs(os.path.dirname(os.path.abspath(base)) or ".", exist_ok=True)
    fmts = [x.strip() for x in a.formats.split(",") if x.strip()]
    xml = serialize(model)
    written = []
    footer = None
    if a.footer:
        footer = (f"BPMN 2.0.2  |  {LEVEL_LABEL[summ['minimum_level']]}  |  "
                  f"{'valid' if not errors else 'NOT VALID'} (XSD + structural rules)  |  {date.today().isoformat()}")
    for idx, pl in enumerate(planes):
        suffix = "" if idx == 0 else "__" + slug(pl.name or pl.root_id, f"diagram{idx + 1}")
        svg = Svg(model, pl, overlay=overlay, title=not a.no_title, footer=footer, show_messages=a.show_messages).render()
        if "svg" in fmts:
            p = f"{base}{suffix}.svg"
            with open(p, "w", encoding="utf-8") as fh:
                fh.write(svg_with_meta(svg, xml))
            written.append(p)
        if "png" in fmts:
            p = f"{base}{suffix}.png"
            if to_png(svg, p, a.scale):
                embed_png(p, xml)
                written.append(p)
            else:
                print("  PNG not written: install cairosvg  (pip install cairosvg --break-system-packages)")
    if "bpmn" in fmts:
        p = f"{base}.bpmn"
        with open(p, "wb") as fh:
            fh.write(xml)
        written.append(p)
    c = summ["counts"]
    print(f"\nwrote: " + ", ".join(written))
    print(f"model: {c['processes']} process(es), {c['participants']} pool(s), {c['activities']} activities, {c['events']} events, "
          f"{c['gateways']} gateways, {c['sequenceFlows']} sequence flows, {c['messageFlows']} message flows")
    print(f"minimum conformance sub-class: {summ['minimum_level_label']}")
    print(f"validation: {'VALID' if not errors else 'INVALID (forced)'}  ({len(errors)} error(s), {len(warns)} warning(s))")
    return 0 if not errors else 1


def cmd_validate(a):
    from validate_bpmn import main as vmain
    argv = [a.file]
    if a.level:
        argv += ["--level", a.level]
    if a.soundness:
        argv.append("--soundness")
    if a.json:
        argv.append("--json")
    if a.no_style:
        argv.append("--no-style")
    return vmain(argv)


def cmd_normalize(a):
    from normalize import main as nmain
    return nmain([a.file, "-o", a.out])


def cmd_extract(a):
    p = a.file
    blob = None
    if p.lower().endswith(".png"):
        from PIL import Image
        img = Image.open(p)
        blob = img.info.get(META_KEY)
    else:
        txt = open(p, "r", encoding="utf-8", errors="ignore").read()
        m = re.search(r'<metadata id="%s"[^>]*>([^<]+)</metadata>' % META_KEY, txt)
        blob = m.group(1) if m else None
    if not blob:
        print("no embedded BPMN model found (this image was not produced by the skill). "
              "Read it visually: see references/source-analysis.md, 'Reading a diagram image'.")
        return 3
    xml = zlib.decompress(base64.b64decode(blob))
    with open(a.out, "wb") as fh:
        fh.write(xml)
    print(f"recovered {len(xml)} bytes -> {a.out}")
    return 0


def cmd_info(a):
    model = Model.parse(a.file)
    s = summarise(model)
    print(f"{a.file}: BPMN {'definitions' if ln(model.root) == 'definitions' else '?'}  name='{model.root.get('name') or ''}'")
    c = s["counts"]
    print(f"  {c['processes']} processes, {c['participants']} pools, {c['activities']} activities, {c['events']} events, "
          f"{c['gateways']} gateways, {c['sequenceFlows']} sequence flows, {c['messageFlows']} message flows, {c['diagrams']} diagrams")
    print(f"  minimum conformance sub-class: {s['minimum_level_label']}; inside Common Executable subset: {s['within_executable_subset']}")
    print("  hierarchy outline (process -> sub-process / call activity):")

    def walk(cont, depth):
        pad = "    " + "  " * depth
        for n in kids(cont):
            k = ln(n)
            if k in SUBPROCS | {"callActivity"}:
                extra = ""
                if k == "callActivity":
                    t = model.get(n.get("calledElement")) if n.get("calledElement") else None
                    extra = f" -> {t.get('name') or t.get('id')}" if t is not None else (f" -> {n.get('calledElement')} (external)" if n.get("calledElement") else " -> (no calledElement)")
                tag = "event-subprocess" if model.is_event_subprocess(n) else k
                print(f"{pad}- {tag}: {n.get('name') or n.get('id')}{extra}")
                if k in SUBPROCS:
                    walk(n, depth + 1)
    for col in model.collaborations():
        print(f"    collaboration {col.get('id')}: " + ", ".join(p.get("name") or p.get("id") for p in kids(col, "participant")))
    for proc in model.processes():
        print(f"    process {proc.get('name') or proc.get('id')}")
        walk(proc, 1)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("render")
    r.add_argument("file")
    r.add_argument("-o", "--out", required=True, help="output base path without extension")
    r.add_argument("--formats", default="png,svg,bpmn")
    r.add_argument("--overlay")
    r.add_argument("--hints")
    r.add_argument("--subprocess", choices=["auto", "expanded", "collapsed"], default="auto")
    r.add_argument("--relayout", action="store_true", help="ignore DI in the file and compute a new layout")
    r.add_argument("--keep-layout", action="store_true", help="reuse DI even if this skill generated it earlier")
    r.add_argument("--scale", type=float, default=2.0)
    r.add_argument("--level", choices=["descriptive", "analytic", "executable", "full"])
    r.add_argument("--soundness", action="store_true")
    r.add_argument("--no-title", action="store_true")
    r.add_argument("--footer", action="store_true")
    r.add_argument("--show-messages", action="store_true", help="draw an envelope on message flows that carry a messageRef")
    r.add_argument("--force", action="store_true")
    r.add_argument("--verbose", action="store_true")
    r.set_defaults(fn=cmd_render)
    v = sub.add_parser("validate")
    v.add_argument("file")
    v.add_argument("--level", choices=["descriptive", "analytic", "executable", "full"])
    v.add_argument("--soundness", action="store_true")
    v.add_argument("--no-style", action="store_true")
    v.add_argument("--json", action="store_true")
    v.set_defaults(fn=cmd_validate)
    n = sub.add_parser("normalize")
    n.add_argument("file")
    n.add_argument("-o", "--out", required=True)
    n.set_defaults(fn=cmd_normalize)
    e = sub.add_parser("extract")
    e.add_argument("file")
    e.add_argument("-o", "--out", required=True)
    e.set_defaults(fn=cmd_extract)
    i = sub.add_parser("info")
    i.add_argument("file")
    i.set_defaults(fn=cmd_info)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
