#!/usr/bin/env bash
set -euo pipefail

TARGET_NODE="${1:-mtls-lab-m02}"
echo "[INFO] Simulating node reboot on ${TARGET_NODE}..."
docker restart "${TARGET_NODE}"
echo "[INFO] Node ${TARGET_NODE} restarted. Waiting for Ready status..."
kubectl wait --for=condition=Ready "node/${TARGET_NODE}" --timeout=120s
echo "[ OK ] Node ${TARGET_NODE} is back online."
