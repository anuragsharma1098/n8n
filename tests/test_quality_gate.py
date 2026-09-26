"""End-to-end tests for the quality gate: POST /webhook/qa/results."""

from __future__ import annotations

import pytest

from conftest import BASE_URL, Gate
from junit_builder import case_id, fixture, junit

pytestmark = [pytest.mark.e2e, pytest.mark.usefixtures("workflows_installed")]

ALL_PASS = {"test_login": "passed", "test_cart": "passed", "test_pay": "passed"}


class TestVerdict:
    def test_all_passing_run_passes(self, gate: Gate, project: str) -> None:
        result = gate.run(project, junit(ALL_PASS), commit="4f2a9c1")

        assert result["gate"] == "passed"
        assert result["reasons"] == []
        assert result["stats"] == {"total": 3, "passed": 3, "failed": 0, "skipped": 0, "pass_rate": 100,
                                   "min_pass_rate": 95, "duration_ms": 150}
        assert result["previous_run_id"] is None
        assert result["commit"] == "4f2a9c1"
        assert [result[key] for key in ("new_failures", "still_failing", "fixed", "flaky", "failures")] == [[]] * 5

    def test_failure_on_first_run_fails(self, gate: Gate, project: str) -> None:
        result = gate.run(project, junit({"test_login": "passed", "test_pay": "failed"}))

        assert result["gate"] == "failed"
        assert result["new_failures"] == [case_id("test_pay")]
        assert result["reasons"][0] == f"1 new failure: {case_id('test_pay')}"
        assert result["failures"] == [{"test_id": case_id("test_pay"), "status": "failed",
                                       "message": "assert 1 == 2", "flaky": False}]

    def test_regression_is_a_new_failure(self, gate: Gate, project: str) -> None:
        first = gate.run(project, junit(ALL_PASS))
        second = gate.run(project, junit({**ALL_PASS, "test_cart": "failed"}))

        assert second["previous_run_id"] == first["run_id"]
        assert second["new_failures"] == [case_id("test_cart")]
        assert second["gate"] == "failed"

    def test_fixed_test_is_reported(self, gate: Gate, project: str) -> None:
        gate.run(project, junit({**ALL_PASS, "test_cart": "failed"}))
        result = gate.run(project, junit(ALL_PASS))

        assert result["fixed"] == [case_id("test_cart")]
        assert result["gate"] == "passed"

    def test_known_failure_does_not_block_when_pass_rate_is_met(self, gate: Gate, project: str) -> None:
        results = {f"test_{i}": "passed" for i in range(8)} | {"test_8": "failed", "test_9": "failed"}
        gate.run(project, junit(results))
        result = gate.run(project, junit(results), min_pass_rate=80)

        assert result["new_failures"] == []
        assert result["still_failing"] == [case_id("test_8"), case_id("test_9")]
        assert result["stats"]["pass_rate"] == 80
        assert result["gate"] == "passed"

    @pytest.mark.parametrize(("min_pass_rate", "verdict"), [(0, "passed"), (80, "passed"), (80.01, "failed")])
    def test_pass_rate_threshold(self, gate: Gate, project: str, min_pass_rate: float, verdict: str) -> None:
        results = {f"test_{i}": "passed" for i in range(8)} | {"test_8": "failed", "test_9": "failed"}
        gate.run(project, junit(results))  # the failures already failed here, so they aren't new below
        result = gate.run(project, junit(results), min_pass_rate=min_pass_rate)

        assert result["gate"] == verdict
        if verdict == "failed":
            assert result["reasons"] == [f"pass rate 80% is below the required {min_pass_rate}%"]

    def test_skipped_tests_do_not_count_against_pass_rate(self, gate: Gate, project: str) -> None:
        result = gate.run(project, junit({"test_login": "passed", "test_export": "skipped"}))

        assert result["stats"]["skipped"] == 1
        assert result["stats"]["pass_rate"] == 100
        assert result["gate"] == "passed"

    def test_errors_count_as_failures(self, gate: Gate, project: str) -> None:
        result = gate.run(project, junit({"test_login": "passed", "test_db": "error"}))

        assert result["stats"]["failed"] == 1
        assert result["failures"][0]["status"] == "error"
        assert result["gate"] == "failed"

    def test_history_is_kept_per_branch(self, gate: Gate, project: str) -> None:
        main = gate.run(project, junit(ALL_PASS))
        gate.run(project, junit({**ALL_PASS, "test_cart": "failed"}), branch="feature/new-cart")
        result = gate.run(project, junit(ALL_PASS))

        assert result["previous_run_id"] == main["run_id"]
        assert result["fixed"] == []


