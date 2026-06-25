import click
import pytest


def test_upsert_creates(client, journal):
    r = client.page_upsert(journal, "Overview", None, 1, False, "<p>Hello</p>")
    assert r["name"] == "Overview"
    assert "_id" in r


def test_upsert_idempotent(client, journal):
    r1 = client.page_upsert(journal, "Overview", None, 1, False, "<p>v1</p>")
    r2 = client.page_upsert(journal, "Overview", None, 1, False, "<p>v2</p>")
    assert r1["_id"] == r2["_id"]
    dupes = [p for p in client.page_list(journal) if p["name"] == "Overview"]
    assert len(dupes) == 1


def test_upsert_level(client, journal):
    r = client.page_upsert(journal, "Sub", None, 2, False, "<p>sub</p>")
    assert r["title"]["level"] == 2


def test_upsert_public(client, journal):
    r = client.page_upsert(journal, "Public", None, 1, True, "<p>pub</p>")
    assert r["ownership"]["default"] == 2  # OBSERVER


def test_upsert_inherit(client, journal):
    r = client.page_upsert(journal, "Private", None, 1, False, "<p>priv</p>")
    assert r["ownership"]["default"] == -1  # INHERIT — follows parent journal


def test_upsert_with_category(client, journal):
    client.category_upsert(journal, "NPCs")
    r = client.page_upsert(journal, "Grimlash", "NPCs", 1, False, "<p>orc</p>")
    assert r["name"] == "Grimlash"
    pages = client.page_list(journal)
    page = next(p for p in pages if p["name"] == "Grimlash")
    assert page["_category_name"] == "NPCs"


def test_upsert_missing_category(client, journal):
    with pytest.raises(click.ClickException, match="Category 'NoSuchCat' not found"):
        client.page_upsert(journal, "X", "NoSuchCat", 1, False, "<p>x</p>")


def test_upsert_missing_category_hint(client, journal):
    with pytest.raises(click.ClickException) as exc_info:
        client.page_upsert(journal, "X", "NoSuchCat", 1, False, "<p>x</p>")
    assert "category upsert" in exc_info.value.format_message()


def test_list_columns(client, journal):
    client.category_upsert(journal, "Places")
    client.page_upsert(journal, "Ravensmoor", "Places", 1, False, "<p>town</p>")
    pages = client.page_list(journal)
    page = next(p for p in pages if p["name"] == "Ravensmoor")
    assert page["_category_name"] == "Places"
    assert page["title"]["level"] == 1
    assert page["type"] == "text"


def test_delete(client, journal):
    client.page_upsert(journal, "ToDelete", None, 1, False, "<p>bye</p>")
    assert client.page_delete(journal, "ToDelete") is True
    assert not any(p["name"] == "ToDelete" for p in client.page_list(journal))


def test_delete_not_found(client, journal):
    assert client.page_delete(journal, "_nonexistent") is False
