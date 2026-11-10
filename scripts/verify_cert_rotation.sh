#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
export PATH="${PROJECT_ROOT}/bin:${PATH}"

NAMESPACE="${1:-default}"
POD="${2:-}"

echo "=========================================================="
echo " X.509 mTLS Certificate Rotation & Validity Inspector"
echo "=========================================================="

if [ -z "${POD}" ]; then
    # Auto-detect first mesh-injected pod in the namespace
    POD=$(kubectl -n "${NAMESPACE}" get pods -l 'security.istio.io/tlsMode=istio' -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)
    if [ -z "${POD}" ]; then
        POD=$(kubectl -n "${NAMESPACE}" get pods -o jsonpath='{.items[?(@.spec.containers[*].name=="istio-proxy")].metadata.name}' 2>/dev/null | awk '{print $1}' || true)
    fi
fi

if [ -z "${POD}" ]; then
    echo "[ERROR] No mesh pod with istio-proxy found in namespace '${NAMESPACE}'."
    echo "Usage: $0 [namespace] [pod_name]"
    exit 1
fi

echo "Inspecting Pod: ${POD} (Namespace: ${NAMESPACE})"
echo ""

# Extract active secret chain from Envoy SDS via istioctl
SECRET_JSON=$(istioctl proxy-config secret "${POD}.${NAMESPACE}" -o json 2>/dev/null || true)

if [ -z "${SECRET_JSON}" ]; then
    echo "[ERROR] Could not retrieve SDS secret from pod ${POD}."
    exit 1
fi

CERT_BASE64=$(echo "${SECRET_JSON}" | jq -r '
    .dynamicActiveSecrets[]? 
    | select(.name=="default") 
    | .secret.tlsCertificate.certificateChain.inlineBytes // empty
' 2>/dev/null | head -n1)

if [ -z "${CERT_BASE64}" ] || [ "${CERT_BASE64}" = "null" ]; then
    echo "[ERROR] No dynamic 'default' mTLS certificate chain found in Envoy SDS."
    exit 1
fi

PARSED_CERT=$(echo "${CERT_BASE64}" | base64 -d | openssl x509 -noout -dates -subject -issuer 2>/dev/null)

NOT_BEFORE_STR=$(echo "${PARSED_CERT}" | grep "notBefore=" | cut -d= -f2)
NOT_AFTER_STR=$(echo "${PARSED_CERT}" | grep "notAfter=" | cut -d= -f2)
SUBJECT=$(echo "${PARSED_CERT}" | grep "subject=" | cut -d= -f2-)
ISSUER=$(echo "${PARSED_CERT}" | grep "issuer=" | cut -d= -f2-)

NOT_BEFORE_EPOCH=$(date -d "${NOT_BEFORE_STR}" +%s 2>/dev/null || date -jf "%b %d %T %Y %Z" "${NOT_BEFORE_STR}" +%s)
NOT_AFTER_EPOCH=$(date -d "${NOT_AFTER_STR}" +%s 2>/dev/null || date -jf "%b %d %T %Y %Z" "${NOT_AFTER_STR}" +%s)
NOW_EPOCH=$(date +%s)

TOTAL_LIFETIME_SEC=$(( NOT_AFTER_EPOCH - NOT_BEFORE_EPOCH ))
TOTAL_LIFETIME_MIN=$(( TOTAL_LIFETIME_SEC / 60 ))
REMAINING_SEC=$(( NOT_AFTER_EPOCH - NOW_EPOCH ))
REMAINING_MIN=$(( REMAINING_SEC / 60 ))
ELAPSED_SEC=$(( NOW_EPOCH - NOT_BEFORE_EPOCH ))
ELAPSED_MIN=$(( ELAPSED_SEC / 60 ))

# Rotation expected at ~50% of lifetime
ROTATION_DUE_EPOCH=$(( NOT_BEFORE_EPOCH + (TOTAL_LIFETIME_SEC / 2) ))
ROTATION_DUE_STR=$(date -d "@${ROTATION_DUE_EPOCH}" '+%Y-%m-%d %H:%M:%S UTC' 2>/dev/null || date -r "${ROTATION_DUE_EPOCH}" '+%Y-%m-%d %H:%M:%S UTC')

echo "Subject Identity : ${SUBJECT}"
echo "Issuer Authority : ${ISSUER}"
echo ""
echo "Certificate Timestamps:"
echo "  Issued (notBefore)     : ${NOT_BEFORE_STR} (Epoch: ${NOT_BEFORE_EPOCH})"
echo "  Expires (notAfter)     : ${NOT_AFTER_STR} (Epoch: ${NOT_AFTER_EPOCH})"
echo "  Total Lifetime         : ${TOTAL_LIFETIME_MIN} minutes (~$(( TOTAL_LIFETIME_MIN / 60 )) hour)"
echo "  Elapsed Age            : ${ELAPSED_MIN} minutes (${ELAPSED_SEC}s)"
echo "  Remaining Validity     : ${REMAINING_MIN} minutes (${REMAINING_SEC}s)"
echo "  Expected Next Renewal  : ${ROTATION_DUE_STR} (~50% TTL mark)"
echo ""

if [ "${TOTAL_LIFETIME_MIN}" -le 75 ]; then
    echo "[ VERIFIED ] Short-TTL policy confirmed! Workload certificate lifetime is ~1 hour."
else
    echo "[ WARNING ] Certificate lifetime is ${TOTAL_LIFETIME_MIN} min (> 75 min). Short-TTL policy may not be active."
fi
