# Quantum Helix Architecture

Technical architecture for the hybrid quantum-classical multi-cloud threat detection prototype.

---

## 1. Design goals

1. **Multi-cloud parity** — AWS and Azure telemetry share one CIM before ML.  
2. **Vector-first detection** — PCA produces ℝ⁴ feature vectors consumed by all engines.  
3. **Classical control group first** — Isolation Forest + RBF SVM establish the baseline.  
4. **Quantum kernel as primary quantum path** — fidelity QSVM; variational QNN is optional.  
5. **Quantum-frugal inference** — Only a 4-D vector crosses the quantum boundary.  
6. **SIEM-native output** — ASFF (Security Hub) + CEF (Sentinel).  
7. **Measurable PoC+** — `benchmark.py` reports detection / FPR / subtle-APT / latency / cost.

---

## 2. Logical architecture (PoC+)

```text
┌──────────────────────────────────────────────────────────────────────────┐
│  Operator Surfaces                                                        │
│  cli.py (scan|benchmark)   validate.py   frontend/ (React) + app.py      │
└───────────────────────────────┬──────────────────────────────────────────┘
                                ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  Stage 1 — Normalization          normalization.py + apt_corpus.py        │
│  AWS / Azure JSON → CloudSecurityEvent (CIM)                              │
└───────────────────────────────┬──────────────────────────────────────────┘
                                ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  Stage 2 — Classical Reduction    data_processor.py                       │
│  StandardScaler + PCA(n=4) → feature vectors ℝ⁴                           │
└───────────────────────────────┬──────────────────────────────────────────┘
                                ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  Stage 3 — Multi-engine detection                                         │
│  classical_baselines.py  IsolationForest | ClassicalSVM                   │
│  quantum_kernel.py       Fidelity kernel + SVC (primary quantum)          │
│  ensemble.py             Weighted HybridThreatEnsemble (default)          │
│  quantum_engine.py       Variational QNN (optional sidecar)               │
└───────────────────────────────┬──────────────────────────────────────────┘
                                ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  Stage 4 — Alerting + Evidence                                            │
│  alerter.py (ASFF/CEF/Slack)    benchmark.py (metrics scoreboard)         │
└──────────────────────────────────────────────────────────────────────────┘
```

See [POC_PLUS.md](POC_PLUS.md) for implementation status and non-claims.

---

## 3. Component responsibilities

| Module | Responsibility | Stateful? |
|--------|----------------|-----------|
| `normalization.py` | CIM dataclass, AWS/Azure parsers, mock generators | Stateless parsers |
| `apt_corpus.py` | Normal / loud / subtle APT synthetic corpora | Stateless |
| `data_processor.py` | Scale + PCA compress to 4-D vectors | **Yes** — fitted scaler/PCA |
| `classical_baselines.py` | Isolation Forest + RBF SVM control group | **Yes** |
| `quantum_kernel.py` | Fidelity kernel + QSVM (primary quantum) | **Yes** |
| `ensemble.py` | Weighted hybrid scorer (default CLI engine) | **Yes** |
| `quantum_engine.py` | Optional variational QNN sidecar | **Yes** — circuit weights |
| `benchmark.py` | Classical vs quantum metrics harness | Ephemeral |
| `alerter.py` | Thresholding, ASFF/CEF, Slack dry-run | Alert history buffer |
| `models.py` | SQLite ORM: users, tenants, alerts, cases, audit | **Yes** — persistent |
| `app.py` / `routes.py` / `frontend/` | Flask REST/SSE + React SPA; JWT + RBAC | Long-running process / local DB |
| `cli.py` / `main.py` | CLI UX shells | Process scope |
| `validate.py` | Deterministic loud-attack gates | Ephemeral |

---

## 4. Data flow (single event)

