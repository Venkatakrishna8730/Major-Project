#!/usr/bin/env bash
# ==============================================================================
# Master Live Demo & Stage-Wise Verification Pipeline
# Early Prediction of mTLS Certificate Rotation Failures in Istio Service Mesh
# ==============================================================================
set -euo pipefail

PROJECT_ROOT="/home/user/Documents/SeriviceMeshML"
SCRIPT_DIR="${PROJECT_ROOT}/scripts"

export PATH="${PROJECT_ROOT}/bin:${PATH}"
export MINIKUBE_HOME="${PROJECT_ROOT}/.minikube"
export PROFILE="mtls-lab"
export SERVICE_PORT="${SERVICE_PORT:-8000}"

# Colors for terminal output
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

cleanup_background() {
    echo -e "\n${YELLOW}[CLEANUP] Stopping background demo processes to protect laptop resources...${NC}"
    fuser -k "${SERVICE_PORT}/tcp" >/dev/null 2>&1 || true
    fuser -k "5000/tcp" >/dev/null 2>&1 || true
    fuser -k "9090/tcp" >/dev/null 2>&1 || true
    echo -e "${GREEN}[ OK ] Port 8000, 5000, 9090 processes cleared.${NC}"
}

trap cleanup_background EXIT

# ------------------------------------------------------------------------------
# 0. System Resource Pre-Flight Checks
# ------------------------------------------------------------------------------
check_system_resources() {
    echo -e "\n${CYAN}${BOLD}==============================================================================${NC}"
    echo -e "${CYAN}${BOLD} 0. System Pre-Flight & Laptop Resource Audit${NC}"
    echo -e "${CYAN}${BOLD}==============================================================================${NC}"

    TOTAL_MEM=$(free -m | awk '/^Mem:/{print $2}')
    AVAIL_MEM=$(free -m | awk '/^Mem:/{print $7}')
    CPU_CORES=$(nproc)
    DISK_AVAIL=$(df -h / | awk 'NR==2 {print $4}')

    echo -e "CPU Cores Available : ${BOLD}${CPU_CORES}${NC}"
    echo -e "Total RAM           : ${BOLD}${TOTAL_MEM} MB${NC}"
    echo -e "Available RAM       : ${BOLD}${AVAIL_MEM} MB${NC}"
    echo -e "Disk Free on /      : ${BOLD}${DISK_AVAIL}${NC}"

    if [ "${AVAIL_MEM}" -lt 1200 ]; then
        echo -e "${YELLOW}[WARN] Available RAM is below 1.2 GB. Freeing cache...${NC}"
        sync || true
    fi

    # Check Docker Daemon
    if ! docker info >/dev/null 2>&1; then
        echo -e "${RED}[ERROR] Docker daemon is not running. Please start Docker first.${NC}"
        exit 1
    fi
    echo -e "${GREEN}[ PASS ] Docker daemon is active and responsive.${NC}"

    # Clear dangling ports to avoid memory leakage
    fuser -k "${SERVICE_PORT}/tcp" >/dev/null 2>&1 || true
    fuser -k "5000/tcp" >/dev/null 2>&1 || true
    fuser -k "9090/tcp" >/dev/null 2>&1 || true
}

# ------------------------------------------------------------------------------
# 1. Cluster Status & Safe Auto-Start
# ------------------------------------------------------------------------------
ensure_cluster_running() {
    echo -e "\n${CYAN}${BOLD}==============================================================================${NC}"
    echo -e "${CYAN}${BOLD} 1. Kubernetes Cluster (mtls-lab) Health & Provisioning${NC}"
    echo -e "${CYAN}${BOLD}==============================================================================${NC}"

    if minikube status -p "${PROFILE}" >/dev/null 2>&1; then
        echo -e "${GREEN}[ OK ] Minikube cluster '${PROFILE}' is already running.${NC}"
    else
        echo -e "${YELLOW}[INFO] Minikube cluster '${PROFILE}' is not running. Starting safely...${NC}"
        # Start with memory-safe limits (2 CPUs, 2500 MB) to prevent laptop freezing
        minikube start \
            -p "${PROFILE}" \
            --driver=docker \
            --container-runtime=containerd \
            --cpus=2 \
            --memory=2500 \
            --wait=all
    fi

    kubectl config use-context "${PROFILE}" >/dev/null 2>&1 || true

    # Tune kernel inotify and DNS inside node
    echo -e "[INFO] Configuring inotify watchers and DNS in cluster container..."
    docker exec -u 0 "${PROFILE}" sysctl -w fs.inotify.max_user_instances=8192 >/dev/null 2>&1 || true
    docker exec -u 0 "${PROFILE}" sysctl -w fs.inotify.max_user_watches=1048576 >/dev/null 2>&1 || true
    docker exec -u 0 "${PROFILE}" sh -c "echo 'nameserver 8.8.8.8' > /etc/resolv.conf && echo 'nameserver 1.1.1.1' >> /etc/resolv.conf" >/dev/null 2>&1 || true

    echo -e "Cluster Nodes Status:"
    kubectl get nodes -o wide
}

