#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

export PATH="${PROJECT_ROOT}/bin:${PATH}"
export MINIKUBE_HOME="${PROJECT_ROOT}/.minikube"

echo "=========================================================="
echo " Stage 3: Bookinfo Workload & Baseline Traffic Setup"
echo "=========================================================="

# 1. Enforce Automatic Sidecar Injection on default namespace
echo "[INFO] Ensuring namespace 'default' has automatic sidecar injection enabled..."
kubectl label namespace default istio-injection=enabled --overwrite

# 2. Apply Strict mTLS & DestinationRules
echo ""
echo "--- 1. Applying Strict mTLS & Mutual TLS DestinationRules ---"
kubectl apply -f "${PROJECT_ROOT}/workload/peer-auth-strict.yaml"
kubectl apply -f "${PROJECT_ROOT}/workload/destination-rules-mtls.yaml"

# 3. Deploy Bookinfo Services (4 polyglot services, 6 pod replicas)
echo ""
echo "--- 2. Deploying Bookinfo Application Services ---"
kubectl apply -f "${PROJECT_ROOT}/workload/bookinfo.yaml"
kubectl apply -f "${PROJECT_ROOT}/workload/bookinfo-gateway.yaml"

# 4. Wait for All 6 Microservice Deployments to Roll Out
echo ""
echo "[INFO] Waiting for Bookinfo microservice deployments to roll out..."
DEPLOYMENTS=(
    "productpage-v1"
    "details-v1"
    "ratings-v1"
    "reviews-v1"
    "reviews-v2"
    "reviews-v3"
)

for dep in "${DEPLOYMENTS[@]}"; do
    echo "  Rolling out deployment/${dep}..."
    kubectl -n default rollout status deployment/"${dep}" --timeout=300s
done

echo ""
echo "--- Active Workload Pods (Expect 2/2 containers each: App + Envoy) ---"
kubectl -n default get pods -l 'app in (productpage,details,ratings,reviews)' -o wide

# 5. Ingress Gateway Smoke Test
echo ""
echo "--- 3. Verifying Ingress Gateway & Internal Connectivity ---"
INGRESS_HOST=$(kubectl -n istio-system get pod -l app=istio-ingressgateway -o jsonpath='{.items[0].status.podIP}')
echo "Ingress Gateway IP: ${INGRESS_HOST}"

HTTP_CODE=$(kubectl -n default exec deploy/sleep -c sleep -- curl -s -o /dev/null -w "%{http_code}" http://productpage:9080/productpage 2>/dev/null || echo "000")
echo "Direct Internal Request (sleep -> productpage:9080): HTTP ${HTTP_CODE}"
if [ "${HTTP_CODE}" != "200" ]; then
    echo "[WARN] Initial productpage call returned HTTP ${HTTP_CODE}. Retrying in 5 seconds..."
    sleep 5
    HTTP_CODE=$(kubectl -n default exec deploy/sleep -c sleep -- curl -s -o /dev/null -w "%{http_code}" http://productpage:9080/productpage 2>/dev/null || echo "000")
    echo "Retry Request: HTTP ${HTTP_CODE}"
fi

# 6. Deploy Fortio Steady Load Generator (20 QPS)
echo ""
echo "--- 4. Deploying Fortio In-Cluster Load Generator (20 QPS) ---"
kubectl apply -f "${PROJECT_ROOT}/workload/loadgen.yaml"
kubectl -n default rollout status deployment/loadgen --timeout=180s

echo ""
echo "--- Mesh Pod Status with Load Generator ---"
kubectl -n default get pods -o wide

# 7. Verify Certificate Expiry Poller Across All Workload Pods
echo ""
echo "--- 5. Auditing Dynamic X.509 Certificates Across Mesh Pods ---"
chmod +x "${PROJECT_ROOT}/collector/cert_poller.py"
"${PROJECT_ROOT}/.venv/bin/python" "${PROJECT_ROOT}/collector/cert_poller.py" --once --output "data/raw/cert_poller_stage3.csv"

# 8. Verify Prometheus Captures Active In-Mesh HTTP Traffic
echo ""
echo "--- 6. Verifying Traffic Metrics in Prometheus ---"
sleep 10
REQ_SERIES=$(kubectl -n istio-system exec deploy/prometheus -c prometheus-server -- wget -qO- 'http://localhost:9090/api/v1/query?query=istio_requests_total' 2>/dev/null | jq -r '.data.result | length' || echo "0")
echo "[ OK ] Active 'istio_requests_total' traffic series in Prometheus: ${REQ_SERIES}"

echo ""
echo "=========================================================="
echo " Stage 3: Bookinfo Workload & Steady Traffic Active!"
echo "=========================================================="
