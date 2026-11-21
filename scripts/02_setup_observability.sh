#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

export PATH="${PROJECT_ROOT}/bin:${PATH}"
export MINIKUBE_HOME="${PROJECT_ROOT}/.minikube"

echo "=========================================================="
echo " Stage 2: Full-Stack Observability Pipeline Setup"
echo "=========================================================="

# 1. Verify Cluster Connectivity
echo "[INFO] Verifying cluster connectivity..."
kubectl get nodes >/dev/null 2>&1 || {
    echo "[ERROR] Cannot connect to Kubernetes cluster. Run scripts/01_setup_cluster.sh first."
    exit 1
}

# 2. Deploy Prometheus Addon
echo ""
echo "--- 1. Deploying Prometheus in istio-system ---"
mkdir -p "${PROJECT_ROOT}/cluster/observability"
if [ ! -f "${PROJECT_ROOT}/cluster/observability/prometheus.yaml" ]; then
    cp "${PROJECT_ROOT}/istio-1.22.3/samples/addons/prometheus.yaml" "${PROJECT_ROOT}/cluster/observability/prometheus.yaml"
fi
kubectl apply -f "${PROJECT_ROOT}/cluster/observability/prometheus.yaml"

echo "[INFO] Waiting for Prometheus deployment to roll out..."
kubectl -n istio-system rollout status deployment/prometheus --timeout=180s

# 3. Deploy Kube-State-Metrics via Helm
echo ""
echo "--- 2. Deploying Kube-State-Metrics (KSM) ---"
helm upgrade --install ksm prometheus-community/kube-state-metrics \
    --namespace istio-system \
    --set-string service.annotations."prometheus\.io/scrape"="true" \
    --set-string service.annotations."prometheus\.io/port"="8080"

echo "[INFO] Waiting for KSM deployment to roll out..."
kubectl -n istio-system rollout status deployment/ksm-kube-state-metrics --timeout=120s

# 4. Verify Prometheus Scrape Targets
echo ""
echo "--- 3. Verifying Prometheus Scrape Targets ---"
UP_COUNT=$(kubectl -n istio-system exec deploy/prometheus -c prometheus-server -- wget -qO- 'http://localhost:9090/api/v1/query?query=up' 2>/dev/null | jq -r '.data.result | length' || echo "0")
echo "[ OK ] Active healthy scrape targets: ${UP_COUNT}"

# 5. Verify Core Istio & K8s Metrics
echo ""
echo "--- 4. Validating Key Metrics in Prometheus ---"
check_prom_metric() {
    local q="$1"
    local desc="$2"
    local count
    count=$(kubectl -n istio-system exec deploy/prometheus -c prometheus-server -- wget -qO- "http://localhost:9090/api/v1/query?query=${q}" 2>/dev/null | jq -r '.data.result | length' || echo "0")
    if [ "${count}" -gt 0 ]; then
        printf "  [ OK ] %-38s : %2d series (%s)\n" "${q}" "${count}" "${desc}"
    else
        printf "  [WAIT] %-38s :  0 series (%s)\n" "${q}" "${desc}"
    fi
}

check_prom_metric "citadel_server_csr_count" "Citadel CA CSR counter"
check_prom_metric "citadel_server_success_cert_issuance_count" "Citadel cert issuance counter"
check_prom_metric "process_cpu_seconds_total" "Process CPU seconds"
check_prom_metric "process_resident_memory_bytes" "Process memory footprint"
check_prom_metric "container_cpu_usage_seconds_total" "Cgroup container CPU"
check_prom_metric "pilot_xds_pushes" "Pilot xDS config push rate"
check_prom_metric "istio_agent_cert_expiry_seconds" "Proxy certificate remaining seconds"
check_prom_metric "kube_pod_container_status_restarts_total" "KSM container restarts"

# 6. Test Sidecar Secret Poller
echo ""
echo "--- 5. Testing Sidecar Secret Poller (collector/cert_poller.py) ---"
chmod +x "${PROJECT_ROOT}/collector/cert_poller.py"
"${PROJECT_ROOT}/.venv/bin/python" "${PROJECT_ROOT}/collector/cert_poller.py" --once --output "data/raw/cert_poller_smoke.csv"
echo "[ OK ] Cert poller successfully recorded secret metadata:"
tail -n 2 "${PROJECT_ROOT}/data/raw/cert_poller_smoke.csv"

# 7. Test Log Harvester
echo ""
echo "--- 6. Testing Proxy & Control-Plane Log Harvester ---"
chmod +x "${PROJECT_ROOT}/collector/log_harvester.sh"
"${PROJECT_ROOT}/collector/log_harvester.sh" 15m "${PROJECT_ROOT}/data/raw/logs"

echo ""
echo "=========================================================="
echo " Stage 2: Full-Stack Observability Pipeline Verified!"
echo "=========================================================="
