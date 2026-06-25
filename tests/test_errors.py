import os

import click
import pytest

from conftest import make_cfg
from foundry import FoundryClient


def test_wrong_world(client):
    fc = FoundryClient(make_cfg(world="wrong-world-xyz"))
    with pytest.raises(click.ClickException, match="wrong-world-xyz"):
        fc.connect()


def test_bad_password(client):
    fc = FoundryClient(make_cfg(gm_password="definitely-wrong"))
    with pytest.raises(Exception):
        fc.connect()


def test_journal_not_found(client):
    with pytest.raises(click.ClickException, match="not found"):
        client.page_list("_pytest_no_such_journal")
