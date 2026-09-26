"""Sends a JUnit XML report to the QA Quality Gate and prints its verdict.

    python scripts/publish_results.py reports/junit.xml --project my-org/my-repo --branch main

Prints the gate's Markdown summary. In GitHub Actions, pass --summary-file "$GITHUB_STEP_SUMMARY"
to show it on the run page. Exit code: 0 = gate passed, 1 = gate failed, 2 = request failed.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def token_from_env_file() -> str | None:
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("QA_GATE_TOKEN="):
                return line.split("=", 1)[1].strip() or None
    return None


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("report", type=Path, help="JUnit XML report")
    parser.add_argument("--project", required=True, help="project name, e.g. my-org/my-repo")
    parser.add_argument("--branch", default="main")
    parser.add_argument("--commit", default="")
    parser.add_argument("--build-url", default="", help="link to the CI run")
    parser.add_argument("--min-pass-rate", type=float, help="required pass rate in percent (gate default: 95)")
    parser.add_argument("--url", default=os.environ.get("N8N_URL", "http://localhost:5678"), help="n8n base URL")
    parser.add_argument("--token", default=os.environ.get("QA_GATE_TOKEN") or token_from_env_file(),
                        help="API key (default: QA_GATE_TOKEN from the environment or .env)")
    parser.add_argument("--summary-file", type=Path, help="append the Markdown summary to this file")
    parser.add_argument("--no-fail", action="store_true", help="exit 0 even when the gate fails")
    parser.add_argument("--test", action="store_true",
                        help="send to the test URL, to watch the run on the canvas after clicking "
                             "'Execute workflow' in the n8n editor")
    args = parser.parse_args()

    if not args.token:
        print("No API key: set QA_GATE_TOKEN or pass --token.", file=sys.stderr)
        return 2
    body = {"project": args.project, "branch": args.branch, "commit": args.commit, "build_url": args.build_url,
            "junit_xml": args.report.read_text(encoding="utf-8")}
    if args.min_pass_rate is not None:
        body["min_pass_rate"] = args.min_pass_rate

    webhook = "webhook-test" if args.test else "webhook"
    request = urllib.request.Request(
        f"{args.url.rstrip('/')}/{webhook}/qa/results",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-QA-Token": args.token},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            result = json.load(response)
    except urllib.error.HTTPError as error:
        print(f"The quality gate rejected the report: HTTP {error.code} {error.read().decode('utf-8', 'replace')}",
              file=sys.stderr)
        if args.test and error.code == 404:
            print("The test URL only answers while the editor is waiting: open the workflow, click "
                  "'Execute workflow', then run this command within 2 minutes.", file=sys.stderr)
        return 2
    except urllib.error.URLError as error:
        print(f"Couldn't reach the quality gate at {args.url}: {error.reason}", file=sys.stderr)
        return 2

    print(result["summary_markdown"])
    if args.summary_file:
        with args.summary_file.open("a", encoding="utf-8") as summary:
            summary.write(result["summary_markdown"] + "\n")
    if result["gate"] == "failed":
        print(f"\nQuality gate failed: {'; '.join(result['reasons'])}", file=sys.stderr)
        return 0 if args.no_fail else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
