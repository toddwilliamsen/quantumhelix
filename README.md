# Quantum Helix

**Multi-Cloud Hybrid Quantum-Classical Threat Detection Engine** (PoC+)

Quantum Helix ingests AWS and Azure security telemetry, normalizes it into a Common Information Model (CIM), reduces features with classical PCA into **vectors**, then scores anomalies with a **hybrid ensemble**: Isolation Forest + classical RBF SVM + PennyLane **quantum kernel (QSVM)**. A variational QNN remains an optional research sidecar. Alerts emit AWS Security Hub (ASFF) and Microsoft Sentinel (CEF) payloads.

---

## What it does

| Stage | Capability |
|-------|------------|
| Ingest | Mock / synthetic AWS CloudTrail-style and Azure Activity / NSG-style logs |
| Normalize | Map both clouds into `CloudSecurityEvent` CIM fields |
| Reduce | `StandardScaler` + PCA → exactly **4** principal component **vectors** |
| Detect (default) | Hybrid ensemble: Isolation Forest + RBF SVM + **quantum kernel SVM** |
| Detect (optional) | Variational QNN sidecar (`--engine qnn`) |
| Prove | `benchmark.py` — classical control vs quantum kernel metrics |
| Alert | ASFF + CEF SIEM payloads and Slack webhook mock |

> **PoC+ posture:** Classical baselines are mandatory. Quantum kernel is the primary quantum path. QNN is not required to claim PoC readiness. See [docs/POC_PLUS.md](docs/POC_PLUS.md).

---

## Quick start

```bash
chmod +x setup.sh
./setup.sh

source .venv/bin/activate          # macOS / Linux
# Windows PowerShell: .\.venv\Scripts\Activate.ps1

python validate.py                 # loud-attack pipeline check
python benchmark.py                # classical vs quantum-kernel scoreboard
python cli.py scan --duration 10 --threshold 0.70 --engine ensemble
python app.py                      # start the Flask API backend (port 8000)
cd frontend && npm run dev         # start the React SOC dashboard
python main.py --events 50         # orchestration path (QNN demo)

# Optional: deploy dummy Azure telemetry into your subscription
./azure/deploy_dummy_data.sh
```

Default console login after first `app.py` start: **`admin` / `quantum123`** (override with `ADMIN_PASSWORD`). Open **Administration → Users** to create analyst accounts, assign roles, reset passwords, clear MFA, or deactivate users. Every signed-in user can manage their own password and MFA under **My account**.

**Requirements:** Python **3.11+**, pip, and a terminal (bash / zsh / Git Bash / WSL).

### Keep dependencies current

Quantum / scientific packages mature quickly. Pins target the latest **compatible** stables:

```bash
python check_deps.py              # report drift vs PyPI (exit 1 if outdated)
python check_deps.py --update     # bump requirements.txt
pip install -r requirements.txt && python validate.py
```

Weekly GitHub Dependabot PRs and a Dependencies workflow also watch PyPI. See [docs/DEPENDENCIES.md](docs/DEPENDENCIES.md).

---

## Documentation

| Document | Audience | Description |
|----------|----------|-------------|
| [User Guide](docs/USER_GUIDE.md) | Analysts & operators | Install, run CLI/GUI, roles, user management, interpret scores |
| [PoC+ Status](docs/POC_PLUS.md) | Product / security eng | What is implemented beyond MVP |
| [Architecture](docs/ARCHITECTURE.md) | Architects & engineers | System design, ensemble, quantum kernel, app RBAC |
| [Dependencies](docs/DEPENDENCIES.md) | Maintainers | Latest-stable pin policy, watcher, Dependabot |
| [API Reference](docs/API_REFERENCE.md) | Developers | Modules, auth/user APIs, CLI flags |
| [CIM Reference](docs/CIM.md) | Integrators | Common Information Model field mapping (AWS / Azure) |
| [Validation Guide](docs/VALIDATION.md) | QA / security eng | Automated verification of clean vs. attack traffic |
| [Azure Dummy Data](docs/AZURE_DUMMY_DATA.md) | Azure testers | Deploy test telemetry into an Azure subscription |
| [Operations & Troubleshooting](docs/OPERATIONS.md) | SRE / SOC eng | Bootstrap admin, access control, production checklist |
| [Glossary](docs/GLOSSARY.md) | All readers | Security and QML terms, including console RBAC |
---

## Project layout

```
quantum/
├── normalization.py      # CIM + multi-cloud parsers + mock stream
├── data_processor.py     # Classical StandardScaler + PCA(4)
├── quantum_engine.py     # PennyLane QNN threat detector
├── alerter.py            # ASFF / CEF / Slack alert orchestration
├── cli.py                # Click CLI (`Quantum Helix scan`)
├── models.py             # SQLite models (User, Tenant, Alert, Case, AuditLog, …)
├── app.py                # Flask app entry (SQLite bootstrap, static SPA, background loop)
├── routes.py             # REST + SSE blueprint (auth, users, alerts, cases, MFA)
├── frontend/             # React SPA Dashboard (Vite) — My account + Administration
├── classical_baselines.py # Isolation Forest + RBF SVM control group
├── quantum_kernel.py     # PennyLane fidelity kernel + QSVM
├── ensemble.py           # HybridThreatEnsemble (default scan engine)
├── apt_corpus.py         # Loud + subtle APT synthetic corpora
├── benchmark.py          # Classical vs quantum-kernel scoreboard
├── quantum_engine.py     # Optional variational QNN sidecar
├── azure/
│   ├── deploy_dummy_data.sh   # Deploy test telemetry to Azure
│   ├── generate_telemetry.py  # Build Activity/NSG NDJSON
│   └── fetch_and_score.py     # Download blobs → QNN score
├── validate.py           # Automated detection validation suite
├── check_deps.py         # PyPI freshness watcher / pin updater
├── setup.sh              # Environment bootstrap
├── requirements.txt      # Exact latest-compatible stable pins
├── .github/
│   ├── dependabot.yml
│   └── workflows/deps-freshness.yml
├── README.md
└── docs/                 # Full documentation set
```

---

## Threat score model

Scores are continuous in **`[0.0, 1.0]`**:

| Range | Meaning |
|-------|---------|
| `0.00 – 0.40` | Typical / baseline cloud behavior |
| `0.40 – 0.75` | Elevated — investigate |
| `≥ 0.75` | Default critical threshold — SIEM / Slack alerts |

The score blends QNN Pauli-Z expectation readouts with a classical PCA-space energy prior so extreme multi-signal attacks (high velocity + auth failures + exfiltration volume) separate cleanly from normal traffic.

---

## License & disclaimer

Prototype for research and demonstration. The `qpu` backend option is a **hardware placeholder**; inference currently runs on PennyLane `default.qubit`. Do not point live production SOC webhooks or Security Hub accounts at this build without completing the [production checklist](docs/OPERATIONS.md#production-readiness-checklist).
