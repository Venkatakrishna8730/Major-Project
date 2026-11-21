# Stage 2 Audit Document: Full-Stack Observability Pipeline

**Stage Status**: Completed Successfully  
**Timestamp**: 2026-11-21 16:54:00 UTC (2026-11-21 22:24:00 Local)  
**Cluster Profile**: `mtls-lab` (Minikube 3-Node Topology)  
**Observability Components**: Prometheus v2.51.1, Kube-State-Metrics (KSM), Envoy Secret Poller, Log Harvester  

---

## 1. Intended Scope & Objectives

The goal of Stage 2 is to deploy, calibrate, and verify an end-to-end multi-tier observability pipeline across the service mesh. 

Machine learning for certificate rotation failure forecasting requires continuous numerical time series (control-plane stress, CSR velocity) and ground-truth cryptographic labels (exact remaining certificate seconds, error logs, and rotation transition events).

Key objectives planned in the Master Blueprint:
1. Deploy Prometheus addon in `istio-system` with a 15-second scrape interval.
2. Deploy `kube-state-metrics` (KSM) via Helm in `istio-system` with scrape annotations.
3. Validate active scrape targets and confirm Prometheus captures Citadel CA metrics, `istiod` resources, Envoy proxy metrics, and container restarts.
4. Implement the **Sidecar Secret Poller (`collector/cert_poller.py`)**:
   - Discovers mesh pods with `istio-proxy`.
   - Directly extracts X.509 certificate chains from Envoy's Secret Discovery Service (SDS) every 15s.
   - Computes `seconds_to_expiry`, `cert_age_sec`, and detects rotation events when `notBefore` increments.
5. Implement the **Proxy & Control-Plane Log Harvester (`collector/log_harvester.sh`)** for error event extraction (TLS handshake drops, SDS failures, CSR errors).
6. Author the comprehensive **Feature Catalog (`docs/feature_catalog.md`)**.
7. Provide single-command automation via `scripts/02_setup_observability.sh`.

---

## 2. Implementation & Commands Executed

### 2.1 Prometheus & Kube-State-Metrics Deployment
Applied Prometheus addon from Istio samples:
```bash
kubectl apply -f cluster/observability/prometheus.yaml
kubectl -n istio-system rollout status deployment/prometheus --timeout=180s
```
Deployed Kube-State-Metrics using Helm with string annotations:
```bash
helm upgrade --install ksm prometheus-community/kube-state-metrics \
    --namespace istio-system \
    --set-string service.annotations."prometheus\.io/scrape"="true" \
    --set-string service.annotations."prometheus\.io/port"="8080"
kubectl -n istio-system rollout status deployment/ksm-kube-state-metrics --timeout=120s
```

### 2.2 Sidecar Secret Poller Daemon (`collector/cert_poller.py`)
Implemented a Python daemon that queries Envoy's SDS dynamic active secrets via `istioctl proxy-config secret <pod>.<ns> -o json`:
- Parses X.509 validity dates (`notBefore`, `notAfter`).
- Computes `seconds_to_expiry = notAfter - now` and `cert_age_sec = now - notBefore`.
- Maintains an in-memory `RotationStateTracker` to detect certificate rotation transitions ($1$ when `notBefore` increments, $0$ otherwise).
- Writes tidy time-series CSV rows to `data/raw/cert_poller.csv`.

### 2.3 Proxy & Control-Plane Log Harvester (`collector/log_harvester.sh`)
Implemented bash harvester that pulls:
- Control plane logs from `deploy/istiod`.
- Ingress gateway logs from `deploy/istio-ingressgateway`.
- Workload sidecar logs from all pods with `istio-proxy` in `default`.
- Filters critical keywords (`certificate|tls|sds|citadel|handshake|503|refused|expired`).

### 2.4 Feature Catalog Authoring (`docs/feature_catalog.md`)
Created complete documentation of:
- 5 telemetry tiers (Citadel CA, Control Plane, Envoy Traffic, Cluster Health, Secret Poller).
- Exact PromQL query strings.
- Metric types (counter rates, gauges, ratios, temporal deltas).
- Systems and physical failure indicators.

---

## 3. Verification & Evidence

Automated verification executed via `./scripts/02_setup_observability.sh`:

