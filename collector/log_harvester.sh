#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
export PATH="${PROJECT_ROOT}/bin:${PATH}"

SINCE="${1:-15m}"
OUTPUT_DIR="${2:-${PROJECT_ROOT}/data/raw/logs}"

mkdir -p "${OUTPUT_DIR}"

echo "=========================================================="
echo " Envoy Proxy & Istiod Log Harvester"
echo "=========================================================="
echo "Since Time Window : ${SINCE}"
echo "Destination Dir   : ${OUTPUT_DIR}"
echo ""

# 1. Harvest istiod Control Plane Logs
echo "[INFO] Harvesting istiod logs..."
ISTIOD_POD=$(kubectl -n istio-system get pod -l app=istiod -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)
if [ -n "${ISTIOD_POD}" ]; then
    kubectl -n istio-system logs "${ISTIOD_POD}" --since="${SINCE}" > "${OUTPUT_DIR}/istiod.log" 2>/dev/null || true
    echo "  Saved istiod logs: $(wc -l < "${OUTPUT_DIR}/istiod.log") lines"
fi

# 2. Harvest Sidecar Logs for Workload Pods (default namespace)
echo "[INFO] Harvesting Envoy sidecar logs from workload pods..."
WORKLOAD_PODS=$(kubectl -n default get pods -o jsonpath='{.items[?(@.spec.containers[*].name=="istio-proxy")].metadata.name}' 2>/dev/null || true)

for pod in ${WORKLOAD_PODS}; do
    kubectl -n default logs "${pod}" -c istio-proxy --since="${SINCE}" > "${OUTPUT_DIR}/${pod}_proxy.log" 2>/dev/null || true
    echo "  Saved proxy log for ${pod}: $(wc -l < "${OUTPUT_DIR}/${pod}_proxy.log") lines"
done

# 3. Harvest Ingress Gateway Logs
INGRESS_POD=$(kubectl -n istio-system get pod -l app=istio-ingressgateway -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)
if [ -n "${INGRESS_POD}" ]; then
    kubectl -n istio-system logs "${INGRESS_POD}" -c istio-proxy --since="${SINCE}" > "${OUTPUT_DIR}/ingressgateway.log" 2>/dev/null || true
    echo "  Saved ingress gateway log: $(wc -l < "${OUTPUT_DIR}/ingressgateway.log") lines"
fi

# 4. Extract Critical Error Signals
echo ""
echo "[INFO] Filtering error events (TLS handshake drops, SDS failures, CSR errors, 503s)..."
ERROR_FILE="${OUTPUT_DIR}/extracted_error_events.log"
grep -E -i "certificate|tls|sds|citadel|handshake|503|refused|expired|downstream_peer_cert" "${OUTPUT_DIR}"/*.log > "${ERROR_FILE}" 2>/dev/null || true
echo "  Extracted error lines: $(wc -l < "${ERROR_FILE}") matching events"

echo "=========================================================="
echo " Log Harvesting Complete!"
echo "=========================================================="
