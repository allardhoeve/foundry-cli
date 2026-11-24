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



def _flaky_connect(monkeypatch, failures: int = 0, fail_on: set[int] = frozenset()):
    """Make the first `failures` Socket.io connects (or the calls numbered in
    `fail_on`) fail like a missed handshake; record backoff sleeps instead of
    sleeping."""
    import socketio
    import foundry
    orig = socketio.Client.connect
    calls, sleeps = [0], []

    def connect(self, *a, **k):
        calls[0] += 1
        if calls[0] <= failures or calls[0] in fail_on:
            raise socketio.exceptions.ConnectionError(
                "One or more namespaces failed to connect: ")
        return orig(self, *a, **k)

    monkeypatch.setattr(socketio.Client, "connect", connect)
    monkeypatch.setattr(foundry.time, "sleep", sleeps.append)
    return calls, sleeps


def test_connect_retries_with_exponential_backoff(client, monkeypatch):
    calls, sleeps = _flaky_connect(monkeypatch, failures=3)
    fc = FoundryClient(make_cfg())
    fc.connect()
    fc.disconnect()
    assert calls[0] == 5          # 3 failures, then both connects succeed
    assert len(sleeps) == 3
    base = FoundryClient._BACKOFF_BASE
    for n, slept in enumerate(sleeps):   # base * 2^n, plus up to 50% jitter
        assert base * 2 ** n <= slept <= base * 2 ** n * 1.5


def test_connect_gives_up_with_a_clear_retryable_error(client, monkeypatch):
    calls, sleeps = _flaky_connect(monkeypatch, failures=100)
    with pytest.raises(click.ClickException, match="safe to retry"):
        FoundryClient(make_cfg()).connect()
    assert calls[0] == FoundryClient._CONNECT_ATTEMPTS
    assert len(sleeps) == FoundryClient._CONNECT_ATTEMPTS - 1


def test_both_connections_retry(client, monkeypatch):
    # Call 1: user lookup fails, call 2 succeeds; call 3: the session
    # connection (a reused Client) fails, call 4 succeeds.
    calls, sleeps = _flaky_connect(monkeypatch, fail_on={1, 3})
    fc = FoundryClient(make_cfg())
    fc.connect()
    assert fc._emit({"type": "Scene", "action": "get", "operation": {"query": {}}})
    fc.disconnect()
    assert calls[0] == 4 and len(sleeps) == 2
