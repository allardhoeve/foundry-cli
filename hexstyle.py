"""Label and hex-number styles for hexmap Drawings.

Foundry draws a Drawing's text centred in its shape's bounding box, but never
sizes the box: width and height are stored on the document, and text that
doesn't fit wraps onto a second line. So the CLI measures the text itself,
with the same font files the Shadowdark system ships (a git submodule).
Pillow's measurement agrees with Foundry's own within ~1%.
"""

from functools import cache
from pathlib import Path

from PIL import ImageFont

_FONTS = Path(__file__).parent / "third_party" / "foundryvtt-shadowdark" / "system" / "fonts"

# Font family (as Foundry knows it) -> file to measure with. Both ship with
# the Shadowdark system.
FONT_FILES = {
    "JSL Blackletter": _FONTS / "JBLACK.TTF",
    "Montserrat-Bold": _FONTS / "Montserrat-Bold.ttf",
}

# Foundry centres the whole text line (ascent + descent) in the box. Visually
# the letters sit off-centre: blackletter reads ~12% of the font size high,
# Montserrat ~5% low. The visible box is shifted by this fraction of the size.
OPTICAL_OFFSET = {"JSL Blackletter": 0.12, "Montserrat-Bold": -0.05}

# Big and near-solid on purpose, so labels read when zoomed out; the companion
# module lets each user switch them off.
LABEL_STYLE = {"fontFamily": "JSL Blackletter", "fontSize": 58, "textColor": "#ffffff",
               "fill": "#000000", "fillAlpha": 0.9, "padX": 0.45, "padY": 0.12}

NUMBER_STYLE = {"fontFamily": "Montserrat-Bold", "fontSize": 26, "textColor": "#ffffff",
                "fill": "#000000", "fillAlpha": 0.85, "padX": 0.35, "padY": 0.15}


_SLACK = 1.03   # a hair wider than measured, so Foundry never wraps a label


@cache
def _font(family: str, size: int) -> ImageFont.FreeTypeFont:
    path = FONT_FILES[family]
    if not path.exists():
        raise FileNotFoundError(
            f"Font {path} is missing. Fetch the Shadowdark submodule:\n"
            "  git submodule update --init third_party/foundryvtt-shadowdark")
    return ImageFont.truetype(str(path), size)


def text_width(text: str, family: str, size: int) -> float:
    return _font(family, size).getlength(text) * _SLACK


def boxed_text(text: str, cx: float, cy: float, style: dict) -> dict:
    """Drawing fields for `text` in a filled box whose visible centre is (cx, cy).

    The shape is a polygon inside a taller bounding box: Foundry centres the
    text in the bounding box, and the filled rectangle sits OPTICAL_OFFSET
    higher (or lower) so it centres on the letters instead.
    """
    size = style["fontSize"]
    pad_x, pad_y = round(size * style["padX"]), round(size * style["padY"])
    w = round(text_width(text, style["fontFamily"], size) + 2 * pad_x)
    hb = round(size * 0.9 + 2 * pad_y)
    d = round(OPTICAL_OFFSET.get(style["fontFamily"], 0) * size)
    top = 0 if d >= 0 else -2 * d
    return {
        "x": round(cx - w / 2), "y": round(cy - (top + hb / 2)),
        "shape": {"type": "p", "width": w, "height": hb + 2 * abs(d),
                  "points": [0, top, w, top, w, top + hb, 0, top + hb, 0, top]},
        "bezierFactor": 0,
        "fillType": 1, "fillColor": style["fill"], "fillAlpha": style["fillAlpha"],
        "strokeWidth": 0, "strokeAlpha": 0,
        "text": text, "fontFamily": style["fontFamily"], "fontSize": size,
        "textColor": style["textColor"], "textAlpha": 1,
    }


def box_centre(drawing: dict) -> tuple[float, float]:
    """Visible centre of a drawing made by boxed_text (its x/y inverse)."""
    shape = drawing["shape"]
    ys = (shape.get("points") or [])[1::2]
    mid_y = (min(ys) + max(ys)) / 2 if ys else shape["height"] / 2
    return drawing["x"] + shape["width"] / 2, drawing["y"] + mid_y
