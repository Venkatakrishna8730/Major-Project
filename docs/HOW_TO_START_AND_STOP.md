# Runbook: How to Stop, Resume, and Rebuild the Setup

This runbook documents how to cleanly stop all running resources, resume an existing stopped environment, or rebuild the entire multi-tier system from scratch using our automated stage scripts.

---

## 1. How to Stop All Resources Cleanly

To stop all running Kubernetes nodes, Istio services, Fortio traffic, and Chaos Mesh components so that **zero CPU and zero RAM** are consumed on your machine:

```bash
cd /home/user/Documents/SeriviceMeshML

export MINIKUBE_HOME="/home/user/Documents/SeriviceMeshML/.minikube"
export PATH="/home/user/Documents/SeriviceMeshML/bin:$PATH"

# Stop the 3-node cluster cleanly
minikube stop -p mtls-lab

# Verify all containers have stopped
docker ps
```
> **Note**: Stopping the cluster preserves all disk state, configurations, container images, Istio short-TTL policies, and logs stored in `.minikube/`.

---

## 2. Option A: Fast Resume (Resuming Existing Stopped Setup)

When you return to continue working, you do **not** need to reinstall anything. Resuming the existing cluster takes about **30–60 seconds**:

### Step 1: Set Environment Variables & Start Cluster
```bash
cd /home/user/Documents/SeriviceMeshML

export MINIKUBE_HOME="/home/user/Documents/SeriviceMeshML/.minikube"
export PATH="/home/user/Documents/SeriviceMeshML/bin:$PATH"

# Start the existing profile
minikube start -p mtls-lab
```

### Step 2: Configure Worker Node Parameters
*(Ensures inotify watchers and DNS resolution are active after node power-on)*:
```bash
for node in mtls-lab mtls-lab-m02 mtls-lab-m03; do
    docker exec -u 0 "${node}" sysctl -w fs.inotify.max_user_instances=8192
    docker exec -u 0 "${node}" sysctl -w fs.inotify.max_user_watches=1048576
    docker exec -u 0 "${node}" sh -c "echo 'nameserver 8.8.8.8' > /etc/resolv.conf && echo 'nameserver 1.1.1.1' >> /etc/resolv.conf"
done
```

### Step 3: Verify All Pods Are Ready
```bash
# Check node status (all 3 Ready)
kubectl get nodes

# Check default namespace (all 6 Bookinfo workloads + loadgen + sleep should be 2/2)
kubectl get pods -n default

# Check observability & control plane (istiod, ingressgateway, prometheus, ksm)
kubectl get pods -n istio-system

# Check Chaos Mesh controllers and daemons
kubectl get pods -n chaos-mesh
```

### Step 4: Verify Live Traffic & Certificate Validity
```bash
# Verify continuous Fortio load generator (20 QPS)
kubectl -n default logs -l app=loadgen -c fortio --tail=10

# Audit X.509 certificate expiry across all pods
.venv/bin/python collector/cert_poller.py --once
```

---

## 3. Option B: Full Rebuild from Scratch (Idempotent Scripts)

If you ever delete the cluster or deploy on a new machine, you can rebuild the entire environment from ground zero using our stage automation scripts:

```bash
cd /home/user/Documents/SeriviceMeshML

# Stage 0: Bootstrap CLI tools, jq, istioctl 1.22.3, and Python virtual environment
./scripts/bootstrap_tools.sh
./scripts/00_verify_env.sh

# Stage 1: Provision 3-node Minikube cluster and install Istio with 1-hour cert TTL
./scripts/01_setup_cluster.sh

# Stage 2: Deploy Prometheus, Kube-State-Metrics, and verify telemetry streams
./scripts/02_setup_observability.sh

# Stage 3: Deploy Bookinfo microservices, strict mTLS, and Fortio 20 QPS load generator
./scripts/03_deploy_workload.sh

# Stage 4: Deploy Chaos Mesh with containerd CRI, kernel limits, and execute pilot run
./scripts/04_setup_chaos.sh
```

---

## 4. Quick Troubleshooting & Verification Reference

| Goal | Command |
| :--- | :--- |
| **Inspect a specific pod certificate** | `./scripts/verify_cert_rotation.sh default <pod_name>` |
| **Run real-time cert poller** | `.venv/bin/python collector/cert_poller.py --once` |
| **Check Prometheus request rate** | `kubectl -n istio-system exec deploy/prometheus -c prometheus-server -- wget -qO- 'http://localhost:9090/api/v1/query?query=sum(rate(istio_requests_total[1m]))' \| jq .` |
| **Check CA CSR issuance rate** | `kubectl -n istio-system exec deploy/prometheus -c prometheus-server -- wget -qO- 'http://localhost:9090/api/v1/query?query=sum(rate(citadel_server_success_cert_issuance_count[1m]))' \| jq .` |
| **Trigger a Chaos experiment** | `.venv/bin/python scripts/run_experiment.py --scenario s1_istiod_cpu --fault-duration 60` |
| **Harvest proxy & istiod logs** | `./collector/log_harvester.sh 15m data/raw/logs` |
| **View experiment log** | `cat data/raw/experiment_log.csv` |
| **View ground-truth failure log** | `cat data/raw/event_log.csv` |
