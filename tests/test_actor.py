import click
import pytest

from foundry import _ability_mod, _attack_inputs


def _change(key, value, type_="add"):
    return {"key": key, "value": value, "type": type_, "phase": "initial", "priority": None}


ACTOR = {
    "name": "Charlock",
    "type": "Player",
    "system": {
        "level": {"value": 2},
        "abilities": {"str": {"value": 15}, "dex": {"value": 13}, "cha": {"value": 4}},
    },
    "effects": [
        {"name": "Rat disease", "disabled": True,
         "system": {"changes": [_change("system.abilities.str.value", 1, "subtract")]}},
    ],
    "items": [
        {"name": "Longsword", "type": "Weapon", "effects": [],
         "system": {"equipped": True, "bonuses": {"attackBonus": 1, "damageBonus": 0}}},
        {"name": "Mighty", "type": "Talent", "effects": [
            {"name": "Mighty", "system": {"changes": [
                _change("system.roll.melee.bonus.all", 1),
                _change("system.roll.melee.damage.all", 1),
                _change("system.slots", 2),
            ]}},
        ], "system": {}},
        {"name": "Old", "type": "Talent", "effects": [
            {"name": "Legacy", "changes": [{"key": "system.roll.ranged.bonus.all", "value": 1, "mode": 2}]},
        ], "system": {}},
    ],
}


def test_ability_mod_clamped():
    assert _ability_mod(15) == 2
    assert _ability_mod(9) == -1
    assert _ability_mod(3) == -4
    assert _ability_mod(20) == 4


def test_abilities_and_level():
    r = _attack_inputs(ACTOR)
    assert r["level"] == 2
    assert r["abilities"]["str"] == {"value": 15, "mod": 2}
    assert r["abilities"]["cha"] == {"value": 4, "mod": -3}


def test_weapon_attack_bonuses_only_nonzero():
    w = _attack_inputs(ACTOR)["weapons"]
    assert w == [{"name": "Longsword", "equipped": True, "bonuses": {"attackBonus": 1}}]


def test_effects_filtered_with_source():
    effects = _attack_inputs(ACTOR)["effects"]
    keys = [e["key"] for e in effects]
    assert "system.slots" not in keys
    mighty = [e for e in effects if e["source"] == "Mighty"]
    assert [e["key"] for e in mighty] == ["system.roll.melee.bonus.all", "system.roll.melee.damage.all"]
    assert mighty[0]["sourceType"] == "Talent"


def test_actor_level_effect_disabled():
    e = next(e for e in _attack_inputs(ACTOR)["effects"] if e["effect"] == "Rat disease")
    assert e["sourceType"] == "Actor"
    assert e["type"] == "subtract"
    assert e["disabled"] is True


def test_legacy_changes_layout():
    e = next(e for e in _attack_inputs(ACTOR)["effects"] if e["effect"] == "Legacy")
    assert e["key"] == "system.roll.ranged.bonus.all"
    assert e["type"] == 2


def test_show_not_found(client):
    with pytest.raises(click.ClickException, match="Actor 'No Such Actor' not found"):
        client.actor_show("No Such Actor")
