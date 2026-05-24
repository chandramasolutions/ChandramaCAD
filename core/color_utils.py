"""
Colour and linetype utilities for ChandramaCAD.
Pure-Python module — no Qt dependency.
Provides hex ↔ RGB ↔ ACI conversions and linetype definitions.
"""
from __future__ import annotations


# ── Hex ↔ RGB ────────────────────────────────────────────────────────────────

def hex_to_rgb(hex_str: str) -> tuple[int, int, int]:
    """Convert '#RRGGBB' or '#RGB' to (r, g, b) ints 0-255."""
    h = (hex_str or "").lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6:
        return (26, 26, 36)   # default dark
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def rgb_to_hex(r: int, g: int, b: int) -> str:
    return f"#{r:02X}{g:02X}{b:02X}"


def hex_to_rgb_int(hex_str: str) -> int:
    """24-bit integer used for DXF true_color attribute."""
    r, g, b = hex_to_rgb(hex_str)
    return (r << 16) | (g << 8) | b


# ── AutoCAD Color Index (ACI) palette ────────────────────────────────────────
# Standard AutoCAD ACI has 256 indices.  We build a representative palette
# covering indices 1-255 for nearest-colour mapping.

_ACI_STANDARD: dict[int, tuple[int, int, int]] = {
    1:   (255,   0,   0),   # Red
    2:   (255, 255,   0),   # Yellow
    3:   (  0, 255,   0),   # Green
    4:   (  0, 255, 255),   # Cyan
    5:   (  0,   0, 255),   # Blue
    6:   (255,   0, 255),   # Magenta
    7:   (255, 255, 255),   # White / Black (context-dependent)
    8:   ( 65,  65,  65),   # Dark grey
    9:   (128, 128, 128),   # Grey
    250: ( 51,  51,  51),
    251: ( 80,  80,  80),
    252: (105, 105, 105),
    253: (130, 130, 130),
    254: (190, 190, 190),
    255: (255, 255, 255),
}


def _build_aci_palette() -> dict[int, tuple[int, int, int]]:
    """Build the full ACI palette including the 240-colour ramp (indices 10-249)."""
    pal: dict[int, tuple[int, int, int]] = dict(_ACI_STANDARD)
    # The ACI ramp is arranged as 24 hues × 5 brightness levels (indices 10-249).
    # Hues cycle through the 12 spectral steps, each at 2 saturations.
    hue_rgb = [
        (255,   0,   0), (255, 127,   0), (255, 255,   0), (127, 255,   0),
        (  0, 255,   0), (  0, 255, 127), (  0, 255, 255), (  0, 127, 255),
        (  0,   0, 255), (127,   0, 255), (255,   0, 255), (255,   0, 127),
        (255,  63,  63), (255, 191,  63), (255, 255,  63), (191, 255,  63),
        ( 63, 255,  63), ( 63, 255, 191), ( 63, 255, 255), ( 63, 191, 255),
        ( 63,  63, 255), (191,  63, 255), (255,  63, 255), (255,  63, 191),
    ]
    # 5 brightness levels per hue: lightest → darkest
    brightness = [(255, 255, 255), (255, 200, 200), (255, 0, 0), (180, 0, 0), (80, 0, 0)]
    for hi, (hr, hg, hb) in enumerate(hue_rgb):
        for bi in range(5):
            aci = 10 + hi * 10 + bi
            if 10 <= aci <= 249:
                # Blend hue with brightness mask
                br, bg, bb = brightness[bi]
                r = int(hr * br / 255)
                g = int(hg * bg / 255)
                b = int(hb * bb / 255)
                pal[aci] = (r, g, b)
    return pal


_FULL_ACI: dict[int, tuple[int, int, int]] = _build_aci_palette()


