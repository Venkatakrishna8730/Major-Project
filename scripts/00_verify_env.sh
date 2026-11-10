#!/usr/bin/env bash
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Ensure local bin is on PATH
export PATH="${PROJECT_ROOT}/bin:${PATH}"
export MINIKUBE_HOME="${PROJECT_ROOT}/.minikube"

PASS=0
FAIL=0

check_cmd() {
    local name="$1"
    local version_cmd="$2"
    if command -v "$name" >/dev/null 2>&1; then
        local ver
        ver=$(eval "$version_cmd" 2>&1 | head -n1)
        printf "[ OK ] %-12s : %s\n" "$name" "$ver"
        PASS=$((PASS+1))
    else
        printf "[MISS] %-12s : not found in PATH\n" "$name"
        FAIL=$((FAIL+1))
    fi
}

echo "=========================================================="
echo " Stage 0: Environment & Toolchain Audit"
echo "=========================================================="
echo "Host & System Architecture:"
echo "  OS Kernel   : $(uname -srm)"
echo "  Hostname    : $(hostname)"
echo "  Date / Time : $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo ""

echo "--- Core CLI Binaries ---"
check_cmd docker "docker --version"
check_cmd minikube "minikube version --short 2>/dev/null || minikube version | head -n1"
check_cmd kubectl "kubectl version --client -o yaml 2>/dev/null | grep -m1 gitVersion | awk '{print \$2}' || kubectl version --client"
check_cmd helm "helm version --short"
check_cmd istioctl "istioctl version --remote=false 2>/dev/null || istioctl version | head -n1"
check_cmd python3 "python3 --version"
check_cmd git "git --version"
check_cmd jq "jq --version"
check_cmd openssl "openssl version"
check_cmd curl "curl --version | head -n1"

echo ""
echo "--- Docker Daemon Status ---"
if docker info >/dev/null 2>&1; then
    echo "[ OK ] Docker daemon is active and responding."
    PASS=$((PASS+1))
else
    echo "[FAIL] Docker daemon is not reachable. Check docker service."
    FAIL=$((FAIL+1))
fi

echo ""
echo "--- System Compute Resources ---"
CPU_CORES=$(nproc 2>/dev/null || getconf _NPROCESSORS_ONLN)
echo "  CPU Cores       : ${CPU_CORES}"
if [ "${CPU_CORES}" -ge 4 ]; then
    echo "[ OK ] CPU cores >= 4"
    PASS=$((PASS+1))
else
    echo "[WARN] Less than 4 CPU cores detected (${CPU_CORES}). Minikube may be resource constrained."
fi

if free -h >/dev/null 2>&1; then
    TOTAL_RAM=$(free -h | awk '/Mem:/ {print $2}')
    FREE_RAM=$(free -h | awk '/Mem:/ {print $7}')
    echo "  RAM Total/Avail : ${TOTAL_RAM} total / ${FREE_RAM} available"
    PASS=$((PASS+1))
fi

DISK_AVAIL=$(df -h "${PROJECT_ROOT}" | awk 'NR==2 {print $4}')
echo "  Disk Free Here  : ${DISK_AVAIL}"

echo ""
echo "--- Python Virtual Environment & Packages ---"
PY_BIN="python3"
if [ -f "${PROJECT_ROOT}/.venv/bin/python" ]; then
    PY_BIN="${PROJECT_ROOT}/.venv/bin/python"
    echo "Using virtualenv Python: ${PY_BIN}"
else
    echo "Using system Python (virtualenv not yet created): $(which python3)"
fi

${PY_BIN} - <<'EOF'
import importlib
packages = [
    "requests",
    "pandas",
    "numpy",
    "pyarrow",
    "sklearn",
    "xgboost",
    "yaml",
    "matplotlib",
    "mlflow",
    "fastapi",
    "uvicorn"
]
for pkg in packages:
    try:
        mod = importlib.import_module(pkg)
        ver = getattr(mod, "__version__", "installed")
        print(f"[ OK ] {pkg:<12} : {ver}")
    except ImportError:
        print(f"[MISS] {pkg:<12} : not installed")
EOF

echo ""
echo "=========================================================="
echo " Audit Summary: ${PASS} checks passed, ${FAIL} problems detected"
echo "=========================================================="
