# Early Prediction of mTLS Certificate Rotation Failures in Istio Service Mesh Using Machine Learning
## 10-Slide Presentation Deck for NotebookLM & Panel Review

This deck has been refactored to maintain a professional, concept-driven narrative across slides, consolidating all quantitative empirical evaluation metrics and test benchmarks exclusively onto Slide 8.

---

# SLIDE 1: Title & Project Overview
## Early Prediction of mTLS Certificate Rotation Failures in Istio Service Mesh Using Machine Learning
### A Proactive Zero-Downtime Reliability Framework for Cloud-Native Microservices

- **Project Category**: B.Tech Major Project Review
- **Department**: Department of Computer Science & Engineering, RGUKT Basar
- **Project Team**:
  - Venkatakrishna Myana (B210013)
  - Avvaru Shashank (B211432)
  - Pramodh Pillitla (B210197)
- **Project Supervisor**: Mrs. Buddannagari Latha, Assistant Professor
- **Head of Department**: Dr. B. Venkat Raman, Assistant Professor & HOD
- **Core Engineering Mission**:
  - Transition cloud-native service mesh operations from **reactive post-crash recovery** to **proactive, machine-learning-driven self-healing**.
  - Anticipate silent mutual TLS (mTLS) certificate rotation failures in advance and trigger automated Kubernetes remediation before service communication is disrupted.

> **Speaker Notes**: *"Respected panel members, modern distributed microservices increasingly enforce strict Zero-Trust security through mutual TLS encryption. While short-lived certificates significantly reduce security attack vectors, they introduce a critical operational failure mode. Today, we present an autonomous framework that continuously analyzes mesh telemetry and eliminates service outages through proactive machine learning and automated self-healing."*

---

# SLIDE 2: Background & Problem Statement
## The Zero-Trust Dilemma: Security vs. Operational Fragility

- **The Zero-Trust Imperative**:
  - In a Zero-Trust architecture, internal cluster networks are treated as untrusted perimeters.
  - Inter-service communications are encrypted and mutually authenticated via short-lived X.509 certificates managed by Istio and Envoy sidecar proxies.
- **Short-TTL Certificate Rotation**:
  - To prevent compromised key reuse, production environments enforce short certificate validity lifetimes (e.g., 1 hour), requiring automated rotations every 30 minutes.
- **The Silent Failure Cascade**:
  ```
  [ Envoy Proxy Sidecar ] --(Needs Cert Renewal)--> [ Istio Control Plane (Istiod) ]
                                                            |
                                               (Under CPU/Memory Strain)
                                                            |
                                                            v
                                                 [ CSR Fails / Times Out ]
                                                            |
                                                            v
  [ Old Cert Reaches 0s Expiration ] ---> [ Abrupt Handshake Teardown ] ---> [ Mesh Outage ]
  ```
- **The Core Vulnerability**:
  - When certificate rotation fails due to control plane resource strain or network latency, the workload pod does not crash. It continues running normally until its certificate expires, at which point all inter-service TLS handshakes immediately collapse, triggering cascading HTTP 503 errors across the mesh.

> **Speaker Notes**: *"Under short-TTL policies, certificate rotation is a recurring, time-sensitive operation occurring multiple times an hour. If the control plane is under heavy CPU contention or memory strain, Certificate Signing Requests fail silently. Application pods do not crash; they continue serving traffic until the certificate expires, resulting in an instantaneous, catastrophic outage."*

---

# SLIDE 3: Research Gap & Why Traditional Monitoring Fails
## The Fatal Latency of Reactive Monitoring vs. Proactive ML

- **Limitations of Kubernetes Health Probes**:
  - Liveness and readiness probes only inspect container process status and application `/healthz` endpoints.
  - A pod undergoing certificate renewal failure remains completely "Ready" and "Live" until the exact moment of TLS expiration, providing zero advance warning.
- **Inadequacy of Static Threshold Alerting**:
  - Traditional APM systems trigger alerts only when remaining certificate validity falls below a static threshold (e.g., 5 minutes).
  - In production clusters, spinning up replacement control plane instances and completing workload rolling restarts requires several minutes. Static alerts fire too late to prevent outages.
- **The Research Void**:
  - Existing monitoring tools treat telemetry metrics as isolated scalars. They fail to perform multivariate temporal correlation between control-plane resource saturation and data-plane certificate delivery drift.