class TestFlakyDetection:
    def test_test_that_keeps_flipping_is_flaky_and_does_not_block(self, gate: Gate, project: str) -> None:
        for status in ["passed", "failed", "passed", "failed"]:
            result = gate.run(project, junit({"test_login": "passed", "test_search": status}), min_pass_rate=50)

        assert result["flaky"] == [{"test_id": case_id("test_search"), "flips": 3, "failures": 2, "runs": 4,
                                    "passed_on_retry": 0}]
        assert result["new_failures"] == [case_id("test_search")]  # it passed in the previous run...
        assert result["failures"][0]["flaky"] is True
        assert result["gate"] == "passed"  # ...but a known flaky test doesn't block

    def test_regression_that_gets_fixed_is_not_flaky(self, gate: Gate, project: str) -> None:
        for status in ["passed", "failed", "passed"]:
            result = gate.run(project, junit({"test_search": status}))

        assert result["flaky"] == []
        assert result["fixed"] == [case_id("test_search")]

    def test_consistent_failure_is_not_flaky(self, gate: Gate, project: str) -> None:
        for _ in range(3):
            result = gate.run(project, junit({"test_login": "passed", "test_search": "failed"}), min_pass_rate=50)

        assert result["flaky"] == []
        assert result["still_failing"] == [case_id("test_search")]

    def test_pass_after_rerun_is_flaky(self, gate: Gate, project: str) -> None:
        result = gate.run(project, junit({"test_login": "passed", "test_search": "flaky"}))

        assert result["stats"]["passed"] == 2
        assert result["flaky"] == [{"test_id": case_id("test_search"), "flips": 0, "failures": 0, "runs": 1,
                                    "passed_on_retry": 1}]
        assert result["gate"] == "passed"

    def test_flips_on_another_branch_do_not_count(self, gate: Gate, project: str) -> None:
        for status in ["passed", "failed", "passed", "failed"]:
            gate.run(project, junit({"test_search": status}), branch="feature/search", min_pass_rate=0)
        result = gate.run(project, junit({"test_search": "failed"}), min_pass_rate=0)

        assert result["flaky"] == []
        assert result["gate"] == "failed"


class TestReportFormats:
    def test_pytest_report(self, gate: Gate, project: str) -> None:
        result = gate.run(project, fixture("pytest-report.xml"), min_pass_rate=0)

        assert result["stats"] == {"total": 6, "passed": 3, "failed": 2, "skipped": 1, "pass_rate": 60,
                                   "min_pass_rate": 0, "duration_ms": 2612}
        failures = {f["test_id"]: f for f in result["failures"]}
        assert failures["tests.api.test_users::test_delete_user"]["message"] == \
            "AssertionError: expected status 204, got 500"
        assert failures["tests.api.test_orders::test_refund"]["status"] == "error"

    def test_maven_surefire_report_with_rerun(self, gate: Gate, project: str) -> None:
        result = gate.run(project, fixture("surefire-report.xml"))

        assert result["stats"]["total"] == 4
        assert result["stats"]["passed"] == 3
        assert result["new_failures"] == ["com.example.checkout.CheckoutTest::calculatesTax"]
        assert [f["test_id"] for f in result["flaky"]] == ["com.example.checkout.CheckoutTest::appliesDiscountCode"]
        assert result["failures"][0]["message"] == "expected: <18.00> but was: <17.99>"

    def test_nested_suites_and_single_suite_root(self, gate: Gate, project: str) -> None:
        nested = """<testsuites><testsuite name="e2e">
            <testsuite name="e2e.login"><testcase classname="e2e.login" name="valid_user" time="1.5"/></testsuite>
            <testsuite name="e2e.search"><testcase name="finds_product" time="2"/></testsuite>
        </testsuite></testsuites>"""
        result = gate.run(project, nested)
        single = gate.run(project, '<testsuite name="smoke"><testcase name="home_page_loads"/></testsuite>')

        assert result["stats"]["total"] == 2
        assert result["stats"]["duration_ms"] == 3500
        assert single["stats"]["total"] == 1
        assert single["fixed"] == []