```text
Raw AWS or Azure JSON
        │
        ▼
parse_aws() / parse_azure()
        │
        ▼
CloudSecurityEvent
  timestamp, normalized_identity, source_ip,
  api_velocity, auth_failures, data_volume_bytes,
  cloud_provider, raw_event_id
        │
        ▼
to_feature_vector()
  [api_velocity, auth_failures, data_volume_bytes, ip_hash]
        │
        ▼
StandardScaler → PCA → ℝ⁴
        │
        ▼
AngleEmbedding → StronglyEntanglingLayers → ⟨Z₀…Z₃⟩
        │
        ▼
Threat Score  (QNN readout ⊕ PCA energy prior)
        │
        ├── < threshold → silent / “ok”
        └── ≥ threshold → ASFF + CEF + Slack
```

---

## 5. Common Information Model (CIM)

Canonical type: `CloudSecurityEvent` in `normalization.py`.

| CIM field | Role in detection |
|-----------|-------------------|
| `api_velocity` | Burst / automation signal |
| `auth_failures` | Credential stuffing / RBAC denial signal |
| `data_volume_bytes` | Exfiltration / bulk egress signal |
| `source_ip` (hashed) | Spatial / reputation-adjacent numeric feature |
| Identity / provider / id | Alert enrichment (not PCA inputs) |

Full field mapping: [CIM.md](CIM.md).

**Anomaly injection (mock stream):** ~5% of events combine high velocity + elevated auth failures + large byte volume to stress the detector.

---

## 6. Classical feature pipeline

`ClassicalFeaturePipeline`:

1. Materialize event feature rows as a NumPy matrix.  
2. `StandardScaler.fit_transform` during warmup.  
3. `PCA(n_components=4).fit_transform` — width fixed to qubit count.  
4. Persist fitted objects in memory for `transform_single`.

**Why PCA = 4?**  
Matches `wires=4` on the QNode. Keeping the quantum width small is intentional for eventual shot-budget / queue economics on real QPUs.

Warmup batch size must be ≥ 4 (prefer tens–hundreds for stable covariance).

---

## 7. Quantum engine

### Device

```python
dev = qml.device("default.qubit", wires=4)
```

### Circuit (`quantum_anomaly_circuit`)

| Layer | PennyLane API | Purpose |
|-------|---------------|---------|
| Embedding | `AngleEmbedding(..., rotation='X')` | Map PCA coords → RX angles |
| Trainable | `StronglyEntanglingLayers(weights)` | Entangled variational ansatz |
| Measurement | `expval(PauliZ(i))` for `i∈{0,1,2,3}` | Real readout vector |

### Weight shape

```python
qml.StronglyEntanglingLayers.shape(n_layers=3, n_wires=4)  # → (3, 4, 3)
```

Using `.shape(...)` avoids dimension mismatches during training / inference.

### Threat score

1. Map each ⟨Z⟩ ∈ [-1, 1] → `[0, 1]` via `(1 - z) / 2`.  
2. Average across four wires → QNN score.  
3. Compute PCA-space L2 energy; logistic-map to an energy score.  
4. Blend (~40% QNN / ~60% energy) and clip to `[0, 1]`.

The hybrid blend makes injected multi-signal attacks reliably separable in the prototype while preserving a trainable quantum term.

### Training

`QuantumThreatDetector.train_on_batch` uses `qml.AdamOptimizer` with MSE against weak labels (`0` benign / `1` anomalous). Demonstrates weight updates; not a production MLOps trainer.

---

## 8. Alerting & SIEM contracts

`AlertOrchestrator.evaluate_and_alert(event, threat_score, threshold)`:

| Artifact | Standard | Consumer |
|----------|----------|----------|
| ASFF JSON | AWS Security Finding Format `2018-10-08` | Security Hub |
| CEF string | ArcSight-style CEF | Microsoft Sentinel |
| Slack blocks | Incoming webhook JSON | SOC channel (dry-run by default) |

Default threshold: **0.75** (CLI/main) or adjustable via the dashboard / `POST /api/controls`. Validation suite uses a slightly lower gate for clear pass/fail margins.

---

## 9. Operator surfaces

