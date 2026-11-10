"""Text measurement / wrapping for labels. Uses the real font metrics when PIL + a
metric-compatible font (Liberation Sans = Arial metrics) is available; otherwise a heuristic."""
from __future__ import annotations

import functools
import subprocess

FONT_FAMILY = "Arial, 'Liberation Sans', Helvetica, 'DejaVu Sans', sans-serif"

_font_cache = {}


@functools.lru_cache(maxsize=1)
def _font_path():
    cands = []
    try:
        out = subprocess.run(["fc-match", "-f", "%{file}", "Arial"], capture_output=True, text=True, timeout=5).stdout.strip()
        if out:
            cands.append(out)
    except Exception:
        pass
    cands += ["/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
              "/Library/Fonts/Arial.ttf", "C:/Windows/Fonts/arial.ttf"]
    import os
    for c in cands:
        if os.path.exists(c):
            return c
    return None


def _get_font(size, bold=False):
    key = (size, bold)
    if key in _font_cache:
        return _font_cache[key]
    f = None
    try:
        from PIL import ImageFont
        p = _font_path()
        if p:
            if bold:
                bp = p.replace("Regular", "Bold")
                import os
                if os.path.exists(bp):
                    p = bp
            f = ImageFont.truetype(p, int(round(size)))
    except Exception:
        f = None
    _font_cache[key] = f
    return f


def text_width(s: str, size: float = 12, bold: bool = False) -> float:
    f = _get_font(size, bold)
    if f is not None:
        try:
            return f.getlength(s) * (size / int(round(size)))
        except Exception:
            pass
    return len(s) * size * 0.56


def wrap(text: str, max_w: float, size: float = 12, bold: bool = False) -> list[str]:
    """Greedy word wrap; honours explicit newlines; hard-breaks words wider than the box."""
    lines: list[str] = []
    for para in (text or "").split("\n"):
        words = para.split()
        if not words:
            lines.append("")
            continue
        cur = ""
        for w in words:
            trial = (cur + " " + w).strip()
            if text_width(trial, size, bold) <= max_w or not cur:
                cur = trial
                while text_width(cur, size, bold) > max_w and len(cur) > 1:
                    # hard break an over-long word
                    k = len(cur)
                    while k > 1 and text_width(cur[:k], size, bold) > max_w:
                        k -= 1
                    lines.append(cur[:k])
                    cur = cur[k:]
            else:
                lines.append(cur)
                cur = w
        lines.append(cur)
    return lines


def block(text: str, max_w: float, size: float = 12, line_h: float | None = None, bold=False):
    """-> (lines, width, height) of the wrapped block."""
    lh = line_h or size * 1.2
    ls = wrap(text, max_w, size, bold)
    w = max((text_width(l, size, bold) for l in ls), default=0)
    return ls, w, lh * len(ls)
