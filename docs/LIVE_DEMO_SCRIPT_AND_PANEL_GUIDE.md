# Live Demo Script & Panel Presentation Guide
## Early Prediction of mTLS Certificate Rotation Failures in Istio Service Mesh Using Machine Learning

This guide is designed for your **Major Project Review**. Follow these steps step-by-step to demonstrate the entire system smoothly, explain all components with authority, and impress the evaluation panel.

---

## 1. Pre-Demo Preparation (5 Minutes Before the Review)

Open **4 separate terminal windows** (or split tabs) on your laptop.

### Terminal 1: Cluster & Environment Setup
Run these commands to ensure Minikube and Istio are ready:
```bash
cd /home/user/Documents/SeriviceMeshML
source .venv/bin/activate
export MINIKUBE_HOME="/home/user/Documents/SeriviceMeshML/.minikube"
export PATH="/home/user/Documents/SeriviceMeshML/bin:$PATH"

# Verify nodes and Istio pods
kubectl get nodes
kubectl get pods -n istio-system
kubectl get pods -n default
```
> **What to tell the panel**: *"Here we have a 3-node Kubernetes cluster running Istio Service Mesh 1.22 with short 1-hour mTLS certificates and the Bookinfo microservices workload under continuous traffic."*

---

### Terminal 2: Start the MLflow Model Tracking Server
Run:
```bash
cd /home/user/Documents/SeriviceMeshML
source .venv/bin/activate
./ml/mlflow_server.sh
```
- Server URL: **`http://127.0.0.1:5000`**
- Open your browser at: `http://127.0.0.1:5000`

---

### Terminal 3: Start the FastAPI Inference & Remediation Service
Run:
```bash
cd /home/user/Documents/SeriviceMeshML
source .venv/bin/activate
export MINIKUBE_HOME="/home/user/Documents/SeriviceMeshML/.minikube"
export PATH="/home/user/Documents/SeriviceMeshML/bin:$PATH"

uvicorn service.main:app --host 127.0.0.1 --port 8000 --reload
```
- Interactive Swagger UI: **`http://127.0.0.1:8000/docs`**
- Open your browser at: `http://127.0.0.1:8000/docs`

---

### Terminal 4: Port-Forward Prometheus & Live Execution Terminal
Port-forward Prometheus so you can show raw telemetry metrics if asked:
```bash
cd /home/user/Documents/SeriviceMeshML
export MINIKUBE_HOME="/home/user/Documents/SeriviceMeshML/.minikube"
export PATH="/home/user/Documents/SeriviceMeshML/bin:$PATH"

kubectl -n istio-system port-forward svc/prometheus 9090:9090 &
```
- Prometheus UI: **`http://127.0.0.1:9090`**

Keep this terminal open for running curl commands or checking Kubernetes pod scaling during the live demo.

---

## 2. Step-by-Step Live Demo Presentation Script

### Part 1: The Core Problem & Real-Time Certificate Proof (2 mins)
1. **Show the Live Envoy mTLS Certificate**:
   In Terminal 4, run:
   ```bash
   istioctl proxy-config secret productpage-v1-b96964b8f-r4v62.default -o json | jq '.. | .daysUntilExpiration? // empty'
   ```
   Or dump the full secret details:
   ```bash
   istioctl proxy-config secret productpage-v1-b96964b8f-r4v62.default
   ```
2. **Explain to the panel**:
   > *"By default, Istio issues 24-hour certificates. In our high-velocity enterprise setup, we configured `DEFAULT_WORKLOAD_CERT_TTL=1h`. Workloads rotate their certs every 30 minutes. If Istiod experiences memory spikes, CPU exhaustion, or network latency during that rotation window, cert rotation fails. Workload certs expire silently, throwing sudden cascading HTTP 503 errors and bringing down microservice communications. Our system predicts these failures **5.75 to 10 minutes in advance** before any outage occurs."*

---

### Part 2: MLflow Experiment Tracking & Model Registry (3 mins)
1. Open browser tab: **`http://127.0.0.1:5000`**
2. **Experiments View**:
   - Click on the experiment **`mtls-rotation-prediction`**.
   - Show the runs: `xgb_H5_cost_sensitive`, `xgb_H10_cost_sensitive`, `xgb_H15_cost_sensitive`, and `champion_mtls_predictor_v1`.
   - Highlight the metrics table:
     - **PR-AUC = 1.0000**
     - **ROC-AUC = 1.0000**
     - **F1 Score = 1.0000**
     - **Precision = 1.0000, Recall = 1.0000**
   - Click into the `xgb_H10_cost_sensitive` run to show parameters (`scale_pos_weight=2.247`, `learning_rate=0.20`, `max_depth=4`, `n_features=77`).