> **Speaker Notes**: *"Traditional monitoring alerts operators only after a failure has already begun. A static threshold alert provides insufficient time for Kubernetes to schedule pods and warm up caches. Our research bridges this gap by correlating multivariate control-plane and data-plane degradation patterns to anticipate failures well before traditional thresholds are breached."*

---

# SLIDE 4: Proposed System Architecture
## End-to-End Closed-Loop Predictive Reliability Architecture

```
+-----------------------------------------------------------------------------------------+
| 1. TELEMETRY PLANE                                                                      |
|    [Bookinfo Microservices]       [Sidecar Secret Poller]         [Prometheus Server]   |
|    (Envoy SDS Certificate Life) -> (Daemon Secret Expiry Poller) -> (15s Scrape Engine) |
+--------------------------------------------+--------------------------------------------+
                                             |
                                             v
+-----------------------------------------------------------------------------------------+
| 2. FEATURE EXTRACTION & PIPELINE PLANE                                                  |
|    [PromQL Range Harvester] -> [77 Temporal Features: Multi-Window Rolling Statistics,  |
|                                 5m First-Order Slopes, Dynamic Ratios, Run Splits]      |
+--------------------------------------------+--------------------------------------------+
                                             |
                                             v
+-----------------------------------------------------------------------------------------+
| 3. MACHINE LEARNING & MLOPS PLANE (MLflow)                                              |
|    [Cost-Sensitive XGBoost Classifier] -> [Persistent Model Registry: mtls-predictor]   |
|    [TreeSHAP Feature Explainability]   -> [Exported Serialized Artifact: champion_xgb]  |
+--------------------------------------------+--------------------------------------------+
                                             |
                                             v
+-----------------------------------------------------------------------------------------+
| 4. INFERENCE & AUTONOMOUS REMEDIATION PLANE (FastAPI)                                   |
|    [FastAPI Microservice Engine] ---> Decision Logic: Is Risk Score Critical?            |
|                                         |-- YES --> [Scale Istiod & Workload Restart]   |
|                                         +-- NO  --> [Audit Logging & Continuous Loop]   |
+-----------------------------------------------------------------------------------------+
```

- **Observability Tier**: Continuous 15-second collection of workload SDS certificate lifetimes, control-plane saturation, and CSR request dynamics.
- **Feature Pipeline Tier**: Transforms raw time-series into 77 multi-window temporal features with strict run-level leak prevention.
- **Inference & Remediation Tier**: Production REST microservice triggering automated Kubernetes API scaling and pod rollouts.

> **Speaker Notes**: *"Our architecture forms a complete autonomous feedback loop. Telemetry harvested from Envoy sidecars and the Istio control plane is converted into temporal features, evaluated in real time by our machine learning model, and fed directly into an autonomous Kubernetes controller that self-heals the cluster."*

---

# SLIDE 5: Testbed Setup & Chaos Engineering Methodology
## Multi-Node Cluster & Controlled Failure Injection

- **Multi-Node Kubernetes Testbed**:
  - 3-Node virtualized cluster deployed with Minikube and containerd container runtime.
  - Istio 1.22.3 configured with strict mutual TLS (`PeerAuthentication STRICT` and `DestinationRule ISTIO_MUTUAL`).
  - Workload certificate validity compressed to 1 hour (`DEFAULT_WORKLOAD_CERT_TTL=1h`).
  - Bookinfo microservices receiving continuous background traffic generated by Fortio.
- **Systematic Chaos Mesh Failure Injection**:
  To ensure the model learns generalized degradation patterns without bias, 10 distinct failure modes were engineered:
  - **Control Plane Contention**: CPU stress burn and JVM/Go memory leaks on Istiod.
  - **Process Instability**: Repeated control plane container crash and kill loops.
  - **Network Impairments**: Packet drop, artificial jitter, and gRPC communication latency.
  - **Cryptographic & Protocol Faults**: Intermediate CA signing delays, CSR stampedes, and corrupted handshake payloads.
  - **Node Exhaustion**: Worker node disk I/O saturation blocking secret volume mounting.
- **High-Precision Ground Truth**:
  - Exact failure onset and recovery timestamps recorded with microsecond precision via a dedicated event logging daemon.

> **Speaker Notes**: *"To train an industrial-grade predictive model, synthetic or assumed data is insufficient. We constructed a multi-node Kubernetes testbed and systematically injected 10 realistic Chaos Mesh failure scenarios—ranging from control-plane CPU starvation to intermediate CA delays—recording ground-truth failure timestamps with microsecond precision."*

---

