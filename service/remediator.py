#!/usr/bin/env python3
"""
Automated Kubernetes Remediation Controller
Executes closed-loop mitigation actions when predicted failure risk exceeds threshold:
  1. Horizontal auto-scaling of Istiod control plane (Citadel CA queue relief).
  2. Proactive rolling secret refresh on at-risk workloads before hard expiration.
  3. Structured audit logging to remediation_audit.log.
"""

import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BIN_DIR = PROJECT_ROOT / "bin"
AUDIT_LOG_FILE = PROJECT_ROOT / "data" / "raw" / "remediation_audit.log"

# Default configuration
DEFAULT_RISK_THRESHOLD = float(os.environ.get("REMEDIATION_THRESHOLD", "0.75"))
COOLDOWN_SECONDS = int(os.environ.get("REMEDIATION_COOLDOWN", "60"))

# State tracker for cooldown
_LAST_REMEDIATION_TIME = 0.0


def run_kubectl(cmd: str) -> Tuple[int, str, str]:
    """Execute kubectl command with environment configuration."""
    env = os.environ.copy()
    env["PATH"] = f"{BIN_DIR}:{env.get('PATH', '')}"
    env["MINIKUBE_HOME"] = str(PROJECT_ROOT / ".minikube")

    full_cmd = f"kubectl {cmd}"
    res = subprocess.run(full_cmd, shell=True, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return res.returncode, res.stdout.strip(), res.stderr.strip()


def log_remediation_event(entry: Dict[str, any]):
    """Append structured JSON entry to remediation audit log."""
    AUDIT_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(AUDIT_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def execute_remediation(
    risk_score: float,
    affected_workload: str = "all",
    force: bool = False,
    dry_run: bool = False
) -> Dict[str, any]:
    """Execute automated mitigation actions if risk exceeds threshold and cooldown has elapsed."""
    global _LAST_REMEDIATION_TIME

    now = time.time()
    now_iso = datetime.now(timezone.utc).isoformat()
    elapsed = now - _LAST_REMEDIATION_TIME

    if not force and elapsed < COOLDOWN_SECONDS:
        return {
            "status": "SKIPPED_COOLDOWN",
            "message": f"Remediation skipped: In cooldown window ({int(COOLDOWN_SECONDS - elapsed)}s remaining)",
            "risk_score": risk_score,
            "timestamp": now_iso
        }

    if risk_score < DEFAULT_RISK_THRESHOLD and not force:
        return {
            "status": "NO_ACTION_REQUIRED",
            "message": f"Risk score {risk_score:.3f} below threshold {DEFAULT_RISK_THRESHOLD:.2f}",
            "risk_score": risk_score,
            "timestamp": now_iso
        }

    actions_executed = []

    # Action 1: Scale Istiod Replicas (relieve Citadel CA signing queues)
    scale_cmd = "scale deployment/istiod -n istio-system --replicas=3"
    if dry_run:
        actions_executed.append(f"[DRY-RUN] kubectl {scale_cmd}")
    else:
        rc, out, err = run_kubectl(scale_cmd)
        if rc == 0:
            actions_executed.append("Scaled istio-system/istiod deployment to 3 replicas")
        else:
            actions_executed.append(f"Istiod scale warning: {err or out}")

    # Action 2: Trigger Graceful Workload Rolling Refresh
    if affected_workload and affected_workload != "all":
        refresh_cmd = f"rollout restart deployment/{affected_workload} -n default"
    else:
        refresh_cmd = "rollout restart deployment/ratings-v1 -n default"

    if dry_run:
        actions_executed.append(f"[DRY-RUN] kubectl {refresh_cmd}")
    else:
        rc, out, err = run_kubectl(refresh_cmd)
        if rc == 0:
            actions_executed.append(f"Triggered rolling cert refresh: {refresh_cmd}")
        else:
            actions_executed.append(f"Workload rollout warning: {err or out}")

    _LAST_REMEDIATION_TIME = now

    audit_entry = {
        "timestamp": now_iso,
        "risk_score": risk_score,
        "threshold": DEFAULT_RISK_THRESHOLD,
        "actions": actions_executed,
        "dry_run": dry_run,
        "status": "EXECUTED"
    }
    log_remediation_event(audit_entry)

    return {
        "status": "EXECUTED",
        "timestamp": now_iso,
        "risk_score": risk_score,
        "actions_executed": actions_executed,
        "cooldown_sec": COOLDOWN_SECONDS
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Kubernetes Remediation Trigger")
    parser.add_argument("--risk", type=float, default=0.85, help="Simulated risk score")
    parser.add_argument("--workload", type=str, default="ratings-v1", help="Target workload")
    parser.add_argument("--dry-run", action="store_true", help="Perform dry-run simulation")
    parser.add_argument("--force", action="store_true", help="Bypass cooldown and threshold")
    args = parser.parse_args()

    result = execute_remediation(args.risk, affected_workload=args.workload, force=args.force, dry_run=args.dry_run)
    print(json.dumps(result, indent=2))
