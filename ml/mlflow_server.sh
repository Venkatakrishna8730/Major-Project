#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

MLFLOW_PORT="${MLFLOW_PORT:-5000}"
MLFLOW_HOST="${MLFLOW_HOST:-127.0.0.1}"
DB_PATH="${PROJECT_ROOT}/mlruns.db"
ARTIFACT_DIR="${PROJECT_ROOT}/mlartifacts"

mkdir -p "${ARTIFACT_DIR}"
mkdir -p "${PROJECT_ROOT}/ml/plots"
mkdir -p "${PROJECT_ROOT}/models"

# Check if MLflow is already running
if nc -z "${MLFLOW_HOST}" "${MLFLOW_PORT}" >/dev/null 2>&1; then
    echo "[OK] MLflow Tracking Server is already active on http://${MLFLOW_HOST}:${MLFLOW_PORT}"
    exit 0
fi

echo "[INFO] Starting MLflow Tracking Server on http://${MLFLOW_HOST}:${MLFLOW_PORT}..."
echo "  Backend Store URI : sqlite:///${DB_PATH}"
echo "  Artifact Root     : ${ARTIFACT_DIR}"

nohup "${PROJECT_ROOT}/.venv/bin/mlflow" server \
    --backend-store-uri "sqlite:///${DB_PATH}" \
    --default-artifact-root "${ARTIFACT_DIR}" \
    --host "${MLFLOW_HOST}" \
    --port "${MLFLOW_PORT}" \
    > "${PROJECT_ROOT}/data/raw/mlflow.log" 2>&1 &

MLFLOW_PID=$!
echo "[INFO] MLflow Server spawned with PID: ${MLFLOW_PID}"

# Wait for readiness
for i in {1..20}; do
    if nc -z "${MLFLOW_HOST}" "${MLFLOW_PORT}" >/dev/null 2>&1; then
        echo "[ OK ] MLflow Server successfully initialized and listening on http://${MLFLOW_HOST}:${MLFLOW_PORT}"
        exit 0
    fi
    sleep 1
done

echo "[WARN] MLflow Server did not respond within 20 seconds. Check data/raw/mlflow.log"
