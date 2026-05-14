#!/usr/bin/env python3
"""
circuit_tool.py — CircuiTikz LaTeX ↔ CAD (DXF) converter
Usage:
    python circuit_tool.py parse   input.tex              # Print parsed circuit data
    python circuit_tool.py latex   circuit.json           # Generate LaTeX from JSON
    python circuit_tool.py dxf     circuit.json out.dxf   # Export to CAD DXF
    python circuit_tool.py demo                           # Generate demo circuits (your examples)
    python circuit_tool.py all     circuit.json           # Generate both LaTeX + DXF
"""

import re
import json
import sys
import math
import argparse
from dataclasses import dataclass, field, asdict
from typing import Optional


# ─────────────────────────────────────────────────────────────────────────────
# Data Model
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Element:
    """One two-terminal circuit element on a wire segment."""
    x1: float
    y1: float
    x2: float
    y2: float
    kind: str          # battery | R | V | short | open | C | L | lamp | diode | ...
    label: str = ""    # LaTeX label string
    current: str = ""  # i_ current label
    options: str = ""  # raw extra options string

@dataclass
class Circuit:
    """A complete circuit (one circuitikz environment)."""
    elements: list = field(default_factory=list)
    name: str = "circuit"

    def add(self, x1, y1, x2, y2, kind, label="", current="", options=""):
        self.elements.append(Element(x1, y1, x2, y2, kind, label, current, options))
        return self


# ─────────────────────────────────────────────────────────────────────────────
# LaTeX Parser  (circuitikz \draw commands)
# ─────────────────────────────────────────────────────────────────────────────

def _parse_coord(s):
    """Parse (x,y) → (float, float)."""
    s = s.strip().lstrip("(").rstrip(")")
    parts = s.split(",")
    return float(parts[0].strip()), float(parts[1].strip())

_DRAW_RE = re.compile(
    r'\\draw\s*(.*?)(?=\\draw|\Z)', re.DOTALL)
_SEGMENT_RE = re.compile(
    r'\(([^)]+)\)\s*'              # start coord
    r'to\[([^\]]+)\]\s*'           # to[element options]
    r'\(([^)]+)\)'                 # end coord
)
_SHORT_RE = re.compile(
    r'\(([^)]+)\)\s*to\[short\]\s*\(([^)]+)\)'
)

def _parse_element_opts(opts_str):
    """Parse 'R, l=$33\,\Omega$, i_=$0.1A$' into (kind, label, current, options)."""
    parts = [p.strip() for p in opts_str.split(",", 1)]
    kind = parts[0].strip()
    rest = parts[1] if len(parts) > 1 else ""

    label_m = re.search(r'l\s*=\s*\$([^$]*)\$', rest)
    label_m2 = re.search(r'l\s*=\s*([^,\]]+)', rest) if not label_m else None
    curr_m = re.search(r'i_?\s*=\s*\$([^$]*)\$', rest)

    label = label_m.group(1).strip() if label_m else (label_m2.group(1).strip() if label_m2 else "")
    current = curr_m.group(1).strip() if curr_m else ""

    # strip known keys from options remainder
    options = re.sub(r'l\s*=\s*(\$[^$]*\$|[^,\]]+)', '', rest)
    options = re.sub(r'i_?\s*=\s*(\$[^$]*\$|[^,\]]+)', '', options)
    options = options.strip(" ,")

    return kind, label, current, options

def parse_latex(tex_source: str) -> list:
    """Parse circuitikz environments from a LaTeX source string.
    Returns list of Circuit objects."""
    circuits = []
    # find all circuitikz environments
    env_re = re.compile(
        r'\\begin\{circuitikz\}(.*?)\\end\{circuitikz\}', re.DOTALL)
    for idx, m in enumerate(env_re.finditer(tex_source)):
        body = m.group(1)
        circ = Circuit(name=f"circuit_{idx+1}")

        for seg_m in _SEGMENT_RE.finditer(body):
            x1, y1 = _parse_coord(seg_m.group(1))
            x2, y2 = _parse_coord(seg_m.group(3))
            opts = seg_m.group(2)
            kind, label, current, options = _parse_element_opts(opts)
            circ.add(x1, y1, x2, y2, kind, label, current, options)

        circuits.append(circ)
    return circuits


# ─────────────────────────────────────────────────────────────────────────────
# LaTeX Generator
# ─────────────────────────────────────────────────────────────────────────────

def _fmt_label(el: Element) -> str:
    opts = [el.kind]
    if el.label:
        opts.append(f"l=${el.label}$")
    if el.current:
        opts.append(f"i_=${el.current}$")
    if el.options:
        opts.append(el.options)
    return ", ".join(opts)

