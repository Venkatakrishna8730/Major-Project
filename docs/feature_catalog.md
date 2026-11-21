# Feature Catalog: Predictive mTLS Certificate Rotation Failure Telemetry

This document provides the definitive catalog of all telemetry signals, PromQL expressions, and sidecar poller features used by the machine learning pipeline to forecast mTLS certificate rotation failures.

---

## 1. Feature Taxonomy Overview

The feature space is structured into **five complementary telemetry tiers**:
1. **Citadel / CA Authority Signals**: Direct indicators of Certificate Signing Request (CSR) throughput, bottlenecks, and authentication stalls.
2. **Control-Plane Resource Signals**: CPU, memory, and xDS push stress on `istiod`.
3. **Envoy Proxy & Traffic Signals**: In-mesh connection failures, HTTP 503 response flags, and real-time proxy certificate countdowns.
4. **Cluster State & Pod Churn**: Container restart frequencies and node health.
5. **Sidecar Secret Poller Signals**: Cryptographic X.509 temporal validity and rotation transition events.

---

## 2. Telemetry Signal Catalog

### Tier 1: Citadel CA & Signing Pipeline Metrics
| Signal Name | Metric Type | Exact PromQL Expression | Systems Meaning & Failure Indication |
| :--- | :--- | :--- | :--- |
| `csr_request_rate` | Counter (`rate`) | `sum(rate(citadel_server_csr_count[1m]))` | CSR arrival velocity. Sudden spikes indicate thundering herds (e.g. after node reboot). |
| `cert_issuance_rate` | Counter (`rate`) | `sum(rate(citadel_server_success_cert_issuance_count[1m]))` | Certificate issuance throughput from the CA. |
| `csr_auth_failure_rate` | Counter (`rate`) | `sum(rate(citadel_server_authentication_failure_count[1m]))` | Rejection of CSRs due to missing or invalid ServiceAccount tokens (Scenario S9). |
| `csr_parse_err_rate` | Counter (`rate`) | `sum(rate(citadel_server_csr_parsing_err_count[1m]))` | Corrupted or malformed CSR requests. |
| `csr_success_ratio` | Derived Ratio | `sum(rate(citadel_server_success_cert_issuance_count[1m])) / clamp_min(sum(rate(citadel_server_csr_count[1m])), 0.001)` | Health ratio of CA pipeline. Value $< 1.0$ indicates signing requests are queueing, timing out, or failing. |

---

### Tier 2: Istiod Control Plane Resource Stress
| Signal Name | Metric Type | Exact PromQL Expression | Systems Meaning & Failure Indication |
| :--- | :--- | :--- | :--- |
| `istiod_process_cpu` | Counter (`rate`) | `sum(rate(process_cpu_seconds_total{app="istiod"}[1m]))` | CPU processing time consumed by `istiod`. High values indicate signing backlog or discovery churn. |
| `istiod_resident_memory` | Gauge | `sum(process_resident_memory_bytes{app="istiod"})` | Working memory consumed by `istiod`. Pre-OOM memory exhaustion leads to CA unavailability. |
| `istiod_cgroup_cpu` | Counter (`rate`) | `sum(rate(container_cpu_usage_seconds_total{namespace="istio-system",pod=~"istiod.*"}[1m]))` | Cgroup-level CPU utilization. Throttled CPU directly prolongs CSR signing latency. |
| `pilot_xds_push_rate` | Counter (`rate`) | `sum(rate(pilot_xds_pushes[1m]))` | Frequency of dynamic config pushes from Pilot to Envoy proxies. High push rates compete with CA workers. |

---

### Tier 3: Envoy Proxy & Traffic Telemetry
| Signal Name | Metric Type | Exact PromQL Expression | Systems Meaning & Failure Indication |
| :--- | :--- | :--- | :--- |
| `envoy_cert_expiry_sec` | Gauge | `min by (pod) (istio_agent_cert_expiry_seconds{namespace="default"})` | Continuous countdown of remaining certificate lifetime in seconds reported by `istio-agent`. |
| `envoy_5xx_rate` | Counter (`rate`) | `sum(rate(istio_requests_total{response_code=~"5.."}[1m]))` | In-mesh HTTP 5xx errors. Spikes with flags `UF` (Upstream Connection Failure) or `URX` (Reset). |
| `envoy_handshake_drops` | Counter (`rate`) | `sum(rate(envoy_server_ssl_connection_error[1m]))` | Drop in SSL/mTLS handshakes between sidecars due to invalid, expired, or missing peer certificates. |

---

### Tier 4: Kubernetes Cluster & Pod Health (via Kube-State-Metrics)
| Signal Name | Metric Type | Exact PromQL Expression | Systems Meaning & Failure Indication |
| :--- | :--- | :--- | :--- |
| `pod_restarts_5m` | Counter (`increase`) | `sum(increase(kube_pod_container_status_restarts_total[5m]))` | Pod restart frequency across the mesh. Crash loops cause mass re-registration and CSR spikes. |
| `node_ready_count` | Gauge | `sum(kube_node_status_condition{condition="Ready",status="true"})` | Count of active ready worker nodes. Node dropouts indicate potential partition or reboot chaos (S7). |

---

### Tier 5: Dynamic Secret Poller Features (via `collector/cert_poller.py`)
| Feature Name | Type | Unit | Description |
| :--- | :--- | :--- | :--- |
| `seconds_to_expiry` | Numerical | Seconds | $t_{\text{notAfter}} - t_{\text{now}}$. Exact remaining lifetime on active Envoy X.509 secret. |
| `cert_age_sec` | Numerical | Seconds | $t_{\text{now}} - t_{\text{notBefore}}$. Age since certificate was issued. |
| `total_lifetime_sec` | Numerical | Seconds | Total validity window ($t_{\text{notAfter}} - t_{\text{notBefore}}$), fixed to ~3720s (62 min). |
| `rotation_detected` | Binary | $\{0, 1\}$ | Transition flag: $1$ at the exact poll interval where $t_{\text{notBefore}}$ increments (new cert installed). |
| `rotation_count` | Counter | Integer | Cumulative count of successful rotations completed by this pod since startup. |

---

## 3. Machine Learning Feature Matrix Construction

During Stage 5 feature engineering, each 15-second time step $t$ combines:
1. **Instantaneous Values**: All raw gauge and rate signals above.
2. **Rolling Temporal Windows** ($W \in \{1\text{m}, 5\text{m}, 15\text{m}\}$):
   - Rolling Mean: $\mu(X, W)$
   - Rolling Max: $\max(X, W)$
   - Rolling Standard Deviation: $\sigma(X, W)$
3. **Velocity Derivatives**: First-order difference $\Delta(X) = X_t - X_{t-1}$ to capture acceleration of CPU, memory, and CSR queues.
4. **Prediction Horizon Labels**:
   - $y^{(H)}_t = 1$ if a ground-truth rotation failure occurs in $(t, t+H]$ where $H \in \{5\text{m}, 10\text{m}, 15\text{m}\}$.
