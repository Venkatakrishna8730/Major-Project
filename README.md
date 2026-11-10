# Early Prediction of mTLS Certificate Rotation Failures in Istio Service Mesh Using Machine Learning

[![Kubernetes](https://img.shields.io/badge/Kubernetes-Minikube-326CE5?logo=kubernetes&logoColor=white)](https://kubernetes.io/)
[![Istio](https://img.shields.io/badge/Service_Mesh-Istio_1.22.3-466BB0?logo=istio&logoColor=white)](https://istio.io/)
[![Chaos Mesh](https://img.shields.io/badge/Fault_Injection-Chaos_Mesh-1E88E5)](https://chaos-mesh.org/)
[![MLflow](https://img.shields.io/badge/MLOps-MLflow-0194E2?logo=mlflow&logoColor=white)](https://mlflow.org/)
[![XGBoost](https://img.shields.io/badge/Model-XGBoost-EB5424)](https://xgboost.readthedocs.io/)
[![FastAPI](https://img.shields.io/badge/Serving-FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)

---

## 1. Research Overview

In modern cloud-native Kubernetes deployments, Mutual TLS (mTLS) is the cornerstone of zero-trust microservice communication. Workload identity certificates are issued with short validity windows and automatically renewed by the service mesh control plane (`istiod`) in the background.

In production, however, certificate rotation pipelines silently degrade due to:
- Control-plane CPU/memory exhaustion (`istiod`).
- gRPC transport degradation (packet loss, latency spikes on port 15012).
- Intermittent network partitions and CNI glitches.
- Identity validation stalls (e.g., ServiceAccount deletion, token expiry).

Currently, detection is **strictly reactive**: operators only notice rotation failures after certificates expire, causing cascading TLS handshake failures and `503 Service Unavailable (UF/URX)` outages.

### Research Contribution & Novelty Claim
1. **Predictive Failure Forecasting**: Moving from reactive alerting to **proactive failure prediction**, forecasting rotation failures **10–15 minutes before certificate expiration** while existing certificates are still serving traffic.
2. **Novel Telemetry Dataset**: Generating the first labeled dataset for mTLS rotation failures in service meshes using controlled Chaos Mesh fault injection.
3. **Three-Tier Operational Architecture**: Automated metric harvesting $\rightarrow$ MLflow versioned model training $\rightarrow$ real-time FastAPI inference microservice with automated Kubernetes remediation (e.g. `istiod` proactive autoscaling).

---

## 2. Project Roadmap & Documentation

The project is structured into **nine progressive stages (Stages 0 to 8)**. Every stage includes automated scripts, verifiable evidence, and a dedicated audit document:

- 📋 **[Master Implementation Plan](docs/MASTER_IMPLEMENTATION_PLAN.md)**: Full end-to-end technical blueprint and architectural deep-dives.
- 📄 **[Stage 0: Environment & Automation Bootstrap](docs/stage_0_environment_audit.md)**: Completed audit of compute resources, pinned binaries (`istioctl 1.22.3`, `jq`), and Python virtualenv.
- 📄 **[Stage 1: Multi-Node Minikube & Short-TTL Istio Mesh](docs/stage_1_cluster_and_mesh.md)**: Completed 3-node cluster with containerd CRI and Istio configured for ~1-hour certificates rotating every ~30 minutes.

---

## 3. Repository Structure

```
.
├── Resources/            # Background research notes, papers, and reference documents
├── bin/                  # Project-local pinned executables (istioctl, jq)
├── chaos/                # Chaos Mesh fault injection manifests (S0–S10)
│   └── scenarios/
├── cluster/              # Kubernetes, Minikube, and IstioOperator configurations
├── collector/            # PromQL range collector, cert-poller, and log harvesters
├── data/                 # Data storage (git-ignored)
│   ├── raw/              # Per-run raw metrics and logs
│   └── processed/        # Feature tables (Parquet)
├── docs/                 # Master roadmap, stage audit docs, feature catalogs, dataset card
├── ml/                   # MLflow training scripts, XGBoost models, evaluation metrics
├── scripts/              # Automated bash and python runners
├── service/              # FastAPI real-time inference microservice & auto-remediator
├── workload/             # Istio Bookinfo microservice manifests & fortio load generator
├── requirements.txt      # Pinned Python package dependencies
└── README.md
```

---

## 4. Quick Start

### Step 1: Environment Bootstrap & Verification
```bash
chmod +x scripts/*.sh
./scripts/bootstrap_tools.sh
./scripts/00_verify_env.sh
```

### Step 2: Spin Up Multi-Node Cluster & Mesh
```bash
./scripts/01_setup_cluster.sh
```

### Step 3: Cryptographically Audit Certificate Rotation
```bash
./scripts/verify_cert_rotation.sh default <pod_name>
```