def circuit_to_latex(circ: Circuit, standalone=False) -> str:
    lines = []
    if standalone:
        lines += [
            r"\documentclass{article}",
            r"\usepackage{circuitikz}",
            r"\usepackage{amsmath}",
            r"\usepackage{amssymb}",
            r"\begin{document}",
        ]
    lines += [
        r"\begin{center}",
        r"    \begin{circuitikz}",
    ]

    # Group elements into \draw chains where endpoints connect
    # Simple approach: one \draw per element
    for el in circ.elements:
        opts = _fmt_label(el)
        line = f"        \\draw ({el.x1},{el.y1}) to[{opts}] ({el.x2},{el.y2});"
        lines.append(line)

    lines += [
        r"    \end{circuitikz}",
        r"\end{center}",
    ]
    if standalone:
        lines.append(r"\end{document}")
    return "\n".join(lines)

def circuits_to_latex(circuits: list, filename="output.tex") -> str:
    lines = [
        r"\documentclass{article}",
        r"\usepackage{circuitikz}",
        r"\usepackage{amsmath}",
        r"\usepackage{amssymb}",
        r"\begin{document}",
    ]
    for i, circ in enumerate(circuits):
        lines.append(f"% {circ.name}")
        lines.append(circuit_to_latex(circ, standalone=False))
        lines.append("")
    lines.append(r"\end{document}")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# DXF Exporter  (pure Python — no library needed)
# DXF R12 ASCII format — compatible with AutoCAD, KiCad, FreeCAD, Fusion 360
# ─────────────────────────────────────────────────────────────────────────────

SCALE = 10.0   # 1 circuitikz unit = 10 mm in CAD

# Symbol drawing functions — each returns list of (x,y) polyline segments
# relative to midpoint of the element, axis-aligned horizontally.
# We rotate/translate when placing.

def _resistor_symbol(length=1.0):
    """Zigzag resistor body."""
    segs = []
    body = length * 0.6
    lead = (length - body) / 2
    n = 6
    step = body / n
    pts = [(0, 0)]
    for i in range(n):
        x = lead + i * step + step / 2
        y = (0.15 if i % 2 == 0 else -0.15)
        pts.append((x, y))
    pts.append((length, 0))
    # leads
    segs.append([(0, 0), (lead, 0)])
    segs.append(pts[1:-1])  # zigzag body
    segs.append([(length - lead, 0), (length, 0)])
    return segs

def _battery_symbol(length=1.0):
    """Battery: two lines + plates."""
    mid = length / 2
    segs = []
    segs.append([(0, 0), (mid - 0.12, 0)])   # lead left
    segs.append([(mid - 0.12, -0.2), (mid - 0.12, 0.2)])  # long plate
    segs.append([(mid + 0.0, -0.12), (mid + 0.0, 0.12)])  # short plate
    segs.append([(mid + 0.0, 0), (length, 0)])  # lead right
    return segs

def _voltage_symbol(length=1.0):
    """Voltage source: circle with + / -"""
    mid = length / 2
    r = 0.2
    segs = []
    segs.append([(0, 0), (mid - r, 0)])
    # circle approximated as 16-gon
    n = 16
    circle = []
    for i in range(n + 1):
        a = 2 * math.pi * i / n
        circle.append((mid + r * math.cos(a), r * math.sin(a)))
    segs.append(circle)
    segs.append([(mid + r, 0), (length, 0)])
    return segs

def _short_symbol(length=1.0):
    return [[(0, 0), (length, 0)]]

def _capacitor_symbol(length=1.0):
    mid = length / 2
    segs = []
    segs.append([(0, 0), (mid - 0.08, 0)])
    segs.append([(mid - 0.08, -0.2), (mid - 0.08, 0.2)])
    segs.append([(mid + 0.08, -0.2), (mid + 0.08, 0.2)])
    segs.append([(mid + 0.08, 0), (length, 0)])
    return segs

def _inductor_symbol(length=1.0):
    """Inductor: series of bumps."""
    n = 3
    seg_pts = [(0, 0)]
    step = length / (n + 0.5)
    for i in range(n):
        cx = step * (i + 0.5)
        for j in range(9):
            a = math.pi * j / 8
            seg_pts.append((cx + (step * 0.4) * (math.cos(a) - 1),
                             (step * 0.3) * math.sin(a)))
    seg_pts.append((length, 0))
    return [seg_pts]

SYMBOL_MAP = {
    "battery": _battery_symbol,
    "R":        _resistor_symbol,
    "V":        _voltage_symbol,
    "short":    _short_symbol,
    "C":        _capacitor_symbol,
    "L":        _inductor_symbol,
}

