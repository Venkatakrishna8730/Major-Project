# Stage 1 Audit Document: Multi-Node Minikube Cluster & Short-TTL Istio Mesh

**Stage Status**: Completed Successfully  
**Timestamp**: 2026-11-08 19:27:00 UTC (2026-11-09 00:57:00 Local)  
**Cluster Profile**: `mtls-lab` (Minikube 3-Node Topology)  
**Istio Version**: 1.22.3 (Demo Profile with custom pilot env vars)  

---

## 1. Intended Scope & Objectives

The goal of Stage 1 is to provision a realistic multi-node Kubernetes cluster and establish a live Istio service mesh configured specifically for **rapid mTLS certificate rotation**.

In standard production meshes, workload certificates live for 24 hours, meaning renewal attempts occur only once every 12 hours (at 50% TTL). To generate a training dataset with hundreds of natural and fault-induced rotation events within practical experiment runs (45–60 minutes), the mesh must issue short-lived certificates (~1 hour) that rotate every ~30 minutes.

Key objectives planned in the Master Blueprint:
1. Provision a 3-node Minikube cluster (`mtls-lab`: 1 control-plane + 2 worker nodes) with `containerd` CRI for seamless Chaos Mesh integration.
2. Define and apply `cluster/istio-operator-short-ttl.yaml` configuring `DEFAULT_WORKLOAD_CERT_TTL=1h` on Pilot and `SECRET_TTL=1h` in Envoy proxy metadata.
3. Validate rollout and readiness of `istiod` and `istio-ingressgateway`.
4. Enable automatic sidecar injection on the `default` namespace (`istio-injection=enabled`).
5. Develop and execute `scripts/verify_cert_rotation.sh` to extract X.509 certificate chains directly from Envoy's Secret Discovery Service (SDS) and verify the 1-hour expiration window.

---

## 2. Implementation & Commands Executed

### 2.1 Cluster Topology Provisioning
Executed via automated script `scripts/01_setup_cluster.sh`:
```bash
export MINIKUBE_HOME="${PROJECT_ROOT}/.minikube"
minikube start \
    -p mtls-lab \
    --nodes=3 \
    --driver=docker \
    --container-runtime=containerd \
    --cpus=4 \
    --memory=5120 \
    --wait=all
```

### 2.2 Short-TTL IstioOperator Configuration
Created manifest `cluster/istio-operator-short-ttl.yaml`:
```yaml
apiVersion: install.istio.io/v1alpha1
kind: IstioOperator
metadata:
  namespace: istio-system
  name: istiocontrolplane
spec:
  profile: demo
  meshConfig:
    enableAutoMtls: true
    defaultConfig:
      proxyMetadata:
        SECRET_TTL: "1h"
  components:
    pilot:
      k8s:
        env:
        - name: DEFAULT_WORKLOAD_CERT_TTL
          value: "1h"
    egressGateways:
    - name: istio-egressgateway
      enabled: false
```
Applied via:
```bash
istioctl install -y -f cluster/istio-operator-short-ttl.yaml
```

### 2.3 Automatic Injection & Probe Workload
```bash
kubectl label namespace default istio-injection=enabled --overwrite
kubectl apply -f istio-1.22.3/samples/sleep/sleep.yaml -n default
kubectl -n default rollout status deployment/sleep --timeout=180s
```

### 2.4 Cryptographic Verification Utility (`scripts/verify_cert_rotation.sh`)
Implemented utility extracting Envoy dynamic active secrets:
```bash
istioctl proxy-config secret "${POD}.${NAMESPACE}" -o json \
  | jq -r '.dynamicActiveSecrets[] | select(.name=="default") | .secret.tlsCertificate.certificateChain.inlineBytes' \
  | base64 -d | openssl x509 -noout -dates -subject -issuer
```

---

## 3. Verification & Evidence

