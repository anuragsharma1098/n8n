"""Static checks on workflows/*.json. Fast, and they don't need n8n running."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

WORKFLOWS = sorted((Path(__file__).resolve().parent.parent / "workflows").glob("*.json"))
CODE_NODES = [
    pytest.param(node["parameters"]["jsCode"], id=f"{path.stem}/{node['name']}")
    for path in WORKFLOWS
    for node in json.loads(path.read_text(encoding="utf-8"))["nodes"]
    if node["type"] == "n8n-nodes-base.code"
]
# Parses the code the way n8n's Code node wraps it (an async function body), without running it.
PARSE_JS = ("const AsyncFunction = (async () => {}).constructor;"
            "new AsyncFunction(require('fs').readFileSync(0, 'utf8'));")


def load(name: str) -> dict:
    return json.loads(next(p for p in WORKFLOWS if p.name == name).read_text(encoding="utf-8"))


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.stem)
def test_every_connection_points_at_an_existing_node(path: Path) -> None:
    workflow = json.loads(path.read_text(encoding="utf-8"))
    names = {node["name"] for node in workflow["nodes"]}

    assert len(names) == len(workflow["nodes"]), "node names must be unique"
    for source, outputs in workflow["connections"].items():
        assert source in names
        for targets in outputs["main"]:
            for target in targets:
                assert target["node"] in names, f"{source} -> {target['node']}"


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.stem)
def test_no_pinned_test_data_is_committed(path: Path) -> None:
    assert json.loads(path.read_text(encoding="utf-8")).get("pinData", {}) == {}


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js isn't installed")
@pytest.mark.parametrize("code", CODE_NODES)
def test_code_node_javascript_parses(code: str) -> None:
    result = subprocess.run(["node", "-e", PARSE_JS], input=code, capture_output=True, text=True, encoding="utf-8")

    assert result.returncode == 0, result.stderr


def test_webhooks_match_the_documented_api() -> None:
    webhooks = {
        (node["parameters"]["httpMethod"], node["parameters"]["path"]): node
        for name in ("qa-quality-gate.json", "qa-dashboard.json")
        for node in load(name)["nodes"]
        if node["type"] == "n8n-nodes-base.webhook"
    }

    assert set(webhooks) == {("POST", "qa/results"), ("GET", "qa/dashboard")}
    assert webhooks["POST", "qa/results"]["parameters"]["authentication"] == "headerAuth"
    assert all(node["parameters"]["responseMode"] == "responseNode" for node in webhooks.values())


def test_every_path_through_the_gate_ends_in_a_response() -> None:
    workflow = load("qa-quality-gate.json")
    nodes = {node["name"]: node for node in workflow["nodes"] if node["type"] != "n8n-nodes-base.stickyNote"}
    outgoing = {name: [t["node"] for targets in c["main"] for t in targets] for name, c in workflow["connections"].items()}

    dead_ends = [name for name in nodes
                 if not outgoing.get(name) and nodes[name]["type"] != "n8n-nodes-base.respondToWebhook"]
    assert dead_ends == []