def _get_symbol(kind):
    fn = SYMBOL_MAP.get(kind, _short_symbol)
    return fn(1.0)

def _transform_pts(pts, x1, y1, x2, y2, scale):
    """Scale and rotate symbol pts to fit the element endpoints in CAD space."""
    dx = (x2 - x1) * scale
    dy = (y2 - y1) * scale
    length_cad = math.hypot(dx, dy)
    if length_cad < 1e-9:
        return []
    angle = math.atan2(dy, dx)
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    ox, oy = x1 * scale, y1 * scale

    result = []
    for pt in pts:
        # pt is in [0..1] x [-0.5..0.5] space
        lx, ly = pt[0] * length_cad, pt[1] * length_cad
        rx = lx * cos_a - ly * sin_a + ox
        ry = lx * sin_a + ly * cos_a + oy
        result.append((rx, ry))
    return result

def _dxf_polyline(pts, layer="CIRCUIT"):
    """Emit DXF R12 POLYLINE entity."""
    lines = []
    lines.append("  0\nPOLYLINE")
    lines.append("  8\n" + layer)
    lines.append(" 66\n1")  # vertices follow
    lines.append(" 10\n0.0\n 20\n0.0\n 30\n0.0")
    for x, y in pts:
        lines.append("  0\nVERTEX")
        lines.append("  8\n" + layer)
        lines.append(f" 10\n{x:.4f}\n 20\n{y:.4f}\n 30\n0.0")
    lines.append("  0\nSEQEND")
    return "\n".join(lines)

def _dxf_text(text, x, y, height=2.0, layer="LABELS"):
    text_clean = re.sub(r'\$|\\[a-zA-Z]+|[{}]', '', text).strip()
    if not text_clean:
        return ""
    return (
        f"  0\nTEXT\n  8\n{layer}\n"
        f" 10\n{x:.4f}\n 20\n{y:.4f}\n 30\n0.0\n"
        f" 40\n{height:.4f}\n  1\n{text_clean}"
    )

def _dxf_line(x1, y1, x2, y2, layer="CIRCUIT"):
    return (
        f"  0\nLINE\n  8\n{layer}\n"
        f" 10\n{x1:.4f}\n 20\n{y1:.4f}\n 30\n0.0\n"
        f" 11\n{x2:.4f}\n 21\n{y2:.4f}\n 31\n0.0"
    )

def circuit_to_dxf(circ: Circuit, scale: float = SCALE) -> str:
    entities = []

    for el in circ.elements:
        segs = _get_symbol(el.kind)
        for seg_pts in segs:
            if len(seg_pts) < 2:
                continue
            if len(seg_pts) == 2:
                p1 = _transform_pts([seg_pts[0]], el.x1, el.y1, el.x2, el.y2, scale)
                p2 = _transform_pts([seg_pts[1]], el.x1, el.y1, el.x2, el.y2, scale)
                if p1 and p2:
                    entities.append(_dxf_line(p1[0][0], p1[0][1], p2[0][0], p2[0][1]))
            else:
                tpts = _transform_pts(seg_pts, el.x1, el.y1, el.x2, el.y2, scale)
                if tpts:
                    entities.append(_dxf_polyline(tpts))

        # Label text at midpoint, offset perpendicular
        mx = (el.x1 + el.x2) / 2 * scale
        my = (el.y1 + el.y2) / 2 * scale
        # perpendicular offset
        dx = (el.x2 - el.x1)
        dy = (el.y2 - el.y1)
        dist = math.hypot(dx, dy)
        if dist > 0:
            px, py = -dy / dist * 3.0, dx / dist * 3.0
        else:
            px, py = 0, 3.0

        if el.label:
            txt = _dxf_text(el.label, mx + px, my + py, height=1.8)
            if txt:
                entities.append(txt)
        if el.current:
            txt = _dxf_text(el.current, mx - px * 0.5, my - py * 0.5, height=1.5, layer="CURRENT")
            if txt:
                entities.append(txt)

    # ── DXF R12 file structure ──────────────────────────────────────────────
    dxf = []
    dxf.append("  0\nSECTION\n  2\nHEADER")
    dxf.append("  9\n$ACADVER\n  1\nAC1009")  # R12
    dxf.append("  0\nENDSEC")

    dxf.append("  0\nSECTION\n  2\nTABLES")
    # Layer table
    dxf.append("  0\nTABLE\n  2\nLAYER\n 70\n3")
    for lname, color in [("CIRCUIT", 7), ("LABELS", 3), ("CURRENT", 4)]:
        dxf.append(
            f"  0\nLAYER\n  2\n{lname}\n 70\n0\n 62\n{color}\n  6\nCONTINUOUS")
    dxf.append("  0\nENDTAB\n  0\nENDSEC")

    dxf.append("  0\nSECTION\n  2\nENTITIES")
    dxf.extend(entities)
    dxf.append("  0\nENDSEC\n  0\nEOF")

    return "\n".join(dxf)


