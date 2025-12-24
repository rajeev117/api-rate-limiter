from __future__ import annotations

import argparse
import concurrent.futures
import random
import statistics
import time
import urllib.error
import urllib.request
from collections import Counter
from dataclasses import dataclass


@dataclass(frozen=True)
class Result:
    status: int
    latency_ms: float


def _one_request(url: str, timeout_s: float, headers: dict[str, str]) -> Result:
    start = time.perf_counter()
    req = urllib.request.Request(url, method="GET", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            status = resp.status
            resp.read()  # drain
    except urllib.error.HTTPError as e:
        status = e.code
        _ = e.read()
    end = time.perf_counter()
    return Result(status=status, latency_ms=(end - start) * 1000.0)


def main() -> int:
    p = argparse.ArgumentParser(description="Tiny concurrent load test for /limited")
    p.add_argument("--url", default="http://localhost:8000/limited")
    p.add_argument("--requests", type=int, default=200)
    p.add_argument("--concurrency", type=int, default=25)
    p.add_argument("--timeout", type=float, default=2.0)

    client = p.add_mutually_exclusive_group()
    client.add_argument(
        "--single-client",
        action="store_true",
        help="All requests use the same client identity (expect 429s).",
    )
    client.add_argument(
        "--unique-clients",
        action="store_true",
        help="Vary X-Real-IP per request to simulate many clients (expect fewer 429s).",
    )

    args = p.parse_args()

    if args.requests <= 0:
        raise SystemExit("--requests must be > 0")
    if args.concurrency <= 0:
        raise SystemExit("--concurrency must be > 0")

    base_headers = {"User-Agent": "rate-limiter-load-test"}

    def headers_for_request(i: int) -> dict[str, str]:
        if args.unique_clients:
            # 10.0.0.0/8 pseudo-random client IPs
            ip = f"10.{random.randint(0, 255)}.{random.randint(0, 255)}.{random.randint(1, 254)}"
            return {**base_headers, "X-Real-IP": ip}
        # Default: same client (or let server infer socket addr)
        if args.single_client:
            return {**base_headers, "X-Real-IP": "10.0.0.1"}
        return base_headers

    results: list[Result] = []
    start = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        futs = [
            ex.submit(_one_request, args.url, args.timeout, headers_for_request(i))
            for i in range(args.requests)
        ]
        for fut in concurrent.futures.as_completed(futs):
            results.append(fut.result())
    total_s = time.perf_counter() - start

    counts = Counter(r.status for r in results)
    latencies = [r.latency_ms for r in results]

    def pct(p: float) -> float:
        if not latencies:
            return 0.0
        k = max(0, min(len(latencies) - 1, int(round((p / 100.0) * (len(latencies) - 1)))))
        return sorted(latencies)[k]

    print(f"URL: {args.url}")
    print(f"Requests: {args.requests}, Concurrency: {args.concurrency}, Time: {total_s:.3f}s")
    print("Status counts:")
    for code in sorted(counts):
        print(f"  {code}: {counts[code]}")

    print("Latency (ms):")
    print(f"  mean={statistics.mean(latencies):.2f}")
    print(f"  p50={pct(50):.2f}  p90={pct(90):.2f}  p99={pct(99):.2f}")

    # Exit non-zero if there were connection-level failures.
    if 0 in counts:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
