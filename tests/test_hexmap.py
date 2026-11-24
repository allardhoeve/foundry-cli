"""hexmap commands against the Docker test instance, on a throwaway hex scene."""

import uuid

import click
import pytest

import hexgrid as hg
import hexstyle


@pytest.fixture
def scene(client):
    """A Landel-like hex scene: pointy-top (HEXODDR), size 217, 25% padding."""
    name = f"_pytest_hex_{uuid.uuid4().hex[:8]}"
    r = client._emit({"type": "Scene", "action": "create", "operation": {"data": [{
        "name": name, "width": 2583, "height": 3632, "padding": 0.25,
        "grid": {"type": 2, "size": 217},
    }]}})
    scene_id = r["result"][0]["_id"]
    yield name
    client._emit({"type": "Scene", "action": "delete", "operation": {"ids": [scene_id]}})


def _drag_anchors(client, scene_name, true_cal, size=(10, 17)):
    """Simulate the GM dragging each anchor onto its true hex centre."""
    s = client._find_scene(scene_name)
    updates = []
    for d in client._hexmap_drawings(s, "anchor"):
        c, r = hg.parse_hex(d["flags"]["world"]["hexmap"]["hex"])
        x, y = hg.hex_center(true_cal, c, r)
        updates.append({"_id": d["_id"],
                        "x": round(x - d["shape"]["width"] / 2),
                        "y": round(y - d["shape"]["height"] / 2)})
    client._scene_emit(s, "update", {"updates": updates})


TRUE = {"orientation": "rows", "shifted": "even", "col_step": 217.0,
        "row_step": 0.75 * 217 * 2 / 3 ** 0.5, "origin": [1000.0, 1200.0]}


def _setup(client, scene):
    client.hexmap_init(scene, (10, 17), "even")
    _drag_anchors(client, scene, TRUE)
    return client.hexmap_calibrate(scene)


def test_scene_not_found(client):
    with pytest.raises(click.ClickException, match="not found"):
        client.hexmap_list("_pytest_no_such_scene")


def test_init_places_two_hidden_anchor_hexagons(client, scene):
    anchors = client.hexmap_init(scene, (10, 17), "even")
    assert sorted(d["flags"]["world"]["hexmap"]["hex"] for d in anchors) == ["0101", "1017"]
    for d in anchors:
        assert d["hidden"] is True
        assert d["shape"]["type"] == "p"
        assert d["shape"]["width"] == 217


def test_init_keeps_dragged_anchors(client, scene):
    client.hexmap_init(scene, (10, 17), "even")
    _drag_anchors(client, scene, TRUE)
    before = {d["_id"]: (d["x"], d["y"])
              for d in client._hexmap_drawings(client._find_scene(scene), "anchor")}
    client.hexmap_init(scene, (10, 17), "even")
    after = {d["_id"]: (d["x"], d["y"])
             for d in client._hexmap_drawings(client._find_scene(scene), "anchor")}
    assert before == after


def test_label_requires_calibration(client, scene):
    client.hexmap_init(scene, (10, 17), "even")
    with pytest.raises(click.ClickException, match="calibrate"):
        client.hexmap_label(scene, "0507", "Wormden Keep", None, None)


def test_calibrate_recovers_grid(client, scene):
    r = _setup(client, scene)
    cal = r["calibration"]
    assert cal["col_step"] == pytest.approx(217, abs=0.2)
    assert cal["row_step"] == pytest.approx(TRUE["row_step"], abs=0.2)
    assert r["warnings"] == []


def test_calibrate_warns_on_wrong_hex(client, scene):
    client.hexmap_init(scene, (10, 17), "even")
    wrong = dict(TRUE, col_step=180.0)   # anchors one hex short of where they belong
    _drag_anchors(client, scene, wrong)
    assert client.hexmap_calibrate(scene)["warnings"]


def test_label_lifecycle(client, scene):
    _setup(client, scene)
    d = client.hexmap_label(scene, "507", "Wormden Keep", None, None)
    assert d["_created"] and d["hidden"] is True and d["_hex"] == "0507"

    # Box visibly centred on the label point of 0507, in the label style.
    x, y = hg.label_point(TRUE, 5, 7, "bottom")
    assert hexstyle.box_centre(d) == pytest.approx((x, y), abs=1)
    assert d["fontFamily"] == "JSL Blackletter"

    client.hexmap_label(scene, "0507", None, True, None)
    assert client.hexmap_list(scene) == [
        {"hex": "0507", "text": "Wormden Keep", "hidden": False, "_id": d["_id"]}]

    # New text keeps visibility and doesn't create a second label.
    client.hexmap_label(scene, "0507", "Wormden (ruined)", None, None)
    [l] = client.hexmap_list(scene)
    assert (l["text"], l["hidden"]) == ("Wormden (ruined)", False)

    assert client.hexmap_unlabel(scene, "0507") is True
    assert client.hexmap_list(scene) == []
    assert client.hexmap_unlabel(scene, "0507") is False


def test_label_keeps_manual_position(client, scene):
    _setup(client, scene)
    d = client.hexmap_label(scene, "0507", "Wormden Keep", None, None)
    s = client._find_scene(scene)
    client._scene_emit(s, "update", {"updates": [{"_id": d["_id"], "x": 5, "y": 6}]})
    dragged = hexstyle.box_centre(d | {"x": 5, "y": 6})
    client.hexmap_label(scene, "0507", "Wormden", None, None)
    [moved] = client._hexmap_drawings(client._find_scene(scene), "label")
    # New text, narrower box, same visible centre as where it was dragged.
    assert moved["shape"]["width"] < d["shape"]["width"]
    assert hexstyle.box_centre(moved) == pytest.approx(dragged, abs=1)


def test_label_off_map(client, scene):
    _setup(client, scene)
    with pytest.raises(click.ClickException, match="off the map"):
        client.hexmap_label(scene, "1101", "Nowhere", None, None)


def test_numbers_and_remove_leave_labels_alone(client, scene):
    _setup(client, scene)
    client.hexmap_label(scene, "0507", "Wormden Keep", None, None)
    assert client.hexmap_numbers(scene) == 170
    assert client.hexmap_numbers(scene) == 170   # re-run replaces, doesn't double
    s = client._find_scene(scene)
    numbers = client._hexmap_drawings(s, "number")
    assert len(numbers) == 170
    assert not any(n["hidden"] for n in numbers)   # numbers aren't secret
    client.hexmap_numbers(scene, remove=True)
    s = client._find_scene(scene)
    assert client._hexmap_drawings(s, "number") == []
    assert len(client.hexmap_list(scene)) == 1