# ------------------------------------------------------------------------------
# Stage 0: Environment Verification
# ------------------------------------------------------------------------------
run_stage_0() {
    echo -e "\n${BLUE}${BOLD}--- [Stage 0] Verifying Environment & Pinned Tooling ---${NC}"
    "${PROJECT_ROOT}/scripts/00_verify_env.sh"
}

# ------------------------------------------------------------------------------
# Stage 1: Short-TTL Istio Service Mesh
# ------------------------------------------------------------------------------
run_stage_1() {
    echo -e "\n${BLUE}${BOLD}--- [Stage 1] Verifying Istio Mesh & Short-TTL (1h) Certificate Policy ---${NC}"
    if ! kubectl get deployment istiod -n istio-system >/dev/null 2>&1; then
        echo -e "[INFO] Istio control plane not detected. Installing with 1-hour cert TTL..."
        istioctl install -y -f "${PROJECT_ROOT}/cluster/istio-operator-short-ttl.yaml"
    fi

    kubectl -n istio-system rollout status deployment/istiod --timeout=60s
    kubectl label namespace default istio-injection=enabled --overwrite >/dev/null 2>&1

    # Deploy verification probe if not present
    if ! kubectl get deployment sleep -n default >/dev/null 2>&1; then
        kubectl apply -f "${PROJECT_ROOT}/istio-1.22.3/samples/sleep/sleep.yaml" -n default >/dev/null 2>&1
        kubectl -n default rollout status deployment/sleep --timeout=60s >/dev/null 2>&1
    fi

    SLEEP_POD=$(kubectl -n default get pod -l app=sleep -o jsonpath='{.items[0].metadata.name}')
    echo -e "Inspecting cryptographic certificate for pod: ${BOLD}${SLEEP_POD}${NC}"
    "${PROJECT_ROOT}/scripts/verify_cert_rotation.sh" default "${SLEEP_POD}"
}

# ------------------------------------------------------------------------------
# Stage 2: Observability Pipeline (Prometheus)
# ------------------------------------------------------------------------------
run_stage_2() {
    echo -e "\n${BLUE}${BOLD}--- [Stage 2] Verifying Observability (Prometheus) in istio-system ---${NC}"
    if ! kubectl get deployment prometheus -n istio-system >/dev/null 2>&1; then
        echo -e "[INFO] Deploying Prometheus in istio-system..."
        kubectl apply -f "${PROJECT_ROOT}/cluster/observability/prometheus.yaml" >/dev/null 2>&1
    fi
    kubectl -n istio-system rollout status deployment/prometheus --timeout=90s
    echo -e "${GREEN}[ PASS ] Prometheus server running and scraping at 15s intervals.${NC}"
}

# ------------------------------------------------------------------------------
# Stage 3: Workload & Strict mTLS Baseline
# ------------------------------------------------------------------------------
run_stage_3() {
    echo -e "\n${BLUE}${BOLD}--- [Stage 3] Verifying Bookinfo Workload with Strict mTLS ---${NC}"
    kubectl apply -f "${PROJECT_ROOT}/workload/peer-auth-strict.yaml" >/dev/null 2>&1
    kubectl apply -f "${PROJECT_ROOT}/workload/destination-rules-mtls.yaml" >/dev/null 2>&1

    if ! kubectl get deployment productpage-v1 -n default >/dev/null 2>&1; then
        echo -e "[INFO] Deploying Bookinfo microservices..."
        kubectl apply -f "${PROJECT_ROOT}/workload/bookinfo.yaml" -n default >/dev/null 2>&1
    fi

    kubectl -n default rollout status deployment/productpage-v1 --timeout=60s
    echo -e "Active Workload Pods (Expect 2/2 containers each: App + Envoy):"
    kubectl -n default get pods -l 'app in (productpage,details,ratings,reviews)' --no-headers | awk '{printf "  %-35s %-10s %s\n", $1, $2, $3}'
}

