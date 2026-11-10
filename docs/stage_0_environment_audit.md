# Stage 0 Audit Document: Environment Verification & Tool Automation Bootstrap

**Stage Status**: Completed Successfully  
**Timestamp**: 2026-11-08 18:47:00 UTC (2026-11-09 00:17:00 Local)  
**Execution Node**: Linux 6.8.0-138-generic x86_64 (`vk`)  

---

## 1. Intended Scope & Objectives

The goal of Stage 0 is to eliminate environmental ambiguity, configure hardware/compute boundaries, and bootstrap a 100% reproducible development and execution environment for the predictive mTLS failure lifecycle project.

Key objectives planned in the Master Blueprint:
1. Audit host compute resources (CPU cores, RAM capacity, free disk, Docker daemon responsiveness).
2. Provision and verify core container and cloud-native CLI binaries (`docker`, `minikube`, `kubectl`, `helm`, `istioctl`, `jq`, `git`, `openssl`, `curl`).
3. Pin `istioctl` to version `1.22.3` across the entire research study.
4. Establish an isolated Python 3.10 virtual environment (`.venv`) with pinned dependencies for data processing, machine learning, MLflow experiment tracking, and FastAPI microservice inference.
5. Create the project repository directory skeleton.
6. Provide fully automated, idempotent bootstrap scripts (`scripts/bootstrap_tools.sh` and `scripts/00_verify_env.sh`).

---

## 2. Implementation & Commands Executed

### 2.1 Repository Layout Initialization
Created the standardized modular directory structure:
```bash
mkdir -p scripts cluster collector chaos/scenarios workload ml service docs data/raw data/processed bin
```

### 2.2 Toolchain Bootstrap Script (`scripts/bootstrap_tools.sh`)
Implemented an automated installer that:
- Downloads and places standalone `jq` v1.7.1 into local project `bin/`.
- Downloads Istio `1.22.3` and creates a symlink from `istio-1.22.3/bin/istioctl` to `bin/istioctl`.
- Generates Python virtual environment at `.venv/`.
- Upgrades `pip` and installs pinned packages from `requirements.txt`.

### 2.3 Python Dependency Definition (`requirements.txt`)
Defined dependencies across four core subsystems:
- **Data & Telemetry**: `requests`, `pyyaml`, `pandas>=2.0.0`, `pyarrow>=14.0.0`, `prometheus-api-client`
- **Machine Learning**: `scikit-learn>=1.3.0`, `xgboost>=2.0.0`, `shap>=0.44.0`
- **Experiment Tracking**: `mlflow>=2.10.0`
- **Serving & Inference**: `fastapi>=0.110.0`, `uvicorn[standard]>=0.28.0`

### 2.4 Automated Verification Script (`scripts/00_verify_env.sh`)
Implemented an audit utility that tests:
- System kernel and host specs.
- CLI commands with version reporting.
- Docker daemon reachability.
- Resource thresholds (CPUs $\ge 4$, free RAM, free disk).
- Python module imports and version introspection within `.venv`.

---

## 3. Verification & Evidence

The complete verification run was executed via `./scripts/00_verify_env.sh`.

### 3.1 Terminal Output Summary
```
==========================================================
 Stage 0: Environment & Toolchain Audit
==========================================================
Host & System Architecture:
  OS Kernel   : Linux 6.8.0-138-generic x86_64
  Hostname    : vk
  Date / Time : 2026-11-08 18:46:45 UTC

--- Core CLI Binaries ---
[ OK ] docker       : Docker version 28.3.1, build 38b7060
[ OK ] minikube     : v1.36.0
[ OK ] kubectl      : v1.33.1
[ OK ] helm         : v3.18.3+g6838ebc
[ OK ] istioctl     : 1.22.3
[ OK ] python3      : Python 3.10.12
[ OK ] git          : git version 2.34.1
[ OK ] jq           : jq-1.7.1
[ OK ] openssl      : OpenSSL 3.0.2 15 Mar 2022 (Library: OpenSSL 3.0.2 15 Mar 2022)
[ OK ] curl         : curl 7.81.0 (x86_64-pc-linux-gnu) libcurl/7.81.0 OpenSSL/3.0.2

--- Docker Daemon Status ---
[ OK ] Docker daemon is active and responding.

--- System Compute Resources ---
  CPU Cores       : 4
[ OK ] CPU cores >= 4
  RAM Total/Avail : 7.5Gi total / 4.4Gi available
  Disk Free Here  : 85G

--- Python Virtual Environment & Packages ---
Using virtualenv Python: /home/user/Documents/SeriviceMeshML/.venv/bin/python
[ OK ] requests     : 2.34.2
[ OK ] pandas       : 2.3.3
[ OK ] numpy        : 2.2.6
[ OK ] pyarrow      : 25.0.1
[ OK ] sklearn      : 1.7.2
[ OK ] xgboost      : 3.2.0
[ OK ] yaml         : 6.0.3
[ OK ] matplotlib   : 3.10.9
[ OK ] mlflow       : 3.18.0
[ OK ] fastapi      : 0.162.2
[ OK ] uvicorn      : 0.54.0

==========================================================
 Audit Summary: 13 checks passed, 0 problems detected
==========================================================
```

### 3.2 Key Hardware & Software Baseline Record
- **Compute**: 4 vCPU cores, 7.5 GiB total memory, 85 GiB free disk storage.
- **Istio Version**: `1.22.3` (Pinned).
- **Minikube Version**: `v1.36.0` (Docker container driver).
- **MLflow Version**: `3.18.0`.
- **XGBoost Version**: `3.2.0`.
- **FastAPI Version**: `0.162.2`.

---

## 4. Deviations & Modifications from Original Draft

1. **Local Binary Directory Isolation**:
   - `jq` and `istioctl` were installed into the project-local `bin/` directory rather than requiring global `/usr/local/bin` system modifications. Scripts prepend `${PROJECT_ROOT}/bin` to `PATH`.
2. **Minikube Directory Scoping**:
   - `MINIKUBE_HOME` is explicitly routed to `${PROJECT_ROOT}/.minikube` to prevent permission collisions on host home directories.
3. **MLflow Version Alignment**:
   - Installed MLflow `3.18.0` with SQLite/file-backed tracing capabilities ready for local experiment logging in Stage 6.

---

## 5. Handoff Checklist to Next Stage (Stage 1)

- [x] Docker daemon operational and responsive.
- [x] Minikube binary operational (`v1.36.0`).
- [x] `kubectl` and `helm` ready for cluster interaction.
- [x] `istioctl` pinned to `1.22.3` and available in `bin/istioctl`.
- [x] `jq` available for JSON parsing of Envoy secrets.
- [x] Python virtual environment populated and verified.
- [x] Directory structure prepared.

**Ready to proceed with Stage 1: Multi-Node Minikube Cluster & Istio Mesh with Short-Lived Certificates.**
