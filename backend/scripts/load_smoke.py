"""Read-only local API load smoke. This is not a production capacity benchmark."""

import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
from dotenv import dotenv_values

parser = argparse.ArgumentParser()
parser.add_argument("--requests", type=int, default=120)
parser.add_argument("--concurrency", type=int, default=6)
args = parser.parse_args()
if not 1 <= args.requests <= 10000 or not 1 <= args.concurrency <= 32:
    raise SystemExit("Use 1..10000 requests and 1..32 workers")
root = Path(__file__).resolve().parents[2]
values = dotenv_values(root / "backend" / ".env")
with httpx.Client(base_url="http://127.0.0.1:8000", trust_env=False, timeout=30) as client:
    response = client.post(
        "/api/v1/auth/dev-login",
        json={"user_id": "hr", "password": values.get("DEV_LOGIN_PASSWORD")},
    )
    if response.status_code != 200:
        raise SystemExit("Local development login unavailable; no requests performed")
    client.headers["Authorization"] = "Bearer " + response.json()["token"]
    paths = [
        "/api/v1/hr/candidates",
        "/api/v1/hr/positions",
        "/api/v1/hr/workbench-live",
        "/api/v1/hr/ai-jobs",
    ]

    def run(i):
        started = time.perf_counter()
        try:
            status = client.get(paths[i % len(paths)]).status_code
        except httpx.HTTPError:
            status = 0
        return status, (time.perf_counter() - started) * 1000

    started = time.perf_counter()
    with ThreadPoolExecutor(args.concurrency) as pool:
        results = list(pool.map(run, range(args.requests)))
    elapsed = time.perf_counter() - started
latencies = sorted(ms for _, ms in results)
report = {
    "scope": "local Compose, current demo dataset, read-only requests",
    "requests": args.requests,
    "concurrency": args.concurrency,
    "errors": sum(status != 200 for status, _ in results),
    "elapsed_seconds": round(elapsed, 3),
    "requests_per_second": round(args.requests / elapsed, 2),
    "p50_ms": round(latencies[len(latencies) // 2], 2),
    "p95_ms": round(latencies[min(len(latencies) - 1, int(len(latencies) * 0.95))], 2),
    "max_ms": round(max(latencies), 2),
}
destination = root / "test-results" / "local-load.json"
destination.parent.mkdir(exist_ok=True)
destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
print(json.dumps(report))
if report["errors"]:
    raise SystemExit(1)
