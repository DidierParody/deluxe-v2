"""
Converts .excalidraw JSON files → clean SVG files renderable by GitHub.
Usage: python docs/export_svg.py
"""
import json
import math
import os
import textwrap
from pathlib import Path

DOCS = Path(__file__).parent
PADDING = 40
FONT = "system-ui, -apple-system, sans-serif"


def wrap(text: str, max_chars: int = 28) -> list[str]:
    lines = []
    for raw in text.split("\n"):
        if len(raw) <= max_chars:
            lines.append(raw)
        else:
            lines.extend(textwrap.wrap(raw, max_chars) or [raw])
    return lines


def escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def bounds(elements: list) -> tuple:
    xs, ys, x2s, y2s = [], [], [], []
    for el in elements:
        x, y = el.get("x", 0), el.get("y", 0)
        w, h = abs(el.get("width", 0)), abs(el.get("height", 0))
        xs.append(x)
        ys.append(y)
        x2s.append(x + w)
        y2s.append(y + h)
    return min(xs), min(ys), max(x2s), max(y2s)


def render_arrow(el, ox, oy) -> str:
    x, y = el["x"] - ox, el["y"] - oy
    w, h = el.get("width", 0), el.get("height", 0)
    color = el.get("strokeColor", "#000")
    x2, y2 = x + w, y + h
    # arrowhead length
    AL = 10
    dx, dy = w, h
    length = math.hypot(dx, dy) or 1
    ux, uy = dx / length, dy / length
    # arrowhead points
    ax = x2 - AL * ux + AL * 0.35 * (-uy)
    ay = y2 - AL * uy + AL * 0.35 * ux
    bx = x2 - AL * ux - AL * 0.35 * (-uy)
    by_ = y2 - AL * uy - AL * 0.35 * ux
    return (
        f'<line x1="{x:.1f}" y1="{y:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
        f'stroke="{color}" stroke-width="1.5" />'
        f'<polygon points="{x2:.1f},{y2:.1f} {ax:.1f},{ay:.1f} {bx:.1f},{by_:.1f}" '
        f'fill="{color}" />'
    )


def render_rect(el, ox, oy) -> str:
    x, y = el["x"] - ox, el["y"] - oy
    w, h = el.get("width", 1), el.get("height", 1)
    fill = el.get("backgroundColor", "transparent")
    stroke = el.get("strokeColor", "#000")
    sw = el.get("strokeWidth", 1)
    r = 6  # corner radius
    parts = [
        f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" '
        f'rx="{r}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}" />'
    ]
    text = el.get("text", "")
    if text:
        fs = el.get("fontSize", 13)
        lines = wrap(text)
        line_h = fs * 1.35
        total_h = line_h * len(lines)
        ty = y + h / 2 - total_h / 2 + fs
        for i, line in enumerate(lines):
            cy = ty + i * line_h
            parts.append(
                f'<text x="{x + w/2:.1f}" y="{cy:.1f}" '
                f'font-family="{FONT}" font-size="{fs}px" '
                f'fill="{stroke}" text-anchor="middle" dominant-baseline="auto">'
                f'{escape(line)}</text>'
            )
    return "\n".join(parts)


def render_text(el, ox, oy) -> str:
    x, y = el["x"] - ox, el["y"] - oy
    text = el.get("text", "")
    fs = el.get("fontSize", 13)
    color = el.get("strokeColor", "#212529")
    lines = wrap(text, 60)
    line_h = fs * 1.35
    parts = []
    for i, line in enumerate(lines):
        cy = y + i * line_h
        parts.append(
            f'<text x="{x:.1f}" y="{cy:.1f}" '
            f'font-family="{FONT}" font-size="{fs}px" '
            f'fill="{color}">'
            f'{escape(line)}</text>'
        )
    return "\n".join(parts)


def to_svg(filepath: Path) -> str:
    data = json.loads(filepath.read_text(encoding="utf-8"))
    elements = data.get("elements", [])
    if not elements:
        return ""

    min_x, min_y, max_x, max_y = bounds(elements)
    ox = min_x - PADDING
    oy = min_y - PADDING
    vw = max_x - min_x + PADDING * 2
    vh = max_y - min_y + PADDING * 2

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {vw:.0f} {vh:.0f}" '
        f'width="{vw:.0f}" height="{vh:.0f}" '
        f'style="background:#ffffff">'
    ]

    # draw containers (large rects) first, then other elements on top
    rects = [e for e in elements if e["type"] == "rectangle"]
    rects_sorted = sorted(rects, key=lambda e: e.get("width", 0) * e.get("height", 0), reverse=True)
    others = [e for e in elements if e["type"] != "rectangle"]

    for el in rects_sorted:
        parts.append(render_rect(el, ox, oy))

    for el in others:
        t = el["type"]
        if t == "arrow":
            parts.append(render_arrow(el, ox, oy))
        elif t == "text":
            parts.append(render_text(el, ox, oy))

    parts.append("</svg>")
    return "\n".join(parts)


if __name__ == "__main__":
    for src in DOCS.glob("*.excalidraw"):
        out = src.with_suffix(".svg")
        svg = to_svg(src)
        if svg:
            out.write_text(svg, encoding="utf-8")
            print(f"Exported: {out.name}  ({len(svg):,} bytes)")