# ─────────────────────────────────────────────────────────────────────────────
# JSON serialisation helpers
# ─────────────────────────────────────────────────────────────────────────────

def circuit_to_dict(circ: Circuit) -> dict:
    return {
        "name": circ.name,
        "elements": [asdict(e) for e in circ.elements]
    }

def dict_to_circuit(d: dict) -> Circuit:
    circ = Circuit(name=d.get("name", "circuit"))
    for e in d.get("elements", []):
        circ.elements.append(Element(**e))
    return circ


# ─────────────────────────────────────────────────────────────────────────────
# Demo: your four circuits re-created programmatically
# ─────────────────────────────────────────────────────────────────────────────

def make_demo_circuits() -> list:
    circuits = []

    # ── Circuit 1 ──
    c1 = Circuit(name="circuit_1")
    c1.add(0,0, 0,2, "battery",  r"10 \pm 0.1 \, V",  r"0.07 \pm 0.01 \, A")
    c1.add(0,2, 2,2, "R",        r"33\, \Omega")
    c1.add(2,2, 2.5,2, "short")
    c1.add(2.5,2, 2.5,0, "R",   r"100\, \Omega")
    c1.add(2.5,0, 0,0, "short")
    c1.add(0,2, 0,3.5, "short")
    c1.add(0,3.5, 2.5,3.5, "V", r"2.49 \pm 0.01 \, V")
    c1.add(2.5,3.5, 2.5,2, "short")
    c1.add(2.5,2, 4,2.5, "short")
    c1.add(4,2.5, 5,1, "V",     r"7.62 \pm 0.01 \, V")
    c1.add(5,1, 2.5,0, "short")
    circuits.append(c1)

    # ── Circuit 2 ──
    c2 = Circuit(name="circuit_2")
    c2.add(0,0, 0,2, "battery",  r"10 \pm 0.1 \,V",   r"0.23 \pm 0.01 \, A")
    c2.add(0,2, 2,2, "R",        r"10\, \Omega")
    c2.add(2,2, 2.5,2, "short")
    c2.add(2.5,2, 2.5,0, "R",   r"33\, \Omega")
    c2.add(2.5,0, 0,0, "short")
    c2.add(0,2, 0,3.5, "short")
    c2.add(0,3.5, 2.5,3.5, "V", r"2.36 \pm 0.01 \, V")
    c2.add(2.5,3.5, 2.5,2, "short")
    c2.add(2.5,2, 4,2.5, "short")
    c2.add(4,2.5, 5,1, "V",     r"7.74 \pm 0.01 \, V")
    c2.add(5,1, 2.5,0, "short")
    circuits.append(c2)

    # ── Circuit 3 ──
    c3 = Circuit(name="circuit_3")
    c3.add(0,0, 0,2, "battery",  r"5 \pm 0.1 \, V",   r"0.2 \pm 0.01 \, A")
    c3.add(0,2, 2,2, "short")
    c3.add(2,2, 2.5,2, "short")
    c3.add(2.5,2, 2.5,0, "R",   r"33 \Omega")
    c3.add(2.5,0, 0,0, "short")
    c3.add(2.5,2, 4.5,2, "short")
    c3.add(4.5,2, 4.5,0, "R",   r"100 \Omega")
    c3.add(4.5,0, 2.5,0, "short")
    c3.add(2.5,2, 2.75,3.5, "short")
    c3.add(2.75,3.5, 0,3.5, "V",r"4.97 \pm 0.1 \, V")
    c3.add(0,3.5, 2.5,0, "short")
    c3.add(4.5,2, 7,2, "short")
    c3.add(7,2, 7,0, "V",       r"4.97 \pm 0.1 \, V")
    c3.add(7,0, 2.5,0, "short")
    circuits.append(c3)

    # ── Circuit 4 ──
    c4 = Circuit(name="circuit_4")
    c4.add(0,0, 0,2, "battery",  r"5.1 \, V",          r"0.15 \pm 0.01 \, A")
    c4.add(0,2, 2,2, "R",        r"10 \Omega")
    c4.add(2,2, 2.5,2, "short")
    c4.add(2.5,2, 2.5,0, "R",   r"33 \Omega")
    c4.add(2.5,0, 0,0, "short")
    c4.add(2.5,2, 4.5,2, "short")
    c4.add(4.5,2, 4.5,0, "R",   r"100 \Omega")
    c4.add(4.5,0, 2.5,0, "short")
    c4.add(0,2, 0,3.5, "short")
    c4.add(0,3.5, 2.5,3.5, "V", r"1.48 \pm 0.01\,V")
    c4.add(2.5,3.5, 2.5,2, "short")
    c4.add(4.5,2, 7,2, "short")
    c4.add(7,2, 7,0, "V",       r"3.66 \pm 0.01\,V")
    c4.add(7,0, 2.5,0, "short")
    circuits.append(c4)

    return circuits


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def cmd_parse(args):
    src = open(args.input).read()
    circuits = parse_latex(src)
    print(f"Found {len(circuits)} circuit(s).\n")
    for c in circuits:
        print(f"[{c.name}]  {len(c.elements)} elements")
        for e in c.elements:
            print(f"  ({e.x1},{e.y1})→({e.x2},{e.y2})  {e.kind:10s}  {e.label}")
    if args.json:
        data = [circuit_to_dict(c) for c in circuits]
        with open(args.json, "w") as f:
            json.dump(data, f, indent=2)
        print(f"\nSaved JSON → {args.json}")