### 3.1 Cluster Node Topology
```
NAME           STATUS   ROLES           AGE    VERSION   INTERNAL-IP    EXTERNAL-IP   OS-IMAGE             KERNEL-VERSION      CONTAINER-RUNTIME
mtls-lab       Ready    control-plane   101s   v1.33.1   192.168.58.2   <none>        Ubuntu 22.04.5 LTS   6.8.0-138-generic   containerd://1.7.27
mtls-lab-m02   Ready    <none>          30s    v1.33.1   192.168.58.3   <none>        Ubuntu 22.04.5 LTS   6.8.0-138-generic   containerd://1.7.27
mtls-lab-m03   Ready    <none>          5s     v1.33.1   192.168.58.4   <none>        Ubuntu 22.04.5 LTS   6.8.0-138-generic   containerd://1.7.27
```
All 3 nodes transitioned to `Ready` status with containerd runtime.

### 3.2 Istio Control Plane Readiness
```
deployment "istiod" successfully rolled out
deployment "istio-ingressgateway" successfully rolled out
```

### 3.3 Probe Pod Sidecar Injection
```
NAME                     READY   STATUS    RESTARTS   AGE
sleep-868c754c4b-6wrpn   2/2     Running   0          45s
```
Container count `2/2` verifies that `istio-proxy` was automatically injected alongside the application container.

### 3.4 Cryptographic X.509 Evidence
Inspection results from `./scripts/verify_cert_rotation.sh default sleep-868c754c4b-6wrpn`:
```
==========================================================
 X.509 mTLS Certificate Rotation & Validity Inspector
==========================================================
Inspecting Pod: sleep-868c754c4b-6wrpn (Namespace: default)

Subject Identity : 
Issuer Authority : O = cluster.local

Certificate Timestamps:
  Issued (notBefore)     : Nov  8 19:24:35 2026 GMT (Epoch: 1794165875)
  Expires (notAfter)     : Nov  8 20:26:35 2026 GMT (Epoch: 1794169595)
  Total Lifetime         : 62 minutes (~1 hour)
  Elapsed Age            : 2 minutes (122s)
  Remaining Validity     : 59 minutes (3598s)
  Expected Next Renewal  : 2026-11-09 01:25:35 UTC (~50% TTL mark)

[ VERIFIED ] Short-TTL policy confirmed! Workload certificate lifetime is ~1 hour.
```

The difference between `notAfter` (20:26:35 GMT) and `notBefore` (19:24:35 GMT) is exactly **62 minutes (~1 hour)**. Istio's internal grace period adds 2 minutes to the requested 1h window. Renewal is scheduled to initiate at ~50% TTL (~30 minutes from issuance).

---

## 4. Deviations & Modifications from Original Draft

1. **Minikube Node Sizing & Memory Boundary**:
   - Tuned memory pool to `5120MB` across 3 nodes to ensure the host machine retains ~2.4GB free memory for the upcoming Prometheus stack, Python data harvesters, and MLflow processes.
2. **Egress Gateway Disabled**:
   - Disabled `istio-egressgateway` in `istio-operator-short-ttl.yaml` because intra-mesh mTLS testing only relies on `istiod`, `istio-ingressgateway`, and sidecar proxies, saving cluster compute.
3. **Automated Probe Verification Built-in**:
   - Added automated deployment of `istio-1.22.3/samples/sleep` directly into `scripts/01_setup_cluster.sh` so that every cluster spin-up immediately validates certificate generation without manual intervention.

---

## 5. Handoff Checklist to Next Stage (Stage 2)

- [x] 3-node Minikube cluster running with containerd socket accessible.
- [x] Istio 1.22.3 control plane (`istiod`) healthy and operational.
- [x] Workload certificate short TTL (~1 hour) cryptographically verified via X.509 inspection.
- [x] Namespace `default` configured for automatic sidecar injection (`istio-injection=enabled`).
- [x] `verify_cert_rotation.sh` operational for ongoing certificate audits.

**Ready to proceed with Stage 2: Full-Stack Observability Pipeline (Prometheus, KSM, Sidecar Secret Poller, Log Harvester).**
