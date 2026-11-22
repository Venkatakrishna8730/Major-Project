#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

export PATH="${PROJECT_ROOT}/bin:${PATH}"
export MINIKUBE_HOME="${PROJECT_ROOT}/.minikube"

echo "=========================================================="
echo " Stage 5: Multi-Run Dataset Harvesting & Feature Pipeline"
echo "=========================================================="

# 1. Ensure Prometheus Port-Forward is active
if ! curl -s 'http://localhost:9090/api/v1/query?query=up' >/dev/null 2>&1; then
    echo "[INFO] Starting Prometheus port-forward on port 9090..."
    kubectl -n istio-system port-forward svc/prometheus 9090:9090 >/dev/null 2>&1 &
    sleep 3
fi
echo "[ OK ] Prometheus API accessible at http://localhost:9090"

# 2. Execute Pilot Multi-Scenario Data Harvesting Runs
SCENARIOS=("s0_baseline" "s1_istiod_cpu" "s4_net_loss")
RUN_DIRS=()

for sc in "${SCENARIOS[@]}"; do
    echo ""
    echo "=========================================================="
    echo " Executing Data Collection Run: ${sc}"
    echo "=========================================================="
    T_START=$(date +%s)
    
    "${PROJECT_ROOT}/.venv/bin/python" "${PROJECT_ROOT}/scripts/run_experiment.py" \
        --scenario "${sc}" \
        --fault-duration 45 \
        --pre-fault 15 \
        --recovery 15 \
        --seed 101

    T_END=$(date +%s)

    # Find the run_id that was just completed
    LATEST_RUN_ID=$(tail -n 1 "${PROJECT_ROOT}/data/raw/experiment_log.csv" | cut -d',' -f1)
    RUN_OUTPUT_DIR="${PROJECT_ROOT}/data/raw/${LATEST_RUN_ID}"
    RUN_DIRS+=("${RUN_OUTPUT_DIR}")

    echo "[INFO] Harvesting Prometheus range metrics for ${LATEST_RUN_ID} (${T_START} -> ${T_END})..."
    "${PROJECT_ROOT}/.venv/bin/python" "${PROJECT_ROOT}/collector/prom_collector.py" \
        --run-id "${LATEST_RUN_ID}" \
        --start "${T_START}" \
        --end "${T_END}" \
        --step "15s" \
        --output-dir "${RUN_OUTPUT_DIR}"
done

# 3. Concatenate All Run Metric Tables
echo ""
echo "--- Concatenating Multi-Run Metrics ---"
"${PROJECT_ROOT}/.venv/bin/python" - <<'EOF'
import pandas as pd
from pathlib import Path

raw_dir = Path("data/raw")
all_dfs = []
for p in raw_dir.glob("run_*/metrics.parquet"):
    try:
        df = pd.read_parquet(p)
        all_dfs.append(df)
        print(f"  Loaded {len(df)} rows from {p.parent.name}")
    except Exception as e:
        print(f"  Error reading {p}: {e}")

if all_dfs:
    combined = pd.concat(all_dfs, ignore_index=True)
    out_file = raw_dir / "all_runs_metrics.parquet"
    combined.to_parquet(out_file)
    print(f"[ OK ] Consolidated {len(combined)} total rows across {len(all_dfs)} runs -> {out_file}")
EOF

# 4. Run Feature Engineering & Labeling Pipeline
echo ""
echo "--- Building Feature Dataset (Parquet & CSV) ---"
"${PROJECT_ROOT}/.venv/bin/python" "${PROJECT_ROOT}/collector/feature_pipeline.py" \
    --metrics "data/raw/all_runs_metrics.parquet" \
    --events "data/raw/event_log.csv" \
    --output-parquet "data/processed/features_v1.parquet" \
    --output-csv "data/processed/features_v1.csv"

echo ""
echo "=========================================================="
echo " Stage 5: Dataset Generation & Feature Engineering Complete!"
echo "=========================================================="
