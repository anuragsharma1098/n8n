"""Installs the QA Quality Gate into the running n8n stack.

Start the stack first (docker compose up -d), then run:

    python scripts/install_workflows.py

Safe to run again, for example after changing a workflow file. It:
1. adds a random QA_GATE_TOKEN to .env if there isn't one,
2. creates the qa_metrics database and its tables,
3. imports the two credentials the workflows use (database login and API key),
4. imports and publishes both workflows, then restarts n8n so their webhooks go live.
"""

from __future__ import annotations

import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.request

from stack import ENV_FILE, ROOT, WORKFLOWS_DIR, compose, read_env, require_running, step

N8N_URL = os.environ.get("N8N_URL", "http://localhost:5678").rstrip("/")
DATABASE = "qa_metrics"
IMPORT_DIR = "/home/node"  # n8n's home folder in its container


def ensure_token(env: dict[str, str]) -> str:
    if env.get("QA_GATE_TOKEN"):
        return env["QA_GATE_TOKEN"]
    token = secrets.token_hex(32)
    lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
    if any(line.startswith("QA_GATE_TOKEN=") for line in lines):
        lines = [f"QA_GATE_TOKEN={token}" if line.startswith("QA_GATE_TOKEN=") else line for line in lines]
    else:
        lines += ["", "# API key that CI sends in the X-QA-Token header to the quality gate.", f"QA_GATE_TOKEN={token}"]
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    step("Generated QA_GATE_TOKEN and saved it to .env")
    return token


def copy_into_n8n(content: str, path: str) -> None:
    """Writes a file only the n8n user can read, in its home folder inside the container."""
    compose("exec", "-T", "n8n", "sh", "-c", f"umask 077 && cat > {path}", stdin=content)


def wait_for(url: str, what: str, timeout: int = 180) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                if response.status == 200:
                    return
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            pass
        time.sleep(2)
    sys.exit(f"Timed out after {timeout}s waiting for {what} at {url}")


def main() -> None:
    env = read_env()
    require_running("postgres", "n8n")
    token = ensure_token(env)
    user, password = env["POSTGRES_USER"], env["POSTGRES_PASSWORD"]

    psql = ("exec", "-T", "postgres", "psql", "-U", user, "-v", "ON_ERROR_STOP=1", "-q")
    exists = compose(*psql, "-d", env["POSTGRES_DB"], "-tAc",
                     f"SELECT 1 FROM pg_database WHERE datname = '{DATABASE}'").strip()
    if exists != "1":
        compose(*psql, "-d", env["POSTGRES_DB"], "-c", f"CREATE DATABASE {DATABASE}")
        step(f"Created the {DATABASE} database")
    compose(*psql, "-d", DATABASE, stdin=(ROOT / "sql" / "schema.sql").read_text(encoding="utf-8"))
    step(f"Applied sql/schema.sql to {DATABASE}")

    credentials = [
        {"id": "qaMetricsPostgres", "name": "QA metrics database", "type": "postgres",
         "data": {"host": "postgres", "port": 5432, "database": DATABASE, "user": user, "password": password,
                  "ssl": "disable", "allowUnauthorizedCerts": False, "maxConnections": 10}},
        {"id": "qaGateHeaderAuth", "name": "QA Gate API key", "type": "httpHeaderAuth",
         "data": {"name": "X-QA-Token", "value": token}},
    ]
    try:
        copy_into_n8n(json.dumps(credentials), f"{IMPORT_DIR}/qa-credentials.json")
        compose("exec", "-T", "n8n", "n8n", "import:credentials", f"--input={IMPORT_DIR}/qa-credentials.json")
    finally:
        compose("exec", "-T", "n8n", "rm", "-f", f"{IMPORT_DIR}/qa-credentials.json")
    step("Imported credentials: QA metrics database, QA Gate API key")

    for path in sorted(WORKFLOWS_DIR.glob("*.json")):
        workflow = json.loads(path.read_text(encoding="utf-8"))
        target = f"{IMPORT_DIR}/{path.name}"
        copy_into_n8n(path.read_text(encoding="utf-8"), target)
        compose("exec", "-T", "n8n", "n8n", "import:workflow", f"--input={target}")
        compose("exec", "-T", "n8n", "n8n", "publish:workflow", f"--id={workflow['id']}")
        compose("exec", "-T", "n8n", "rm", "-f", target)
        step(f"Imported and published: {workflow['name']}")

    step("Restarting n8n so the webhooks go live...")
    compose("restart", "n8n")
    wait_for(f"{N8N_URL}/healthz", "n8n")
    wait_for(f"{N8N_URL}/webhook/qa/dashboard", "the dashboard webhook")

    print(f"\nDone.\n  Quality gate: POST {N8N_URL}/webhook/qa/results  (header X-QA-Token, value QA_GATE_TOKEN in .env)"
          f"\n  Dashboard:    {N8N_URL}/webhook/qa/dashboard")


if __name__ == "__main__":
    main()
