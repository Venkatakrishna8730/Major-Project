# Stage 3 Audit Document: Bookinfo Workload & Baseline Traffic Profiling

**Stage Status**: Completed Successfully  
**Timestamp**: 2026-11-21 17:50:00 UTC (2026-11-21 23:20:00 Local)  
**Cluster Profile**: `mtls-lab` (Minikube 3-Node Topology)  
**Workload Components**: Istio Bookinfo (4 Services, 6 Pod Replicas), Fortio Load Generator (20 QPS), Strict mTLS  

---

## 1. Intended Scope & Objectives

The goal of Stage 3 is to deploy a representative microservices benchmark application across the 3-node cluster, enforce strict mutual TLS encryption between all inter-service hops, and establish an uninterrupted synthetic traffic baseline.

Key objectives planned in the Master Blueprint:
1. Deploy the 4 polyglot Bookinfo services spanning 6 pod replicas (`productpage-v1`, `details-v1`, `ratings-v1`, `reviews-v1`, `reviews-v2`, `reviews-v3`) with automatic Envoy sidecar injection (`2/2` containers).
2. Apply `PeerAuthentication` with `mode: STRICT` to enforce mutual TLS across the mesh.
3. Configure `DestinationRule` with `mode: ISTIO_MUTUAL` for all internal endpoints.
4. Deploy an in-cluster continuous traffic generator (`fortio`) sustaining 20 QPS (8 concurrent threads) hitting `http://productpage:9080/productpage`.
5. Verify end-to-end request flows and confirm Prometheus records healthy request rates (`istio_requests_total`).
6. Run `collector/cert_poller.py` to audit and record X.509 validity across all 9 mesh pods.
7. Harvest initial baseline logs to `data/raw/s0_baseline/logs`.
8. Provide automated provisioning via `scripts/03_deploy_workload.sh`.

---

## 2. Implementation & Commands Executed

### 2.1 Mutual TLS & Security Policy Enforcement
Created and applied strict peer authentication:
```yaml
apiVersion: security.istio.io/v1beta1
kind: PeerAuthentication
metadata:
  name: default
  namespace: default
spec:
  mtls:
    mode: STRICT
```
Applied strict mutual TLS destination rules across all services (`workload/destination-rules-mtls.yaml`).

### 2.2 Bookinfo Polyglot Microservices Deployment
Applied `workload/bookinfo.yaml` and `workload/bookinfo-gateway.yaml`:
```bash
kubectl apply -f workload/bookinfo.yaml
kubectl apply -f workload/bookinfo-gateway.yaml
```

### 2.3 Continuous Traffic Generator (`workload/loadgen.yaml`)
Configured in-mesh Fortio deployment executing:
```bash
fortio load -qps 20 -t 0 -c 8 -abort-on 0 http://productpage:9080/productpage
```
`-abort-on 0` ensures Fortio resiliently continues load generation without aborting on initial container startup network handshakes.

### 2.4 Automation Script (`scripts/03_deploy_workload.sh`)
Implemented deployment pipeline that:
- Labels namespace `default` with `istio-injection=enabled`.
- Applies security policies, microservice manifests, gateway rules, and load generator.
- Waits for rollout readiness on all 6 deployments.
- Executes internal curl smoke test from `sleep` pod.
- Audits active certificates across all workload pods.

---

## 3. Verification & Evidence

Automated verification executed via `./scripts/03_deploy_workload.sh`:

### 3.1 Workload Pod Status (`2/2` Containers: App + Envoy)
```
NAME                             READY   STATUS    RESTARTS   AGE
details-v1-684d4f87d4-bzj69      2/2     Running   0          12m
loadgen-f56fbc78c-jfc6f          2/2     Running   0          2m
productpage-v1-b96964b8f-r4v62   2/2     Running   0          12m
ratings-v1-5fbdcb594d-tpw4n      2/2     Running   0          12m
reviews-v1-7bbf79f58d-dvsl4      2/2     Running   0          12m
reviews-v2-86f65648b8-t7vsz      2/2     Running   0          12m
reviews-v3-74d7f98ccb-92ctk      2/2     Running   0          12m
sleep-868c754c4b-6wrpn           2/2     Running   4          12d
```
All 6 Bookinfo workloads and the Fortio load generator are healthy with `istio-proxy` injected.

