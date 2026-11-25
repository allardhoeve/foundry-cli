"""visualize: paint items, characters, locations and creatures with FLUX.2 klein, locally.

Each kind (visualize_kinds/<kind>.toml) has a prompt template, a size and a
moodbook: the images in moodbooks/<kind>/ go along as style references on every
`new`. Each run writes the next version under output/visualize/<kind>/<slug>/:
vN.json (the request and notes), vN-a.png, vN-b.png, ... and vN-sheet.png.
"""

import json
import os
import random
import re
import shutil
import sys
import time
import tomllib
from pathlib import Path

import click
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

HERE = Path(__file__).parent
KINDS_DIR = HERE / "visualize_kinds"
MODEL_DIR = Path.home() / ".cache" / "visualize" / "klein-4b-q8"
STEPS = 4  # the distilled model is trained for 4 steps; more does not help
IMAGE_SUFFIXES = {".png", ".webp", ".jpg", ".jpeg"}
STYLE_SENTENCE = (
    "Painted in the style of the reference images, but showing only the object described here, "
    "not the objects in the reference images."
)
# Final boost for item icons, tuned by eye in Foundry's inventory list. Stronger
# blows out white objects; cropping the margin made icons blurry, so the frame is kept.
SATURATION, CONTRAST, BRIGHTNESS = 1.2, 1.1, 1.03


# --- engine -----------------------------------------------------------------

class MfluxEngine:
    """FLUX.2 klein 4B (distilled, 8-bit) through mflux. Loads on first use."""

    def __init__(self):
        self._models = {}

    def _model(self, with_refs: bool):
        if with_refs not in self._models:
            if not sys.stdout.isatty():
                # tqdm redraws its bar with \r, which outside a terminal (Claude's task
                # view, a log) becomes a run-on line; run_generation reports per variant.
                # tqdm reads this when mflux imports it, just below.
                os.environ.setdefault("TQDM_DISABLE", "1")
            from mflux.models.common.config import ModelConfig
            from mflux.models.flux2.variants import Flux2Klein, Flux2KleinEdit

            if not MODEL_DIR.exists():
                click.echo(f"First run: downloading FLUX.2 klein 4B (~16 GB) and saving it 8-bit to {MODEL_DIR}",
                           err=True)
                Flux2Klein(quantize=8, model_config=ModelConfig.flux2_klein_4b()).save_model(str(MODEL_DIR))
            import mlx.core as mx

            # Without a cap MLX caches every freed buffer, within a denoising pass
            # too; on 16 GB that swaps (28 s -> 104 s per variant). mflux's own
            # MemorySaver uses the same 1 GB cap.
            mx.set_cache_limit(1000**3)
            cls = Flux2KleinEdit if with_refs else Flux2Klein  # the edit model needs at least one reference
            self._models = {with_refs: cls(quantize=8, model_path=str(MODEL_DIR),
                                           model_config=ModelConfig.flux2_klein_4b())}
        return self._models[with_refs]

    def generate(self, prompt, refs, seed, width, height):
        kwargs = {"image_paths": [str(r) for r in refs]} if refs else {}
        import mlx.core as mx

        result = self._model(bool(refs)).generate_image(
            seed=seed, prompt=prompt, num_inference_steps=STEPS, width=width, height=height, **kwargs)
        image = result.image.copy()
        del result
        mx.clear_cache()  # what is left of the cache after each image
        return image


# --- helpers ----------------------------------------------------------------

def load_kind(kind: str) -> dict:
    path = KINDS_DIR / f"{kind}.toml"
    if not path.exists():
        known = ", ".join(sorted(p.stem for p in KINDS_DIR.glob("*.toml")))
        raise click.UsageError(f"Unknown kind '{kind}'. Kinds: {known}")
    return tomllib.loads(path.read_text())


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def images_in(folder: Path) -> list[Path]:
    if not folder.is_dir():
        return []
    return sorted(p for p in folder.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES)


def next_version(folder: Path) -> int:
    versions = [int(m.group(1)) for p in folder.glob("v*.json") if (m := re.fullmatch(r"v(\d+)", p.stem))]
    return max(versions, default=0) + 1


def letters(n: int) -> list[str]:
    return [chr(ord("a") + i) for i in range(n)]