### 3.1 Prometheus Pod & Target Health
```
NAME                                      READY   STATUS    RESTARTS   AGE
istio-ingressgateway-d57867d76-96vqt      1/1     Running   2          12d
istiod-7dd8c95694-8q5wl                   1/1     Running   2          12d
ksm-kube-state-metrics-65c95647dc-4sw66   1/1     Running   0          3m
prometheus-644fc9cd87-hcpqr               2/2     Running   0          4m
```
Active healthy Prometheus scrape targets: **13 targets responding with `up=1`** (including `istiod:15014`, `ingressgateway:15020`, `sleep:15020`, `ksm:8080`, cAdvisor, and apiserver).

### 3.2 Key Telemetry Metrics Validation
```
  [ OK ] citadel_server_csr_count               :  1 series (Citadel CA CSR counter)
  [ OK ] citadel_server_success_cert_issuance_count :  1 series (Citadel cert issuance counter)
  [ OK ] process_cpu_seconds_total              :  7 series (Process CPU seconds)
  [ OK ] process_resident_memory_bytes          :  7 series (Process memory footprint)
  [ OK ] container_cpu_usage_seconds_total      : 68 series (Cgroup container CPU)
  [ OK ] pilot_xds_pushes                       :  4 series (Pilot xDS config push rate)
  [ OK ] istio_agent_cert_expiry_seconds        :  2 series (Proxy certificate remaining seconds)
  [ OK ] kube_pod_container_status_restarts_total : 19 series (KSM container restarts)
```

### 3.3 Sidecar Secret Poller Output
From `collector/cert_poller.py --once`:
```
timestamp_iso,timestamp_epoch,namespace,pod_name,app,not_before_iso,not_after_iso,not_before_epoch,not_after_epoch,total_lifetime_sec,seconds_to_expiry,cert_age_sec,rotation_detected,rotation_count
2026-11-21T16:53:08.170937+00:00,1795279988,default,sleep-868c754c4b-6wrpn,sleep,2026-11-21T16:44:16+00:00,2026-11-21T17:46:16+00:00,1795279456,1795283176,3720,3188,532,0,0
2026-11-21T16:53:08.170937+00:00,1795279988,istio-system,istio-ingressgateway-d57867d76-96vqt,istio-ingressgateway,2026-11-21T16:44:17+00:00,2026-11-21T17:46:17+00:00,1795279457,1795283177,3720,3189,531,0,0
```
- Certificate validity confirmed: `total_lifetime_sec = 3720s` (62 minutes).
- Real-time countdown confirmed: `seconds_to_expiry = 3188s`, `cert_age_sec = 532s`.

### 3.4 Log Harvester Output
```
[INFO] Harvesting istiod logs...
  Saved istiod logs: 605 lines
[INFO] Harvesting Envoy sidecar logs from workload pods...
  Saved ingress gateway log: 122 lines
[INFO] Filtering error events (TLS handshake drops, SDS failures, CSR errors, 503s)...
  Extracted error lines: 49 matching events
```

---

## 4. Deviations & Modifications from Original Draft

1. **Helm Annotation Type Enforcement**:
   - Passed `--set-string` for both `prometheus.io/scrape="true"` and `prometheus.io/port="8080"` to prevent Helm from coercing string annotations into integer/boolean YAML types.
2. **Prometheus Container Scoping**:
   - Observed that Istio's Prometheus pod contains two containers (`prometheus-server` and `prometheus-server-configmap-reload`). Automated queries and commands explicitly target `-c prometheus-server`.
3. **Dual Expiry Monitoring**:
   - Discovered that `istio_agent_cert_expiry_seconds` is actively emitted by the sidecar proxy into Prometheus, giving a continuous Prometheus gauge alongside our independent SDS X.509 poller daemon.

---

## 5. Handoff Checklist to Next Stage (Stage 3)

- [x] Prometheus running with 15s scrape interval and 13 active scrape targets.
- [x] Kube-State-Metrics running and scraped by Prometheus.
- [x] Citadel CA, control plane CPU/mem, and cert expiry metrics confirmed active.
- [x] `collector/cert_poller.py` verified and writing structured time series.
- [x] `collector/log_harvester.sh` operational for log collection.
- [x] `docs/feature_catalog.md` published.

**Ready to proceed with Stage 3: Bookinfo Workload Deployment & Baseline Traffic Profiling.**
