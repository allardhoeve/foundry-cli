"""Generate one icon version through the Draw Things HTTP API.

    uv run --with pillow python .claude/skills/foundry-icon/generate.py output/icons/<slug>/vN.json

Reads the generation settings from vN.json and writes vN.png (as generated)
and vN.webp (256x256, the size of Foundry's own icons) next to it.
"""

import base64
import io
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from PIL import Image

API = "http://127.0.0.1:7860"
# Keys in vN.json that are sent to Draw Things; the rest (item, notes, moodboard) is bookkeeping.
API_KEYS = {
    "prompt", "negative_prompt", "model", "loras", "width", "height",
    "steps", "guidance_scale", "seed", "sampler", "seed_mode",
}
ICON_SIZE = 256


def main(spec_path: str) -> None:
    spec_file = Path(spec_path)
    spec = json.loads(spec_file.read_text())
    request = {k: v for k, v in spec.items() if k in API_KEYS}

    try:
        urllib.request.urlopen(API, timeout=5)
    except (urllib.error.URLError, TimeoutError):
        sys.exit(f"Draw Things API not reachable at {API}: enable the API server in Draw Things settings.")

    started = time.time()
    response = urllib.request.urlopen(
        urllib.request.Request(
            f"{API}/sdapi/v1/txt2img",
            data=json.dumps(request).encode(),
            headers={"Content-Type": "application/json"},
        ),
        timeout=1800,
    )
    png = base64.b64decode(json.load(response)["images"][0])

    png_path = spec_file.with_suffix(".png")
    webp_path = spec_file.with_suffix(".webp")
    png_path.write_bytes(png)
    Image.open(io.BytesIO(png)).convert("RGB").resize(
        (ICON_SIZE, ICON_SIZE), Image.LANCZOS
    ).save(webp_path, quality=90)
    print(f"{png_path} and {webp_path} in {time.time() - started:.0f}s")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
