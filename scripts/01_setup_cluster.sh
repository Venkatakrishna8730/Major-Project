#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

export PATH="${PROJECT_ROOT}/bin:${PATH}"
export MINIKUBE_HOME="${PROJECT_ROOT}/.minikube"

PROFILE="mtls-lab"
NODES=3
CPUS=4
MEMORY=5120

echo "=========================================================="
echo " Stage 1: Multi-Node Minikube & Short-TTL Istio Setup"
echo "=========================================================="
echo "Profile           : ${PROFILE}"
echo "Node Count        : ${NODES} (1 Control-Plane + 2 Workers)"
echo "Container Runtime : containerd (via Docker driver)"
echo "Cluster Memory    : ${MEMORY} MB"
echo "Cluster CPUs      : ${CPUS}"
echo ""

# 1. Start Minikube cluster if not already active
if minikube status -p "${PROFILE}" >/dev/null 2>&1; then
    echo "[INFO] Minikube profile '${PROFILE}' is already running."
else
    echo "[INFO] Launching multi-node Minikube cluster '${PROFILE}'..."
    minikube start \
        -p "${PROFILE}" \
        --nodes="${NODES}" \
        --driver=docker \
        --container-runtime=containerd \
        --cpus="${CPUS}" \
        --memory="${MEMORY}" \
        --wait=all
fi

# Ensure context is pointing to mtls-lab
kubectl config use-context "${PROFILE}"

echo ""
echo "--- Kubernetes Cluster Nodes ---"
kubectl get nodes -o wide
echo ""

# Wait for nodes to be Ready
echo "[INFO] Waiting for all nodes to report Ready status..."
kubectl wait --for=condition=Ready nodes --all --timeout=120s

# 2. Install Istio with Short-TTL Configuration
echo ""
echo "--- Installing Istio 1.22.3 with Short-Lived Certificates (1h TTL) ---"
ISTIO_OP_FILE="${PROJECT_ROOT}/cluster/istio-operator-short-ttl.yaml"

if [ ! -f "${ISTIO_OP_FILE}" ]; then
    echo "[ERROR] IstioOperator manifest not found at ${ISTIO_OP_FILE}"
    exit 1
fi

istioctl install -y -f "${ISTIO_OP_FILE}"

echo ""
echo "[INFO] Waiting for istiod control plane to roll out..."
kubectl -n istio-system rollout status deployment/istiod --timeout=240s
kubectl -n istio-system rollout status deployment/istio-ingressgateway --timeout=240s

# 3. Label default namespace for automatic sidecar injection
echo ""
echo "[INFO] Enabling automatic Envoy sidecar injection on namespace 'default'..."
kubectl label namespace default istio-injection=enabled --overwrite

# 4. Deploy validation workload (sleep service) to cryptographically verify mTLS cert
echo ""
echo "[INFO] Deploying verification probe pod in default namespace..."
SLEEP_MANIFEST="${PROJECT_ROOT}/istio-1.22.3/samples/sleep/sleep.yaml"
kubectl apply -f "${SLEEP_MANIFEST}" -n default

echo "[INFO] Waiting for verification pod to become Ready (2/2 containers: app + istio-proxy)..."
kubectl -n default rollout status deployment/sleep --timeout=180s

echo ""
echo "=========================================================="
echo " Cryptographic X.509 Certificate Verification"
echo "=========================================================="
SLEEP_POD=$(kubectl -n default get pod -l app=sleep -o jsonpath='{.items[0].metadata.name}')
"${SCRIPT_DIR}/verify_cert_rotation.sh" default "${SLEEP_POD}"

echo ""
echo "=========================================================="
echo " Stage 1 Cluster and Mesh Provisioning Completed!"
echo "=========================================================="
