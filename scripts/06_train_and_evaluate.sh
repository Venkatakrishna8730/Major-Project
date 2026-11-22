#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

export PATH="${PROJECT_ROOT}/bin:${PATH}"
export MINIKUBE_HOME="${PROJECT_ROOT}/.minikube"
export MLFLOW_TRACKING_URI="sqlite:///${PROJECT_ROOT}/mlruns.db"

echo "=========================================================="
echo " Stage 6: Cost-Sensitive XGBoost Training & MLflow Tracking"
echo "=========================================================="

# 1. Start MLflow Tracking Server
chmod +x "${PROJECT_ROOT}/ml/mlflow_server.sh"
"${PROJECT_ROOT}/ml/mlflow_server.sh"

# 2. Check / Prepare Feature Matrix
if [ ! -f "${PROJECT_ROOT}/data/processed/features_v1.parquet" ]; then
    echo "[INFO] features_v1.parquet not found. Generating benchmark dataset..."
    "${PROJECT_ROOT}/.venv/bin/python" "${PROJECT_ROOT}/collector/generate_benchmark_dataset.py" --runs 50
    "${PROJECT_ROOT}/.venv/bin/python" "${PROJECT_ROOT}/collector/feature_pipeline.py" \
        --metrics "${PROJECT_ROOT}/data/raw/all_runs_metrics.parquet" \
        --events "${PROJECT_ROOT}/data/raw/event_log.csv" \
        --output-parquet "${PROJECT_ROOT}/data/processed/features_v1.parquet" \
        --output-csv "${PROJECT_ROOT}/data/processed/features_v1.csv"
fi

# 3. Train XGBoost Models across H5, H10, H15 and select Champion
echo ""
echo "=========================================================="
echo " Step 1: Training Multi-Horizon XGBoost Models"
echo "=========================================================="
"${PROJECT_ROOT}/.venv/bin/python" "${PROJECT_ROOT}/ml/train.py" \
    --data "${PROJECT_ROOT}/data/processed/features_v1.parquet" \
    --models-dir "${PROJECT_ROOT}/models" \
    --tracking-uri "${MLFLOW_TRACKING_URI}"

# 4. Evaluate Champion Model on Test Split, Lead-Time & TreeSHAP
echo ""
echo "=========================================================="
echo " Step 2: Model Evaluation, Lead Time & TreeSHAP Analysis"
echo "=========================================================="
"${PROJECT_ROOT}/.venv/bin/python" "${PROJECT_ROOT}/ml/evaluate.py" \
    --data "${PROJECT_ROOT}/data/processed/features_v1.parquet" \
    --events "${PROJECT_ROOT}/data/raw/event_log.csv" \
    --model "${PROJECT_ROOT}/models/champion_xgb.joblib" \
    --plots-dir "${PROJECT_ROOT}/ml/plots" \
    --tracking-uri "${MLFLOW_TRACKING_URI}"

echo ""
echo "=========================================================="
echo " Stage 6: Training, Evaluation & MLflow Registry Complete!"
echo "=========================================================="
echo "  Champion Model Artifact : ${PROJECT_ROOT}/models/champion_xgb.joblib"
echo "  Feature Catalog Schema  : ${PROJECT_ROOT}/models/feature_names.json"
echo "  SHAP Feature Importance : ${PROJECT_ROOT}/models/shap_feature_importance.json"
echo "  Evaluation Plots        : ${PROJECT_ROOT}/ml/plots/"
echo "  MLflow UI Accessible at : http://127.0.0.1:5000"
echo "=========================================================="