def contact_sheet(images: dict[str, Image.Image]) -> Image.Image:
    cols = 2 if len(images) <= 4 else 3
    rows = -(-len(images) // cols)
    w, h = next(iter(images.values())).size
    sheet = Image.new("RGB", (cols * w, rows * h), (40, 40, 40))
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default(size=max(24, w // 12))
    for i, (letter, im) in enumerate(images.items()):
        x, y = (i % cols) * w, (i // cols) * h
        sheet.paste(im, (x, y))
        draw.text((x + 12, y + 8), letter, fill="white", font=font, stroke_width=3, stroke_fill="black")
    return sheet


def run_generation(ctx, kind: str, name: str, prompt: str, refs: list[Path], variants: int,
                   seed: int | None, record: dict) -> None:
    k = load_kind(kind)
    folder = ctx.obj["root"] / "output" / "visualize" / kind / slugify(name)
    folder.mkdir(parents=True, exist_ok=True)
    v = next_version(folder)
    base = seed if seed is not None else random.randrange(2**31)
    seeds = {letter: base + i for i, letter in enumerate(letters(variants))}
    record = {"kind": kind, "name": name, **record, "prompt": prompt, "refs": [str(r) for r in refs],
              "seeds": seeds, "width": k["width"], "height": k["height"], "steps": STEPS,
              "model": "flux2-klein-4b q8", "notes": ""}
    (folder / f"v{v}.json").write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n")

    engine = ctx.obj.get("engine") or MfluxEngine()
    refs_note = f", {len(refs)} reference{'s' if len(refs) != 1 else ''}" if refs else ""
    click.echo(f"v{v}: {variants} variants of {name}{refs_note}")
    images = {}
    started = time.time()
    for i, (letter, s) in enumerate(seeds.items(), 1):
        t = time.time()
        im = engine.generate(prompt, refs, s, k["width"], k["height"])
        im.save(folder / f"v{v}-{letter}.png")
        images[letter] = im
        line = f"v{v}-{letter} done ({i}/{variants}, {time.time() - t:.0f}s)"
        if i < variants:
            line += f", about {(time.time() - started) / i * (variants - i):.0f}s left"
        click.echo(line)
    contact_sheet(images).save(folder / f"v{v}-sheet.png")
    click.echo(folder / f"v{v}-sheet.png")


def example_epilog() -> str:
    ex = load_kind("item")["example"]
    return (
        "\b\nExample. Item text:\n"
        f"  {ex['text']}\n"
        "\b\nVisible traits only, as the subject:\n"
        f"  visualize new item \"Verdigris Armor\" \\\n    --subject \"{ex['subject']}\""
    )


# --- commands ---------------------------------------------------------------

@click.group()
@click.option("--root", type=click.Path(file_okay=False, path_type=Path), default=HERE, show_default=False,
              help="Folder holding output/ and moodbooks/ (default: this repo).")
@click.pass_context
def cli(ctx, root):
    """Paint items, characters, locations and creatures locally with FLUX.2 klein.

    \b
    Workflow:
      visualize new item "Name" --subject "visible traits"   -> vN-a..d.png + vN-sheet.png
      visualize edit item "Name" --from vN-b --instruction "make the plates greener"
      visualize final item "Name" vN-b                       -> name.webp
    """
    ctx.ensure_object(dict)
    ctx.obj["root"] = root


@cli.command()
def kinds():
    """List the kinds with their size and description."""
    for path in sorted(KINDS_DIR.glob("*.toml")):
        k = tomllib.loads(path.read_text())
        click.echo(f"{path.stem:10} {k['width']}x{k['height']}  {k['description']}")


@cli.command(epilog=example_epilog())
@click.argument("kind")
@click.argument("name")
@click.option("--subject", required=True,
              help="What to paint: visible traits only (shape, material, colour, condition). "
                   "Filled into the kind's template.")
@click.option("--variants", default=4, show_default=True, help="Images to make, each with the next seed.")
@click.option("--seed", type=int, help="First seed (default: random). Keep it to compare a wording change.")
@click.option("--ref", "refs", multiple=True, type=click.Path(exists=True, dir_okay=False, path_type=Path),
              help="Extra reference image, after the moodbook. Repeatable.")
@click.option("--no-moodbook", is_flag=True, help="Leave out the kind's moodbook images.")
@click.pass_context
def new(ctx, kind, name, subject, variants, seed, refs, no_moodbook):
    """Paint a new version of NAME from its subject text.

    The kind's moodbook (moodbooks/KIND/) goes along as style references.
    About 20 s per variant without references, 35 s with two.
    """
    k = load_kind(kind)
    all_refs = ([] if no_moodbook else images_in(ctx.obj["root"] / "moodbooks" / kind)) + list(refs)
    prompt = k["template"].format(subject=subject)
    if all_refs:
        prompt += " " + STYLE_SENTENCE
    run_generation(ctx, kind, name, prompt, all_refs, variants, seed, {"subject": subject})


@cli.command()
@click.argument("kind")
@click.argument("name")
@click.option("--from", "source", required=True,
              help="Variant to start from (e.g. v2-b) or a path to any image, such as a Foundry icon.")
@click.option("--instruction", required=True,
              help="The change, as an instruction: \"Recolour the plates sage green. Keep the shape, "
                   "outline and painting style the same.\"")
@click.option("--variants", default=4, show_default=True)
@click.option("--seed", type=int)
@click.option("--ref", "refs", multiple=True, type=click.Path(exists=True, dir_okay=False, path_type=Path),
              help="Extra reference image after the source, e.g. one showing the wanted detail.")
@click.pass_context
def edit(ctx, kind, name, source, instruction, variants, seed, refs):
    """Paint a new version of NAME by changing an existing image.

    The moodbook is not used: the source image already carries the style.
    """
    load_kind(kind)
    folder = ctx.obj["root"] / "output" / "visualize" / kind / slugify(name)
    if re.fullmatch(r"v\d+-[a-z]", source):
        src = folder / f"{source}.png"
        if not src.exists():
            raise click.UsageError(f"No variant {source} for {name}: {src} does not exist.")
    else:
        src = Path(source)
        if not src.exists():
            raise click.UsageError(f"Source image not found: {source}")
    run_generation(ctx, kind, name, instruction, [src, *refs], variants, seed,
                   {"source": source, "instruction": instruction})


@cli.command()
@click.argument("kind")
@click.argument("name")
@click.argument("variant")
@click.pass_context
def final(ctx, kind, name, variant):
    """Make VARIANT (e.g. v2-b) the final image: <name>.webp next to the versions.

    Items become a 256x256 icon, brightened to match Foundry's own icons.
    """
    k = load_kind(kind)
    folder = ctx.obj["root"] / "output" / "visualize" / kind / slugify(name)
    m = re.fullmatch(r"(v\d+)-[a-z]", variant)
    src = folder / f"{variant}.png"
    if not m or not src.exists():
        raise click.UsageError(f"No variant {variant} for {name} in {folder}")
    im = Image.open(src).convert("RGB")
    if k["final"]["boost"]:
        im = ImageOps.autocontrast(im, cutoff=0.5, preserve_tone=True)
        im = ImageEnhance.Color(im).enhance(SATURATION)
        im = ImageEnhance.Contrast(im).enhance(CONTRAST)
        im = ImageEnhance.Brightness(im).enhance(BRIGHTNESS)
    if size := k["final"]["size"]:
        im = im.resize((size, size), Image.LANCZOS).filter(ImageFilter.UnsharpMask(1.2, 60, 2))
    out = folder / f"{slugify(name).replace('-', '_')}.webp"
    im.save(out, quality=90)

    record_path = folder / f"{m.group(1)}.json"
    record = json.loads(record_path.read_text())
    record["notes"] = (record["notes"] + f" Chosen as final: {variant}.").strip()
    record_path.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n")
    click.echo(out)


@cli.group()
def moodbook():
    """The style references for a kind: images in moodbooks/KIND/ (not in git)."""


@moodbook.command("list")
@click.argument("kind")
@click.pass_context
def moodbook_list(ctx, kind):
    """List the moodbook images of KIND."""
    load_kind(kind)
    for p in images_in(ctx.obj["root"] / "moodbooks" / kind):
        click.echo(p)


@moodbook.command("add")
@click.argument("kind")
@click.argument("files", nargs=-1, required=True, type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.pass_context
def moodbook_add(ctx, kind, files):
    """Copy FILES into the moodbook of KIND."""
    load_kind(kind)
    folder = ctx.obj["root"] / "moodbooks" / kind
    folder.mkdir(parents=True, exist_ok=True)
    for f in files:
        shutil.copy2(f, folder / f.name)
        click.echo(folder / f.name)


@moodbook.command("init")
@click.argument("kind")
@click.option("--foundry-data", type=click.Path(file_okay=False, path_type=Path),
              help="Foundry's public data folder (default: the Docker test instance's docker/data/public).")
@click.pass_context
def moodbook_init(ctx, kind, foundry_data):
    """Copy the kind's suggested Foundry icons into its moodbook.

    The icons are licensed Foundry art, so they are copied from a local Foundry
    install rather than kept in this repo.
    """
    suggested = load_kind(kind)["moodbook"]
    if not suggested:
        click.echo(f"No suggested icons for {kind}; add your own with `visualize moodbook add {kind} FILE...`.")
        return
    data = foundry_data or HERE / "docker" / "data" / "public"
    missing = [rel for rel in suggested if not (data / rel).exists()]
    if missing:
        raise click.ClickException("Not found under " + str(data) + ":\n  " + "\n  ".join(missing))
    folder = ctx.obj["root"] / "moodbooks" / kind
    folder.mkdir(parents=True, exist_ok=True)
    for rel in suggested:
        shutil.copy2(data / rel, folder / Path(rel).name)
        click.echo(folder / Path(rel).name)


if __name__ == "__main__":
    cli(obj={})
