#!/usr/bin/env python3
"""
Generate professional UML diagrams for the Major Project Report using Matplotlib.
Outputs:
1. report/figures/use_case_diagram.png
2. report/figures/component_architecture.png
3. report/figures/sequence_diagram.png
4. report/figures/activity_dataflow.png
"""

import matplotlib.pyplot as plt
import matplotlib.patches as patches
from pathlib import Path

FIGURES_DIR = Path("/home/user/Documents/SeriviceMeshML/report/figures")
FIGURES_DIR.mkdir(parents=True, exist_ok=True)

plt.rcParams['font.sans-serif'] = 'DejaVu Sans'
plt.rcParams['font.family'] = 'sans-serif'

# -------------------------------------------------------------
# 1. USE CASE DIAGRAM
# -------------------------------------------------------------
def generate_use_case():
    fig, ax = plt.subplots(figsize=(10, 7), dpi=300)
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 8)
    ax.axis('off')

    # Boundary Box (System)
    sys_box = patches.FancyBboxPatch((2.2, 0.5), 5.6, 7.0, boxstyle="round,pad=0.2",
                                     ec="#1e3a8a", fc="#f8fafc", lw=2)
    ax.add_patch(sys_box)
    ax.text(5.0, 7.2, "System Boundary: Predictive mTLS Reliability Framework",
            ha='center', va='center', fontsize=12, fontweight='bold', color="#1e3a8a")

    # Use Cases (Ellipses)
    use_cases = [
        (5.0, 6.2, "UC1: Scrape & Buffer SDS\nSecret Expiry & CSR Rates"),
        (5.0, 5.0, "UC2: Compute 77 Rolling\nTemporal & Slope Features"),
        (5.0, 3.8, "UC3: Infer Early Rotation\nFailure Risk (Horizon H=10m)"),
        (5.0, 2.6, "UC4: Autonomous Control Plane\nScaling & Workload Restart"),
        (5.0, 1.4, "UC5: Model Retraining &\nMLflow Registry Promotion")
    ]
    for x, y, label in use_cases:
        ellipse = patches.Ellipse((x, y), 3.8, 0.85, ec="#2563eb", fc="#eff6ff", lw=1.5)
        ax.add_patch(ellipse)
        ax.text(x, y, label, ha='center', va='center', fontsize=9, fontweight='semibold', color="#0f172a")

    # Actors
    actors = [
        (1.0, 5.5, "Mesh Telemetry\nAgents (Envoy/K8s)"),
        (1.0, 2.0, "SRE / Cluster\nAdministrator"),
        (9.0, 4.0, "Kubernetes API\nOrchestrator"),
        (9.0, 1.5, "MLflow Registry\n& Tracking DB")
    ]
    for x, y, label in actors:
        # Draw stick figure head + body
        circle = patches.Circle((x, y + 0.35), 0.22, ec="#334155", fc="#cbd5e1", lw=1.5)
        ax.add_patch(circle)
        ax.plot([x, x], [y + 0.13, y - 0.25], color="#334155", lw=2)
        ax.plot([x - 0.25, x + 0.25], [y, y], color="#334155", lw=2)
        ax.plot([x, x - 0.2], [y - 0.25, y - 0.55], color="#334155", lw=2)
        ax.plot([x, x + 0.2], [y - 0.25, y - 0.55], color="#334155", lw=2)
        ax.text(x, y - 0.8, label, ha='center', va='center', fontsize=9, fontweight='bold', color="#1e293b")

    # Connections
    lines = [
        ((1.3, 5.5), (3.1, 6.2)),
        ((1.3, 5.5), (3.1, 5.0)),
        ((1.3, 2.0), (3.1, 2.6)),
        ((1.3, 2.0), (3.1, 1.4)),
        ((6.9, 3.8), (8.6, 4.0)),
        ((6.9, 2.6), (8.6, 4.0)),
        ((6.9, 1.4), (8.6, 1.5))
    ]
    for start, end in lines:
        ax.annotate("", xy=end, xytext=start, arrowprops=dict(arrowstyle="-", color="#64748b", lw=1.2))

    plt.tight_layout()
    plt.savefig(FIGURES_DIR / "use_case_diagram.png", dpi=300)
    plt.close()
    print("[OK] Generated use_case_diagram.png")

