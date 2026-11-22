#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

export PATH="${PROJECT_ROOT}/bin:${PATH}"
export MINIKUBE_HOME="${PROJECT_ROOT}/.minikube"
SERVICE_PORT="${SERVICE_PORT:-8000}"

echo "=========================================================="
echo " Stage 7: FastAPI Inference Microservice & Auto-Remediation"
echo "=========================================================="

# 1. Validate Kubernetes Manifests
echo "[INFO] Validating Kubernetes deployment manifests..."
kubectl apply --dry-run=client -f "${PROJECT_ROOT}/cluster/inference-deployment.yaml" >/dev/null
kubectl apply --dry-run=client -f "${PROJECT_ROOT}/cluster/cronjob-retrain.yaml" >/dev/null
echo "[ OK ] Kubernetes manifests syntax and schema validated."

# 2. Check / Spawn FastAPI Inference Microservice locally
if nc -z 127.0.0.1 "${SERVICE_PORT}" >/dev/null 2>&1; then
    echo "[INFO] Port ${SERVICE_PORT} in use. Stopping previous service..."
    fuser -k "${SERVICE_PORT}/tcp" >/dev/null 2>&1 || true
    sleep 2
fi

echo "[INFO] Starting FastAPI Inference Service on port ${SERVICE_PORT}..."
PYTHONPATH="${PROJECT_ROOT}" nohup "${PROJECT_ROOT}/.venv/bin/uvicorn" \
    service.main:app \
    --host 127.0.0.1 \
    --port "${SERVICE_PORT}" \
    > "${PROJECT_ROOT}/data/raw/service.log" 2>&1 &

SERVICE_PID=$!
echo "[INFO] Inference Microservice spawned with PID: ${SERVICE_PID}"

# Wait for health probe
for i in {1..15}; do
    if curl -s "http://127.0.0.1:${SERVICE_PORT}/health" >/dev/null 2>&1; then
        echo "[ OK ] Inference Service is healthy and ready on http://127.0.0.1:${SERVICE_PORT}"
        break
    fi
    sleep 1
done

# 3. Test Probe /health
echo ""
echo "--- 1. Testing GET /health ---"
curl -s "http://127.0.0.1:${SERVICE_PORT}/health" | jq .

# 4. Test Normal Healthy Workload Telemetry
echo ""
echo "--- 2. Testing POST /predict (Healthy Baseline Telemetry) ---"
curl -s -X POST "http://127.0.0.1:${SERVICE_PORT}/predict" \
    -H "Content-Type: application/json" \
    -d '{
        "telemetry": {
            "envoy_cert_expiry_sec": 3200.0,
            "csr_request_rate": 0.067,
            "cert_issuance_rate": 0.067,
            "csr_success_ratio": 1.0,
            "istiod_process_cpu": 0.002,
            "istiod_memory_bytes": 55000000.0,
            "req_rate_total": 146.0,
            "req_rate_5xx": 0.0
        },
        "auto_remediate": false
    }' | jq .

# 5. Test Critical Distress Telemetry & Automated Mitigation
echo ""
echo "--- 3. Testing POST /predict (Critical Failure Telemetry with Auto-Remediation) ---"
curl -s -X POST "http://127.0.0.1:${SERVICE_PORT}/predict" \
    -H "Content-Type: application/json" \
    -d '{
        "telemetry": {
            "envoy_cert_expiry_sec": 420.0,
            "csr_request_rate": 8.5,
            "cert_issuance_rate": 0.0,
            "csr_success_ratio": 0.0,
            "istiod_process_cpu": 1.95,
            "istiod_memory_bytes": 280000000.0,
            "req_rate_total": 80.0,
            "req_rate_5xx": 45.0
        },
        "auto_remediate": true,
        "affected_workload": "ratings-v1"
    }' | jq .

# 6. Verify Remediation Action on Cluster
echo ""
echo "--- 4. Verifying Remediation Action on Cluster ---"
echo "Istiod replicas in istio-system:"
kubectl -n istio-system get deploy/istiod -o jsonpath='{.spec.replicas}' && echo " replicas configured"
if [ -f "${PROJECT_ROOT}/data/raw/remediation_audit.log" ]; then
    echo "Remediation audit log entry:"
    tail -n 1 "${PROJECT_ROOT}/data/raw/remediation_audit.log" | jq .
else
    echo "No remediation audit log entries yet."
fi

# 7. Test Prometheus Metrics Exposition
echo ""
echo "--- 5. Testing GET /metrics (Prometheus Metric Scraping) ---"
curl -s "http://127.0.0.1:${SERVICE_PORT}/metrics"

echo ""
echo "=========================================================="
echo " Stage 7: Inference Service & Auto-Remediation Verified!"
echo "=========================================================="