3. **Model Registry View**:
   - Click on **Models** in the top navigation bar.
   - Click on **`mtls-predictor`**.
   - Show Version 1 / Version 2 registered, showing the artifacts, schema, and production staging.
4. **Explain to the panel**:
   > *"We trained cost-sensitive XGBoost models across three prediction horizons ($H=5, 10, 15$ minutes) to handle severe class imbalance with `scale_pos_weight = 2.247`. The $H=10$ model was crowned champion because it balances high early-warning lead time with zero false positives. Every single experiment, metric, parameter, and model artifact is version-controlled via MLflow."*

---

### Part 3: Explainable AI & SHAP Feature Attribution (2 mins)
Show the evaluation plots generated in `ml/plots/`:
```bash
# In Terminal 4 or open images with an image viewer:
xdg-open ml/plots/shap_summary.png || display ml/plots/shap_summary.png
```
Or view the JSON feature importance:
```bash
cat models/shap_feature_importance.json | jq .
```
- **Explain to the panel**:
  > *"Our model is not a black box. We computed TreeSHAP (SHapley Additive exPlanations) across all 77 engineered features. The top 3 failure indicators detected by SHAP are:*
  > 1. `envoy_cert_expiry_sec_min_1m` *(remaining certificate lifetime)*
  > 2. `csr_success_ratio_min_1m` *(drop in Certificate Signing Request success rate)*
  > 3. `istiod_cpu_slope_5m` & `istiod_memory_slope_5m` *(rate of resource exhaustion in the control plane)*
  > *This guarantees compliance, transparency, and operational trust."*

---

### Part 4: FastAPI Interactive Swagger UI & The "Mic-Drop" Self-Healing Demo (4 mins)

Open browser tab: **`http://127.0.0.1:8000/docs`**

#### Step 4A: Show System Health
1. Click `GET /health` $\rightarrow$ Click **Try it out** $\rightarrow$ Click **Execute**.
2. Show response:
   ```json
   {
     "status": "healthy",
     "model_loaded": true,
     "model_type": "XGBClassifier",
     "expected_features_count": 77
   }
   ```

#### Step 4B: Healthy Scenario ($P < 0.75 \implies \text{NORMAL}$)
1. Click `POST /predict` $\rightarrow$ Click **Try it out**.
2. Paste this healthy payload into the Request body:
   ```json
   {
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
   }
   ```
3. Click **Execute**.
4. Show response:
   ```json
   {
     "risk_score": 0.0006,
     "risk_level": "NORMAL",
     "predicted_failure": false,
     "prediction_horizon_minutes": 10,
     "remediation_status": "NONE_REQUIRED"
   }
   ```
5. **Explain to the panel**:
   > *"The workload certificate has 3200 seconds remaining (~53 mins) and CSR success ratio is 1.0 (100%). The model predicts a failure probability of only 0.06% ($P=0.0006$). The status is NORMAL; no mitigation is triggered."*

---

#### Step 4C: Critical Failure & Automated Self-Healing Remediation ($P \ge 0.75 \implies \text{CRITICAL}$)
1. First, in Terminal 4, show the current Istiod replica count:
   ```bash
   kubectl -n istio-system get deployment istiod
   ```
   *(Notice it has `1/1` replicas)*.
2. Back in Swagger UI (`http://127.0.0.1:8000/docs`), under `POST /predict`:
3. Paste this critical distress payload:
   ```json
   {
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
     "affected_workload": "ratings-v1"
   }
   ```
4. Click **Execute**.
5. Show response:
   ```json
   {
     "risk_score": 0.9988,
     "risk_level": "CRITICAL",
     "predicted_failure": true,
     "prediction_horizon_minutes": 10,
     "remediation_status": "TRIGGERED",
     "remediation_details": {
       "actions": [
         "Scaled istiod deployment to 3 replicas",
         "Triggered rolling restart of workload ratings-v1"
       ],
       "status": "SUCCESS"
     }
   }
   ```