# -------------------------------------------------------------
# 2. COMPONENT / ARCHITECTURE UML DIAGRAM
# -------------------------------------------------------------
def generate_component_diagram():
    fig, ax = plt.subplots(figsize=(11, 7.5), dpi=300)
    ax.set_xlim(0, 11)
    ax.set_ylim(0, 8)
    ax.axis('off')

    def draw_component(x, y, w, h, title, subtext, bg="#f1f5f9", border="#0f766e"):
        box = patches.FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.15", ec=border, fc=bg, lw=1.8)
        ax.add_patch(box)
        # Small component tabs on top left
        t1 = patches.Rectangle((x - 0.15, y + h - 0.45), 0.3, 0.15, ec=border, fc=bg, lw=1.2)
        t2 = patches.Rectangle((x - 0.15, y + h - 0.75), 0.3, 0.15, ec=border, fc=bg, lw=1.2)
        ax.add_patch(t1)
        ax.add_patch(t2)
        ax.text(x + w/2, y + h - 0.35, title, ha='center', va='center', fontsize=10, fontweight='bold', color="#0f172a")
        ax.text(x + w/2, y + h/2 - 0.15, subtext, ha='center', va='center', fontsize=8, color="#334155")

    # Components
    draw_component(0.8, 4.8, 2.8, 1.8, "«component»\nWorkload Pods (Envoy)", "Envoy Proxy Sidecar\nSDS Secret Agent\nShort-TTL (1h) Certs", "#e0f2fe", "#0284c7")
    draw_component(4.2, 4.8, 2.8, 1.8, "«component»\nControl Plane (Istiod)", "Pilot & Citadel CA\nCSR Processing Engine\nxDS Configuration Push", "#fef3c7", "#d97706")
    draw_component(7.6, 4.8, 2.8, 1.8, "«component»\nTelemetry Pipeline", "Sidecar Secret Poller\nPrometheus Scraper (15s)\nPromQL Harvester", "#f3e8ff", "#9333ea")

    draw_component(0.8, 1.2, 2.8, 1.8, "«component»\nFeature Pipeline", "77-Dimensional Engine\nRolling Windows (1m,5m,15m)\n1st-Order Slopes (dy/dt)", "#ecfdf5", "#059669")
    draw_component(4.2, 1.2, 2.8, 1.8, "«component»\nML Inference Service", "FastAPI Microservice\nChampion XGBoost (H10)\nTreeSHAP Explainability", "#ffe4e6", "#e11d48")
    draw_component(7.6, 1.2, 2.8, 1.8, "«component»\nAuto-Remediator", "K8s Controller Client\nIstiod Auto-Scaler (1->3)\nWorkload Rolling Restarter", "#ffedd5", "#ea580c")

    # Connectors
    arrows = [
        ((3.6, 5.7), (4.2, 5.7), "gRPC / CSR (mTLS)"),
        ((7.0, 5.7), (7.6, 5.7), "Scrapes Metrics"),
        ((7.6, 4.8), (2.2, 3.0), "Metrics Parquet"),
        ((3.6, 2.1), (4.2, 2.1), "77 Features"),
        ((7.0, 2.1), (7.6, 2.1), "Risk P >= 0.75"),
        ((9.0, 3.0), (5.6, 4.8), "Scale Replicas")
    ]
    for start, end, lbl in arrows:
        ax.annotate(lbl, xy=end, xytext=start,
                    arrowprops=dict(arrowstyle="->", color="#1e293b", lw=1.5),
                    fontsize=8, fontweight='semibold', color="#1e293b",
                    ha='center', va='bottom')

    plt.tight_layout()
    plt.savefig(FIGURES_DIR / "component_architecture.png", dpi=300)
    plt.close()
    print("[OK] Generated component_architecture.png")

# -------------------------------------------------------------
# 3. SEQUENCE UML DIAGRAM
# -------------------------------------------------------------
def generate_sequence_diagram():
    fig, ax = plt.subplots(figsize=(11, 7.5), dpi=300)
    ax.set_xlim(0, 11)
    ax.set_ylim(0, 8.5)
    ax.axis('off')

    entities = [
        (1.2, "Envoy Proxy\n(Workload)"),
        (3.5, "Istiod CA\n(Control Plane)"),
        (5.8, "Prometheus\n& Pipeline"),
        (8.0, "FastAPI ML\nInference"),
        (10.0, "K8s API\nController")
    ]

    for x, name in entities:
        # Entity Header
        box = patches.FancyBboxPatch((x - 0.8, 7.5), 1.6, 0.7, boxstyle="round,pad=0.1", ec="#1e3a8a", fc="#dbeafe", lw=1.5)
        ax.add_patch(box)
        ax.text(x, 7.85, name, ha='center', va='center', fontsize=8.5, fontweight='bold', color="#1e3a8a")
        # Lifeline
        ax.plot([x, x], [7.5, 0.5], color="#94a3b8", linestyle="--", lw=1.5)

    def message(y, x1, x2, text, is_dotted=False, color="#0f172a"):
        ls = "--" if is_dotted else "-"
        ax.annotate("", xy=(x2, y), xytext=(x1, y),
                    arrowprops=dict(arrowstyle="->", color=color, lw=1.4, linestyle=ls))
        ax.text((x1 + x2)/2, y + 0.12, text, ha='center', va='bottom', fontsize=8, fontweight='medium', color=color)

    # Sequence Messages
    message(7.0, 1.2, 3.5, "1. Send CSR (Cert Expiry < 1800s)")
    message(6.4, 3.5, 3.5, "Stress: CPU 1.95, Goroutines locked", color="#b91c1c")
    message(5.8, 3.5, 1.2, "2. CSR Timeout / Error 504", is_dotted=True, color="#b91c1c")
    message(5.1, 1.2, 5.8, "3. Scrape cert_expiry=420s, csr_fail=100%")
    message(4.4, 5.8, 8.0, "4. Ingest 77 Features (Min/Mean/Slopes)")
    message(3.7, 8.0, 8.0, "5. XGBoost Inference (Risk P=0.9988 >= 0.75)", color="#b91c1c")
    message(3.0, 8.0, 10.0, "6. Trigger Remediation (/remediate)", color="#ea580c")
    message(2.3, 10.0, 3.5, "7. Scale istiod (1 -> 3 replicas)", color="#047857")
    message(1.6, 10.0, 1.2, "8. Rolling restart ratings-v1", color="#047857")
    message(0.9, 1.2, 3.5, "9. Fresh CSR Issued & Rotated Successfully", color="#0284c7")

    plt.tight_layout()
    plt.savefig(FIGURES_DIR / "sequence_diagram.png", dpi=300)
    plt.close()
    print("[OK] Generated sequence_diagram.png")

