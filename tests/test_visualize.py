"""visualize CLI: files, prompts and references, with a fake engine instead of the model."""

import json
import tomllib
from pathlib import Path

import pytest
from click.testing import CliRunner
from PIL import Image

import visualize


class FakeEngine:
    def __init__(self):
        self.calls = []

    def generate(self, prompt, refs, seed, width, height):
        self.calls.append({"prompt": prompt, "refs": list(refs), "seed": seed, "size": (width, height)})
        return Image.new("RGB", (width, height), (seed % 256, 80, 80))


@pytest.fixture
def run(tmp_path):
    engine = FakeEngine()

    def _run(*args, ok=True):
        result = CliRunner().invoke(visualize.cli, ["--root", str(tmp_path), *args], obj={"engine": engine})
        if ok:
            assert result.exit_code == 0, result.output
        return result

    _run.engine = engine
    _run.root = tmp_path
    return _run


def subject_dir(root, kind="item", slug="verdigris-armor"):
    return root / "output" / "visualize" / kind / slug


def test_every_kind_has_a_template_with_a_subject_slot_and_an_example():
    kinds = sorted(p.stem for p in visualize.KINDS_DIR.glob("*.toml"))
    assert kinds == ["character", "creature", "item", "location"]
    for kind in kinds:
        k = tomllib.loads((visualize.KINDS_DIR / f"{kind}.toml").read_text())
        assert "{subject}" in k["template"]
        assert k["example"]["subject"]


def test_new_writes_variants_sheet_and_record(run):
    run("new", "item", "Verdigris Armor", "--subject", "a green breastplate", "--seed", "7")
    d = subject_dir(run.root)
    assert sorted(p.name for p in d.iterdir()) == [
        "v1-a.png", "v1-b.png", "v1-c.png", "v1-d.png", "v1-sheet.png", "v1.json"]
    record = json.loads((d / "v1.json").read_text())
    assert record["name"] == "Verdigris Armor"
    assert record["subject"] == "a green breastplate"
    assert record["seeds"] == {"a": 7, "b": 8, "c": 9, "d": 10}
    assert "a green breastplate" in record["prompt"]
    assert "hand-painted fantasy game item icon" in record["prompt"]
    assert record["notes"] == ""
    assert [c["seed"] for c in run.engine.calls] == [7, 8, 9, 10]
    assert run.engine.calls[0]["size"] == (512, 512)


def test_new_reports_one_line_per_variant(run):
    out = run("new", "item", "Verdigris Armor", "--subject", "x", "--variants", "2").output.splitlines()
    assert out[0].startswith("v1: 2 variants of Verdigris Armor")
    assert out[1].startswith("v1-a done (1/2,") and "left" in out[1]
    assert out[2].startswith("v1-b done (2/2,") and "left" not in out[2]
    assert out[3].endswith("v1-sheet.png")


def test_new_uses_kind_size(run):
    run("new", "location", "Wormden Keep", "--subject", "a tower", "--variants", "1")
    assert run.engine.calls[0]["size"] == (1024, 640)


def test_second_run_is_the_next_version(run):
    run("new", "item", "Verdigris Armor", "--subject", "x", "--variants", "1")
    run("new", "item", "Verdigris Armor", "--subject", "y", "--variants", "2")
    d = subject_dir(run.root)
    assert (d / "v2.json").exists() and (d / "v2-b.png").exists()
    assert not (d / "v2-c.png").exists()


def test_moodbook_images_are_sent_as_references(run):
    mood = run.root / "moodbooks" / "item"
    mood.mkdir(parents=True)
    for name in ["b.png", "a.webp"]:
        Image.new("RGB", (8, 8)).save(mood / name)
    (mood / "notes.txt").write_text("not an image")
    extra = run.root / "extra.png"
    Image.new("RGB", (8, 8)).save(extra)

    run("new", "item", "Verdigris Armor", "--subject", "x", "--variants", "1", "--ref", str(extra))
    refs = run.engine.calls[0]["refs"]
    assert refs == [mood / "a.webp", mood / "b.png", extra]
    record = json.loads((subject_dir(run.root) / "v1.json").read_text())
    assert record["refs"] == [str(mood / "a.webp"), str(mood / "b.png"), str(extra)]
    assert "style of the reference images" in record["prompt"]