| Surface | Coupling | Notes |
|---------|----------|-------|
| `cli.py` | Warmup fit → stream mock → score → ASCII table | Blocking, rate-limited sleep |
| `app.py` + `routes.py` + `frontend/` | Flask REST/SSE + React SPA | JWT sessions, multi-tenant RBAC, SQLite persistence |
| `main.py` | Explicit 4-stage logged pipeline | Best for architecture demos |
| `validate.py` | Synthetic normal + fixed attacks | CI-friendly exit codes |

All surfaces import the same detection modules — no duplicated scoring logic.

### Application access control

```text
Browser (React SPA)
    │  Bearer session JWT  (type=session)
    ▼
routes.require_auth  ──► reject mfa_temp / stream tokens
                     ──► reject deactivated users
    │
    ├─ require_role(ADMIN_ROLES)  → user / tenant / playbook / controls
    └─ tenant_id filter           → alerts, cases, audit, rules
```

| Concern | Implementation |
|---------|----------------|
| Identity | Local `users` table; password hashes via Werkzeug |
| Session | HS256 JWT (`SECRET_KEY`), 12h expiry, typed (`session` / `mfa_temp` / `stream`), `tv` session revoke |
| MFA | Optional TOTP + WebAuthn; admin can clear enrollment |
| Authorization | Role checks + tenant scoping; last active `SUPER_ADMIN` protected |
| Audit | `audit_logs` for privileged analyst and user-admin actions |

UI surfaces: **My account** (self-service) and **Administration → Users** (lifecycle). Details: [User Guide](USER_GUIDE.md#333-administration--users), [API Reference](API_REFERENCE.md#auth--users).

---

## 10. Scaling from simulator to hardware

| Concern | Prototype today | Production direction |
|---------|-----------------|----------------------|
| Device | `default.qubit` (analytic / local) | PennyLane Braket / Azure Quantum plugins |
| Ingest | In-process mock generator | Kinesis / Event Hubs / Pub-Sub → Flink/Spark |
| Feature store | In-memory scaler/PCA | Versioned model artifacts (S3 / ADLS) |
| Training | Short Adam loops | Offline jobs; parameter-shift / gradient-free on QPU |
| Shots | Exact expectations | Configure `shots=` for hardware variance |
| Alerts | Dry-run Slack + printed ASFF/CEF | `batch_import_findings`, Sentinel Data Connector, real webhooks |

**Invariant:** CIM width → PCA(4) → 4-qubit template → SIEM schemas. Changing cloud ingest or QPU vendor should not require redesigning those contracts.

---

## 11. Security & trust boundaries

Prototype assumptions:

- Mock detection data only; no live cloud tenant credentials required for scoring demos.  
- Slack URLs default to a non-routable example host with `dry_run_webhook=True`.  
- `backend="qpu"` logs a warning and still executes on the local simulator.
- Console auth is local JWT + optional MFA (not SSO). Default `admin` / `quantum123` is for local demos only — set `ADMIN_PASSWORD` and `SECRET_KEY` before any shared deployment.
- Deactivated users are rejected at login and on every authenticated request.

Treat alert JSON as sensitive once real identities appear; redact before sharing logs externally.

---

## 12. Extension points

| Extension | Suggested hook |
|-----------|----------------|
| Real CloudTrail / Activity Log files | New methods on `MultiCloudLogParser` or adapters feeding `parse_aws` / `parse_azure` |
| Extra CIM features | Extend `to_feature_vector` and increase qubits + PCA components together |
| Model registry | Serialize `scaler`, `pca`, `weights` after warmup |
| Multi-tenant routing | Tag ASFF `AwsAccountId` / Azure workspace from config |
| True QPU path | Replace `dev = qml.device(...)` behind a factory keyed by `backend` |

---

## 13. Related docs

- [User Guide](USER_GUIDE.md) — operating procedures  
- [API Reference](API_REFERENCE.md) — classes and flags  
- [CIM Reference](CIM.md) — field-level mapping  
- [Operations](OPERATIONS.md) — troubleshooting and production checklist  
