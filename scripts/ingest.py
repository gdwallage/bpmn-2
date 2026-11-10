#!/usr/bin/env python3
"""Normalise heterogeneous process sources into text + images multimodal LLMs can read.

  ingest.py SOURCE... -o workdir [--frames-every 20]

For each source writes workdir/<name>.txt (plain text with page/slide/sheet markers) and, for images
and video, extra files (tiles, frames) listed in workdir/MANIFEST.md. It never guesses at content it
cannot read: audio without a transcript is reported as such (no speech-to-text is available offline).
"""
from __future__ import annotations

import argparse
import csv
import html
import os
import re
import shutil
import subprocess
import sys
import zipfile
from xml.etree import ElementTree as ET

IMG = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tif", ".tiff"}
VID = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"}
AUD = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def text_pdf(p):
    if shutil.which("pdftotext"):
        r = run(["pdftotext", "-layout", p, "-"])
        if r.stdout.strip():
            return r.stdout.replace("\f", "\n\n----- page break -----\n\n")
    # scanned PDF: OCR first pages if possible
    if shutil.which("pdftoppm") and shutil.which("tesseract"):
        tmp = p + "_ocr"
        os.makedirs(tmp, exist_ok=True)
        run(["pdftoppm", "-r", "150", "-png", p, os.path.join(tmp, "pg")])
        out = []
        for f in sorted(os.listdir(tmp)):
            out.append(f"----- {f} (OCR) -----\n" + run(["tesseract", os.path.join(tmp, f), "-", "--psm", "6"]).stdout)
        return "\n".join(out)
    return "(no text layer and no OCR tool available)"


def _ooxml_text(z, names, tag_p, tag_t, label):
    out = []
    for i, n in enumerate(names, 1):
        root = ET.fromstring(z.read(n))
        paras = []
        for p in root.iter(tag_p):
            t = "".join(x.text or "" for x in p.iter(tag_t))
            if t.strip():
                paras.append(t)
        out.append(f"----- {label} {i} -----\n" + "\n".join(paras))
    return "\n".join(out)


def text_docx(p):
    W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    with zipfile.ZipFile(p) as z:
        body = _ooxml_text(z, ["word/document.xml"], W + "p", W + "t", "document")
        extra = [n for n in z.namelist() if re.match(r"word/(comments|footnotes|endnotes)\.xml", n)]
        if extra:
            body += "\n" + _ooxml_text(z, extra, W + "p", W + "t", "notes/comments")
    return body


def text_pptx(p):
    A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
    with zipfile.ZipFile(p) as z:
        slides = sorted([n for n in z.namelist() if re.match(r"ppt/slides/slide\d+\.xml$", n)], key=lambda s: int(re.findall(r"\d+", s)[-1]))
        notes = sorted([n for n in z.namelist() if re.match(r"ppt/notesSlides/notesSlide\d+\.xml$", n)], key=lambda s: int(re.findall(r"\d+", s)[-1]))
        out = _ooxml_text(z, slides, A + "p", A + "t", "slide")
        if notes:
            out += "\n" + _ooxml_text(z, notes, A + "p", A + "t", "speaker notes")
    return out


def text_xlsx(p):
    try:
        import openpyxl
        wb = openpyxl.load_workbook(p, data_only=True)
        out = []
        for ws in wb.worksheets:
            out.append(f"----- sheet {ws.title} ({ws.max_row}x{ws.max_column}) -----")
            for row in ws.iter_rows(values_only=True):
                if any(c is not None for c in row):
                    out.append("\t".join("" if c is None else str(c) for c in row))
        return "\n".join(out)
    except ImportError:
        return "(openpyxl not installed: pip install openpyxl --break-system-packages)"


def text_html(p):
    s = open(p, encoding="utf-8", errors="ignore").read()
    s = re.sub(r"(?is)<(script|style).*?</\1>", "", s)
    s = re.sub(r"(?s)<br\s*/?>|</p>|</li>|</tr>|</h\d>", "\n", s)
    return html.unescape(re.sub(r"<[^>]+>", "", s))


def text_subs(p):
    s = open(p, encoding="utf-8", errors="ignore").read()
    s = re.sub(r"(?m)^\d+\s*$", "", s)
    s = re.sub(r"(?m)^WEBVTT.*$", "", s)
    return re.sub(r"\n{3,}", "\n\n", s)