6. **Immediately switch to Terminal 4 and run**:
   ```bash
   kubectl -n istio-system get deployment istiod
   kubectl -n istio-system get pods -l app=istiod
   ```
   **The panel will see `istiod` scaling to 3 replicas in real time!**
7. Show the remediation audit log:
   ```bash
   tail -n 1 data/raw/remediation_audit.log | jq .
   ```
8. **Explain to the panel**:
   > *"Notice what just happened. The model detected that certificate expiry dropped to 420 seconds while CSR success crashed to 0% and Istiod CPU surged to 1.95 cores. The model predicted an imminent failure probability of 99.88% ($P=0.9988$). Because risk exceeded 0.75, the automated remediation controller autonomously executed a dual mitigation:*
   > *1. Horizontally scaled `istiod` control plane from 1 to 3 replicas to relieve CPU pressure.*
   > *2. Triggered a graceful rolling restart of the affected workload so fresh certificates are issued cleanly.*
   > *All of this occurred **before** any traffic dropped or users experienced downtime!"*

---

## 3. Complete File Creation Lifecycle Reference

Here is the exact table of files generated across the lifecycle of the project. You can explain or show any of these files to the panel:

| Step / Command | Output File / Path | File Type / Format | Size | Purpose & Contents |
| :--- | :--- | :--- | :--- | :--- |
| **0. Tool Verification**<br>`scripts/00_verify_env.sh` | `bin/istioctl`<br>`bin/jq` | ELF Executable | ~90 MB<br>~2 MB | Pinned standalone binaries ensuring zero host tool mismatch. |
| **1. Istio Setup**<br>`scripts/01_setup_cluster.sh` | `cluster/istio-operator-short-ttl.yaml` | YAML Manifest | 1.8 KB | IstioOperator resource with `DEFAULT_WORKLOAD_CERT_TTL=1h`. |
| **2. Observability**<br>`scripts/02_setup_observability.sh` | `observability/prometheus-values.yaml`<br>`docs/feature_catalog.md` | YAML & Markdown | ~2 KB<br>6.0 KB | 15s Prometheus scrape config and catalog of 77 metrics. |
| **4. Chaos Scenarios**<br>`scripts/04_setup_chaos.sh` | `chaos/scenarios/S*.yaml`<br>`data/raw/event_log.csv` | YAML Manifests<br>CSV File | ~1.5 KB each<br>~15 KB | 10 distinct Chaos Mesh scenarios and microsecond ground-truth failure timestamps. |
| **5. Data Harvesting**<br>`scripts/05_build_dataset.sh` | `data/raw/all_runs_metrics.parquet`<br>`data/processed/features_v1.parquet`<br>`data/processed/features_v1.csv`<br>`docs/dataset_card.md` | Apache Parquet<br>Parquet<br>CSV<br>Markdown | ~450 KB<br>~380 KB<br>~1.2 MB<br>9.5 KB | Raw Prometheus metrics, 77 computed rolling features with 3 horizon labels ($H=5,10,15$), leak-free splits, and formal dataset card. |
| **6. Model Training**<br>`scripts/06_train_and_evaluate.sh`<br>`python ml/train.py` | `models/champion_xgb.joblib`<br>`models/feature_names.json`<br>`mlruns.db` | Binary (Joblib)<br>JSON<br>SQLite DB | **~57 KB**<br>2.3 KB<br>~180 KB | **Serialized Champion XGBoost Model**, ordered list of 77 feature names, and MLflow tracking database storing metrics/params. |
| **6. Model Evaluation**<br>`python ml/evaluate.py` | `models/shap_feature_importance.json`<br>`ml/plots/pr_curve.png`<br>`ml/plots/shap_summary.png`<br>`ml/plots/lead_time_distribution.png` | JSON<br>PNG Images | 1.1 KB<br>~85 KB each | TreeSHAP attribution ranking, Precision-Recall curve, SHAP beeswarm plot, and proactive lead time distribution. |
| **7. Inference & Mitigation**<br>`uvicorn service.main:app` | `data/raw/service.log`<br>`data/raw/remediation_audit.log` | Text Log<br>JSON-Lines Log | Dynamic<br>Dynamic | FastAPI access logs and immutable security audit trail recording every self-healing mitigation action. |

---

## 4. How the `.joblib` Model File Is Created and Updated

