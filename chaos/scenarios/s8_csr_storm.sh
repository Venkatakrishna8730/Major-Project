#!/usr/bin/env bash
set -euo pipefail

echo "[INFO] Inducing CSR burst by cycling deployment replicas..."
for i in {1..5}; do
    kubectl -n default scale deployment/details-v1 --replicas=5
    sleep 5
    kubectl -n default scale deployment/details-v1 --replicas=1
    sleep 5
done
echo "[ OK ] CSR storm cycle finished."
