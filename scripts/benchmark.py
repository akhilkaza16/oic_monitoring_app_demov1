from __future__ import annotations

import argparse
import os
import statistics
import time
from dataclasses import dataclass
from pathlib import Path

import requests


def _load_backend_url_from_env() -> str:
    direct = os.environ.get("REACT_APP_BACKEND_URL", "").strip()
    if direct:
        return direct.rstrip("/")

    env_path = Path("/app/frontend/.env")
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("REACT_APP_BACKEND_URL="):
                value = line.split("=", 1)[1].strip()
                if value:
                    return value.rstrip("/")

    raise RuntimeError("REACT_APP_BACKEND_URL is required (env variable or /app/frontend/.env)")


@dataclass
class BenchResult:
    endpoint: str
    samples_ms: list[float]

    @property
    def avg(self) -> float:
        return statistics.mean(self.samples_ms)

    @property
    def p95(self) -> float:
        return sorted(self.samples_ms)[int(len(self.samples_ms) * 0.95) - 1]

    @property
    def max(self) -> float:
        return max(self.samples_ms)


def measure(base_url: str, endpoint: str, runs: int) -> BenchResult:
    samples: list[float] = []
    for _ in range(runs):
        start = time.perf_counter()
        response = requests.get(f"{base_url}{endpoint}", timeout=10)
        response.raise_for_status()
        samples.append((time.perf_counter() - start) * 1000)
    return BenchResult(endpoint=endpoint, samples_ms=samples)


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark badger-oic-monitor read endpoints")
    parser.add_argument("--base-url", default="")
    parser.add_argument("--runs", type=int, default=10)
    args = parser.parse_args()

    resolved_base = args.base_url.strip() or f"{_load_backend_url_from_env()}/api"
    base_url = resolved_base.rstrip("/")

    print(f"Benchmarking {base_url} with {args.runs} runs per endpoint")

    summary = measure(base_url, "/executive-summary", args.runs)
    integrations = measure(base_url, "/integrations?limit=40&offset=0", args.runs)

    list_response = requests.get(f"{base_url}/integrations?limit=1&offset=0", timeout=10)
    list_response.raise_for_status()
    first_item = list_response.json()["items"][0]
    detail = measure(base_url, f"/integrations/{first_item['integration_id']}", args.runs)

    latency_logs = requests.get(
        f"{base_url}/latency-logs?limit=5",
        timeout=10,
    )
    latency_logs.raise_for_status()

    results = [summary, integrations, detail]

    print("\nEndpoint latency report (ms):")
    for result in results:
        print(
            f"- {result.endpoint}: avg={result.avg:.2f} p95={result.p95:.2f} max={result.max:.2f}"
        )

    print("\nRecent API latency logs from backend:")
    for entry in latency_logs.json():
        print(
            f"- {entry['endpoint']} {entry['method']} {entry['latency_ms']:.2f}ms at {entry['created_at']}"
        )


if __name__ == "__main__":
    main()
