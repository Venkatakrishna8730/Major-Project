#!/usr/bin/env python3
"""
Model Training & MLflow Tracking Pipeline
Trains cost-sensitive XGBoost classifiers across prediction horizons H in {5, 10, 15} minutes.
Logs parameters, PR-AUC, ROC-AUC, F1, and model artifacts to MLflow.
Selects and exports champion model (H=10) to models/champion_xgb.joblib.
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import joblib
import mlflow
import mlflow.xgboost
import numpy as np
import pandas as pd
from sklearn.metrics import (
    average_precision_score,
    classification_report,
    f1_score,
    log_loss,
    precision_score,
    recall_score,
    roc_auc_score
)
from xgboost import XGBClassifier

# Silence agent hints
os.environ["MLFLOW_DISABLE_AGENT_HINT"] = "1"

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA_PATH = PROJECT_ROOT / "data" / "processed" / "features_v1.parquet"
DEFAULT_MODELS_DIR = PROJECT_ROOT / "models"
DEFAULT_TRACKING_URI = os.environ.get("MLFLOW_TRACKING_URI", f"sqlite:///{PROJECT_ROOT}/mlruns.db")

EXCLUDED_COLUMNS = {
    "run_id", "timestamp", "timestamp_epoch", "dataset_split",
    "already_failing", "label_H5", "label_H10", "label_H15"
}


def load_and_prep_data(parquet_path: Path) -> Tuple[pd.DataFrame, List[str]]:
    """Load feature table and extract feature columns."""
    print(f"[DATA] Loading dataset from: {parquet_path}")
    df = pd.read_parquet(parquet_path)
    feature_cols = [c for c in df.columns if c not in EXCLUDED_COLUMNS]
    print(f"[DATA] Loaded {len(df)} total rows. Identified {len(feature_cols)} input features.")
    return df, feature_cols


def train_horizon_model(
    df: pd.DataFrame,
    feature_cols: List[str],
    horizon: str = "H10",
    random_seed: int = 42
) -> Tuple[XGBClassifier, Dict[str, float]]:
    """Train cost-sensitive XGBoost classifier for a specific horizon."""
    target_col = f"label_{horizon}"
    if target_col not in df.columns:
        raise ValueError(f"Target column {target_col} not found in dataset.")

    # Filter out active failure rows to focus on early distress prediction
    clean_df = df[df["already_failing"] == 0].copy()

    train_mask = clean_df["dataset_split"] == "train"
    val_mask = clean_df["dataset_split"] == "val"

    X_train = clean_df.loc[train_mask, feature_cols]
    y_train = clean_df.loc[train_mask, target_col].astype(int)

    X_val = clean_df.loc[val_mask, feature_cols]
    y_val = clean_df.loc[val_mask, target_col].astype(int)

    pos_count = int(y_train.sum())
    neg_count = int(len(y_train) - pos_count)
    scale_pos_weight = neg_count / max(1, pos_count)

    print(f"\n--- Training Horizon {horizon} Model ---")
    print(f"  Train samples: {len(X_train)} (Positive: {pos_count}, Negative: {neg_count})")
    print(f"  Val samples  : {len(X_val)} (Positive: {int(y_val.sum())}, Negative: {int(len(y_val) - y_val.sum())})")
    print(f"  Class Weight (scale_pos_weight): {scale_pos_weight:.3f}")

    params = {
        "n_estimators": 120,
        "max_depth": 4,
        "learning_rate": 0.05,
        "subsample": 0.85,
        "colsample_bytree": 0.85,
        "scale_pos_weight": scale_pos_weight,
        "random_state": random_seed,
        "eval_metric": "aucpr",
        "early_stopping_rounds": 15
    }

    model = XGBClassifier(**params)
    model.fit(
        X_train, y_train,
        eval_set=[(X_train, y_train), (X_val, y_val)],
        verbose=False
    )

    # Predictions on validation set
    y_val_prob = model.predict_proba(X_val)[:, 1]
    y_val_pred = (y_val_prob >= 0.5).astype(int)

    val_pr_auc = float(average_precision_score(y_val, y_val_prob))
    val_roc_auc = float(roc_auc_score(y_val, y_val_prob))
    val_f1 = float(f1_score(y_val, y_val_pred, zero_division=0))
    val_prec = float(precision_score(y_val, y_val_pred, zero_division=0))
    val_rec = float(recall_score(y_val, y_val_pred, zero_division=0))
    val_loss = float(log_loss(y_val, y_val_prob))

    metrics = {
        "val_pr_auc": val_pr_auc,
        "val_roc_auc": val_roc_auc,
        "val_f1": val_f1,
        "val_precision": val_prec,
        "val_recall": val_rec,
        "val_log_loss": val_loss,
        "scale_pos_weight": scale_pos_weight,
        "best_iteration": int(model.best_iteration if hasattr(model, "best_iteration") else params["n_estimators"])
    }

    print(f"[METRICS] Horizon {horizon}:")
    print(f"  PR-AUC   : {val_pr_auc:.4f}")
    print(f"  ROC-AUC  : {val_roc_auc:.4f}")
    print(f"  F1 Score : {val_f1:.4f}")
    print(f"  Precision: {val_prec:.4f}")
    print(f"  Recall   : {val_rec:.4f}")

    return model, metrics


def run_training_pipeline(
    data_path: Path = DEFAULT_DATA_PATH,
    models_dir: Path = DEFAULT_MODELS_DIR,
    tracking_uri: str = DEFAULT_TRACKING_URI,
    experiment_name: str = "mtls-rotation-prediction"
):
    """Execute complete multi-horizon training run and register champion model."""
    models_dir.mkdir(parents=True, exist_ok=True)
    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment(experiment_name)

    df, feature_cols = load_and_prep_data(data_path)

    # Save feature names list
    feature_names_path = models_dir / "feature_names.json"
    with open(feature_names_path, "w") as f:
        json.dump(feature_cols, f, indent=2)
    print(f"[MODEL] Saved feature catalog schema to: {feature_names_path}")

    horizons = ["H5", "H10", "H15"]
    models = {}
    metrics_by_h = {}

    for h in horizons:
        with mlflow.start_run(run_name=f"xgb_{h}_cost_sensitive"):
            model, metrics = train_horizon_model(df, feature_cols, horizon=h)
            models[h] = model
            metrics_by_h[h] = metrics

            # Log to MLflow
            mlflow.log_params({
                "horizon": h,
                "n_features": len(feature_cols),
                "model_type": "XGBClassifier",
                "max_depth": 4,
                "learning_rate": 0.05,
                "scale_pos_weight": metrics["scale_pos_weight"]
            })
            mlflow.log_metrics(metrics)

            # Log model
            mlflow.xgboost.log_model(
                xgb_model=model,
                artifact_path=f"model_{h}",
                registered_model_name=None
            )

    # Select Champion Model (H10: 10-Minute Early Warning Objective)
    champion_h = "H10"
    champion_model = models[champion_h]
    champion_metrics = metrics_by_h[champion_h]

    champion_path = models_dir / "champion_xgb.joblib"
    joblib.dump(champion_model, champion_path)
    print(f"\n[CHAMPION] Selected Horizon {champion_h} as Champion Model (PR-AUC: {champion_metrics['val_pr_auc']:.4f})")
    print(f"[CHAMPION] Saved serialized model to: {champion_path}")

    # Register champion model in MLflow Model Registry
    with mlflow.start_run(run_name="champion_mtls_predictor_v1"):
        mlflow.log_params({"champion_horizon": champion_h, "selected_reason": "Primary 10m Lead Time Metric"})
        mlflow.log_metrics(champion_metrics)
        mlflow.xgboost.log_model(
            xgb_model=champion_model,
            artifact_path="champion_model",
            registered_model_name="mtls-predictor"
        )
        print("[MLFLOW] Successfully registered 'mtls-predictor' in MLflow Model Registry.")

    return champion_model, metrics_by_h


def main():
    parser = argparse.ArgumentParser(description="mTLS Failure Prediction MLflow Training")
    parser.add_argument("--data", type=str, default=str(DEFAULT_DATA_PATH), help="Path to features parquet")
    parser.add_argument("--models-dir", type=str, default=str(DEFAULT_MODELS_DIR), help="Output models directory")
    parser.add_argument("--tracking-uri", type=str, default=DEFAULT_TRACKING_URI, help="MLflow tracking URI")
    args = parser.parse_args()

    run_training_pipeline(
        data_path=Path(args.data),
        models_dir=Path(args.models_dir),
        tracking_uri=args.tracking_uri
    )


if __name__ == "__main__":
    main()
