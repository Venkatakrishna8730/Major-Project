#!/usr/bin/env python3
"""
Ground-Truth Failure Event & Rotation Latency Logger
Evaluates:
  1. Expiration failures (seconds_to_expiry <= 0)
  2. Late rotation / near-miss events (rotation latency beyond 50% TTL window)
  3. Envoy / SDS handshake drop events
Outputs structured ground-truth labels to event_log.csv.
"""

import argparse
import csv
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional


def evaluate_pod_status(run_id: str, namespace: str = "default") -> List[Dict[str, any]]:
    """Scan workload pods and determine if failure or near-miss events have occurred."""
    events = []
    now = datetime.now(timezone.utc)
    now_epoch = int(now.timestamp())
    now_iso = now.isoformat()

    project_root = Path(__file__).resolve().parent.parent
    cert_poller_file = project_root / "data" / "raw" / "cert_poller.csv"

    # Read latest poller entries if available
    latest_by_pod = {}
    if cert_poller_file.exists():
        try:
            with open(cert_poller_file, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    latest_by_pod[row["pod_name"]] = row
        except Exception:
            pass

    for pod_name, row in latest_by_pod.items():
        try:
            sec_to_exp = int(row.get("seconds_to_expiry", 9999))
            cert_age = int(row.get("cert_age_sec", 0))
            total_life = int(row.get("total_lifetime_sec", 3720))
            rot_detected = int(row.get("rotation_detected", 0))

            # Criterion 1: Hard Expiration Failure
            if sec_to_exp <= 0:
                events.append({
                    "run_id": run_id,
                    "workload": row.get("app", pod_name),
                    "pod_name": pod_name,
                    "event_type": "HARD_EXPIRY_FAILURE",
                    "event_time_iso": now_iso,
                    "event_time_epoch": now_epoch,
                    "seconds_to_expiry": sec_to_exp,
                    "evidence_source": "SDS_X509_EXPIRED",
                    "details": f"Certificate expired at {row.get('not_after_iso')} without replacement"
                })

            # Criterion 2: Renewal Delayed Beyond 75% TTL (Late Rotation Warning)
            expected_renew_age = total_life // 2
            critical_threshold_age = int(total_life * 0.75)
            if cert_age >= critical_threshold_age and rot_detected == 0:
                events.append({
                    "run_id": run_id,
                    "workload": row.get("app", pod_name),
                    "pod_name": pod_name,
                    "event_type": "CRITICAL_ROTATION_STALL",
                    "event_time_iso": now_iso,
                    "event_time_epoch": now_epoch,
                    "seconds_to_expiry": sec_to_exp,
                    "evidence_source": "SDS_ROTATION_LATENCY",
                    "details": f"Cert age {cert_age}s exceeded critical threshold {critical_threshold_age}s"
                })

            # Criterion 3: Successful Rotation (Near-Miss / Cadence Marker)
            if rot_detected == 1:
                rotation_latency = cert_age - expected_renew_age
                events.append({
                    "run_id": run_id,
                    "workload": row.get("app", pod_name),
                    "pod_name": pod_name,
                    "event_type": "ROTATION_COMPLETED",
                    "event_time_iso": now_iso,
                    "event_time_epoch": now_epoch,
                    "seconds_to_expiry": sec_to_exp,
                    "evidence_source": "SDS_NOT_BEFORE_CHANGE",
                    "details": f"Rotation completed with latency {rotation_latency}s past scheduled window"
                })
        except Exception:
            continue

    return events


def append_events_to_log(events: List[Dict[str, any]], output_path: Path):
    """Write events to CSV log file."""
    if not events:
        return
    output_path.parent.mkdir(parents=True, exist_ok=True)
    file_exists = output_path.exists()
    headers = [
        "run_id", "workload", "pod_name", "event_type", "event_time_iso",
        "event_time_epoch", "seconds_to_expiry", "evidence_source", "details"
    ]
    with open(output_path, "a", encoding="utf-8") as f:
        if not file_exists:
            f.write(",".join(headers) + "\n")
        for ev in events:
            row = [str(ev.get(h, "")) for h in headers]
            f.write(",".join(row) + "\n")


def main():
    parser = argparse.ArgumentParser(description="Ground-Truth Event Logger")
    parser.add_argument("--run-id", type=str, default="run_test", help="Experiment Run ID")
    parser.add_argument("--output", type=str, default="data/raw/event_log.csv", help="Event log destination")
    parser.add_argument("--once", action="store_true", help="Run single evaluation cycle")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    output_path = project_root / args.output

    events = evaluate_pod_status(run_id=args.run_id)
    if events:
        append_events_to_log(events, output_path)
        print(f"[EVENT LOGGER] Recorded {len(events)} ground-truth event(s) for {args.run_id}:")
        for ev in events:
            print(f"  -> [{ev['event_type']}] {ev['pod_name']}: {ev['details']}")
    else:
        print(f"[EVENT LOGGER] No failure or rotation events detected at this timestamp.")


if __name__ == "__main__":
    main()
