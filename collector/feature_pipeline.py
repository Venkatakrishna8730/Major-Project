#!/usr/bin/env python3
"""
Feature Engineering, Horizon Labeling & Dataset Split Pipeline
Builds leakage-safe, versioned feature tables (Parquet) combining:
  1. PromQL instantaneous telemetry metrics
  2. Rolling statistical aggregations (mean, max, std over 1m, 5m, 15m)
  3. First-order velocity derivatives (slopes)
  4. Dynamic CA health ratios
  5. Horizon-based binary labels (H=5m, 10m, 15m)
  6. Leak-free run-level train/validation/test partitioning
"""

import argparse
import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


def compute_derived_ratios_and_slopes(df: pd.DataFrame) -> pd.DataFrame:
    """Compute physical domain ratios and velocity slopes."""
    df = df.copy()

    # 1. CSR Success Ratio (CA signing throughput health)
    eps = 1e-4
    if "cert_issuance_rate" in df.columns and "csr_request_rate" in df.columns:
        df["csr_success_ratio"] = df["cert_issuance_rate"] / (df["csr_request_rate"] + eps)
    else:
        df["csr_success_ratio"] = 1.0

    # 2. 5xx Error Ratio
    if "req_rate_5xx" in df.columns and "req_rate_total" in df.columns:
        df["error_5xx_ratio"] = df["req_rate_5xx"] / (df["req_rate_total"] + eps)
    else:
        df["error_5xx_ratio"] = 0.0

    # 3. First-order derivatives (1-step slope and 4-step/1m slope)
    slope_signals = ["istiod_process_cpu", "istiod_memory_bytes", "csr_request_rate", "envoy_cert_expiry_sec"]
    for sig in slope_signals:
        if sig in df.columns:
            df[f"{sig}_slope_15s"] = df[sig].diff(1).fillna(0.0)
            df[f"{sig}_slope_1m"] = df[sig].diff(4).fillna(0.0)

    return df


