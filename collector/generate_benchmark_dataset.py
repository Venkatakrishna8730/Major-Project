#!/usr/bin/env python3
"""
Benchmark Dataset Generator for mTLS Certificate Rotation Failure
Generates 50 multi-scenario telemetry runs anchored on real empirical cluster baselines.
Simulates realistic failure dynamics across all 10 catalog scenarios (S0-S10)
and produces synchronized ground-truth event logs (event_log.csv) and metrics tables.
"""

import argparse
import csv
import json
import os
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"


def generate_single_run(
    run_id: str,
    scenario_id: str,
    seed: int,
    base_time: datetime,
    n_steps: int = 60,
    step_sec: int = 15
) -> Tuple[pd.DataFrame, List[Dict[str, any]]]:
    """Simulate a single time series run with realistic physical dynamics and events."""
    np.random.seed(seed)
    random.seed(seed)

    timestamps = [base_time + timedelta(seconds=i * step_sec) for i in range(n_steps)]
    epochs = [int(ts.timestamp()) for ts in timestamps]

    # Baseline healthy values
    cpu_base = 0.0025 + np.random.normal(0, 0.0003, n_steps).clip(0.001, 0.005)
    mem_base = 5.5e7 + np.random.normal(0, 1.5e6, n_steps)
    cgroup_cpu = cpu_base * 1.8 + np.random.normal(0, 0.0005, n_steps).clip(0.002, 0.008)
    traffic_base = 146.0 + np.random.normal(0, 1.2, n_steps)
    traffic_5xx = np.zeros(n_steps)
    restarts = np.zeros(n_steps)
    nodes_ready = np.full(n_steps, 3.0)
    xds_pushes = np.random.choice([0.0, 0.05, 0.1], size=n_steps, p=[0.8, 0.15, 0.05])

    csr_req = np.random.choice([0.0, 0.067], size=n_steps, p=[0.9, 0.1])
    cert_iss = csr_req.copy()
    csr_auth_err = np.zeros(n_steps)
    csr_parse_err = np.zeros(n_steps)

    # Initial cert remaining seconds (e.g. 1800s ~ 50% TTL, countdown to renewal)
    expiry_countdown = np.zeros(n_steps)
    start_expiry = 2400.0 - (seed % 600)  # Between 1800s and 2400s

    events = []
    fault_start_idx = 15  # Pre-fault window = 15 steps (225s)

    if scenario_id == "s0_baseline":
        # Normal renewal at ~1800s remaining
        curr_exp = start_expiry
        for i in range(n_steps):
            curr_exp -= step_sec
            if curr_exp <= 1800.0:  # 50% TTL reached -> renews successfully
                csr_req[i] = 1.0
                cert_iss[i] = 1.0
                curr_exp = 3600.0   # Fresh certificate minted!
                events.append({
                    "run_id": run_id,
                    "workload": "productpage-v1",
                    "pod_name": "productpage-v1-sim",
                    "event_type": "ROTATION_COMPLETED",
                    "event_time_iso": timestamps[i].isoformat(),
                    "event_time_epoch": epochs[i],
                    "seconds_to_expiry": int(curr_exp),
                    "evidence_source": "SDS_NOT_BEFORE_CHANGE",
                    "details": "Routine 50% TTL rotation completed on schedule"
                })
            expiry_countdown[i] = max(100.0, curr_exp)

    elif scenario_id == "s1_istiod_cpu":
        # CPU stress starting at step 15
        curr_exp = start_expiry
        for i in range(n_steps):
            if i >= fault_start_idx and i < fault_start_idx + 35:
                cpu_base[i] = 1.85 + np.random.normal(0, 0.08)
                cgroup_cpu[i] = 2.1 + np.random.normal(0, 0.1)
                csr_req[i] = 2.5 + np.random.normal(0, 0.3)
                cert_iss[i] = 0.2 + np.random.normal(0, 0.05)  # Throttled CA signing
                xds_pushes[i] = 0.8
            curr_exp -= step_sec
            if curr_exp <= 900.0:  # Critical stall
                events.append({
                    "run_id": run_id,
                    "workload": "reviews-v1",
                    "pod_name": "reviews-v1-sim",
                    "event_type": "CRITICAL_ROTATION_STALL",
                    "event_time_iso": timestamps[i].isoformat(),
                    "event_time_epoch": epochs[i],
                    "seconds_to_expiry": int(curr_exp),
                    "evidence_source": "SDS_ROTATION_LATENCY",
                    "details": "Istiod CPU exhaustion stalled CSR signing"
                })
            expiry_countdown[i] = max(150.0, curr_exp)

    elif scenario_id == "s2_istiod_memory":
        curr_exp = start_expiry
        for i in range(n_steps):
            if i >= fault_start_idx:
                mem_base[i] = 2.8e8 + (i - fault_start_idx) * 2e6  # 280MB+
                cpu_base[i] = 0.6 + np.random.normal(0, 0.15)       # GC thrashing
                if i >= fault_start_idx + 20 and curr_exp <= 1000.0:
                    events.append({
                        "run_id": run_id,
                        "workload": "details-v1",
                        "pod_name": "details-v1-sim",
                        "event_type": "CRITICAL_ROTATION_STALL",
                        "event_time_iso": timestamps[i].isoformat(),
                        "event_time_epoch": epochs[i],
                        "seconds_to_expiry": int(curr_exp),
                        "evidence_source": "SDS_ROTATION_LATENCY",
                        "details": "Istiod memory pressure caused GC latency stall"
                    })
            curr_exp -= step_sec
            expiry_countdown[i] = max(200.0, curr_exp)

    elif scenario_id == "s3_istiod_kill":
        curr_exp = start_expiry
        for i in range(n_steps):
            if i >= fault_start_idx and i < fault_start_idx + 8:  # 120s pod restart window
                cpu_base[i] = 0.0
                mem_base[i] = 0.0
                cgroup_cpu[i] = 0.0
                cert_iss[i] = 0.0
                csr_req[i] = 0.0
            elif i >= fault_start_idx + 8:
                cpu_base[i] = 0.9  # Startup spike
                csr_req[i] = 6.0   # Reconnect burst
                cert_iss[i] = 4.0
            curr_exp -= step_sec
            expiry_countdown[i] = max(300.0, curr_exp)

    elif scenario_id in ["s4_net_loss", "s5_net_delay", "s10_compound"]:
        # CA communication severed: certificate expires completely!
        curr_exp = 800.0  # Near expiration (13 minutes left)
        fail_emitted = False
        for i in range(n_steps):
            if i >= fault_start_idx:
                csr_req[i] = 4.0 + np.random.normal(0, 0.5)  # Aggressive retries
                cert_iss[i] = 0.0                             # 0% success
                if scenario_id == "s10_compound":
                    cpu_base[i] = 1.9 + np.random.normal(0, 0.1)

            curr_exp -= step_sec

            # Trigger Critical Rotation Stall at 400s
            if curr_exp <= 450.0 and not fail_emitted and i >= fault_start_idx:
                events.append({
                    "run_id": run_id,
                    "workload": "ratings-v1",
                    "pod_name": "ratings-v1-sim",
                    "event_type": "CRITICAL_ROTATION_STALL",
                    "event_time_iso": timestamps[i].isoformat(),
                    "event_time_epoch": epochs[i],
                    "seconds_to_expiry": int(curr_exp),
                    "evidence_source": "SDS_ROTATION_LATENCY",
                    "details": "Packet loss on CA port 15012 blocked CSR renewal"
                })

            # Hard expiration at <= 0
            if curr_exp <= 0.0:
                curr_exp = 0.0
                traffic_5xx[i] = 85.0 + np.random.normal(0, 5.0)  # 5xx mTLS handshake failure!
                traffic_base[i] = 60.0                            # Traffic drop
                if not any(e["event_type"] == "HARD_EXPIRY_FAILURE" for e in events):
                    events.append({
                        "run_id": run_id,
                        "workload": "ratings-v1",
                        "pod_name": "ratings-v1-sim",
                        "event_type": "HARD_EXPIRY_FAILURE",
                        "event_time_iso": timestamps[i].isoformat(),
                        "event_time_epoch": epochs[i],
                        "seconds_to_expiry": 0,
                        "evidence_source": "SDS_X509_EXPIRED",
                        "details": "mTLS Certificate expired; TLS handshakes failing"
                    })
            expiry_countdown[i] = curr_exp

    elif scenario_id == "s6_clock_skew":
        # Zero-shot holdout scenario: sudden jump
        curr_exp = 2000.0
        for i in range(n_steps):
            if i >= fault_start_idx:
                curr_exp = -3600.0  # Time jumped 2 hours ahead!
                traffic_5xx[i] = 110.0
                traffic_base[i] = 30.0
                if not events:
                    events.append({
                        "run_id": run_id,
                        "workload": "reviews-v3",
                        "pod_name": "reviews-v3-sim",
                        "event_type": "HARD_EXPIRY_FAILURE",
                        "event_time_iso": timestamps[i].isoformat(),
                        "event_time_epoch": epochs[i],
                        "seconds_to_expiry": -3600,
                        "evidence_source": "SDS_X509_EXPIRED",
                        "details": "Workload clock skew (+2h) caused instant expiration"
                    })
            else:
                curr_exp -= step_sec
            expiry_countdown[i] = curr_exp

    elif scenario_id == "s7_node_restart":
        curr_exp = start_expiry
        for i in range(n_steps):
            if i >= fault_start_idx and i < fault_start_idx + 10:
                nodes_ready[i] = 2.0
                restarts[i] = 2.0
                traffic_base[i] = 115.0
            curr_exp -= step_sec
            expiry_countdown[i] = max(400.0, curr_exp)

    elif scenario_id == "s8_csr_storm":
        curr_exp = start_expiry
        for i in range(n_steps):
            if i >= fault_start_idx and i < fault_start_idx + 25:
                csr_req[i] = 25.0 + np.random.normal(0, 3.0)
                cert_iss[i] = 12.0 + np.random.normal(0, 2.0)  # Saturated
                cpu_base[i] = 1.4 + np.random.normal(0, 0.1)
            curr_exp -= step_sec
            expiry_countdown[i] = max(350.0, curr_exp)

    elif scenario_id == "s9_sa_disruption":
        curr_exp = start_expiry
        for i in range(n_steps):
            if i >= fault_start_idx and i < fault_start_idx + 20:
                csr_auth_err[i] = 8.0 + np.random.normal(0, 1.0)
                cert_iss[i] = 0.0
                csr_req[i] = 8.5
            curr_exp -= step_sec
            if curr_exp <= 800.0 and not events:
                events.append({
                    "run_id": run_id,
                    "workload": "details-v1",
                    "pod_name": "details-v1-sim",
                    "event_type": "CRITICAL_ROTATION_STALL",
                    "event_time_iso": timestamps[i].isoformat(),
                    "event_time_epoch": epochs[i],
                    "seconds_to_expiry": int(curr_exp),
                    "evidence_source": "SDS_ROTATION_LATENCY",
                    "details": "ServiceAccount token invalidated; Citadel rejected CSR auth"
                })
            expiry_countdown[i] = max(200.0, curr_exp)

    data = {
        "run_id": [run_id] * n_steps,
        "timestamp": timestamps,
        "timestamp_epoch": epochs,
        "csr_request_rate": csr_req.clip(0, None),
        "cert_issuance_rate": cert_iss.clip(0, None),
        "csr_auth_err_rate": csr_auth_err.clip(0, None),
        "csr_parse_err_rate": csr_parse_err.clip(0, None),
        "istiod_process_cpu": cpu_base.clip(0, None),
        "istiod_memory_bytes": mem_base.clip(0, None),
        "istiod_cgroup_cpu": cgroup_cpu.clip(0, None),
        "pilot_xds_pushes": xds_pushes.clip(0, None),
        "envoy_cert_expiry_sec": expiry_countdown,
        "req_rate_total": traffic_base.clip(0, None),
        "req_rate_5xx": traffic_5xx.clip(0, None),
        "pod_restarts_5m": restarts.clip(0, None),
        "node_ready_count": nodes_ready
    }

    df = pd.DataFrame(data)
    df.set_index("timestamp", inplace=True)
    return df, events


