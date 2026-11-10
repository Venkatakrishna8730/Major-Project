#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
BIN_DIR="${PROJECT_ROOT}/bin"

mkdir -p "${BIN_DIR}"
export PATH="${BIN_DIR}:${PATH}"

echo "=========================================================="
echo " Bootstrapping Toolchain & Python Environment"
echo "=========================================================="

# 1. Install jq if missing
if ! command -v jq >/dev/null 2>&1; then
    echo "[INFO] Installing standalone jq binary into ${BIN_DIR}..."
    curl -sLo "${BIN_DIR}/jq" https://github.com/jqlang/jq/releases/download/jq-1.7.1/jq-linux-amd64
    chmod +x "${BIN_DIR}/jq"
    echo "[ OK ] jq installed: $("${BIN_DIR}/jq" --version)"
else
    echo "[ OK ] jq already present: $(command -v jq)"
fi

# 2. Install istioctl 1.22.3 if missing
ISTIO_VERSION="1.22.3"
if ! command -v istioctl >/dev/null 2>&1; then
    echo "[INFO] Downloading Istio ${ISTIO_VERSION} into ${PROJECT_ROOT}/istio-${ISTIO_VERSION}..."
    if [ ! -d "${PROJECT_ROOT}/istio-${ISTIO_VERSION}" ]; then
        cd "${PROJECT_ROOT}"
        curl -sL https://istio.io/downloadIstio | ISTIO_VERSION="${ISTIO_VERSION}" sh -
    fi
    ln -sf "${PROJECT_ROOT}/istio-${ISTIO_VERSION}/bin/istioctl" "${BIN_DIR}/istioctl"
    chmod +x "${BIN_DIR}/istioctl"
    echo "[ OK ] istioctl installed: $("${BIN_DIR}/istioctl" version --remote=false 2>/dev/null || true)"
else
    echo "[ OK ] istioctl already present: $(command -v istioctl)"
fi

# 3. Setup Python Virtual Environment
VENV_DIR="${PROJECT_ROOT}/.venv"
if [ ! -d "${VENV_DIR}" ]; then
    echo "[INFO] Creating Python virtual environment at ${VENV_DIR}..."
    python3 -m venv "${VENV_DIR}"
fi

echo "[INFO] Upgrading pip and installing Python packages..."
"${VENV_DIR}/bin/pip" install --upgrade pip
"${VENV_DIR}/bin/pip" install -r "${PROJECT_ROOT}/requirements.txt"

echo "=========================================================="
echo " Bootstrap Complete! Testing environment..."
echo "=========================================================="
"${SCRIPT_DIR}/00_verify_env.sh"
