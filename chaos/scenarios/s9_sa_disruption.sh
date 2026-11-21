#!/usr/bin/env bash
set -euo pipefail

ACTION="${1:-inject}" # 'inject' or 'restore'

if [ "${ACTION}" = "inject" ]; then
    echo "[INFO] Injecting S9: Deleting ServiceAccount bookinfo-details..."
    kubectl -n default delete sa bookinfo-details --ignore-not-found=true
    kubectl -n default rollout restart deployment/details-v1
elif [ "${ACTION}" = "restore" ]; then
    echo "[INFO] Restoring S9: Recreating ServiceAccount bookinfo-details..."
    kubectl -n default create sa bookinfo-details || true
    kubectl -n default rollout restart deployment/details-v1
    kubectl -n default rollout status deployment/details-v1 --timeout=120s
fi
