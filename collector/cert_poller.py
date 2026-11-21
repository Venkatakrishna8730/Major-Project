#!/usr/bin/env python3
"""
Sidecar Secret / Certificate Expiry Poller
Extracts X.509 dynamic certificate metadata directly from Envoy SDS via istioctl.
Tracks per-pod seconds_to_expiry, cert_age, and detects rotation events.
"""

import argparse
import base64
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

try:
    from cryptography import x509
    from cryptography.hazmat.backends import default_backend
    HAS_CRYPTOGRAPHY = True
except ImportError:
    HAS_CRYPTOGRAPHY = False


def run_command(cmd: List[str], timeout: int = 15) -> Optional[str]:
    """Execute a subprocess command with timeout and return stdout."""
    try:
        res = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            check=True
        )
        return res.stdout.strip()
    except Exception:
        return None


def get_mesh_pods(namespace: str = "default", project_bin: str = "bin") -> List[Dict[str, str]]:
    """Discover all pods with istio-proxy sidecar in the target namespace."""
    cmd = [
        "kubectl", "-n", namespace, "get", "pods",
        "-o", "jsonpath={range .items[*]}{.metadata.name}{'\\t'}{.metadata.labels.app}{'\\t'}{range .spec.containers[*]}{.name}{','}{end}{'\\n'}{end}"
    ]
    raw = run_command(cmd)
    if not raw:
        return []

    mesh_pods = []
    for line in raw.strip().splitlines():
        parts = line.split("\t")
        if len(parts) >= 3:
            pod_name, app_label, containers = parts[0], parts[1], parts[2]
            if "istio-proxy" in containers.split(","):
                mesh_pods.append({
                    "namespace": namespace,
                    "pod": pod_name,
                    "app": app_label or "unknown"
                })
    return mesh_pods


