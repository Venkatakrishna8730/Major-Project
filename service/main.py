#!/usr/bin/env python3
"""
FastAPI Inference Microservice for mTLS Rotation Failure Early Prediction
Serves real-time failure risk scores, provides Prometheus metrics exposition,
and triggers automated Kubernetes mitigation.
"""

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import joblib
import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Request, Response
from pydantic import BaseModel, Field

# Local imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
from service.remediator import execute_remediation

app = FastAPI(
    title="Istio mTLS Rotation Failure Prediction Service",
    description="Early warning inference microservice for predicting mTLS certificate rotation stalls and certificate expiry failures.",
    version="1.0.0"
)

# Global State
MODEL = None
FEATURE_NAMES: List[str] = []
CURRENT_RISK_SCORE: float = 0.0
PREDICTION_COUNT: int = 0
ALERT_COUNT: int = 0


def get_default_model_path() -> Path:
    return PROJECT_ROOT / "models" / "champion_xgb.joblib"


def get_default_features_path() -> Path:
    return PROJECT_ROOT / "models" / "feature_names.json"


@app.on_event("startup")
def load_model():
    """Load serialized champion model and feature schema on startup."""
    global MODEL, FEATURE_NAMES
    model_path = get_default_model_path()
    feat_path = get_default_features_path()

    if not model_path.exists():
        raise RuntimeError(f"Champion model not found at: {model_path}. Please run Stage 6 training first.")

    MODEL = joblib.load(model_path)
    with open(feat_path, "r", encoding="utf-8") as f:
        FEATURE_NAMES = json.load(f)

    print(f"[SERVICE] Loaded champion XGBoost model from: {model_path}")
    print(f"[SERVICE] Configured with {len(FEATURE_NAMES)} expected input features.")


# Schemas
class TelemetryPayload(BaseModel):
    telemetry: Dict[str, float] = Field(
        ...,
        description="Dictionary of PromQL and rolling telemetry features matching feature catalog schema"
    )
    auto_remediate: bool = Field(
        default=False,
        description="Whether to automatically execute Kubernetes mitigation if risk exceeds 0.75"
    )
    affected_workload: Optional[str] = Field(
        default="ratings-v1",
        description="Target workload deployment for rolling secret refresh"
    )


class PredictResponse(BaseModel):
    risk_score: float
    alert: bool
    horizon: str
    severity: str
    remediation_triggered: bool
    remediation_result: Optional[Dict[str, Any]] = None
    timestamp: str


@app.get("/health")
def health_check():
    """Service health and model readiness probe."""
    return {
        "status": "HEALTHY",
        "model_loaded": MODEL is not None,
        "features_count": len(FEATURE_NAMES),
        "horizon": "10m",
        "current_risk_score": CURRENT_RISK_SCORE,
        "total_predictions": PREDICTION_COUNT,
        "total_alerts": ALERT_COUNT,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@app.post("/predict", response_model=PredictResponse)
def predict_failure_risk(payload: TelemetryPayload):
    """Compute mTLS certificate rotation failure risk score (10-minute horizon)."""
    global CURRENT_RISK_SCORE, PREDICTION_COUNT, ALERT_COUNT

    if MODEL is None or not FEATURE_NAMES:
        raise HTTPException(status_code=503, detail="Inference model is not initialized.")

    raw_features = dict(payload.telemetry)

    # Impute missing rolling/derived signals from base signals if only raw Prometheus metrics provided
    if "envoy_cert_expiry_sec" not in raw_features:
        raw_features["envoy_cert_expiry_sec"] = 3600.0

    eps = 1e-4
    if "csr_success_ratio" not in raw_features:
        csr_req = raw_features.get("csr_request_rate", 0.0)
        cert_iss = raw_features.get("cert_issuance_rate", 0.0)
        raw_features["csr_success_ratio"] = cert_iss / (csr_req + eps)

    if "error_5xx_ratio" not in raw_features:
        req_tot = raw_features.get("req_rate_total", 0.0)
        req_5xx = raw_features.get("req_rate_5xx", 0.0)
        raw_features["error_5xx_ratio"] = req_5xx / (req_tot + eps)

    for f in FEATURE_NAMES:
        if f not in raw_features:
            if "_mean_" in f or "_max_" in f:
                base_col = f.rsplit("_", 2)[0]
                raw_features[f] = raw_features.get(base_col, 0.0)
            else:
                raw_features[f] = 0.0

    input_vector = [float(raw_features[f]) for f in FEATURE_NAMES]
    X_in = pd.DataFrame([input_vector], columns=FEATURE_NAMES)
    risk_prob = float(MODEL.predict_proba(X_in)[0, 1])
    CURRENT_RISK_SCORE = risk_prob
    PREDICTION_COUNT += 1

    alert = bool(risk_prob >= 0.75)
    if alert:
        ALERT_COUNT += 1

    if risk_prob >= 0.75:
        severity = "CRITICAL"
    elif risk_prob >= 0.40:
        severity = "ELEVATED"
    else:
        severity = "NORMAL"

    remediation_res = None
    if alert and payload.auto_remediate:
        remediation_res = execute_remediation(
            risk_score=risk_prob,
            affected_workload=payload.affected_workload or "ratings-v1"
        )

    return PredictResponse(
        risk_score=round(risk_prob, 4),
        alert=alert,
        horizon="10m",
        severity=severity,
        remediation_triggered=remediation_res is not None and remediation_res.get("status") == "EXECUTED",
        remediation_result=remediation_res,
        timestamp=datetime.now(timezone.utc).isoformat()
    )


@app.post("/remediate")
def manual_remediation(workload: str = "ratings-v1", force: bool = False, dry_run: bool = False):
    """Manually invoke Kubernetes remediation controller."""
    result = execute_remediation(
        risk_score=CURRENT_RISK_SCORE,
        affected_workload=workload,
        force=force,
        dry_run=dry_run
    )
    return result


@app.get("/metrics")
def prometheus_metrics():
    """Prometheus metric exposition endpoint."""
    output = []
    output.append("# HELP mtls_predicted_failure_risk_score Current predicted mTLS rotation failure risk score (0.0 to 1.0)")
    output.append("# TYPE mtls_predicted_failure_risk_score gauge")
    output.append(f'mtls_predicted_failure_risk_score{{horizon="10m",model="champion_xgb"}} {CURRENT_RISK_SCORE:.4f}')

    output.append("# HELP mtls_prediction_total Total number of inference requests processed")
    output.append("# TYPE mtls_prediction_total counter")
    output.append(f"mtls_prediction_total {PREDICTION_COUNT}")

    output.append("# HELP mtls_alert_total Total number of proactive failure risk alerts emitted")
    output.append("# TYPE mtls_alert_total counter")
    output.append(f"mtls_alert_total {ALERT_COUNT}")

    return Response(content="\n".join(output) + "\n", media_type="text/plain; version=0.0.4")


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("SERVICE_PORT", "8000"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