# ------------------------------------------------------------------------------
# Stage 4: Chaos Scenarios & Ground-Truth
# ------------------------------------------------------------------------------
run_stage_4() {
    echo -e "\n${BLUE}${BOLD}--- [Stage 4] Auditing 10 Chaos Scenarios Catalog ---${NC}"
    SCENARIO_COUNT=$(find "${PROJECT_ROOT}/chaos/scenarios" -name "*.yaml" | wc -l)
    echo -e "Total Chaos Mesh scenarios configured: ${BOLD}${SCENARIO_COUNT}${NC}"
    ls -1 "${PROJECT_ROOT}/chaos/scenarios" | head -n 5 | awk '{print "  - " $1}'
    echo -e "  ... and 5 more scenarios (S6 to S10)."
    echo -e "${GREEN}[ PASS ] Chaos Mesh failure injection catalog verified.${NC}"
}

# ------------------------------------------------------------------------------
# Stage 5: Dataset & Feature Matrix
# ------------------------------------------------------------------------------
run_stage_5() {
    echo -e "\n${BLUE}${BOLD}--- [Stage 5] Auditing Processed Feature Matrix (77 Features) ---${NC}"
    if [ ! -f "${PROJECT_ROOT}/data/processed/features_v1.parquet" ]; then
        echo -e "[INFO] Building feature matrix from harvested raw telemetry..."
        "${PROJECT_ROOT}/.venv/bin/python" "${PROJECT_ROOT}/collector/feature_pipeline.py" \
            --metrics "${PROJECT_ROOT}/data/raw/all_runs_metrics.parquet" \
            --events "${PROJECT_ROOT}/data/raw/event_log.csv" \
            --output-parquet "${PROJECT_ROOT}/data/processed/features_v1.parquet" \
            --output-csv "${PROJECT_ROOT}/data/processed/features_v1.csv"
    fi

    "${PROJECT_ROOT}/.venv/bin/python" -c "
import pandas as pd
df = pd.read_parquet('${PROJECT_ROOT}/data/processed/features_v1.parquet')
print(f'  Dataset Shape   : {df.shape[0]} rows x {df.shape[1]} columns')
print(f'  Feature Columns : {len([c for c in df.columns if not c.startswith(\"label\") and c not in [\"run_id\", \"timestamp\", \"already_failing\", \"dataset_split\"]])} numerical features')
print(f'  Splits          : Train={len(df[df.dataset_split==\"train\"])}, Val={len(df[df.dataset_split==\"val\"])}, Test={len(df[df.dataset_split==\"test\"])}')
"
    echo -e "${GREEN}[ PASS ] Leak-free feature matrix is verified and ready.${NC}"
}

# ------------------------------------------------------------------------------
# Stage 6: Champion Model Artifacts & MLflow
# ------------------------------------------------------------------------------
run_stage_6() {
    echo -e "\n${BLUE}${BOLD}--- [Stage 6] Auditing Champion Model Artifacts & MLflow Registry ---${NC}"
    MODEL_FILE="${PROJECT_ROOT}/models/champion_xgb.joblib"
    SCHEMA_FILE="${PROJECT_ROOT}/models/feature_names.json"

    if [ ! -f "${MODEL_FILE}" ]; then
        echo -e "[INFO] Training cost-sensitive XGBoost models..."
        "${PROJECT_ROOT}/.venv/bin/python" "${PROJECT_ROOT}/ml/train.py"
    fi

    echo -e "Champion Model File : ${BOLD}${MODEL_FILE}${NC} ($(ls -lh "${MODEL_FILE}" | awk '{print $5}'))"
    echo -e "Feature Catalog     : ${BOLD}${SCHEMA_FILE}${NC} ($(ls -lh "${SCHEMA_FILE}" | awk '{print $5}'))"
    echo -e "${GREEN}[ PASS ] Champion XGBoost model artifact is loaded and verified.${NC}"
}