def image_job(p, out, name):
    notes = []
    try:
        from PIL import Image
        im = Image.open(p)
        w, h = im.size
        notes.append(f"{w}x{h}px")
        if max(w, h) > 1800:
            # tiles with overlap so a large diagram can be read at legible size
            tw, th, ov = 1400, 1000, 120
            n = 0
            for y in range(0, h, th - ov):
                for x in range(0, w, tw - ov):
                    tile = im.crop((x, y, min(x + tw, w), min(y + th, h)))
                    tp = os.path.join(out, f"{name}_tile_r{y // (th - ov)}c{x // (tw - ov)}.png")
                    tile.convert("RGB").save(tp)
                    n += 1
            notes.append(f"{n} overlapping tiles written ({name}_tile_rXcY.png): view each one")
    except Exception as e:
        notes.append(f"PIL failed: {e}")
    ocr = ""
    if shutil.which("tesseract"):
        ocr = run(["tesseract", p, "-", "--psm", "11"]).stdout
        notes.append("OCR text below is a HELPER only: read the picture itself with `view`; OCR loses arrows, lanes and shapes")
    else:
        notes.append("tesseract not available: no OCR")
    return "\n".join(notes) + "\n\n----- OCR -----\n" + ocr


def video_job(p, out, name, every):
    notes = []
    if not shutil.which("ffmpeg"):
        return "(ffmpeg not available)"
    probe = run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type,codec_name", "-of", "default=nw=1", p]).stdout
    notes.append(probe.strip())
    fr = os.path.join(out, f"{name}_frames")
    os.makedirs(fr, exist_ok=True)
    run(["ffmpeg", "-y", "-i", p, "-vf", f"fps=1/{every},scale=1280:-1", os.path.join(fr, "f_%04d.jpg")])
    nfr = len([f for f in os.listdir(fr) if f.endswith(".jpg")])
    notes.append(f"{nfr} frames (one every {every}s) in {fr}: view them in order for on-screen process steps, whiteboards, slides")
    sub = os.path.join(out, f"{name}.subs.srt")
    r = run(["ffmpeg", "-y", "-i", p, "-map", "0:s:0", sub])
    if os.path.exists(sub) and os.path.getsize(sub) > 0:
        notes.append("embedded subtitles extracted:\n" + text_subs(sub))
    else:
        notes.append("NO subtitle track. The audio cannot be transcribed here (no offline speech-to-text). Ask for a transcript, "
                     "or fetch one from the meeting tool. Frames show only what was on screen.")
    return "\n".join(notes)


def audio_job(p):
    probe = run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1", p]).stdout.strip() if shutil.which("ffprobe") else ""
    return (f"AUDIO FILE ({probe}).\nNo speech-to-text is available in this environment, so the content has NOT been read.\n"
            "Ask the user for a transcript (.txt/.srt/.vtt/.docx) or fetch one from a connected meeting tool (e.g. Granola, Teams). "
            "Do not model a process from audio you could not hear.")


def ingest(path, out, every):
    name = re.sub(r"[^A-Za-z0-9_.-]+", "_", os.path.splitext(os.path.basename(path))[0])
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        t = text_pdf(path)
    elif ext == ".docx":
        t = text_docx(path)
    elif ext == ".pptx":
        t = text_pptx(path)
    elif ext in (".xlsx", ".xlsm"):
        t = text_xlsx(path)
    elif ext in (".html", ".htm"):
        t = text_html(path)
    elif ext in (".srt", ".vtt"):
        t = text_subs(path)
    elif ext in (".txt", ".md", ".csv", ".tsv", ".json", ".xml", ".bpmn", ".log", ".eml"):
        t = open(path, encoding="utf-8", errors="ignore").read()
    elif ext in IMG:
        t = image_job(path, out, name)
    elif ext in VID:
        t = video_job(path, out, name, every)
    elif ext in AUD:
        t = audio_job(path)
    else:
        t = f"(unsupported type {ext}; open it manually)"
    dest = os.path.join(out, name + ".txt")
    with open(dest, "w", encoding="utf-8") as fh:
        fh.write(t)
    return dest, len(t), ext


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sources", nargs="+")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--frames-every", type=int, default=20)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    lines = ["# Ingest manifest", ""]
    for s in a.sources:
        dest, n, ext = ingest(s, a.out, a.frames_every)
        lines.append(f"* `{s}` ({ext}) -> `{dest}` ({n} chars)")
        print(f"{s} -> {dest} ({n} chars)")
    with open(os.path.join(a.out, "MANIFEST.md"), "w") as fh:
        fh.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