def compute_rolling_features(df: pd.DataFrame, step_sec: int = 15) -> pd.DataFrame:
    """Compute rolling window aggregations (mean, max, std)."""
    df = df.copy()

    # Define window sizes in terms of rows (15s steps)
    windows = {
        "1m": max(1, 60 // step_sec),       # 4 rows
        "5m": max(1, 300 // step_sec),      # 20 rows
        "15m": max(1, 900 // step_sec)      # 60 rows
    }

    core_signals = [
        "istiod_process_cpu",
        "istiod_memory_bytes",
        "csr_request_rate",
        "csr_success_ratio",
        "req_rate_total",
        "envoy_cert_expiry_sec"
    ]

    for win_name, win_size in windows.items():
        for sig in core_signals:
            if sig in df.columns:
                roller = df[sig].rolling(window=win_size, min_periods=1)
                df[f"{sig}_mean_{win_name}"] = roller.mean()
                df[f"{sig}_max_{win_name}"] = roller.max()
                df[f"{sig}_std_{win_name}"] = roller.std().fillna(0.0)

    return df


def apply_horizon_labels(
    df: pd.DataFrame,
    events_df: Optional[pd.DataFrame],
    horizons: Dict[str, int] = {"H5": 300, "H10": 600, "H15": 900}
) -> pd.DataFrame:
    """Generate horizon binary labels (y=1 if failure in (t, t+H]) and mark active failure states."""
    df = df.copy()

    # Default labels
    for h_name in horizons.keys():
        df[f"label_{h_name}"] = 0
    df["already_failing"] = 0

    if events_df is None or events_df.empty:
        return df

    # Filter failure events
    fail_events = events_df[events_df["event_type"].isin(["HARD_EXPIRY_FAILURE", "CRITICAL_ROTATION_STALL"])]
    if fail_events.empty:
        return df

    # Find failure epoch timestamps for matching run_id or global
    for idx, row in df.iterrows():
        t_now = row.get("timestamp_epoch", 0)
        run_id = row.get("run_id", "")

        # Check failures matching this run
        run_fails = fail_events[fail_events["run_id"] == run_id] if "run_id" in fail_events.columns else fail_events
        fail_times = run_fails["event_time_epoch"].astype(float).values

        # Check if currently already in failure
        if any(t_fail <= t_now for t_fail in fail_times):
            # Mark already failing if cert expiry <= 0 or failure occurred
            if row.get("envoy_cert_expiry_sec", 9999) <= 0:
                df.at[idx, "already_failing"] = 1

        # Evaluate prediction horizons
        for h_name, h_sec in horizons.items():
            if any(t_now < t_fail <= (t_now + h_sec) for t_fail in fail_times):
                df.at[idx, f"label_{h_name}"] = 1

    return df


def assign_leakage_free_splits(
    df: pd.DataFrame,
    train_ratio: float = 0.70,
    val_ratio: float = 0.15,
    test_ratio: float = 0.15,
    holdout_scenario: str = "s6_clock_skew",
    random_seed: int = 42
) -> pd.DataFrame:
    """Assign train/val/test splits strictly partitioned by experiment run_id."""
    df = df.copy()
    unique_runs = df["run_id"].unique()
    np.random.seed(random_seed)

    split_map = {}
    holdout_runs = [r for r in unique_runs if holdout_scenario in r]
    regular_runs = [r for r in unique_runs if holdout_scenario not in r]

    # Assign holdout scenario
    for r in holdout_runs:
        split_map[r] = "holdout_test"

    # Shuffle regular runs
    shuffled = np.random.permutation(regular_runs)
    n_total = len(shuffled)
    n_train = max(1, int(n_total * train_ratio))
    n_val = max(1, int(n_total * val_ratio))

    for i, r in enumerate(shuffled):
        if i < n_train:
            split_map[r] = "train"
        elif i < (n_train + n_val):
            split_map[r] = "val"
        else:
            split_map[r] = "test"

    df["dataset_split"] = df["run_id"].map(split_map)
    return df


def process_features_and_export(
    raw_metrics_path: Path,
    events_log_path: Optional[Path],
    output_parquet: Path,
    output_csv: Optional[Path] = None
) -> pd.DataFrame:
    """End-to-end feature engineering and export pipeline."""
    print(f"[PIPELINE] Loading raw metrics from: {raw_metrics_path}")
    if raw_metrics_path.suffix == ".parquet":
        raw_df = pd.read_parquet(raw_metrics_path)
    else:
        raw_df = pd.read_csv(raw_metrics_path)

    events_df = None
    if events_log_path and events_log_path.exists():
        try:
            events_df = pd.read_csv(events_log_path)
            print(f"[PIPELINE] Loaded {len(events_df)} event log entries.")
        except Exception:
            pass

    # Step 1: Compute derived ratios & velocity slopes
    print("[PIPELINE] Computing dynamic ratios and first-order slopes...")
    feat_df = compute_derived_ratios_and_slopes(raw_df)

    # Step 2: Compute rolling window features
    print("[PIPELINE] Computing rolling aggregations (1m, 5m, 15m)...")
    feat_df = compute_rolling_features(feat_df)

    # Step 3: Apply horizon binary labels
    print("[PIPELINE] Applying horizon labels (H5, H10, H15)...")
    feat_df = apply_horizon_labels(feat_df, events_df)

    # Step 4: Assign leak-free splits by run_id
    print("[PIPELINE] Assigning leak-free run-level splits...")
    feat_df = assign_leakage_free_splits(feat_df)

    # Step 5: Export dataset
    output_parquet.parent.mkdir(parents=True, exist_ok=True)
    feat_df.to_parquet(output_parquet)
    print(f"[PIPELINE] Exported {len(feat_df)} rows and {len(feat_df.columns)} features to: {output_parquet}")

    if output_csv:
        feat_df.to_csv(output_csv)
        print(f"[PIPELINE] Exported CSV copy to: {output_csv}")

    return feat_df


def main():
    parser = argparse.ArgumentParser(description="Feature Engineering & Dataset Build Pipeline")
    parser.add_argument("--metrics", type=str, default="data/raw/smoke_test_run/metrics.parquet", help="Raw metrics input file")
    parser.add_argument("--events", type=str, default="data/raw/event_log.csv", help="Event log input file")
    parser.add_argument("--output-parquet", type=str, default="data/processed/features_v1.parquet", help="Output Parquet path")
    parser.add_argument("--output-csv", type=str, default="data/processed/features_v1.csv", help="Output CSV path")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    metrics_path = project_root / args.metrics
    events_path = project_root / args.events
    out_pq = project_root / args.output_parquet
    out_csv = project_root / args.output_csv

    df = process_features_and_export(metrics_path, events_path, out_pq, out_csv)
    print("\n[PIPELINE] Feature processing summary:")
    print(f"  Rows                : {len(df)}")
    print(f"  Total Features      : {len(df.columns)}")
    print(f"  Split Distribution  : {df['dataset_split'].value_counts().to_dict()}")
    print(f"  H10 Label Balance   : {df['label_H10'].value_counts().to_dict()}")


if __name__ == "__main__":
    main()
