"""Fills the dashboard with a demo history: 12 CI runs of a made-up project, demo/shop-api.

    python scripts/seed_demo_data.py

Then open http://localhost:5678/webhook/qa/dashboard?project=demo/shop-api

The history has a flaky test, a test that only passes on retry, a regression that is still failing,
and a failure that gets fixed, so every part of the dashboard has something to show.
Run it once: running it again adds 12 more runs to the same history.
"""

from __future__ import annotations

import json
import os
import random
import sys
import urllib.request
from xml.sax.saxutils import quoteattr

from stack import read_env

PROJECT = "demo/shop-api"
RUNS = 12
TESTS = {
    "tests.api.test_auth": ["test_login", "test_logout", "test_refresh_token", "test_rejects_expired_token"],
    "tests.api.test_catalog": ["test_list_products", "test_search_by_name", "test_filter_by_price", "test_product_images"],
    "tests.api.test_checkout": ["test_add_to_cart", "test_apply_coupon", "test_calculate_tax", "test_place_order"],
    "tests.api.test_orders": ["test_order_history", "test_refund_full", "test_refund_partial", "test_export_csv"],
}
SLOW = {"test_place_order": 3.2, "test_search_by_name": 1.4, "test_refund_full": 0.9}


def outcome(name: str, run: int) -> str:
    """What each test does on a given run (1-based)."""
    if name == "test_apply_coupon" and run in (3, 5, 8, 11):
        return '<failure message="AssertionError: expected total 45.00, got 50.00">Coupon was applied after the total was calculated</failure>'
    if name == "test_product_images" and run in (4, 10):
        return '<flakyFailure message="ReadTimeout: image CDN took longer than 5s">requests.exceptions.ReadTimeout</flakyFailure>'
    if name == "test_refund_partial" and run >= 9:
        return '<failure message="AssertionError: expected refund 25.00, got 50.00">Partial refunds are paid in full</failure>'
    if name == "test_calculate_tax" and run in (5, 6):
        return '<failure message="AssertionError: expected tax 18.00, got 17.99">Rounding error in tax calculation</failure>'
    if name == "test_export_csv":
        return '<skipped message="export service is not deployed in CI" />'
    return ""


def report(run: int, rng: random.Random) -> str:
    suites = []
    for classname, names in TESTS.items():
        cases = "".join(
            f'<testcase classname={quoteattr(classname)} name={quoteattr(name)} '
            f'time="{SLOW.get(name, 0.2) * rng.uniform(0.8, 1.3):.3f}">{outcome(name, run)}</testcase>'
            for name in names
        )
        suites.append(f'<testsuite name={quoteattr(classname)}>{cases}</testsuite>')
    return f'<?xml version="1.0" encoding="utf-8"?><testsuites>{"".join(suites)}</testsuites>'


def main() -> None:
    url = os.environ.get("N8N_URL", "http://localhost:5678").rstrip("/")
    token = os.environ.get("QA_GATE_TOKEN") or read_env().get("QA_GATE_TOKEN")
    if not token:
        sys.exit("QA_GATE_TOKEN isn't set. Run: python scripts/install_workflows.py")
    rng = random.Random(42)
    for run in range(1, RUNS + 1):
        body = {"project": PROJECT, "branch": "main", "commit": f"{rng.getrandbits(160):040x}",
                "junit_xml": report(run, rng)}
        request = urllib.request.Request(
            f"{url}/webhook/qa/results", data=json.dumps(body).encode("utf-8"), method="POST",
            headers={"Content-Type": "application/json", "X-QA-Token": token})
        with urllib.request.urlopen(request, timeout=60) as response:
            result = json.load(response)
        print(f"run {run:>2}: gate {result['gate']:<6}  pass rate {result['stats']['pass_rate']}%")
    print(f"\nOpen {url}/webhook/qa/dashboard?project={PROJECT}")


if __name__ == "__main__":
    main()
