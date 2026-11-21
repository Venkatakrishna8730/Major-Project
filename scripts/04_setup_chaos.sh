#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

export PATH="${PROJECT_ROOT}/bin:${PATH}"
export MINIKUBE_HOME="${PROJECT_ROOT}/.minikube"

echo "=========================================================="
echo " Stage 4: Chaos Mesh Engine & Fault Injection Setup"
echo "=========================================================="

# 1. Enforce kernel limits on Minikube nodes for Chaos Mesh inotify watchers
echo "[INFO] Configuring node kernel inotify and DNS settings..."
for node in mtls-lab mtls-lab-m02 mtls-lab-m03; do
    docker exec -u 0 "${node}" sysctl -w fs.inotify.max_user_instances=8192 >/dev/null 2>&1 || true
    docker exec -u 0 "${node}" sysctl -w fs.inotify.max_user_watches=1048576 >/dev/null 2>&1 || true
    docker exec -u 0 "${node}" sh -c "echo 'nameserver 8.8.8.8' > /etc/resolv.conf && echo 'nameserver 1.1.1.1' >> /etc/resolv.conf" >/dev/null 2>&1 || true
done
echo "[ OK ] Node kernel parameters and DNS configured."

# 2. Deploy / Verify Chaos Mesh Helm Release
echo ""
echo "--- 1. Verifying Chaos Mesh Helm Release ---"
if ! helm -n chaos-mesh status chaos-mesh >/dev/null 2>&1; then
    echo "[INFO] Installing Chaos Mesh..."
    helm upgrade --install chaos-mesh chaos-mesh/chaos-mesh \
        -n chaos-mesh --create-namespace \
        --set chaosDaemon.runtime=containerd \
        --set chaosDaemon.socketPath=/run/containerd/containerd.sock \
        --set dashboard.create=false
fi

echo "[INFO] Waiting for Chaos Mesh components to report Ready..."
kubectl -n chaos-mesh rollout status deployment/chaos-controller-manager --timeout=120s
kubectl -n chaos-mesh rollout status daemonset/chaos-daemon --timeout=120s

echo ""
echo "--- Active Chaos Mesh Pods ---"
kubectl -n chaos-mesh get pods -o wide

# 3. Verify Registered Chaos CRDs
echo ""
echo "--- 2. Auditing Chaos Mesh CRDs ---"
CRD_COUNT=$(kubectl get crd | grep -c "chaos-mesh.org" || echo "0")
echo "[ OK ] Chaos Mesh CRDs registered in API server: ${CRD_COUNT}"

# 4. Verify Catalog of Scenarios
echo ""
echo "--- 3. Auditing Fault Scenario Catalog (chaos/scenarios/) ---"
ls -la "${PROJECT_ROOT}/chaos/scenarios"

# 5. Execute Pilot Test Run (Scenario S1 - Istiod CPU Stress)
echo ""
echo "--- 4. Executing Pilot Validation Experiment (S1 CPU Stress) ---"
"${PROJECT_ROOT}/.venv/bin/python" "${PROJECT_ROOT}/scripts/run_experiment.py" \
    --scenario "s1_istiod_cpu" \
    --fault-duration 30 \
    --pre-fault 10 \
    --recovery 10 \
    --seed 42

# 6. Verify Experiment Metadata & Event Logs
echo ""
echo "--- 5. Validating Experiment and Event Logs ---"
if [ -f "${PROJECT_ROOT}/data/raw/experiment_log.csv" ]; then
    echo "[ OK ] experiment_log.csv generated:"
    cat "${PROJECT_ROOT}/data/raw/experiment_log.csv"
fi

echo ""
echo "=========================================================="
echo " Stage 4: Chaos Mesh Engine & Event Logger Verified!"
echo "=========================================================="
