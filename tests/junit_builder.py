"""Builds small JUnit XML reports for tests."""

from __future__ import annotations

from pathlib import Path
from xml.sax.saxutils import quoteattr

FIXTURES = Path(__file__).resolve().parent / "fixtures"
CLASSNAME = "tests.test_checkout"

_BODIES = {
    "passed": "",
    "failed": '<failure message="assert 1 == 2">AssertionError: assert 1 == 2</failure>',
    "error": '<error message="fixture db failed">ConnectionError: database unavailable</error>',
    "skipped": '<skipped message="not ready yet" />',
    # Maven Surefire writes this when a test fails and then passes on a rerun.
    "flaky": '<flakyFailure message="Timed out after 5s">TimeoutError</flakyFailure>',
}


def junit(results: dict[str, str], classname: str = CLASSNAME) -> str:
    """results maps a test name to passed, failed, error, skipped or flaky (failed, then passed on rerun)."""
    cases = "\n".join(
        f'    <testcase classname={quoteattr(classname)} name={quoteattr(name)} time="0.05">{_BODIES[status]}</testcase>'
        for name, status in results.items()
    )
    statuses = list(results.values())
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n<testsuites>\n'
        f'  <testsuite name={quoteattr(classname)} tests="{len(statuses)}" failures="{statuses.count("failed")}" '
        f'errors="{statuses.count("error")}" skipped="{statuses.count("skipped")}">\n{cases}\n  </testsuite>\n</testsuites>\n'
    )


def case_id(name: str, classname: str = CLASSNAME) -> str:
    """The ID the gate gives a test case: classname::name."""
    return f"{classname}::{name}"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")
