"""Turn a chosen version into the final Foundry icon.

    uv run --with pillow python .claude/skills/foundry-icon/finalise.py output/icons/<slug>/vN.png <item_name>.webp

Generated images come out muted next to Foundry's own icons, so this stretches
contrast (keeping hues), boosts saturation, contrast and brightness, sharpens
for display at inventory size, and saves a 256x256 webp next to the source.
"""

import sys
from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter, ImageOps

# Tuned by eye in Foundry's inventory list. Stronger blows out white objects;
# cropping the margin made icons look blurry and cut off, so the frame is kept.
SATURATION, CONTRAST, BRIGHTNESS = 1.2, 1.1, 1.03
ICON_SIZE = 256


def finalise(src: Path, name: str) -> Path:
    im = Image.open(src).convert("RGB")
    im = ImageOps.autocontrast(im, cutoff=0.5, preserve_tone=True)
    im = ImageEnhance.Color(im).enhance(SATURATION)
    im = ImageEnhance.Contrast(im).enhance(CONTRAST)
    im = ImageEnhance.Brightness(im).enhance(BRIGHTNESS)
    im = im.resize((ICON_SIZE, ICON_SIZE), Image.LANCZOS).filter(ImageFilter.UnsharpMask(1.2, 60, 2))
    out = src.with_name(name)
    im.save(out, quality=90)
    return out


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    print(finalise(Path(sys.argv[1]), sys.argv[2]))
