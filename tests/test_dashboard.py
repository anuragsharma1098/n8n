"""End-to-end tests for the dashboard: GET /webhook/qa/dashboard."""

from __future__ import annotations

from urllib.parse import quote

import pytest
import requests

from conftest import DASHBOARD_URL, Gate
from junit_builder import case_id, junit

pytestmark = [pytest.mark.e2e, pytest.mark.usefixtures("workflows_installed")]


def shown(test_id: str) -> str:
    """How the dashboard writes a test ID: with line-break hints after '.' and '::'."""
    return test_id.replace(".", ".<wbr>").replace("::", "::<wbr>")


def open_dashboard(**params: str) -> requests.Response:
    response = requests.get(DASHBOARD_URL, params=params, timeout=30)
    assert response.status_code == 200, response.text
    assert response.headers["Content-Type"].startswith("text/html")
    return response


def test_project_list_links_to_each_project(gate: Gate, project: str) -> None:
    gate.run(project, junit({"test_login": "passed"}))
    page = open_dashboard().text

    assert f'href="?project={quote(project, safe="")}&amp;branch=main"' in page


def test_project_page_shows_failures_and_flaky_tests(gate: Gate, project: str) -> None:
    for status in ["passed", "failed", "passed", "failed"]:
        gate.run(project, junit({"test_login": "passed", "test_search": status, "test_pay": "failed"}), min_pass_rate=0)
    page = open_dashboard(project=project, branch="main").text

    assert f"<title>QA dashboard: {project}</title>" in page
    assert f'<code>{shown(case_id("test_pay"))}</code></td><td class="msg">assert 1 == 2</td>' in page
    assert f'<code>{shown(case_id("test_search"))}</code> <span class="pill bad">flaky</span>' in page
    assert page.count('<div class="bar ') == 4


def test_unknown_project_shows_empty_state(project: str) -> None:
    page = open_dashboard(project=project).text

    assert "No runs recorded for" in page


def test_values_from_reports_are_html_escaped(gate: Gate, project: str) -> None:
    payload = '<img src=x onerror="alert(1)">'
    gate.run(project, junit({payload: "failed"}))
    page = open_dashboard(project=project).text

    assert "<img" not in page
    assert "&lt;img src=x onerror=&quot;alert(1)&quot;&gt;" in page
