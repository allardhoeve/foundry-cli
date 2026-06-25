import uuid
import pytest


def test_upsert_creates(client, journal):
    names = [e["name"] for e in client.get_journals()]
    assert journal in names


def test_upsert_idempotent(client, journal):
    r1 = client.journal_upsert(journal, folder=None, public=False)
    r2 = client.journal_upsert(journal, folder=None, public=False)
    assert r1["_id"] == r2["_id"]
    dupes = [e for e in client.get_journals() if e["name"] == journal]
    assert len(dupes) == 1


def test_upsert_public(client, journal):
    r = client.journal_upsert(journal, folder=None, public=True)
    assert r["ownership"]["default"] == 2  # OBSERVER


def test_upsert_private(client, journal):
    r = client.journal_upsert(journal, folder=None, public=False)
    # Foundry omits ownership when it's the default (NONE=0)
    assert r.get("ownership", {}).get("default", 0) == 0


def test_delete(client):
    name = f"_pytest_{uuid.uuid4().hex[:8]}"
    client.journal_upsert(name, folder=None, public=False)
    assert client.journal_delete(name) is True
    assert not any(e["name"] == name for e in client.get_journals())


def test_delete_not_found(client):
    assert client.journal_delete("_pytest_nonexistent_xyz") is False


def test_list_includes_created(client, journal):
    entries = client.get_journals()
    assert any(e["name"] == journal for e in entries)