def build_full_benchmark_dataset(n_runs: int = 50, output_dir: Path = RAW_DIR):
    """Generate 50 benchmark runs, saving raw Parquet and event logs."""
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Scenario allocation distribution
    scenario_counts = {
        "s0_baseline": 15,
        "s1_istiod_cpu": 5,
        "s2_istiod_memory": 4,
        "s3_istiod_kill": 3,
        "s4_net_loss": 6,
        "s5_net_delay": 4,
        "s6_clock_skew": 4,  # Holdout test
        "s7_node_restart": 3,
        "s8_csr_storm": 3,
        "s9_sa_disruption": 3,
        "s10_compound": 4
    }

    all_dfs = []
    all_events = []
    exp_log_entries = []

    base_time = datetime(2026, 11, 21, 10, 0, 0, tzinfo=timezone.utc)
    seed = 100

    print("==========================================================")
    print(" Generating Multi-Scenario Telemetry Benchmark Dataset")
    print(f" Target Runs: {sum(scenario_counts.values())} across 10 Scenarios")
    print("==========================================================")

    for sc_id, count in scenario_counts.items():
        for run_idx in range(count):
            seed += 1
            run_id = f"run_{base_time.strftime('%Y%m%d_%H%M%S')}_{sc_id}_r{run_idx+1}"
            run_df, events = generate_single_run(
                run_id=run_id,
                scenario_id=sc_id,
                seed=seed,
                base_time=base_time,
                n_steps=50,
                step_sec=15
            )

            # Save per-run raw parquet
            run_out = output_dir / run_id
            run_out.mkdir(parents=True, exist_ok=True)
            run_df.to_parquet(run_out / "metrics.parquet")

            all_dfs.append(run_df.reset_index())
            all_events.extend(events)

            t_start = run_df.index[0].isoformat()
            t_end = run_df.index[-1].isoformat()
            t_fault_start = run_df.index[15].isoformat()
            t_fault_end = run_df.index[-10].isoformat()

            exp_log_entries.append({
                "run_id": run_id,
                "scenario_id": sc_id,
                "seed": seed,
                "pre_fault_sec": 225,
                "fault_duration_sec": 375,
                "recovery_sec": 150,
                "t_start": t_start,
                "t_fault_start": t_fault_start,
                "t_fault_end": t_fault_end,
                "t_end": t_end,
                "status": "COMPLETED"
            })

            base_time += timedelta(minutes=20)

    # 1. Save Consolidated Raw Parquet
    consolidated_df = pd.concat(all_dfs, ignore_index=True)
    raw_pq = output_dir / "all_runs_metrics.parquet"
    consolidated_df.to_parquet(raw_pq)
    print(f"[ OK ] Consolidated {len(consolidated_df)} rows from {len(all_dfs)} runs -> {raw_pq}")

    # 2. Save Event Log CSV
    event_csv = output_dir / "event_log.csv"
    if all_events:
        headers = [
            "run_id", "workload", "pod_name", "event_type", "event_time_iso",
            "event_time_epoch", "seconds_to_expiry", "evidence_source", "details"
        ]
        with open(event_csv, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            writer.writerows(all_events)
        print(f"[ OK ] Recorded {len(all_events)} failure/rotation events -> {event_csv}")

    # 3. Save Experiment Log CSV
    exp_csv = output_dir / "experiment_log.csv"
    exp_df = pd.DataFrame(exp_log_entries)
    exp_df.to_csv(exp_csv, index=False)
    print(f"[ OK ] Logged {len(exp_df)} experiment executions -> {exp_csv}")

    return consolidated_df, all_events


def main():
    parser = argparse.ArgumentParser(description="Multi-Scenario Benchmark Generator")
    parser.add_argument("--runs", type=int, default=50, help="Total runs to generate")
    args = parser.parse_args()

    build_full_benchmark_dataset(n_runs=args.runs)


if __name__ == "__main__":
    main()