# -------------------------------------------------------------
# 4. ACTIVITY / DATA FLOW DIAGRAM
# -------------------------------------------------------------
def generate_activity_diagram():
    fig, ax = plt.subplots(figsize=(10, 8), dpi=300)
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 9)
    ax.axis('off')

    # Initial Node
    start_circle = patches.Circle((5.0, 8.4), 0.2, ec="#0f172a", fc="#0f172a")
    ax.add_patch(start_circle)

    def draw_activity(x, y, text, w=4.4, h=0.7, bg="#e0f2fe", border="#0284c7"):
        b = patches.FancyBboxPatch((x - w/2, y - h/2), w, h, boxstyle="round,pad=0.15", ec=border, fc=bg, lw=1.5)
        ax.add_patch(b)
        ax.text(x, y, text, ha='center', va='center', fontsize=8.5, fontweight='semibold', color="#0f172a")

    draw_activity(5.0, 7.4, "Scrape Sidecar Secret & Istiod Metrics (15s)")
    draw_activity(5.0, 6.2, "Compute 77 Features (Rolling Stats & Slopes)")
    draw_activity(5.0, 5.0, "Execute XGBoost Model Inference (Champion H=10)")

    # Decision Diamond
    diamond = patches.Polygon([[5.0, 4.2], [6.2, 3.7], [5.0, 3.2], [3.8, 3.7]],
                              ec="#d97706", fc="#fef3c7", lw=1.5)
    ax.add_patch(diamond)
    ax.text(5.0, 3.7, "Risk Score\nP >= 0.75?", ha='center', va='center', fontsize=8, fontweight='bold', color="#92400e")

    # Branches
    draw_activity(2.2, 2.2, "Log Risk Status: NORMAL\n(Audit Trail: Healthy)", w=3.4, h=0.7, bg="#ecfdf5", border="#059669")
    draw_activity(7.8, 2.2, "Autonomous Auto-Remediation:\n1. Scale Istiod (1->3)\n2. Restart Affected Workload", w=3.8, h=0.8, bg="#fee2e2", border="#dc2626")
    draw_activity(5.0, 0.8, "Publish Metrics & Wait for Next Telemetry Window", w=5.0, h=0.6, bg="#f1f5f9", border="#475569")

    # Arrows
    arrows = [
        ((5.0, 8.2), (5.0, 7.85), ""),
        ((5.0, 6.95), (5.0, 6.65), ""),
        ((5.0, 5.75), (5.0, 5.45), ""),
        ((5.0, 4.55), (5.0, 4.2), ""),
        ((3.8, 3.7), (2.2, 3.7), "No (P < 0.75)"),
        ((2.2, 3.7), (2.2, 2.65), ""),
        ((6.2, 3.7), (7.8, 3.7), "Yes (P >= 0.75)"),
        ((7.8, 3.7), (7.8, 2.7), ""),
        ((2.2, 1.75), (4.0, 1.1), ""),
        ((7.8, 1.7), (6.0, 1.1), "")
    ]
    for start, end, txt in arrows:
        ax.annotate(txt, xy=end, xytext=start,
                    arrowprops=dict(arrowstyle="->", color="#334155", lw=1.4),
                    fontsize=8, fontweight='bold', color="#0f172a", ha='center', va='bottom')

    plt.tight_layout()
    plt.savefig(FIGURES_DIR / "activity_dataflow.png", dpi=300)
    plt.close()
    print("[OK] Generated activity_dataflow.png")

if __name__ == "__main__":
    generate_use_case()
    generate_component_diagram()
    generate_sequence_diagram()
    generate_activity_diagram()
    print("[SUCCESS] All 4 UML diagrams successfully rendered in report/figures!")
