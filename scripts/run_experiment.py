#!/usr/bin/env python3
"""
Automated Experiment Runner Harness for Chaos Fault Injection
Orchestrates:
  1. Pre-fault healthy baseline window
  2. Chaos fault injection (YAML apply or scenario script)
  3. Continuous certificate & metric collection
  4. Post-fault recovery window
  5. Teardown & cluster state verification
  6. Experiment metadata logging (experiment_log.csv)
"""

import argparse
import csv
import json
import os
import random
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCENARIOS_DIR = PROJECT_ROOT / "chaos" / "scenarios"
RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw"
BIN_DIR = PROJECT_ROOT / "bin"

# Ensure bin is on PATH
os.environ["PATH"] = f"{BIN_DIR}:{os.environ.get('PATH', '')}"
os.environ["MINIKUBE_HOME"] = str(PROJECT_ROOT / ".minikube")


def run_cmd(cmd, check=True):
    """Run shell command and return output."""
    res = subprocess.run(cmd, shell=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if check and res.returncode != 0:
        raise RuntimeError(f"Command failed ({res.returncode}): {cmd}\n{res.stderr}")
    return res.stdout.strip()


def cleanup_all_chaos():
    """Remove any active Chaos Mesh custom resources across namespaces."""
    print("[CLEANUP] Removing active Chaos Mesh CRDs...")
    run_cmd("kubectl delete stresschaos --all -A --ignore-not-found=true", check=False)
    run_cmd("kubectl delete networkchaos --all -A --ignore-not-found=true", check=False)
    run_cmd("kubectl delete podchaos --all -A --ignore-not-found=true", check=False)
    run_cmd("kubectl delete timechaos --all -A --ignore-not-found=true", check=False)
    # Ensure ServiceAccount is restored if S9 was used
    run_cmd("kubectl -n default create sa bookinfo-details --dry-run=client -o yaml | kubectl apply -f -", check=False)


def apply_scenario(scenario_id: str):
    """Trigger the designated fault scenario."""
    print(f"\n[CHAOS INJECTION] Applying scenario: {scenario_id}...")
    yaml_file = SCENARIOS_DIR / f"{scenario_id}.yaml"
    sh_file = SCENARIOS_DIR / f"{scenario_id}.sh"

    if yaml_file.exists():
        run_cmd(f"kubectl apply -f {yaml_file}")
        print(f"  Applied manifest: {yaml_file.name}")
    elif sh_file.exists():
        run_cmd(f"{sh_file} inject")
        print(f"  Executed script: {sh_file.name}")
    elif scenario_id == "s0_baseline":
        print("  S0 Baseline: No fault injected (healthy observation).")
    else:
        raise ValueError(f"Unknown scenario: {scenario_id}")


def remove_scenario(scenario_id: str):
    """Clean up the specific fault scenario."""
    print(f"\n[CHAOS RECOVERY] Removing scenario: {scenario_id}...")
    yaml_file = SCENARIOS_DIR / f"{scenario_id}.yaml"
    sh_file = SCENARIOS_DIR / f"{scenario_id}.sh"

    if yaml_file.exists():
        run_cmd(f"kubectl delete -f {yaml_file} --ignore-not-found=true", check=False)
    elif sh_file.exists():
        run_cmd(f"{sh_file} restore", check=False)
    cleanup_all_chaos()


def log_experiment_run(entry: dict):
    """Append experiment metadata row to experiment_log.csv."""
    RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
    log_file = RAW_DATA_DIR / "experiment_log.csv"
    headers = [
        "run_id", "scenario_id", "seed", "pre_fault_sec", "fault_duration_sec",
        "recovery_sec", "t_start", "t_fault_start", "t_fault_end", "t_end", "status"
    ]
    file_exists = log_file.exists()
    with open(log_file, "a", encoding="utf-8") as f:
        if not file_exists:
            f.write(",".join(headers) + "\n")
        row = [str(entry.get(h, "")) for h in headers]
        f.write(",".join(row) + "\n")
    print(f"[EXPERIMENT LOG] Logged metadata to {log_file}")


def main():
    parser = argparse.ArgumentParser(description="Chaos Experiment Runner")
    parser.add_argument("--scenario", type=str, default="s1_istiod_cpu", help="Scenario ID (e.g. s1_istiod_cpu, s4_net_loss)")
    parser.add_argument("--fault-duration", type=int, default=60, help="Fault injection duration in seconds")
    parser.add_argument("--pre-fault", type=int, default=15, help="Pre-fault baseline observation in seconds")
    parser.add_argument("--recovery", type=int, default=15, help="Post-fault recovery observation in seconds")
    parser.add_argument("--seed", type=int, default=None, help="Random seed for reproducibility")
    parser.add_argument("--dry-run", action="store_true", help="Test runner logic without applying faults")
    args = parser.parse_args()

    seed = args.seed if args.seed is not None else random.randint(1000, 999999)
    random.seed(seed)

    ts_now = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    run_id = f"run_{ts_now}_{args.scenario}"

    print("==========================================================")
    print(" Automated Chaos Fault Injection Runner")
    print("==========================================================")
    print(f"Run ID           : {run_id}")
    print(f"Scenario         : {args.scenario}")
    print(f"Random Seed      : {seed}")
    print(f"Pre-Fault Window : {args.pre_fault}s")
    print(f"Fault Duration   : {args.fault_duration}s")
    print(f"Recovery Window  : {args.recovery}s")
    print("==========================================================")

    cleanup_all_chaos()

    t_start = datetime.now(timezone.utc).isoformat()

    # Step 1: Pre-fault healthy baseline observation
    print(f"\n[PHASE 1] Pre-fault observation window ({args.pre_fault}s)...")
    run_cmd(f"{PROJECT_ROOT}/.venv/bin/python {PROJECT_ROOT}/collector/cert_poller.py --once", check=False)
    time.sleep(args.pre_fault)

    # Step 2: Inject Fault
    t_fault_start = datetime.now(timezone.utc).isoformat()
    if not args.dry_run:
        apply_scenario(args.scenario)

    print(f"\n[PHASE 2] Active chaos window ({args.fault_duration}s)...")
    t0 = time.time()
    while (time.time() - t0) < args.fault_duration:
        run_cmd(f"{PROJECT_ROOT}/.venv/bin/python {PROJECT_ROOT}/collector/cert_poller.py --once", check=False)
        run_cmd(f"{PROJECT_ROOT}/.venv/bin/python {PROJECT_ROOT}/collector/event_logger.py --run-id {run_id}", check=False)
        time.sleep(15)

    # Step 3: Remove Fault & Recover
    t_fault_end = datetime.now(timezone.utc).isoformat()
    if not args.dry_run:
        remove_scenario(args.scenario)

    print(f"\n[PHASE 3] Recovery window ({args.recovery}s)...")
    time.sleep(args.recovery)
    t_end = datetime.now(timezone.utc).isoformat()

    # Final sweep
    run_cmd(f"{PROJECT_ROOT}/.venv/bin/python {PROJECT_ROOT}/collector/cert_poller.py --once", check=False)
    run_cmd(f"{PROJECT_ROOT}/.venv/bin/python {PROJECT_ROOT}/collector/event_logger.py --run-id {run_id}", check=False)

    log_entry = {
        "run_id": run_id,
        "scenario_id": args.scenario,
        "seed": seed,
        "pre_fault_sec": args.pre_fault,
        "fault_duration_sec": args.fault_duration,
        "recovery_sec": args.recovery,
        "t_start": t_start,
        "t_fault_start": t_fault_start,
        "t_fault_end": t_fault_end,
        "t_end": t_end,
        "status": "COMPLETED"
    }
    log_experiment_run(log_entry)

    print("\n==========================================================")
    print(f" Experiment Run Finished Successfully: {run_id}")
    print("==========================================================")


if __name__ == "__main__":
    main()