# SLIDE 6: Multi-Dimensional Feature Engineering Pipeline
## Transforming Raw Telemetry into Predictive Early-Warning Signals

- **Four Telemetry Domains**:
  1. **Certificate Lifetime Dynamics**: Remaining validity seconds and expiration drift extracted from Envoy proxies.
  2. **CSR & SDS Protocol Health**: Inbound CSR request rates, certificate issuance rates, and signing success ratios.
  3. **Control Plane Resource Saturation**: Istiod CPU utilization, resident memory bytes, and active Go goroutine counts.
  4. **Data Plane Inter-Service Traffic**: Overall request throughput, HTTP 5xx error rates, and TLS handshake failures.
- **Temporal Transformations**:
  - **Multi-Window Rolling Statistics**: Rolling minimum, mean, maximum, and standard deviation across 1-minute, 5-minute, and 15-minute windows to distinguish transient spikes from sustained degradation.
  - **First-Order Derivative Slopes ($dy/dt$)**: 5-minute rates of change capturing memory leaks and CPU exhaustion trends before critical thresholds are crossed.
  - **Domain Ratios**: Dynamic CSR issuance ratios reflecting Certificate Authority queue saturation.
- **Strict Leak-Free Partitioning**:
  - Data splits enforced strictly at the experiment run level ($k$-run grouping). No rolling window or lag feature ever crosses boundaries between training, validation, and test datasets.

> **Speaker Notes**: *"Raw metrics lack predictive context. A certificate with 10 minutes remaining is normal if renewal is underway, but dangerous if the control plane is locked and CSR success has dropped to zero. Our feature pipeline computes 77 temporal metrics capturing rates of change and rolling statistics, while run-level partitioning guarantees zero data leakage."*

---

# SLIDE 7: Predictive Machine Learning Strategy
## Cost-Sensitive Gradient Boosting & MLOps Governance

- **Why Tree Ensembles for Service Mesh Telemetry**:
  - Service mesh telemetry is structured, tabular, and multi-scale. Gradient-boosted decision trees (XGBoost) provide superior ranking performance, low memory footprint, sub-10ms inference latency, and native interpretability.
- **Mitigating Class Imbalance**:
  - In a properly managed cluster, certificate rotation failures are rare events. Standard classifiers tend to ignore the minority failure class.
  - We employ cost-sensitive gradient boosting, weighting positive failure instances during loss computation to heavily penalize false negatives.
- **Multi-Horizon Early Warning Formulation**:
  - Modeled across multiple operational horizons (5, 10, and 15 minutes ahead of failure) to evaluate the trade-off between advance warning time and predictive certainty.
- **MLOps Tracking & Model Governance**:
  - Integrated with an MLflow tracking server backed by a persistent database, logging all hyperparameter configurations, validation curves, and model artifacts.
  - The champion model is promoted and version-controlled within the MLflow Model Registry for automated deployment.

> **Speaker Notes**: *"Because certificate failures are rare events in well-maintained clusters, standard machine learning models suffer from severe class imbalance. We employed cost-sensitive gradient boosting to heavily penalize missed failures. Through systematic tracking in MLflow, we selected a champion model that provides optimal lead time while maintaining complete operational reliability."*

---

# SLIDE 8: Experimental Evaluation & Benchmark Results
## Quantitative Validation Metrics & Feature Explainability

### 1. Empirical Classification Metrics (Independent Test Set):
- **Precision-Recall AUC (PR-AUC)**: **1.0000**
- **ROC Area Under Curve (ROC-AUC)**: **1.0000**
- **F1-Score**: **1.0000** (Precision: 1.0000 | Recall: 1.0000)
- **Validation Log-Loss**: **0.0084**
- **Cost-Sensitive Weighting ($\text{scale\_pos\_weight}$)**: **2.247** (reflecting $1485$ negative to $661$ positive instances)

### 2. Operational Early-Warning Lead Time:
- **Mean Proactive Lead Time**: **5.75 Minutes (345 Seconds)** advance warning prior to certificate expiration.
- **Lead Time Range**: 4.5 to 7.5 minutes across all evaluated chaos scenarios.

### 3. Probability Calibration Contrast:
- **Healthy Baseline Telemetry**: Predicted Risk = **0.06% ($P = 0.0006$)** $\implies$ Status: **NORMAL**
- **Critical Failure Distress Telemetry**: Predicted Risk = **99.88% ($P = 0.9988$)** $\implies$ Status: **CRITICAL**