### 3.2 Direct Smoke Test
```
HTTP/1.1 200 OK
server: envoy
date: Sat, 21 Nov 2026 17:46:22 GMT
content-type: text/html; charset=utf-8
content-length: 4294
```
Productpage serves HTTP 200 responses through Envoy proxy.

### 3.3 Continuous Traffic Generation Rate (Prometheus Query)
PromQL Query: `sum(rate(istio_requests_total[1m]))`
```json
{
  "status": "success",
  "data": {
    "resultType": "vector",
    "result": [
      {
        "metric": {},
        "value": [1795283277.723, "154.18537777777777"]
      }
    ]
  }
}
```
PromQL Query: `sum(rate(istio_requests_total{response_code="200"}[1m]))`
```json
{
  "status": "success",
  "data": {
    "resultType": "vector",
    "result": [
      {
        "metric": {},
        "value": [1795283277.913, "154.18875555555553"]
      }
    ]
  }
}
```
- **Aggregate Mesh Throughput**: ~154.18 requests/second across internal service hops (`productpage` $\rightarrow$ `details` + `reviews` $\rightarrow$ `ratings`).
- **Success Rate**: **100% HTTP 200** with 0 errors during healthy baseline operation.

### 3.4 Cryptographic X.509 Mesh-Wide Audit (via `collector/cert_poller.py`)
Recorded in `data/raw/s0_baseline/cert_poller_s0.csv`:
```
timestamp_iso,timestamp_epoch,namespace,pod_name,app,not_before_epoch,not_after_epoch,total_lifetime_sec,seconds_to_expiry,cert_age_sec,rotation_detected
2026-11-21T17:48:11Z,1795283291,default,details-v1-...,details,1795282408,1795286128,3720,2836,884,0
2026-11-21T17:48:11Z,1795283291,default,loadgen-...,loadgen,1795283117,1795286837,3720,3545,175,0
2026-11-21T17:48:11Z,1795283291,default,productpage-v1-...,productpage,1795282635,1795286355,3720,3062,658,0
2026-11-21T17:48:11Z,1795283291,default,ratings-v1-...,ratings,1795282857,1795286577,3720,3284,436,0
2026-11-21T17:48:11Z,1795283291,default,reviews-v1-...,reviews,1795282626,1795286346,3720,3053,667,0
2026-11-21T17:48:11Z,1795283291,default,reviews-v2-...,reviews,1795282774,1795286494,3720,3201,519,0
2026-11-21T17:48:11Z,1795283291,default,reviews-v3-...,reviews,1795282598,1795286318,3720,3025,695,0
2026-11-21T17:48:11Z,1795283291,default,sleep-...,sleep,1795283056,1795286776,3720,3483,237,0
2026-11-21T17:48:11Z,1795283291,istio-system,istio-ingressgateway-...,istio-ingressgateway,1795283057,1795286777,3720,3483,237,0
```
- Total lifetime: exactly **3720 seconds (62 minutes)** across all mesh pods.
- Poller accurately streams per-pod remaining lifetime.

---

## 4. Deviations & Modifications from Original Draft

1. **Fortio Abort Flag**:
   - Added `-abort-on 0` to `workload/loadgen.yaml` arguments. Without this flag, Fortio aborts execution if an initial TCP handshake experiences a transient timeout while mesh proxies initialize. With `-abort-on 0`, load generation runs continuously and resiliently.
2. **Container Image Pre-caching**:
   - Discovered that concurrent image pulling across multi-node Minikube occasionally caused Docker Hub TLS handshake timeouts. Pre-pulled `docker.io/istio/examples-bookinfo-ratings-v1:1.19.1` and `fortio/fortio:latest` into worker nodes directly using `crictl pull`, accelerating node readiness.

---

## 5. Handoff Checklist to Next Stage (Stage 4)

- [x] All 6 Bookinfo microservices running (`2/2` Ready) with Envoy sidecars.
- [x] Strict mTLS (`mode: STRICT` and `ISTIO_MUTUAL`) enforced on all inter-service hops.
- [x] Fortio generating continuous 20 QPS load.
- [x] Prometheus recording ~154.18 requests/second with 100% 200 OK responses.
- [x] `collector/cert_poller.py` tracking active certificates across all 9 mesh pods.
- [x] S0 baseline logs and metrics archived in `data/raw/s0_baseline/`.

**Ready to proceed with Stage 4: Chaos Mesh Fault Injection Engine & Ground-Truth Event Logger.**
