import click
import pytest


def test_upsert_creates(client, journal):
    r = client.category_upsert(journal, "NPCs")
    assert r["name"] == "NPCs"
    assert "_id" in r


def test_upsert_idempotent(client, journal):
    r1 = client.category_upsert(journal, "Settlements")
    r2 = client.category_upsert(journal, "Settlements")
    assert r1["_id"] == r2["_id"]
    dupes = [c for c in client.category_list(journal) if c["name"] == "Settlements"]
    assert len(dupes) == 1


def test_list(client, journal):
    client.category_upsert(journal, "Factions")
    names = [c["name"] for c in client.category_list(journal)]
    assert "Factions" in names


def test_delete(client, journal):
    client.category_upsert(journal, "ToDelete")
    assert client.category_delete(journal, "ToDelete") is True
    assert not any(c["name"] == "ToDelete" for c in client.category_list(journal))


def test_delete_not_found(client, journal):
    assert client.category_delete(journal, "_nonexistent") is False


def test_journal_not_found(client):
    with pytest.raises(click.ClickException, match="not found"):
        client.category_list("_pytest_no_such_journal")
