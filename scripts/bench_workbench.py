"""看板 API 轻量压测：p50/p95/max，不写数据库。

用法：
  python scripts/bench_workbench.py --range last30 --requests 20 --concurrency 1
鉴权：设置 AGENT_API_TOKEN（未配置时后端 dev 放行）。
"""

from __future__ import annotations

import argparse
import os
import statistics
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor


def _one(url: str, token: str) -> tuple[int, float]:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as resp:
            resp.read()
            return resp.status, time.perf_counter() - started
    except Exception:
        return 0, time.perf_counter() - started


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8100")
    parser.add_argument("--range", default="last30")
    parser.add_argument("--requests", type=int, default=20)
    parser.add_argument("--concurrency", type=int, default=1)
    args = parser.parse_args()
    token = os.getenv("AGENT_API_TOKEN", "").strip()
    url = f"{args.base}/api/workbench/dashboard?range={args.range}&refresh=true"

    _one(url, token)  # warmup
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as pool:
        results = list(pool.map(lambda _: _one(url, token), range(args.requests)))
    total = time.perf_counter() - started

    ok = [elapsed for status, elapsed in results if status == 200]
    failed = len(results) - len(ok)
    if not ok:
        raise SystemExit(f"全部失败（{failed}/{len(results)}）")
    ok.sort()
    p50 = statistics.median(ok)
    p95 = ok[min(len(ok) - 1, int(len(ok) * 0.95))]
    print(
        f"range={args.range} requests={len(results)} concurrency={args.concurrency} "
        f"ok={len(ok)} failed={failed} total={total:.2f}s "
        f"p50={p50 * 1000:.1f}ms p95={p95 * 1000:.1f}ms max={ok[-1] * 1000:.1f}ms"
    )


if __name__ == "__main__":
    main()
