"""Label box geometry; uses the Shadowdark fonts from the submodule, no Foundry."""

import pytest

import hexstyle as hs

LABEL = hs.LABEL_STYLE
NUMBER = hs.NUMBER_STYLE


def test_width_matches_foundry_measurement():
    # Foundry v14 (PIXI.TextMetrics) measured these at 100px.
    assert hs.text_width("Castle Landel", "JSL Blackletter", 100) == pytest.approx(498, rel=0.04)
    assert hs.text_width("The Sunken Abbey of Ravens", "JSL Blackletter", 100) \
        == pytest.approx(1047, rel=0.04)
    # Never narrower than Foundry's own measurement, or the text would wrap.
    assert hs.text_width("Wormden Keep", "JSL Blackletter", 100) >= 552


def test_box_is_visibly_centred_on_point():
    d = hs.boxed_text("Wormden Keep", 1000, 2000, LABEL)
    assert hs.box_centre(d) == pytest.approx((1000, 2000), abs=1)


def test_blackletter_box_sits_above_text_centre():
    # Foundry centres text in the bounding box; the visible fill is shifted up.
    d = hs.boxed_text("Wormden", 0, 0, LABEL)
    text_centre_y = d["y"] + d["shape"]["height"] / 2
    assert hs.box_centre(d)[1] < text_centre_y


def test_montserrat_box_sits_below_text_centre():
    d = hs.boxed_text("0816", 0, 0, NUMBER)
    assert hs.box_centre(d)[1] > d["y"] + d["shape"]["height"] / 2


def test_longer_text_wider_box():
    a = hs.boxed_text("Mill", 0, 0, LABEL)
    b = hs.boxed_text("The Sunken Abbey of Ravens", 0, 0, LABEL)
    assert b["shape"]["width"] > 3 * a["shape"]["width"]