def test_no_moodbook_means_no_references_and_no_style_sentence(run):
    mood = run.root / "moodbooks" / "item"
    mood.mkdir(parents=True)
    Image.new("RGB", (8, 8)).save(mood / "a.png")
    run("new", "item", "Verdigris Armor", "--subject", "x", "--variants", "1", "--no-moodbook")
    assert run.engine.calls[0]["refs"] == []
    assert "reference images" not in run.engine.calls[0]["prompt"]


def test_edit_starts_from_a_variant(run):
    run("new", "item", "Verdigris Armor", "--subject", "x", "--variants", "2")
    run("edit", "item", "Verdigris Armor", "--from", "v1-b", "--instruction", "make the plates greener",
        "--variants", "1")
    d = subject_dir(run.root)
    call = run.engine.calls[-1]
    assert call["refs"] == [d / "v1-b.png"]
    assert call["prompt"] == "make the plates greener"
    record = json.loads((d / "v2.json").read_text())
    assert record["source"] == "v1-b"
    assert record["instruction"] == "make the plates greener"


def test_edit_starts_from_a_file(run):
    src = run.root / "shadowdark-plate.png"
    Image.new("RGB", (8, 8)).save(src)
    run("edit", "item", "Verdigris Armor", "--from", str(src), "--instruction", "recolour", "--variants", "1")
    assert run.engine.calls[-1]["refs"] == [src]
    assert json.loads((subject_dir(run.root) / "v1.json").read_text())["source"] == str(src)


def test_edit_from_unknown_variant_fails_clearly(run):
    result = run("edit", "item", "Verdigris Armor", "--from", "v3-a", "--instruction", "x", ok=False)
    assert result.exit_code != 0
    assert "v3-a" in result.output


def test_unknown_kind_lists_the_kinds(run):
    result = run("new", "spaceship", "X", "--subject", "x", ok=False)
    assert result.exit_code != 0
    assert "item" in result.output and "creature" in result.output


def test_final_item_is_a_boosted_256_webp_named_after_the_item(run):
    run("new", "item", "Verdigris Armor", "--subject", "x", "--variants", "2")
    run("final", "item", "Verdigris Armor", "v1-b")
    d = subject_dir(run.root)
    out = d / "verdigris_armor.webp"
    assert Image.open(out).size == (256, 256)
    assert "Chosen as final: v1-b" in json.loads((d / "v1.json").read_text())["notes"]


def test_final_location_keeps_its_size(run):
    run("new", "location", "Wormden Keep", "--subject", "x", "--variants", "1")
    run("final", "location", "Wormden Keep", "v1-a")
    assert Image.open(subject_dir(run.root, "location", "wormden-keep") / "wormden_keep.webp").size == (1024, 640)


def test_moodbook_init_copies_suggested_foundry_icons(run):
    data = run.root / "foundry-data"
    for rel in tomllib.loads((visualize.KINDS_DIR / "item.toml").read_text())["moodbook"]:
        (data / rel).parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (8, 8)).save(data / rel, "WEBP")
    run("moodbook", "init", "item", "--foundry-data", str(data))
    assert sorted(p.name for p in (run.root / "moodbooks" / "item").iterdir()) == [
        "breastplate-layered-steel.webp", "sword-gold-holy.webp"]


def test_moodbook_init_reports_missing_icons(run):
    result = run("moodbook", "init", "item", "--foundry-data", str(run.root / "nowhere"), ok=False)
    assert result.exit_code != 0
    assert "breastplate-layered-steel.webp" in result.output


def test_moodbook_add_and_list(run):
    src = run.root / "Shadowdark Plate.png"
    Image.new("RGB", (8, 8)).save(src)
    run("moodbook", "add", "item", str(src))
    assert (run.root / "moodbooks" / "item" / "Shadowdark Plate.png").exists()
    assert "Shadowdark Plate.png" in run("moodbook", "list", "item").output


def test_kinds_lists_descriptions(run):
    out = run("kinds").output
    assert "item" in out and "Inventory icon" in out


def test_help_shows_a_worked_example():
    out = CliRunner().invoke(visualize.cli, ["new", "--help"]).output
    assert "Verdigris Armor" in out and "--subject" in out
