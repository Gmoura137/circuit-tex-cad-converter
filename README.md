# circuit_tool.py

A Python utility for creating, parsing, and converting CircuiTikz circuit diagrams — from LaTeX source to paper-ready `.tex` files and CAD-compatible `.dxf` files.

No external dependencies required. Pure Python 3.6+.

---

## Installation

Just download `circuit_tool.py`. No pip installs needed.

```bash
python3 circuit_tool.py --help
```

---

## Commands

### `demo` — Generate example circuits

Reproduces four sample circuits (battery + resistor networks with voltage measurements) as JSON, LaTeX, and DXF all at once.

```bash
python3 circuit_tool.py demo
```

Output: `demo_circuits.json`, `demo_circuits.tex`, `circuit_1.dxf` … `circuit_4.dxf`

---

### `parse` — Read a `.tex` file

Parses all `circuitikz` environments in a LaTeX file and prints each element's coordinates, type, and label. Optionally saves a JSON representation.

```bash
python3 circuit_tool.py parse my_circuits.tex
python3 circuit_tool.py parse my_circuits.tex --json my_circuits.json
```

> **Note:** CircuiTikz's chained `\draw` syntax (multiple `to[…]` hops in one statement) is partially supported. The parser reliably extracts individual hops but may miss elements in the middle of long chains. For best results, build circuits via Python or JSON (see below).

---

### `latex` — JSON → LaTeX

Generates a complete, compilable `.tex` file from a circuit JSON file.

```bash
python3 circuit_tool.py latex my_circuits.json
python3 circuit_tool.py latex my_circuits.json output.tex   # custom output name
```

The output compiles directly with `pdflatex` or any LaTeX engine that has `circuitikz`, `amsmath`, and `amssymb`.

---

### `dxf` — JSON → CAD

Exports each circuit in the JSON as a separate `.dxf` file (AutoCAD R12 ASCII format).

```bash
python3 circuit_tool.py dxf my_circuits.json
python3 circuit_tool.py dxf my_circuits.json single_output.dxf   # for single-circuit files
```

Compatible with: AutoCAD, FreeCAD, KiCad, Fusion 360, LibreCAD, and any software that reads DXF R12.

---

### `all` — JSON → LaTeX + DXF together

```bash
python3 circuit_tool.py all my_circuits.json
```

---

## JSON Format

Circuits are represented as a list of element objects. Each element is a two-terminal component placed between two coordinate points.

```json
[
  {
    "name": "circuit_1",
    "elements": [
      {
        "x1": 0.0, "y1": 0.0,
        "x2": 0.0, "y2": 2.0,
        "kind": "battery",
        "label": "10 \\pm 0.1 \\, V",
        "current": "0.07 \\pm 0.01 \\, A",
        "options": ""
      },
      {
        "x1": 0.0, "y1": 2.0,
        "x2": 2.0, "y2": 2.0,
        "kind": "R",
        "label": "33\\, \\Omega",
        "current": "",
        "options": ""
      }
    ]
  }
]
```

**Element fields:**

| Field | Description |
|---|---|
| `x1, y1` | Start coordinate (CircuiTikz units) |
| `x2, y2` | End coordinate |
| `kind` | Component type (see table below) |
| `label` | LaTeX string for the component value label |
| `current` | LaTeX string for the current annotation (`i_=`) |
| `options` | Any extra CircuiTikz options (usually empty) |

---

## Supported Component Types

| `kind` | CircuiTikz | LaTeX output | DXF symbol |
|---|---|---|---|
| `battery` | `battery` | ✓ | Two-plate battery |
| `R` | `R` | ✓ | Zigzag resistor |
| `V` | `V` | ✓ | Circle voltage source |
| `C` | `C` | ✓ | Parallel-plate capacitor |
| `L` | `L` | ✓ | Inductor bumps |
| `short` | `short` | ✓ | Plain wire |
| anything else | passed through | ✓ | Wire (fallback) |

---

## DXF Layer Structure

DXF files are exported with three named layers for easy layer management in your CAD tool:

| Layer | Color | Contents |
|---|---|---|
| `CIRCUIT` | White/7 | Component symbols and wire lines |
| `LABELS` | Green/3 | Component value labels (LaTeX stripped to plain text) |
| `CURRENT` | Cyan/4 | Current annotations |

Scale: **1 CircuiTikz unit = 10 mm** in CAD space.

---

## Building Circuits in Python

The cleanest workflow — especially for programmatic generation — is to build circuits directly using the Python API, then export.

```python
from circuit_tool import Circuit, circuit_to_latex, circuit_to_dxf

c = Circuit(name="my_circuit")

# add(x1, y1, x2, y2, kind, label="", current="", options="")
c.add(0, 0, 0, 2, "battery", r"9 \, V", r"0.1 \, A")
c.add(0, 2, 3, 2, "R",       r"100 \, \Omega")
c.add(3, 2, 3, 0, "R",       r"47 \, \Omega")
c.add(3, 0, 0, 0, "short")

# LaTeX
print(circuit_to_latex(c, standalone=True))

# DXF
with open("my_circuit.dxf", "w") as f:
    f.write(circuit_to_dxf(c))
```

---

## Adding New Component Symbols (DXF)

The DXF symbol for each component is defined by a function that returns a list of polyline segments. Each segment is a list of `(x, y)` points in a normalised space where the component spans `x = 0.0` to `x = 1.0` and is centred on `y = 0`.

```python
def _my_component_symbol(length=1.0):
    # Return list of point-lists; each point-list is one polyline
    mid = length / 2
    return [
        [(0, 0), (mid - 0.1, 0)],        # left lead
        [(mid - 0.1, -0.2), (mid + 0.1, 0.2)],  # body
        [(mid + 0.1, 0), (length, 0)],   # right lead
    ]

# Register it
SYMBOL_MAP["mycomp"] = _my_component_symbol
```

After registering, use `"mycomp"` as the `kind` in any element and it will render in the DXF automatically. The LaTeX output will also pass `mycomp` through as a CircuiTikz element name, so as long as it's a valid CircuiTikz type, the `.tex` file will compile correctly too.

---

## Typical Workflow

```
Your hand-drawn circuit
        │
        ▼
  Edit circuit.json      ← define elements, labels, coordinates
        │
   ┌────┴────┐
   ▼         ▼
 .tex       .dxf
(paper)    (CAD / PCB)
```

Or starting from an existing LaTeX file:

```
existing .tex
      │
  parse → .json
      │
  ┌───┴───┐
  ▼       ▼
.tex    .dxf
```
## Future Improvments:

1. Add photos into the system that can read images and replicate into the virtual system
2. Fix the CAD optimization for the images
3. Include a visualizer in the system 
