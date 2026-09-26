"""Shared fixtures for the end-to-end tests. They run against a live n8n with the QA workflows installed."""

from __future__ import annotations

import os
import re
import uuid
from pathlib import Path

import pytest
import requests

ROOT = Path(__file__).resolve().parent.parent
BASE_URL = os.environ.get("N8N_URL", "http://localhost:5678").rstrip("/")
RESULTS_URL = f"{BASE_URL}/webhook/qa/results"
DASHBOARD_URL = f"{BASE_URL}/webhook/qa/dashboard"


def _token() -> str | None:
    if os.environ.get("QA_GATE_TOKEN"):
        return os.environ["QA_GATE_TOKEN"]
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("QA_GATE_TOKEN="):
                return line.split("=", 1)[1].strip() or None
    return None


@pytest.fixture(scope="session")
def workflows_installed() -> None:
    """Stops the run early with a clear message when n8n or the QA workflows aren't there."""
    try:
        response = requests.get(DASHBOARD_URL, timeout=10)
    except requests.ConnectionError:
        pytest.exit(f"n8n isn't reachable at {BASE_URL}. Start it with: docker compose up -d", returncode=2)
    if response.status_code != 200:
        pytest.exit("The QA workflows aren't installed. Run: python scripts/install_workflows.py", returncode=2)


@pytest.fixture(scope="session")
def token() -> str:
    value = _token()
    if not value:
        pytest.exit("QA_GATE_TOKEN isn't set in the environment or .env. "
                    "Run: python scripts/install_workflows.py", returncode=2)
    return value


class Gate:
    """Client for POST /webhook/qa/results."""

    def __init__(self, token: str) -> None:
        self.token = token
        self.session = requests.Session()

    def send(self, body: dict, token: str | None = "default") -> requests.Response:
        headers = {} if token is None else {"X-QA-Token": self.token if token == "default" else token}
        return self.session.post(RESULTS_URL, json=body, headers=headers, timeout=60)

    def run(self, project: str, junit_xml: str, branch: str = "main", **fields) -> dict:
        """Sends a report and returns the verdict, failing the test on any non-200 response."""
        response = self.send({"project": project, "branch": branch, "junit_xml": junit_xml, **fields})
        assert response.status_code == 200, f"HTTP {response.status_code}: {response.text}"
        return response.json()


@pytest.fixture(scope="session")
def gate(token: str) -> Gate:
    return Gate(token)


@pytest.fixture
def project(request: pytest.FixtureRequest) -> str:
    """A project name no other test uses, so every test starts with an empty history."""
    name = re.sub(r"[^\w.-]+", "-", request.node.name)[:60]
    return f"pytest/{name}-{uuid.uuid4().hex[:8]}"
