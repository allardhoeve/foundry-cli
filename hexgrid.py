"""Hex-map maths: map hex numbers (CCRR) to scene pixel positions.

Pure functions, no Foundry I/O. A printed hex map numbers its hexes
column-then-row (0507 = column 05, row 07, both starting at 01). Foundry's own
grid indices start somewhere in the scene padding, so instead of reproducing
Foundry's grid placement we calibrate from two anchor hexes whose centres the
GM has lined up on the printed map.

Orientation follows Foundry's grid type:
  "rows"    -- pointy-top hexes (HEXODDR=2, HEXEVENR=3); every other ROW is
               pushed right by half a hex.
  "columns" -- flat-top hexes (HEXODDQ=4, HEXEVENQ=5); every other COLUMN is
               pushed down by half a hex.
`shifted` says which of those lines are pushed, counted in map numbering:
"even" (02, 04, ...) or "odd" (01, 03, ...).
"""

import math
import re

ROW_TYPES = (2, 3)
COLUMN_TYPES = (4, 5)

# Label anchor within a hex, as a fraction of the hex's height from its centre.
# Hex numbers sit in the top tip (NUMBER_OFFSET); "bottom" labels stay clear of
# the numbers of the hexes below.
LABEL_POSITIONS = {"top": -0.15, "center": 0.0, "bottom": 0.15}
NUMBER_OFFSET = -0.38


def orientation_for(grid_type: int) -> str:
    if grid_type in ROW_TYPES:
        return "rows"
    if grid_type in COLUMN_TYPES:
        return "columns"
    raise ValueError(f"grid type {grid_type} is not hexagonal")


def hex_dims(grid_size: float, orientation: str) -> tuple[float, float]:
    """(width, height) of one hex in pixels, as Foundry v14 draws it."""
    long = grid_size * 2 / math.sqrt(3)
    return (grid_size, long) if orientation == "rows" else (long, grid_size)


def parse_hex(s: str, size: tuple[int, int] | None = None) -> tuple[int, int]:
    """'0507' or '507' -> (5, 7). The last two digits are always the row."""
    s = s.strip()
    if not re.fullmatch(r"\d{3,4}", s):
        raise ValueError(f"'{s}' is not a hex number; use CCRR, e.g. 0507")
    col, row = int(s[:-2]), int(s[-2:])
    if col < 1 or row < 1:
        raise ValueError(f"'{s}' is not a hex number; columns and rows start at 01")
    if size is not None:
        cols, rows = size
        if col > cols or row > rows:
            raise ValueError(f"hex {fmt_hex(col, row)} is off the map, which is "
                             f"{cols} columns x {rows} rows ({fmt_hex(1, 1)}-{fmt_hex(cols, rows)})")
    return col, row


def fmt_hex(col: int, row: int) -> str:
    return f"{col:02d}{row:02d}"


def parse_size(s: str) -> tuple[int, int]:
    m = re.fullmatch(r"\s*(\d+)\s*[xX]\s*(\d+)\s*", s)
    if not m or int(m[1]) < 2 or int(m[2]) < 2:
        raise ValueError(f"'{s}' is not a map size; use COLSxROWS, e.g. 10x17")
    return int(m[1]), int(m[2])


def _shift(n: int, shifted: str) -> float:
    """Half-hex offset of map row/column n (1-based)."""
    return 0.5 if (n % 2 == 0) == (shifted == "even") else 0.0


def calibrate(a: tuple[int, int], a_pt: tuple[float, float],
              b: tuple[int, int], b_pt: tuple[float, float],
              orientation: str, shifted: str) -> dict:
    """Derive the grid from two anchor hexes and their centres in scene pixels.

    Returns {"origin": [x, y] (centre of hex 0101), "col_step", "row_step"}.
    """
    (ca, ra), (cb, rb) = a, b
    if orientation == "rows":
        dcol = (cb - ca) + _shift(rb, shifted) - _shift(ra, shifted)
        drow = rb - ra
    else:
        dcol = cb - ca
        drow = (rb - ra) + _shift(cb, shifted) - _shift(ca, shifted)
    if dcol == 0 or drow == 0:
        raise ValueError("anchors must differ in both column and row")
    col_step = (b_pt[0] - a_pt[0]) / dcol
    row_step = (b_pt[1] - a_pt[1]) / drow
    cal = {"orientation": orientation, "shifted": shifted,
           "col_step": col_step, "row_step": row_step, "origin": [0.0, 0.0]}
    ax, ay = hex_center(cal, ca, ra)
    cal["origin"] = [a_pt[0] - ax, a_pt[1] - ay]
    return cal


def hex_center(cal: dict, col: int, row: int) -> tuple[float, float]:
    ox, oy = cal["origin"]
    shifted = cal["shifted"]
    if cal["orientation"] == "rows":
        x = (col - 1 + _shift(row, shifted) - _shift(1, shifted)) * cal["col_step"]
        y = (row - 1) * cal["row_step"]
    else:
        x = (col - 1) * cal["col_step"]
        y = (row - 1 + _shift(col, shifted) - _shift(1, shifted)) * cal["row_step"]
    return ox + x, oy + y


def hex_height(cal: dict) -> float:
    """Pixel height of one hex, from the calibrated steps."""
    if cal["orientation"] == "rows":
        return cal["row_step"] / 0.75
    return cal["row_step"]


def label_point(cal: dict, col: int, row: int, pos: str) -> tuple[float, float]:
    x, y = hex_center(cal, col, row)
    return x, y + LABEL_POSITIONS[pos] * hex_height(cal)


def number_point(cal: dict, col: int, row: int) -> tuple[float, float]:
    x, y = hex_center(cal, col, row)
    return x, y + NUMBER_OFFSET * hex_height(cal)


def expected_steps(grid_size: float, orientation: str) -> tuple[float, float]:
    """(col_step, row_step) Foundry's grid implies, for sanity-checking a calibration."""
    w, h = hex_dims(grid_size, orientation)
    return (w, 0.75 * h) if orientation == "rows" else (0.75 * w, h)


def hexagon_points(width: float, height: float, orientation: str) -> list[float]:
    """Flat [x0, y0, x1, y1, ...] outline of one hex inside a width x height box."""
    w, h = width, height
    if orientation == "rows":   # pointy top
        pts = [(w / 2, 0), (w, h / 4), (w, 3 * h / 4), (w / 2, h), (0, 3 * h / 4), (0, h / 4)]
    else:                       # flat top
        pts = [(w / 4, 0), (3 * w / 4, 0), (w, h / 2), (3 * w / 4, h), (w / 4, h), (0, h / 2)]
    pts.append(pts[0])
    return [round(v, 2) for p in pts for v in p]


def scene_rect(width: int, height: int, padding: float, grid_size: float,
               orientation: str) -> tuple[float, float, float, float]:
    """(x, y, w, h) of the scene image inside the padded canvas, per Foundry v14
    HexagonalGrid.calculateDimensions. Only used to place anchors near their
    hexes before the GM drags them; calibration doesn't depend on it."""
    if not padding:
        return 0.0, 0.0, float(width), float(height)
    columns = orientation == "columns"
    size_x, size_y = hex_dims(grid_size, orientation)
    stride_x = 0.75 * size_x if columns else size_x
    stride_y = size_y if columns else 0.75 * size_y
    x = math.ceil((padding * width) * (1 / stride_x)) * stride_x
    y = math.ceil((padding * height) * (1 / stride_y)) * stride_y
    if round(x / stride_x if columns else y / stride_y) % 2 != 0:
        if columns:
            y += size_y / 2
        else:
            x += size_x / 2
    return x, y, float(width), float(height)
