#!/usr/bin/env python3
"""
Prometheus Metrics Range Collector
Scrapes the Prometheus HTTP range query API (/api/v1/query_range)
at 15s intervals for all PromQL expressions in the feature catalog.
"""

import argparse
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

import numpy as np
import pandas as pd
import requests

DEFAULT_PROM_URL = os.environ.get("PROM_URL", "http://localhost:9090")

# PromQL query expressions from Feature Catalog
FEATURE_QUERIES: Dict[str, str] = {
    # Citadel CA Pipeline
    "csr_request_rate": 'sum(rate(citadel_server_csr_count[1m]))',
    "cert_issuance_rate": 'sum(rate(citadel_server_success_cert_issuance_count[1m]))',
    "csr_auth_err_rate": 'sum(rate(citadel_server_authentication_failure_count[1m]))',
    "csr_parse_err_rate": 'sum(rate(citadel_server_csr_parsing_err_count[1m]))',
    
    # Istiod Control Plane Resources
    "istiod_process_cpu": 'sum(rate(process_cpu_seconds_total{app="istiod"}[1m]))',
    "istiod_memory_bytes": 'sum(process_resident_memory_bytes{app="istiod"})',
    "istiod_cgroup_cpu": 'sum(rate(container_cpu_usage_seconds_total{namespace="istio-system",pod=~"istiod.*"}[1m]))',
    "pilot_xds_pushes": 'sum(rate(pilot_xds_pushes[1m]))',
    
    # Envoy Proxy & Traffic
    "envoy_cert_expiry_sec": 'min(istio_agent_cert_expiry_seconds)',
    "req_rate_total": 'sum(rate(istio_requests_total[1m]))',
    "req_rate_5xx": 'sum(rate(istio_requests_total{response_code=~"5.."}[1m]))',
    
    # Cluster & Pod Churn
    "pod_restarts_5m": 'sum(increase(kube_pod_container_status_restarts_total[5m]))',
    "node_ready_count": 'sum(kube_node_status_condition{condition="Ready",status="true"})'
}


def fetch_query_range(
    query: str,
    start_ts: float,
    end_ts: float,
    step: str = "15s",
    prom_url: str = DEFAULT_PROM_URL,
    timeout: int = 30
) -> pd.Series:
    """Execute a PromQL range query and return a pandas Series indexed by datetime."""
    endpoint = f"{prom_url.rstrip('/')}/api/v1/query_range"
    params = {
        "query": query,
        "start": str(start_ts),
        "end": str(end_ts),
        "step": step
    }

    try:
        resp = requests.get(endpoint, params=params, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") != "success":
            return pd.Series(dtype=float)

        results = data.get("data", {}).get("result", [])
        if not results:
            return pd.Series(dtype=float)

        # Use first returned series
        values = results[0].get("values", [])
        ts_dict = {}
        for item in values:
            epoch = float(item[0])
            val = float(item[1])
            dt = pd.to_datetime(epoch, unit="s", utc=True)
            ts_dict[dt] = val

        return pd.Series(ts_dict, dtype=float)
    except Exception as e:
        print(f"[WARN] Error fetching PromQL '{query}': {e}", file=sys.stderr)
        return pd.Series(dtype=float)


def collect_metrics_for_window(
    run_id: str,
    start_ts: float,
    end_ts: float,
    step: str = "15s",
    prom_url: str = DEFAULT_PROM_URL,
    output_dir: Optional[Path] = None
) -> pd.DataFrame:
    """Harvest all catalog metrics across the given window and return aligned DataFrame."""
    print(f"[COLLECTOR] Harvesting metrics for run '{run_id}' from {start_ts} to {end_ts} (step={step})...")
    series_map = {}

    for name, query in FEATURE_QUERIES.items():
        s = fetch_query_range(query, start_ts, end_ts, step=step, prom_url=prom_url)
        series_map[name] = s

    df = pd.DataFrame(series_map)
    df.index.name = "timestamp"

    # Fill NaN for counters that emit nothing during zero-error conditions
    zero_fill_cols = [
        "csr_auth_err_rate", "csr_parse_err_rate", "req_rate_5xx",
        "pod_restarts_5m", "req_rate_total", "pilot_xds_pushes"
    ]
    for col in zero_fill_cols:
        if col in df.columns:
            df[col] = df[col].fillna(0.0)

    # Forward fill resource gauges (memory, nodes) then backward fill
    df = df.ffill().bfill().fillna(0.0)

    # Add metadata
    df.insert(0, "run_id", run_id)
    df["timestamp_epoch"] = [int(ts.timestamp()) for ts in df.index]

    if output_dir:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        parquet_path = output_dir / "metrics.parquet"
        csv_path = output_dir / "metrics.csv"
        df.to_parquet(parquet_path)
        df.to_csv(csv_path)
        print(f"[COLLECTOR] Saved {len(df)} rows to {parquet_path} and {csv_path}")

    return df


def main():
    parser = argparse.ArgumentParser(description="Prometheus Metric Harvester")
    parser.add_argument("--run-id", type=str, default="run_test", help="Experiment Run ID")
    parser.add_argument("--start", type=float, default=None, help="Start epoch timestamp")
    parser.add_argument("--end", type=float, default=None, help="End epoch timestamp")
    parser.add_argument("--lookback", type=int, default=600, help="Lookback window in seconds if start/end not specified")
    parser.add_argument("--step", type=str, default="15s", help="Sample step resolution")
    parser.add_argument("--prom-url", type=str, default=DEFAULT_PROM_URL, help="Prometheus API URL")
    parser.add_argument("--output-dir", type=str, default=None, help="Output directory")
    args = parser.parse_args()

    end_ts = args.end if args.end is not None else time.time()
    start_ts = args.start if args.start is not None else (end_ts - args.lookback)

    project_root = Path(__file__).resolve().parent.parent
    out_dir = Path(args.output_dir) if args.output_dir else (project_root / "data" / "raw" / args.run_id)

    df = collect_metrics_for_window(
        run_id=args.run_id,
        start_ts=start_ts,
        end_ts=end_ts,
        step=args.step,
        prom_url=args.prom_url,
        output_dir=out_dir
    )
    print(f"[COLLECTOR] Successfully collected DataFrame with shape: {df.shape}")
    print(df.tail(3))


if __name__ == "__main__":
    main()
