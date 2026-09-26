"""Exports the QA workflows from n8n back into workflows/*.json.

Edit a workflow in the n8n editor, then run:

    python scripts/export_workflows.py

Only the fields that define a workflow are kept (id, name, nodes, connections, settings, pinData),
so the files don't change on every export because of timestamps or version IDs.
"""

from __future__ import annotations

import json

from stack import WORKFLOWS_DIR, compose, require_running, step

KEEP = ("id", "name", "nodes", "connections", "settings", "pinData")


def main() -> None:
    require_running("n8n")
    for path in sorted(WORKFLOWS_DIR.glob("*.json")):
        workflow_id = json.loads(path.read_text(encoding="utf-8"))["id"]
        compose("exec", "-T", "n8n", "n8n", "export:workflow", f"--id={workflow_id}", "--output=/home/node/qa-export.json")
        exported = json.loads(compose("exec", "-T", "n8n", "cat", "/home/node/qa-export.json"))
        compose("exec", "-T", "n8n", "rm", "-f", "/home/node/qa-export.json")
        workflow = exported[0] if isinstance(exported, list) else exported
        content = json.dumps({key: workflow[key] for key in KEEP}, indent=2, ensure_ascii=False) + "\n"
        path.write_text(content, encoding="utf-8", newline="\n")
        step(f"Exported {workflow['name']} to workflows/{path.name}")


if __name__ == "__main__":
    main()
