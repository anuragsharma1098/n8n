"""Creates .env from .env.example, with a fresh random value for every secret.

    python scripts/create_env.py

Won't overwrite an existing .env: its Postgres values must stay the same once the database exists.
"""

from __future__ import annotations

import secrets
import sys

from stack import ENV_FILE, ROOT

SECRETS = ("POSTGRES_PASSWORD", "N8N_RUNNERS_AUTH_TOKEN", "QA_GATE_TOKEN")


def main() -> None:
    if ENV_FILE.exists():
        sys.exit(".env already exists, so it was left alone. Delete it first only if you're starting from scratch "
                 "(docker compose down -v), because Postgres keeps the password it was created with.")
    lines = []
    for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        key = line.split("=", 1)[0]
        if key in SECRETS and line == f"{key}=":
            line = f"{key}={secrets.token_hex(32)}"
        lines.append(line)
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(f"Created .env with new random values for {', '.join(SECRETS)}.")


if __name__ == "__main__":
    main()
