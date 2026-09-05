"""Post-Deployment Smoke Test & Live Canary Health Verification.

Verifies that the deployed server on VPS/Cloud pulled the container,
restarted services, and is actively serving healthy HTTP 200 traffic.
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Any

# Ensure stdout/stderr handle UTF-8 cleanly on Windows/PowerShell
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


def query_health_endpoint(
    url: str, timeout_sec: int = 5
) -> tuple[bool, int, dict[str, Any] | None, str]:
    """Perform HTTP GET request against a target health endpoint."""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "JakeAI-CD-SmokeTester/1.0",
            "Accept": "application/json",
            "X-Correlation-ID": f"smoke-test-{int(time.time())}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as response:
            code = response.getcode()
            body_text = response.read().decode("utf-8", errors="replace")
            try:
                data = json.loads(body_text)
            except Exception:
                data = None
            return (code == 200, code, data, body_text)
    except urllib.error.HTTPError as err:
        return (False, err.code, None, str(err))
    except Exception as exc:
        return (False, 0, None, str(exc))


def write_step_summary(summary_md: str) -> None:
    """Write markdown summary to GITHUB_STEP_SUMMARY if available."""
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        try:
            with open(summary_path, "a", encoding="utf-8") as f:
                f.write(summary_md + "\n\n")
        except Exception as err:
            print(f"Failed to write GITHUB_STEP_SUMMARY: {err}", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description="Post-deployment smoke test runner.")
    parser.add_argument("--url", default=None, help="Target application base URL.")
    parser.add_argument(
        "--local",
        action="store_true",
        help="Run against local server http://127.0.0.1:8000.",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=18,
        help="Maximum retry attempts (default: 18 x 10s = 3m).",
    )
    parser.add_argument(
        "--interval", type=int, default=10, help="Seconds between poll retries."
    )
    args = parser.parse_args()

    target_url = args.url or (
        "http://127.0.0.1:8000" if args.local else os.environ.get("DEPLOY_TARGET_URL")
    )

    if not target_url:
        print(
            "================================================================================"
        )
        print("[INFO] DEPLOY_TARGET_URL secret is not configured in repository.")
        print("Skipping live remote smoke test.")
        print(
            "To enable post-deployment canary verification, add 'DEPLOY_TARGET_URL' to GitHub secrets."
        )
        print(
            "================================================================================"
        )
        write_step_summary(
            "### [INFO] Post-Deployment Smoke Test Skipped\n\n"
            "> `DEPLOY_TARGET_URL` secret is not configured in repository secrets.\n"
            "> Configure `DEPLOY_TARGET_URL` (e.g. `https://api.yourdomain.com`) to activate live canary health checks."
        )
        sys.exit(0)

    base_url = target_url.rstrip("/")
    root_health_url = f"{base_url}/health"
    detailed_health_url = f"{base_url}/api/v1/health"

    print(
        "================================================================================"
    )
    print(f"🚀 Initiating Post-Deployment Smoke Test against: {base_url}")
    print(
        f"⏱️ Retries: {args.max_retries} attempts | Interval: {args.interval}s (Max wait: {args.max_retries * args.interval}s)"
    )
    print(
        "================================================================================"
    )

    start_time = time.time()
    attempt = 0
    healthy = False
    last_error = ""
    last_data: dict[str, Any] | None = None

    while attempt < args.max_retries:
        attempt += 1
        elapsed = round(time.time() - start_time, 1)
        print(
            f"[{elapsed}s] Attempt {attempt}/{args.max_retries}: Probing {root_health_url} ..."
        )

        ok, status_code, data, detail = query_health_endpoint(root_health_url)
        if ok and data and data.get("status") in ("healthy", "ok"):
            print(
                f"  ✓ Root health OK ({status_code}). Probing {detailed_health_url} ..."
            )
            detail_ok, d_code, d_data, d_detail = query_health_endpoint(
                detailed_health_url
            )
            if detail_ok:
                healthy = True
                last_data = d_data or data
                print(f"  ✓ Service health probe verified: {last_data}")
                break
            else:
                last_error = f"Detailed health returned HTTP {d_code}: {d_detail}"
                print(f"  ⚠️ Detailed health probe pending: {last_error}")
        else:
            last_error = f"HTTP {status_code} - {detail}"
            print(f"  ⏳ Waiting for container to finish starting ({last_error})")

        time.sleep(args.interval)

    total_duration = round(time.time() - start_time, 1)

    if healthy:
        print(
            "================================================================================"
        )
        print(f"✅ SUCCESS: Post-deployment smoke test PASSED in {total_duration}s!")
        print(f"Application is live, responsive, and verified healthy at {base_url}")
        print(
            "================================================================================"
        )

        summary_md = (
            f"### ✅ Post-Deployment Smoke Test: **PASSED**\n\n"
            f"- **Target URL**: `{base_url}`\n"
            f"- **Verification Time**: {total_duration}s ({attempt} attempts)\n"
            f"- **Endpoints Checked**: `/health`, `/api/v1/health`\n"
            f"- **Status Payload**: `{json.dumps(last_data)}`\n"
        )
        write_step_summary(summary_md)
        sys.exit(0)
    else:
        print(
            "================================================================================"
        )
        print(
            f"❌ ERROR: Post-deployment smoke test FAILED after {total_duration}s ({args.max_retries} attempts)."
        )
        print(f"Target {base_url} did not respond with healthy 200 OK.")
        print(f"Last error: {last_error}")
        print(
            "================================================================================"
        )

        summary_md = (
            f"### ❌ Post-Deployment Smoke Test: **FAILED**\n\n"
            f"- **Target URL**: `{base_url}`\n"
            f"- **Attempts**: {attempt}/{args.max_retries} ({total_duration}s elapsed)\n"
            f"- **Last Error**: `{last_error}`\n\n"
            f"> **Action Required**: Verify server logs on the VPS host using `docker compose logs`."
        )
        write_step_summary(summary_md)
        sys.exit(1)


if __name__ == "__main__":
    main()
