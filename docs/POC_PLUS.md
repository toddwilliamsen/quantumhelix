# PoC+ Implementation Status

What Quantum Helix implements **beyond MVP**, how the engines relate, and how to prove (or refute) quantum value.

---

## Product posture (current)

| Layer | Status | Role |
|-------|--------|------|
| Multi-cloud CIM + PCA vectors | **MVP+ complete** | Immediate classical pipeline value |
| Classical baselines (Isolation Forest, RBF SVM) | **PoC+ complete** | Control group / streaming baseline |
| Quantum Kernel SVM (PennyLane fidelity kernel) | **PoC+ complete** | **Primary quantum path** |
| Hybrid ensemble blend | **PoC+ complete** | Default CLI scan engine |
| Variational QNN | **Optional sidecar** | Research / demo — not required for PoC claims |
| React SOC GUI + Flask API | **PoC+ complete** | Ensemble live charts, engine votes, cloud mix, Evidence Lab, Triage Inbox, Settings |
| Head-to-head benchmark harness | **PoC+ complete** | Detection rate, FPR, subtle-APT recall, latency, cost proxy |
| Subtle APT corpus | **PoC+ complete** | Low-and-slow attacks (not only loud outliers) |
| Live GuardDuty / Defender ingest | Not yet | Next production step |
| Real Braket / Azure Quantum jobs | Placeholder only | Documented, not wired |

---

## Architecture (PoC+)

```text
AWS / Azure telemetry (mock or Azure dummy blobs)
        │
        ▼
CIM normalization  →  StandardScaler + PCA → ℝ⁴ feature vectors
        │
        ├──────────────┬──────────────────┬──────────────────┐
        ▼              ▼                  ▼                  ▼
 IsolationForest   Classical SVM    Quantum Kernel SVM   QNN (optional)
 (unsupervised)    (RBF control)    (fidelity + SVC)     (variational)
        └──────────────┴──────────────────┴──────────────────┘
                                 │
                    HybridThreatEnsemble (default)
                                 │
                    threshold → ASFF / CEF / Slack
                                 │
                    benchmark.py (metrics report)
```

### Why this shape

- **Vectors first** — all detectors share the same PCA features (fair comparison).  
- **Classical control group** — answers “why not Isolation Forest / SVM alone?”  
- **Quantum kernel / QSVM** — primary quantum bet (more suitable than QNN for this PoC).  
- **QNN retained** — optional `--engine qnn` / `--include-qnn` for research, not default.  

---

## New modules

| File | Purpose |
|------|---------|
| `classical_baselines.py` | `IsolationForestDetector`, `ClassicalSVMDetector` |
| `quantum_kernel.py` | Fidelity kernel circuit + `QuantumKernelSVMDetector` |
| `ensemble.py` | `HybridThreatEnsemble` weighted blend |
| `apt_corpus.py` | Normal / loud / subtle APT event builders |
| `benchmark.py` | Train/test split metrics + CLI report |

---

## How to run

```bash
source .venv/bin/activate

# Head-to-head benchmark (classical vs quantum kernel)
python benchmark.py
python benchmark.py --include-qnn
python cli.py benchmark

# Default scan uses the hybrid ensemble
python cli.py scan --duration 8 --threshold 0.70 --engine ensemble

# Single-engine scans
python cli.py scan --engine quantum_kernel --duration 5
python cli.py scan --engine classical_svm --duration 5
python cli.py scan --engine isolation_forest --duration 5
python cli.py scan --engine qnn --duration 5   # optional sidecar
```

### Benchmark columns

| Metric | Meaning |
|--------|---------|
| Detect | Overall attack recall at the decision threshold |
| FPR | False-positive rate on benign test rows |
| Subtle | Recall on low-and-slow APT rows |
| Loud | Recall on high-signal attacks |
| AUC | ROC-AUC on continuous scores |
| Fit(s) | Training / kernel+fit wall time |
| ms/evt | Mean score latency |
| Cost~ | Relative compute proxy (1.0 = Isolation Forest baseline) |

---

## What is *not* claimed yet

This PoC+ stack **enables** evidence collection; it does **not** automatically prove quantum advantage.

A commercially meaningful claim still needs:

1. Larger, labeled multi-cloud APT corpora  
2. Repeated benchmarks with confidence intervals  
3. Cost modeling on Lightning / Braket / Azure Quantum  
4. Cases where quantum kernel clearly beats classical SVM **and** Isolation Forest on subtle recall without exploding FPR  

Use `benchmark.py` deltas (subtle APT recall Δ, FPR Δ) as the honest scoreboard.

---

## Related docs

- [ARCHITECTURE.md](ARCHITECTURE.md) — updated hybrid design  
- [VALIDATION.md](VALIDATION.md) — loud-attack validation suite  
- [API_REFERENCE.md](API_REFERENCE.md) — new public classes  
- [USER_GUIDE.md](USER_GUIDE.md) — operator commands  