def hex_to_aci(hex_str: str) -> int:
    """Return the closest ACI index for the given hex colour string."""
    if not hex_str:
        return 7
    try:
        r, g, b = hex_to_rgb(hex_str)
    except Exception:
        return 7
    best_aci, best_dist = 7, float("inf")
    for aci, (ar, ag, ab) in _FULL_ACI.items():
        d = (r - ar) ** 2 + (g - ag) ** 2 + (b - ab) ** 2
        if d < best_dist:
            best_dist = d
            best_aci = aci
    return best_aci


def aci_to_hex(aci: int) -> str:
    """Convert an ACI index to a hex colour string."""
    rgb = _FULL_ACI.get(aci, (255, 255, 255))
    return rgb_to_hex(*rgb)


# ── Linetype definitions ──────────────────────────────────────────────────────

LINETYPE_LABELS: dict[str, str] = {
    "CONTINUOUS":  "Continuous ————",
    "DASHED":      "Dashed - - - -",
    "DASHED2":     "Dashed½ -- --",
    "DASHEDX2":    "Dashed×2 —  —",
    "DOTTED":      "Dotted . . . .",
    "DOTTED2":     "Dotted½ .. ..",
    "DOTTEDX2":    "Dotted×2 .  .",
    "DASHDOT":     "Dash-dot -.-.",
    "DASHDOT2":    "Dash-dot½ -.-",
    "DASHDOTX2":   "Dash-dot×2 -. .",
    "CENTER":      "Center —·—·—",
    "CENTER2":     "Center½ -·-·",
    "PHANTOM":     "Phantom —··—",
    "HIDDEN":      "Hidden — — —",
}

# SVG stroke-dasharray values (in mm user units)
LINETYPE_SVG_DASH: dict[str, str] = {
    "CONTINUOUS":  "none",
    "DASHED":      "8,4",
    "DASHED2":     "4,2",
    "DASHEDX2":    "16,8",
    "DOTTED":      "1,4",
    "DOTTED2":     "1,2",
    "DOTTEDX2":    "1,8",
    "DASHDOT":     "8,4,1,4",
    "DASHDOT2":    "4,2,1,2",
    "DASHDOTX2":   "16,8,1,8",
    "CENTER":      "16,4,1,4",
    "CENTER2":     "8,2,1,2",
    "PHANTOM":     "16,4,1,4,1,4",
    "HIDDEN":      "4,4",
}

# ezdxf linetype pattern definitions:  list of (description, pattern_length, elements)
# elements: positive = dash, negative = gap, 0 = dot
LINETYPE_DXF_PATTERNS: dict[str, tuple[str, float, list[float]]] = {
    "DASHED":     ("Dashed _ _ _ _",   0.75, [0.5, -0.25]),
    "DASHED2":    ("Dashed (½x)",       0.375, [0.25, -0.125]),
    "DASHEDX2":   ("Dashed (2x)",       1.5,  [1.0, -0.5]),
    "DOTTED":     ("Dotted . . . .",    0.25, [0.0, -0.25]),
    "DOTTED2":    ("Dotted (½x)",       0.125, [0.0, -0.125]),
    "DOTTEDX2":   ("Dotted (2x)",       0.5,  [0.0, -0.5]),
    "DASHDOT":    ("Dash dot -.-.-.-.  ", 1.4, [1.0, -0.2, 0.0, -0.2]),
    "DASHDOT2":   ("Dash dot (½x)",     0.7,  [0.5, -0.1, 0.0, -0.1]),
    "DASHDOTX2":  ("Dash dot (2x)",     2.8,  [2.0, -0.4, 0.0, -0.4]),
    "CENTER":     ("Center ____ _ ____", 2.0,  [1.25, -0.25, 0.25, -0.25]),
    "CENTER2":    ("Center (½x)",       1.0,  [0.625, -0.125, 0.125, -0.125]),
    "PHANTOM":    ("Phantom ____ _ _ __", 2.5, [1.25, -0.25, 0.25, -0.25, 0.25, -0.25]),
    "HIDDEN":     ("Hidden _ _ _ _ _",  0.75, [0.25, -0.125, 0.25, -0.125]),
}