class TestValidation:
    @pytest.mark.parametrize(("change", "detail"), [
        ({"project": None}, "project is required"),
        ({"project": "my project"}, "project must be 1-120 characters with no spaces"),
        ({"junit_xml": None}, "junit_xml is required: send the JUnit XML report as a string"),
        ({"junit_xml": "   "}, "junit_xml is required: send the JUnit XML report as a string"),
        ({"min_pass_rate": 150}, "min_pass_rate must be a number from 0 to 100"),
        ({"min_pass_rate": "95"}, "min_pass_rate must be a number from 0 to 100"),
        ({"build_url": "ftp://ci.example.com/1"}, "build_url must be an http(s) URL"),
    ])
    def test_invalid_field_is_rejected(self, gate: Gate, project: str, change: dict, detail: str) -> None:
        body = {"project": project, "branch": "main", "junit_xml": junit(ALL_PASS)}
        body.update(change)
        body = {key: value for key, value in body.items() if value is not None}
        response = gate.send(body)

        assert response.status_code == 400
        assert response.json() == {"error": "Invalid request", "details": [detail]}

    def test_every_problem_is_listed(self, gate: Gate) -> None:
        response = gate.send({"min_pass_rate": -1})

        assert response.status_code == 400
        assert len(response.json()["details"]) == 3

    @pytest.mark.parametrize("xml", ["<testsuite><testcase name='x'>", "<a><b></a>", "not XML at all"],
                             ids=["truncated", "mismatched-tags", "plain-text"])
    def test_malformed_xml_is_rejected(self, gate: Gate, project: str, xml: str) -> None:
        response = gate.send({"project": project, "junit_xml": xml})

        assert response.status_code == 400
        assert response.json()["error"] == "junit_xml is not valid XML"

    @pytest.mark.parametrize("xml", ["<testsuites/>", "<html><body>Build log</body></html>"])
    def test_xml_without_test_cases_is_rejected(self, gate: Gate, project: str, xml: str) -> None:
        response = gate.send({"project": project, "junit_xml": xml})

        assert response.status_code == 422
        assert response.json() == {"error": "No test cases found", "details": ["The report has no <testcase> elements"]}

    def test_rejected_report_is_not_stored(self, gate: Gate, project: str) -> None:
        gate.send({"project": project, "junit_xml": "<testsuites/>"})
        result = gate.run(project, junit(ALL_PASS))

        assert result["previous_run_id"] is None


class TestAuthentication:
    @pytest.mark.parametrize("api_key", [None, "wrong-token"], ids=["missing", "wrong"])
    def test_request_without_valid_api_key_is_rejected(self, gate: Gate, project: str, api_key: str | None) -> None:
        response = gate.send({"project": project, "junit_xml": junit(ALL_PASS)}, token=api_key)

        assert response.status_code == 403


class TestResponse:
    def test_markdown_summary(self, gate: Gate, project: str) -> None:
        result = gate.run(project, junit({"test_login": "passed", "test_pay": "failed"}))
        summary = result["summary_markdown"]

        assert summary.startswith(f"## ❌ Quality gate failed: {project} (main)")
        assert "| 2 | 1 | 1 | 0 | 50% (min 95%) | 0.1 s |" in summary
        assert f"### New failures (1)\n\n- `{case_id('test_pay')}` — assert 1 == 2" in summary

    def test_dashboard_url_points_at_the_project(self, gate: Gate, project: str) -> None:
        result = gate.run(project, junit(ALL_PASS), branch="release/2.0")

        assert result["dashboard_url"] == (
            f"{BASE_URL}/webhook/qa/dashboard?project={project.replace('/', '%2F')}&branch=release%2F2.0")