def cmd_latex(args):
    with open(args.input) as f:
        data = json.load(f)
    circuits = [dict_to_circuit(d) for d in (data if isinstance(data, list) else [data])]
    tex = circuits_to_latex(circuits)
    out = args.output or args.input.replace(".json", ".tex")
    with open(out, "w") as f:
        f.write(tex)
    print(f"LaTeX written → {out}")

def cmd_dxf(args):
    with open(args.input) as f:
        data = json.load(f)
    circuits = [dict_to_circuit(d) for d in (data if isinstance(data, list) else [data])]
    for circ in circuits:
        out = args.output or f"{circ.name}.dxf"
        if len(circuits) > 1:
            out = f"{circ.name}.dxf"
        dxf = circuit_to_dxf(circ)
        with open(out, "w") as f:
            f.write(dxf)
        print(f"DXF written  → {out}  ({len(circ.elements)} elements)")

def cmd_demo(args):
    circuits = make_demo_circuits()
    # Write JSON
    data = [circuit_to_dict(c) for c in circuits]
    with open("demo_circuits.json", "w") as f:
        json.dump(data, f, indent=2)
    print("Saved → demo_circuits.json")

    # Write LaTeX
    tex = circuits_to_latex(circuits)
    with open("demo_circuits.tex", "w") as f:
        f.write(tex)
    print("Saved → demo_circuits.tex")

    # Write DXF (one file per circuit)
    for circ in circuits:
        dxf = circuit_to_dxf(circ)
        fn = f"{circ.name}.dxf"
        with open(fn, "w") as f:
            f.write(dxf)
        print(f"Saved → {fn}")

def cmd_all(args):
    with open(args.input) as f:
        data = json.load(f)
    circuits = [dict_to_circuit(d) for d in (data if isinstance(data, list) else [data])]
    # LaTeX
    tex = circuits_to_latex(circuits)
    tex_out = args.input.replace(".json", ".tex")
    with open(tex_out, "w") as f:
        f.write(tex)
    print(f"LaTeX → {tex_out}")
    # DXF
    for circ in circuits:
        dxf = circuit_to_dxf(circ)
        fn = f"{circ.name}.dxf"
        with open(fn, "w") as f:
            f.write(dxf)
        print(f"DXF   → {fn}")


def main():
    p = argparse.ArgumentParser(
        description="CircuiTikz LaTeX ↔ CAD (DXF) tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    pp = sub.add_parser("parse", help="Parse .tex → print elements (optionally save JSON)")
    pp.add_argument("input")
    pp.add_argument("--json", metavar="OUT.json", help="also save parsed JSON")

    lp = sub.add_parser("latex", help="JSON → .tex")
    lp.add_argument("input")
    lp.add_argument("output", nargs="?")

    dp = sub.add_parser("dxf", help="JSON → .dxf")
    dp.add_argument("input")
    dp.add_argument("output", nargs="?")

    sub.add_parser("demo", help="Generate all 4 demo circuits (JSON + LaTeX + DXF)")

    ap = sub.add_parser("all", help="JSON → LaTeX + DXF")
    ap.add_argument("input")

    args = p.parse_args()
    {"parse": cmd_parse, "latex": cmd_latex, "dxf": cmd_dxf,
     "demo": cmd_demo, "all": cmd_all}[args.cmd](args)


if __name__ == "__main__":
    main()