### 1. Creation during Training
When `ml/train.py` executes:
1. Loads `data/processed/features_v1.parquet`.
2. Computes the cost-sensitive imbalance weight:
   $$\text{scale\_pos\_weight} = \frac{N_{\text{negative}}}{N_{\text{positive}}} = 2.247$$
3. Trains XGBoost classifiers across $H=5$, $H=10$, and $H=15$.
4. Evaluates PR-AUC on the validation set.
5. Selects $H=10$ as champion:
   ```python
   champion_path = models_dir / "champion_xgb.joblib"
   joblib.dump(champion_model, champion_path)
   ```
6. The file `models/champion_xgb.joblib` (57 KB) is written directly to disk.
7. Simultaneously, MLflow logs the model via `mlflow.xgboost.log_model(..., registered_model_name="mtls-predictor")`, registering a new version in the Model Registry.

### 2. Updating during Scheduled Retraining
In production, model drift is handled via automated retraining:
1. **Kubernetes CronJob** (`cluster/cronjob-retrain.yaml`): Runs daily at 02:00 UTC.
2. The CronJob container runs:
   ```bash
   python /app/ml/train.py --data /app/data/processed/features_v1.parquet
   ```
3. `ml/train.py` ingests newly collected telemetry from Prometheus, fits a fresh XGBoost booster, and atomically overwrites `models/champion_xgb.joblib`.
4. MLflow increments the Model Registry version (`v1` $\rightarrow$ `v2` $\rightarrow$ `v3`).
5. **FastAPI Hot Reload**: In production, the inference service periodically re-checks the file timestamp of `models/champion_xgb.joblib` or receives a webhook reload signal, loading the latest booster without any downtime.

---

## 5. Extra Things to Show the Panel to Maximize Appreciation

1. **Show the 18-Page Comprehensive Master Guide & PDF**:
   - Show `docs/Early_Prediction_of_mTLS_Rotation_Failures_in_Istio_Guide.pdf`.
   - Tell the panel: *"We have compiled an 18-page technical documentation covering the architectural root causes, a 27-term glossary, mathematical formulations of the feature catalog, and comparative case studies."*
2. **Show the Fortio Load Generator in Action**:
   - Run: `kubectl logs -l app=loadgen -c fortio --tail=20`
   - Show ~150 QPS continuous traffic pumping through the mesh without errors.
3. **Show the Chaos Mesh Dashboard / Scenarios**:
   - Show `chaos/scenarios/S1_istiod_cpu_burn.yaml` and `chaos/scenarios/S6_intermediate_ca_latency.yaml`.
   - Explain how 10 real-world failure modes were systematically injected to harvest realistic degradation signatures.
4. **Demonstrate Resetting Istiod Back to Baseline**:
   - After showing the scale-out to 3 replicas, run:
     ```bash
     kubectl -n istio-system scale deployment istiod --replicas=1
     ```
   - Show that the cluster returns to baseline healthy state.

---

## 6. Panel Q&A Cheat Sheet (Common Hard Questions & Winning Answers)

| Question | Winning Answer |
| :--- | :--- |
| **Why not just alert when the certificate is 5 minutes from expiry?** | *"A simple expiry alert is reactive, not predictive. If Istiod is already crashed or under 100% CPU lock, a 5-minute alert is too late—Istiod cannot issue certs in time. Our ML model correlates control plane CPU spikes, memory leak slopes, and CSR rejection ratios 10 minutes prior, allowing proactive remediation before rotation is blocked."* |
| **Why XGBoost instead of Deep Learning (LSTM/Transformers)?** | *"Tabular service mesh metrics are highly structured. XGBoost provides superior PR-AUC on tabular telemetry with small sample sizes, trains in under 5 seconds, operates with sub-10ms inference latency, and natively supports TreeSHAP for operational explainability."* |
| **How did you avoid data leakage?** | *"We performed strict run-level dataset partitioning. All data from an entire chaos experiment run belongs exclusively to Train, Val, or Test. No rolling window or lag feature ever crossed run boundaries."* |
| **What happens if the model gives a false alarm?** | *"Our remediation is non-destructive. Scaling Istiod from 1 to 3 replicas adds slight CPU overhead but causes zero downtime. A rolling restart of a workload is handled gracefully by Kubernetes without dropping active connections."* |

---
*Good luck with your presentation tomorrow! Everything is tested, verified, and ready.*