def extract_cert_dates_openssl(cert_pem_bytes: bytes) -> Dict[str, any]:
    """Extract dates using openssl CLI fallback if cryptography package is unavailable."""
    proc = subprocess.run(
        ["openssl", "x509", "-noout", "-dates", "-subject", "-issuer"],
        input=cert_pem_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=5,
        check=True
    )
    lines = proc.stdout.decode().splitlines()
    not_before_str = ""
    not_after_str = ""
    for line in lines:
        if line.startswith("notBefore="):
            not_before_str = line.split("=", 1)[1]
        elif line.startswith("notAfter="):
            not_after_str = line.split("=", 1)[1]

    # Parse openssl date format: 'Nov 21 16:44:16 2026 GMT'
    nb_dt = datetime.strptime(not_before_str, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
    na_dt = datetime.strptime(not_after_str, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
    return {
        "not_before": nb_dt,
        "not_after": na_dt
    }


def parse_cert_metadata(cert_base64: str) -> Optional[Dict[str, any]]:
    """Parse base64 X.509 cert and return timestamps."""
    try:
        cert_bytes = base64.b64decode(cert_base64)
        if HAS_CRYPTOGRAPHY:
            cert = x509.load_pem_x509_certificate(cert_bytes, default_backend())
            not_before = cert.not_valid_before_utc
            not_after = cert.not_valid_after_utc
        else:
            res = extract_cert_dates_openssl(cert_bytes)
            not_before = res["not_before"]
            not_after = res["not_after"]

        now = datetime.now(timezone.utc)
        nb_epoch = int(not_before.timestamp())
        na_epoch = int(not_after.timestamp())
        now_epoch = int(now.timestamp())

        return {
            "not_before_iso": not_before.isoformat(),
            "not_after_iso": not_after.isoformat(),
            "not_before_epoch": nb_epoch,
            "not_after_epoch": na_epoch,
            "total_lifetime_sec": na_epoch - nb_epoch,
            "seconds_to_expiry": na_epoch - now_epoch,
            "cert_age_sec": now_epoch - nb_epoch
        }
    except Exception:
        return None


def fetch_pod_secret(pod_name: str, namespace: str, istioctl_bin: str) -> Optional[Dict[str, any]]:
    """Query Envoy SDS via istioctl proxy-config secret."""
    cmd = [istioctl_bin, "proxy-config", "secret", f"{pod_name}.{namespace}", "-o", "json"]
    raw_json = run_command(cmd)
    if not raw_json:
        return None

    try:
        data = json.loads(raw_json)
        secrets = data.get("dynamicActiveSecrets", [])
        for s in secrets:
            if s.get("name") == "default":
                chain = s.get("secret", {}).get("tlsCertificate", {}).get("certificateChain", {}).get("inlineBytes")
                if chain:
                    return parse_cert_metadata(chain)
    except Exception:
        pass
    return None


class RotationStateTracker:
    """Tracks previous not_before values to detect rotation transitions."""
    def __init__(self):
        self.last_not_before: Dict[str, int] = {}
        self.rotation_counts: Dict[str, int] = {}

    def update(self, pod_key: str, not_before_epoch: int) -> Dict[str, any]:
        prev = self.last_not_before.get(pod_key)
        if prev is None:
            self.last_not_before[pod_key] = not_before_epoch
            self.rotation_counts[pod_key] = 0
            return {"rotation_detected": 0, "rotation_count": 0}

        if not_before_epoch > prev:
            self.last_not_before[pod_key] = not_before_epoch
            self.rotation_counts[pod_key] += 1
            return {"rotation_detected": 1, "rotation_count": self.rotation_counts[pod_key]}

        return {"rotation_detected": 0, "rotation_count": self.rotation_counts[pod_key]}


def poll_cycle(
    namespaces: List[str],
    output_file: Path,
    tracker: RotationStateTracker,
    istioctl_bin: str
) -> List[Dict[str, any]]:
    """Execute one polling sweep over all discovered mesh pods."""
    records = []
    now = datetime.now(timezone.utc)
    ts_iso = now.isoformat()
    ts_epoch = int(now.timestamp())

    for ns in namespaces:
        pods = get_mesh_pods(namespace=ns)
        for p in pods:
            meta = fetch_pod_secret(p["pod"], ns, istioctl_bin)
            if not meta:
                continue

            pod_key = f"{ns}/{p['pod']}"
            rot_info = tracker.update(pod_key, meta["not_before_epoch"])

            rec = {
                "timestamp_iso": ts_iso,
                "timestamp_epoch": ts_epoch,
                "namespace": ns,
                "pod_name": p["pod"],
                "app": p["app"],
                "not_before_iso": meta["not_before_iso"],
                "not_after_iso": meta["not_after_iso"],
                "not_before_epoch": meta["not_before_epoch"],
                "not_after_epoch": meta["not_after_epoch"],
                "total_lifetime_sec": meta["total_lifetime_sec"],
                "seconds_to_expiry": meta["seconds_to_expiry"],
                "cert_age_sec": meta["cert_age_sec"],
                "rotation_detected": rot_info["rotation_detected"],
                "rotation_count": rot_info["rotation_count"]
            }
            records.append(rec)

    if records:
        output_file.parent.mkdir(parents=True, exist_ok=True)
        file_exists = output_file.exists()
        with open(output_file, "a", encoding="utf-8") as f:
            headers = [
                "timestamp_iso", "timestamp_epoch", "namespace", "pod_name", "app",
                "not_before_iso", "not_after_iso", "not_before_epoch", "not_after_epoch",
                "total_lifetime_sec", "seconds_to_expiry", "cert_age_sec",
                "rotation_detected", "rotation_count"
            ]
            if not file_exists:
                f.write(",".join(headers) + "\n")
            for r in records:
                row = [str(r[h]) for h in headers]
                f.write(",".join(row) + "\n")

    return records


def main():
    parser = argparse.ArgumentParser(description="Envoy SDS Certificate Expiry Poller")
    parser.add_argument("--namespaces", nargs="+", default=["default", "istio-system"], help="Namespaces to inspect")
    parser.add_argument("--interval", type=int, default=15, help="Polling interval in seconds")
    parser.add_argument("--duration", type=int, default=0, help="Total run duration in seconds (0 = forever)")
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    parser.add_argument("--output", type=str, default="data/raw/cert_poller.csv", help="Output CSV path")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    istioctl_bin = str(project_root / "bin" / "istioctl")
    output_path = project_root / args.output

    tracker = RotationStateTracker()
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Starting cert poller (namespaces={args.namespaces}, interval={args.interval}s, output={output_path})")

    t_start = time.time()
    try:
        while True:
            t0 = time.time()
            records = poll_cycle(args.namespaces, output_path, tracker, istioctl_bin)
            for r in records:
                rot_flag = " [ROTATION!]" if r["rotation_detected"] else ""
                print(f"[{datetime.now().strftime('%H:%M:%S')}] {r['namespace']}/{r['pod_name']}: expires in {r['seconds_to_expiry']}s (age={r['cert_age_sec']}s){rot_flag}")

            if args.once:
                break
            if args.duration > 0 and (time.time() - t_start) >= args.duration:
                break

            elapsed = time.time() - t0
            sleep_time = max(0.1, args.interval - elapsed)
            time.sleep(sleep_time)
    except KeyboardInterrupt:
        print("\nPoller stopped by user.")


if __name__ == "__main__":
    main()
