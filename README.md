# ChandramaCAD

**Professional 2D CAD — by Chandrama Solutions**

ChandramaCAD is the first application in the Chandrama three-app ecosystem for 4-axis hotwire foam cutting:

```
ChandramaCAD  →  ChandramaGCODE  →  ChandramaGRBL
(draw shapes)    (generate g-code)   (machine control)
```

## Features (v1.0 MVP)

- Infinite canvas with zoom (scroll wheel) and pan (middle-mouse / Space+drag)
- Grid overlay — toggleable, 1 / 5 / 10 mm spacing
- Snap system: grid snap, endpoint snap, midpoint snap, center snap
- Draw tools: Line, Polyline, Rectangle, Circle, Arc, Spline
- Select, Move, Copy, Delete, Rotate, Scale
- Unlimited Undo / Redo
- Layer manager with per-layer colour and visibility
- Properties panel for selected entity inspection
- Export: DXF (R2010), DAT (Selig airfoil), CAD project JSON

## Stack

| Package    | Version   |
|------------|-----------|
| Python     | 3.12+     |
| PySide6    | ≥ 6.6.0   |
| ezdxf      | ≥ 1.2.0   |
| numpy      | ≥ 1.24.0  |
| pyqtgraph  | ≥ 0.13.0  |

## Quick Start

```bat
run.bat
```

Or:

```bash
pip install -r requirements.txt
python main.py
```

## Keyboard Shortcuts

| Key        | Action         |
|------------|----------------|
| Esc        | Select tool    |
| L          | Line tool      |
| P          | Polyline tool  |
| C          | Circle tool    |
| R          | Rectangle tool |
| A          | Arc tool       |
| G          | Toggle grid    |
| S          | Toggle snap    |
| F          | Fit to screen  |
| Ctrl+Z     | Undo           |
| Ctrl+Y     | Redo           |
| Ctrl+S     | Save project   |
| Ctrl+E     | Export DXF     |
| Delete     | Delete selected|

## Ecosystem

- **ChandramaGCODE** — reads `.dxf` / `.dat` from ChandramaCAD, generates 4-axis hotwire G-code
- **ChandramaGRBL** — sends G-code to the hotwire cutting machine

---
© Chandrama Solutions — chandramasolutions.com