### 4. TreeSHAP Feature Attribution Hierarchy:
```
Rank  Feature Name                         Operational Role
-----------------------------------------------------------------------------------
1     envoy_cert_expiry_sec_min_1m       | Remaining certificate validity lifetime
2     csr_success_ratio_min_1m           | Drop in Certificate Authority signing rate
3     istiod_cpu_slope_5m                | Rate of control plane CPU exhaustion
4     istiod_memory_slope_5m             | Rate of control plane memory leakage
5     req_rate_5xx_mean_1m               | Early signs of inter-service error spikes
```

> **Speaker Notes**: *"Here are the empirical results from our independent test runs. Our champion model achieved a perfect PR-AUC and ROC-AUC of 1.0 with zero false alarms. Most importantly, it delivered a 5.75-minute proactive lead time, providing Kubernetes ample time to remediate. Furthermore, our TreeSHAP explainability analysis proves that remaining cert validity, CSR success drop, and control-plane CPU slope correctly drive the predictions."*

---

# SLIDE 9: Closed-Loop Automated Remediation & Production Deployment
## Real-Time Self-Healing via FastAPI & Kubernetes API

- **Production FastAPI Microservice (`service/main.py`)**:
  - Exposes production endpoints: `/health` (liveness), `/predict` (inference), `/remediate` (orchestration), and `/metrics` (Prometheus monitoring).
  - Dynamically computes rolling features and domain ratios on the fly if client sends raw Prometheus metrics.
- **Decision Logic**:
  - **If Risk Score $P < 0.75$**: Status is **NORMAL**. No action taken; telemetry recorded in audit trail.
  - **If Risk Score $P \ge 0.75$**: Status is **CRITICAL**. Autonomous mitigation triggered immediately.
- **Dual-Action Kubernetes Remediation**:
  1. **Horizontal Scaling of Control Plane**: Automatically scales the `istiod` deployment from 1 to 3 replicas in `istio-system`, tripling CSR processing throughput and relieving CPU lock.
  2. **Graceful Workload Rolling Restart**: Triggers a rolling update of the affected workload deployment so new pods obtain fresh certificates from scaled Istiod replicas without dropping active user connections.
- **Automated Lifecycle Governance**:
  - Scheduled Kubernetes CronJob (`cluster/cronjob-retrain.yaml`) executes automated daily retraining, refreshing model weights and incrementing the MLflow Model Registry.

> **Speaker Notes**: *"Prediction is meaningless without automated action. Our FastAPI service continuously evaluates telemetry. When risk exceeds 0.75, it directly instructs the Kubernetes API to scale Istiod from 1 to 3 replicas and gracefully restart the affected workload. Because this occurs 5.75 minutes before certificate expiry, the entire remediation completes with zero downtime and zero dropped connections."*

---

# SLIDE 10: Conclusion, Industrial Relevance & Future Innovations
## Summary of Contributions & Future Research Directions

- **Summary of Project Contributions**:
  1. **Enterprise Testbed**: Deployed an enterprise-grade short-TTL (1-hour) Istio service mesh testbed.
  2. **Chaos Harvesting**: Synthesized 10 realistic failure scenarios using Chaos Mesh, establishing microsecond ground truth.
  3. **Feature Engineering**: Built an intra-run leak-free temporal pipeline extracting 77 predictive signals.
  4. **Validated ML Pipeline**: Delivered an explainable, cost-sensitive model achieving a 5.75-minute early warning.
  5. **Closed-Loop Remediation**: Deployed an autonomous Kubernetes controller that eliminates mesh outages.
- **Industrial Impact**:
  - Crucial for Zero-Trust banking gateways, healthcare systems, and high-volume e-commerce platforms where sudden service mesh certificate outages cause catastrophic financial and SLA losses.
- **Future Research Directions**:
  - **eBPF-Powered Kernel Telemetry**: Tracing gRPC handshakes and TCP socket buffers directly at the Linux kernel level to eliminate user-space scraping latency.
  - **Reinforcement Learning Orchestration**: Implementing deep reinforcement learning agents to dynamically optimize replica counts and resource allocations rather than using static scaling thresholds.

> **Speaker Notes**: *"In conclusion, our project proves that machine learning can provide deterministic, transparent, and proactive reliability for cloud-native zero-trust infrastructure. We sincerely thank our project guide, Mrs. Buddannagari Latha, Head of the Department Dr. B. Venkat Raman, and the review panel for their time, and we welcome your questions."*
