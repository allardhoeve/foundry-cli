import click
import pytest

# "Occupies One Hand" property, shipped with the Shadowdark system.
PROPERTY_UUID = "Compendium.shadowdark.properties.Item.jq0m0lGb7QOCSJXL"


def test_get(client):
    doc = client.compendium_get(PROPERTY_UUID)
    assert doc["_id"] == "jq0m0lGb7QOCSJXL"
    assert doc["name"] == "Occupies One Hand"
    assert doc["type"] == "Property"


def test_get_includes_embedded_effects(client):
    doc = client.compendium_get("Compendium.shadowdark.spell-effects.Item.h9MTxzrrPmyhEmRL")
    assert doc["name"] == "Spell Effect: Mage Armor"
    changes = doc["effects"][0]["system"]["changes"]
    assert changes[0]["key"] == "system.attributes.ac.value"


def test_get_unknown_pack(client):
    with pytest.raises(click.ClickException, match="Compendium pack 'shadowdark.nope' not found"):
        client.compendium_get("Compendium.shadowdark.nope.Item.jq0m0lGb7QOCSJXL")


def test_get_unknown_id(client):
    with pytest.raises(click.ClickException, match="'doesnotexist0000' not found in compendium 'shadowdark.properties'"):
        client.compendium_get("Compendium.shadowdark.properties.Item.doesnotexist0000")


@pytest.mark.parametrize("uuid", [
    "Item.jq0m0lGb7QOCSJXL",
    "Compendium.shadowdark.properties.Item",
    "Compendium.shadowdark.properties.Item.abc.ActiveEffect.def",
])
def test_get_rejects_non_compendium_uuid(client, uuid):
    with pytest.raises(click.ClickException, match="Not a compendium UUID"):
        client.compendium_get(uuid)
