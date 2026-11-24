"""Pure hex-map maths; no Foundry needed."""

import pytest

import hexgrid as hg


def test_parse_hex():
    assert hg.parse_hex("0507") == (5, 7)
    assert hg.parse_hex("507") == (5, 7)
    assert hg.parse_hex("1017", (10, 17)) == (10, 17)


@pytest.mark.parametrize("bad", ["57", "05a7", "0007", "0500", "12345"])
def test_parse_hex_rejects(bad):
    with pytest.raises(ValueError):
        hg.parse_hex(bad)


def test_parse_hex_off_map():
    with pytest.raises(ValueError, match="10 columns x 17 rows"):
        hg.parse_hex("1101", (10, 17))


def test_parse_size():
    assert hg.parse_size("10x17") == (10, 17)
    with pytest.raises(ValueError):
        hg.parse_size("10")


def _landel():
    # Pointy-top, even rows pushed right, 200px columns, 173px rows.
    a, b = (100.0, 100.0), (100.0 + 9 * 200, 100.0 + 16 * 173)
    return hg.calibrate((1, 1), a, (10, 17), b, "rows", "even")


def test_calibrate_rows_recovers_steps():
    cal = _landel()
    assert cal["col_step"] == pytest.approx(200)
    assert cal["row_step"] == pytest.approx(173)
    assert hg.hex_center(cal, 1, 1) == pytest.approx((100, 100))
    assert hg.hex_center(cal, 10, 17) == pytest.approx((1900, 100 + 16 * 173))


def test_even_rows_are_shifted():
    cal = _landel()
    assert hg.hex_center(cal, 1, 2) == pytest.approx((200, 273))   # half a hex right
    assert hg.hex_center(cal, 5, 7) == pytest.approx((900, 100 + 6 * 173))


def test_odd_shift_and_anchor_in_shifted_row():
    # Odd rows pushed right; second anchor in a shifted row.
    true = {"orientation": "rows", "shifted": "odd", "col_step": 200.0,
            "row_step": 173.0, "origin": [100.0, 100.0]}
    a, b = hg.hex_center(true, 1, 1), hg.hex_center(true, 8, 16)
    cal = hg.calibrate((1, 1), a, (8, 16), b, "rows", "odd")
    assert hg.hex_center(cal, 3, 5) == pytest.approx(hg.hex_center(true, 3, 5))
    assert hg.hex_center(cal, 3, 6)[0] - hg.hex_center(cal, 3, 5)[0] == pytest.approx(-100)


def test_columns_orientation():
    true = {"orientation": "columns", "shifted": "even", "col_step": 150.0,
            "row_step": 173.0, "origin": [50.0, 60.0]}
    a, b = hg.hex_center(true, 1, 1), hg.hex_center(true, 12, 9)
    cal = hg.calibrate((1, 1), a, (12, 9), b, "columns", "even")
    assert cal["col_step"] == pytest.approx(150)
    assert hg.hex_center(cal, 2, 1) == pytest.approx((200, 60 + 86.5))


def test_label_point_below_centre():
    cal = _landel()
    x, y = hg.label_point(cal, 1, 1, "bottom")
    assert x == pytest.approx(100)
    assert y == pytest.approx(100 + 0.15 * 173 / 0.75)


def test_expected_steps_match_foundry_hex_sizes():
    col, row = hg.expected_steps(217, "rows")
    assert col == pytest.approx(217)
    assert row == pytest.approx(217 * 0.866, rel=1e-3)


def test_scene_rect_matches_foundry():
    # Landel: 2583x3632, padding 0.25, size 217, rows -- values from Foundry v14's
    # HexagonalGrid.calculateDimensions (x, y of the scene rectangle).
    x, y, w, h = hg.scene_rect(2583, 3632, 0.25, 217, "rows")
    stride_y = 0.75 * 217 * 2 / 3 ** 0.5
    assert x == pytest.approx(651 + 217 / 2)   # 3 strides, +half (odd row count)
    assert y == pytest.approx(5 * stride_y)
    assert (w, h) == (2583, 3632)


def test_numbers_sit_above_labels_of_the_row_above():
    # A "bottom" label must not reach the number tag of the hexes below it.
    cal = _landel()
    h = hg.hex_height(cal)
    label_bottom = hg.label_point(cal, 5, 7, "bottom")[1] + 0.13 * h   # ~half a label box
    number_top = hg.number_point(cal, 5, 8)[1] - 0.07 * h              # ~half a number tag
    assert label_bottom < number_top
