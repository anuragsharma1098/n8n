"""Helpers the scripts share for talking to the Docker Compose stack."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env"
WORKFLOWS_DIR = ROOT / "workflows"


def step(message: str) -> None:
    print(f"- {message}", flush=True)


def read_env() -> dict[str, str]:
    if not ENV_FILE.exists():
        sys.exit("No .env file. Create one with: python scripts/create_env.py")
    values = {}
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values


def compose(*args: str, stdin: str | None = None) -> str:
    """Runs `docker compose` in the project folder and returns its output. Exits with its error on failure."""
    result = subprocess.run(
        ["docker", "compose", *args],
        cwd=ROOT, input=stdin, capture_output=True, text=True, encoding="utf-8",
    )
    if result.returncode != 0:
        sys.exit(f"`docker compose {' '.join(args)}` failed:\n{(result.stderr or result.stdout).strip()}")
    return result.stdout


def require_running(*services: str) -> None:
    running = set(compose("ps", "--status", "running", "--services").split())
    if not set(services) <= running:
        sys.exit("The stack isn't running. Start it with: docker compose up -d")
