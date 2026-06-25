import os
import sys
import time
import subprocess
import uuid
from pathlib import Path

import pytest
import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env.test", override=True)

sys.path.insert(0, str(Path(__file__).parent.parent))
from foundry import FoundryClient  # noqa: E402

COMPOSE_FILE = Path(__file__).parent.parent / "docker" / "compose.yml"


def make_cfg(**overrides) -> dict:
    cfg = {
        "url":         os.environ["FOUNDRY_URL"],
        "basic_user":  os.getenv("FOUNDRY_BASIC_USER", ""),
        "basic_pass":  os.getenv("FOUNDRY_BASIC_PASS", ""),
        "world":       os.environ["FOUNDRY_WORLD"],
        "gm_user":     os.environ["FOUNDRY_GM_USER"],
        "gm_password": os.getenv("FOUNDRY_GM_PASSWORD", ""),
    }
    cfg.update(overrides)
    return cfg


def _wait_for_world(url: str, world: str, timeout: int = 60) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = requests.get(f"{url}/api/status", timeout=2)
            if r.ok:
                s = r.json()
                if s.get("active") and s.get("world") == world:
                    return
        except Exception:
            pass
        time.sleep(2)
    raise TimeoutError(f"World '{world}' never became active within {timeout}s")


@pytest.fixture(scope="session")
def client():
    subprocess.run(
        ["docker", "compose", "-f", str(COMPOSE_FILE), "up", "-d"],
        check=True, capture_output=True,
    )
    cfg = make_cfg()
    _wait_for_world(cfg["url"], cfg["world"])
    fc = FoundryClient(cfg)
    fc.connect()
    yield fc
    fc.disconnect()


@pytest.fixture
def journal(client):
    """Unique journal per test; deleted on teardown."""
    name = f"_pytest_{uuid.uuid4().hex[:8]}"
    client.journal_upsert(name, folder=None, public=False)
    yield name
    client.journal_delete(name)