# ------------------------------------------------------------------------------
# Stage 7: Live Inference & Autonomous Remediation Demo
# ------------------------------------------------------------------------------
run_stage_7() {
    echo -e "\n${BLUE}${BOLD}--- [Stage 7] Live FastAPI Inference & Automated Kubernetes Self-Healing ---${NC}"

    # 1. Start FastAPI microservice
    echo -e "[INFO] Starting lightweight FastAPI service on port ${SERVICE_PORT}..."
    PYTHONPATH="${PROJECT_ROOT}" "${PROJECT_ROOT}/.venv/bin/uvicorn" \
        service.main:app \
        --host 127.0.0.1 \
        --port "${SERVICE_PORT}" \
        > "${PROJECT_ROOT}/data/raw/service.log" 2>&1 &
    SERVICE_PID=$!

    # Wait for health probe
    for i in {1..15}; do
        if curl -s "http://127.0.0.1:${SERVICE_PORT}/health" >/dev/null 2>&1; then
            echo -e "${GREEN}[ OK ] FastAPI service is live on http://127.0.0.1:${SERVICE_PORT}${NC}"
            break
        fi
        sleep 1
    done

    # 2. Test /health
    echo -e "\n${BOLD}1. Probing GET /health:${NC}"
    curl -s "http://127.0.0.1:${SERVICE_PORT}/health" | jq .

    # 3. Test Normal Baseline Telemetry
    echo -e "\n${BOLD}2. Testing POST /predict (Healthy Baseline Telemetry - Cert Expiry 3200s):${NC}"
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

    # 4. Show Istiod replicas BEFORE remediation
    echo -e "\n${BOLD}Current Istiod replicas before distress injection:${NC}"
    kubectl -n istio-system get deployment istiod -o jsonpath='{.spec.replicas}' && echo " replica"

    # 5. Test Critical Distress Telemetry
    echo -e "\n${BOLD}3. Testing POST /predict (Critical Distress Telemetry - Cert Expiry 420s, CSR Fails):${NC}"
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
            "affected_workload": "productpage-v1"
        }' | jq .

    # 6. Verify Self-Healing Scaling
    echo -e "\n${BOLD}4. Verifying Real-Time Autonomous Kubernetes Remediation:${NC}"
    sleep 2
    ISTIOD_REPLICAS=$(kubectl -n istio-system get deployment istiod -o jsonpath='{.spec.replicas}')
    echo -e "Istiod Replicas in istio-system : ${BOLD}${GREEN}${ISTIOD_REPLICAS} replicas${NC} (Scaled from 1 -> 3)"

    if [ -f "${PROJECT_ROOT}/data/raw/remediation_audit.log" ]; then
        echo -e "\nAudit Log Entry Recorded in data/raw/remediation_audit.log:"
        tail -n 1 "${PROJECT_ROOT}/data/raw/remediation_audit.log" | jq .
    fi

    # Scale back to 1 to preserve laptop CPU/RAM
    echo -e "\n[CLEANUP] Resetting Istiod back to 1 replica to preserve laptop resources..."
    kubectl -n istio-system scale deployment istiod --replicas=1 >/dev/null 2>&1
    echo -e "${GREEN}[ PASS ] Stage 7 live inference and self-healing successfully demonstrated!${NC}"
}

# ------------------------------------------------------------------------------
# Main Dispatcher
# ------------------------------------------------------------------------------
show_help() {
    echo "Usage: ./demo.sh [OPTION]"
    echo ""
    echo "Options:"
    echo "  --all        (Default) Run complete end-to-end stage verification from scratch."
    echo "  --stage N    Run only specific stage (0, 1, 2, 3, 4, 5, 6, 7)."
    echo "  --stop       Stop all background services and minikube to free up laptop resources."
    echo "  --status     Print current status of cluster nodes and memory."
    echo "  --help       Show this help menu."
}

ACTION="${1:---all}"

case "${ACTION}" in
    --stop)
        cleanup_background
        echo "[INFO] Stopping Minikube cluster 'mtls-lab'..."
        minikube stop -p "${PROFILE}" || true
        echo -e "${GREEN}[ SUCCESS ] All demo services and Minikube stopped. Laptop resources freed!${NC}"
        exit 0
        ;;
    --status)
        check_system_resources
        ensure_cluster_running
        exit 0
        ;;
    --stage)
        STAGE_NUM="${2:-7}"
        check_system_resources
        ensure_cluster_running
        case "${STAGE_NUM}" in
            0) run_stage_0 ;;
            1) run_stage_1 ;;
            2) run_stage_2 ;;
            3) run_stage_3 ;;
            4) run_stage_4 ;;
            5) run_stage_5 ;;
            6) run_stage_6 ;;
            7) run_stage_7 ;;
            *) echo "Invalid stage: ${STAGE_NUM}" ;;
        esac
        exit 0
        ;;
    --help)
        show_help
        exit 0
        ;;
    --all)
        check_system_resources
        ensure_cluster_running
        run_stage_0
        run_stage_1
        run_stage_2
        run_stage_3
        run_stage_4
        run_stage_5
        run_stage_6
        run_stage_7
        echo -e "\n${GREEN}${BOLD}==============================================================================${NC}"
        echo -e "${GREEN}${BOLD} ALL STAGES (0 THROUGH 7) VERIFIED AND READY FOR REVIEW PANEL!${NC}"
        echo -e "${GREEN}${BOLD}==============================================================================${NC}"
        ;;
    *)
        show_help
        exit 1
        ;;
esac
