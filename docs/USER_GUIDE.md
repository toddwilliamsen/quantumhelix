# Quantum Helix User Guide

End-user documentation for installing, running, and interpreting Quantum Helix outputs.

---

## 1. Audience & prerequisites

This guide is for:

- **SOC analysts** using the React dashboard or CLI scan table
- **Security engineers** validating detection behavior
- **Operators** bootstrapping a local demo environment

You need:

- Python **3.11 or newer** (required by current PennyLane stables)
- Node.js **18 or newer** (for the React frontend)
- Network access for the first `pip install` and `npm install`
- ~500 MB disk for the virtual environment and node_modules

---

## 2. Installation

### Automated (recommended)

```bash
cd /path/to/quantum
chmod +x setup.sh
./setup.sh
```

`setup.sh` will:

1. Verify Python ≥ 3.9  
2. Create `.venv`  
3. Upgrade pip  
4. Install `requirements.txt`  
5. Print activation and run commands  

### Manual

```bash
python3 -m venv .venv
source .venv/bin/activate                 # macOS / Linux
# .\.venv\Scripts\Activate.ps1            # Windows PowerShell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### Confirm health

```bash
source .venv/bin/activate
python validate.py
```

Exit code `0` and `RESULT: PASSED` means the hybrid engine is working.

---

## 3. Running the system

### 3.1 Automated validation

```bash
python validate.py
```

Feeds **20 normal** events and **3 crafted attacks**, then checks:

- Baseline average score stays low (`< 0.40`)
- Attack scores exceed baseline by a clear margin
- ASFF, CEF, and Slack alerts fire for all three attacks

See [VALIDATION.md](VALIDATION.md) for details.

### 3.2 CLI scanner

```bash
python cli.py scan --duration 10 --threshold 0.70 --engine ensemble
python cli.py benchmark
```

| Flag | Default | Description |
|------|---------|-------------|
| `--duration` | `10` | Scan window in seconds (also scales event count) |
| `--threshold` | `0.75` | Score at/above which alerts fire |
| `--engine` | `ensemble` | `ensemble` (IF+SVM+quantum kernel), `quantum_kernel`, `classical_svm`, `isolation_forest`, `qnn` |
| `--backend` | `simulator` | Used by optional QNN path |
| `--warmup` | `60` | Events used to fit PCA / models |
| `--events-per-second` | `5` | Mock ingest rate |
| `-v` / `--verbose` | off | Debug logging |

**Output:** live Slack-style critical alerts (when triggered) and an ASCII table:

```text
| # | Cloud | Identity | Source IP | Score | Status |
```

`Status = ALERT` means the score met or exceeded `--threshold`.

### 3.3 React SOC dashboard (PoC+)

This application runs as a decoupled React frontend and a Flask backend.

**Step 1: Start the backend API**
```bash
python api.py
```
*(Runs on http://localhost:8000)*

**Step 2: Start the frontend UI**
Open a new terminal and run:
```bash
cd frontend
npm install
npm run dev
```
*(Runs on http://localhost:5173 or similar)*

Opens a full SOC intelligence surface wired to the **same hybrid ensemble** as the CLI — Isolation Forest + classical SVM + quantum kernel.

**What you get**

| Panel | Purpose |
|-------|---------|
| Threat score over time | Live ensemble line chart with optional multi-engine overlay |
| Latest engine votes | Bar chart of IF / SVM / quantum kernel / ensemble for the newest event |
| Cloud mix | Event volume + alert volume for AWS vs Azure |
| Incident feed | Threshold crossings with per-engine score columns |
| Evidence Lab | In-app classical vs quantum benchmark scoreboard |

**Sidebar**

| Control | Purpose |
|---------|---------|
| Alert threshold | Incident + SIEM dry-run gate |
| Events / refresh | Batch size each UI tick |
| Refresh delay | Seconds between stream updates |
| Multi-engine overlay | Show IF / SVM / QSVM beside ensemble |
| Start / Pause / Trash | Stream lifecycle in the sidebar |
| Settings & Rules | Define suppression rules |

First load fits PCA + the ensemble (a few seconds). Click **Start** in the sidebar.

The backend intentionally injects a mix of normal traffic, loud attacks, and subtle APT-style events so the **threat theater**, **engine disagreement**, and **red alert markers** show up during a short demo — not only rare mock anomalies.

### 3.4 Orchestration entrypoint

```bash
python main.py --events 50 --threshold 0.75 --train-steps 20
python main.py --warmup 100 --events 60 --backend simulator -v
```

Useful for end-to-end debugging with architectural logging. Same pipeline as CLI; no interactive table.

---

## 4. Understanding results

### Threat score

| Score | Guidance |
|-------|----------|
| **0.0 – 0.40** | Consistent with baseline / normal operations |
| **0.40 – 0.75** | Elevated — review identity, IP, and volume |
| **≥ 0.75** | Default critical band — SIEM + Slack path engages |

Scores are continuous floats in `[0.0, 1.0]`. They combine:

1. Quantum circuit Pauli-Z expectation aggregation  
2. Classical PCA-space energy (how far the event sits from the fitted baseline)

### Threat Map (Kill Chain)
Stateful mapping of alerts to track attacker progression.

1. **Identity Tracking**: Alerts are automatically mapped into `Initial Access`, `Discovery`, `Credential Access`, or `Exfiltration` based on telemetry.
2. **Containment**: Click **Cut Off Access** on any identity card to immediately acknowledge all related alerts and block future telemetry from that identity.

### Analytics & Modelsntity & source

| Field | Meaning |
|-------|---------|
| `cloud_provider` | `AWS`, `Azure`, or fused tags such as `AWS+Azure` |
| `normalized_identity` | IAM ARN, Azure claims name, or pivot identity |
| `source_ip` | Caller / flow source address |
| `api_velocity` | Burst / request-rate style feature |
| `auth_failures` | Failed auth / denied actions count |
| `data_volume_bytes` | Transfer / egress volume |

### Alerts you will see

When a score crosses the threshold, stdout shows:

```text
🚨 CRITICAL QUANTUM THREAT DETECTED
   • Alert ID     : …
   • Provider     : AWS | Azure | …
   • Identity     : …
   • Threat Score : 0.8xxx
   …
```

Behind the scenes, Quantum Helix also builds:

- **ASFF** — AWS Security Finding Format (Security Hub-compatible JSON)  
- **CEF** — Common Event Format string (Sentinel-compatible)

In this prototype, Slack delivery is a **dry-run** (payload logged; no real HTTP unless configured).

---

## 5. Typical analyst workflows

### A. First-day smoke test

1. `./setup.sh`  
2. `python validate.py` → expect `PASSED`  
3. `python cli.py scan --duration 5 --threshold 0.70` → expect some `ALERT` rows (~5% injected anomalies)  
4. Start the backend (`python api.py`) and frontend (`cd frontend && npm run dev`), log in as admin, start stream, watch Triage Inbox  

### B. Threshold tuning

1. Run CLI with `--threshold 0.90` — fewer alerts  
2. Run with `--threshold 0.50` — more sensitive  
3. Use dashboard slider to find the operating point for your demo audience  

### C. Investigate an alert

1. Note `Identity`, `Source IP`, `Provider`, and score  
2. Correlate with CIM features (velocity, auth failures, bytes)  
3. In a production extension, open the ASFF `Id` in Security Hub or CEF in Sentinel  

---

## 6. Interfaces cheatsheet

| Goal | Command |
|------|---------|
| Install | `./setup.sh` |
| Prove loud-attack path | `python validate.py` |
| Classical vs quantum scoreboard | `python benchmark.py` |
| Batch scan (ensemble) | `python cli.py scan --engine ensemble --duration 10` |
| Live UI | `python api.py` AND `cd frontend && npm run dev` |
| Debug QNN path | `python main.py -v` |
| PoC+ status doc | See [POC_PLUS.md](POC_PLUS.md) |

---

## 7. Getting help

| Symptom | Where to look |
|---------|----------------|
| Import / PennyLane errors | [Operations — Troubleshooting](OPERATIONS.md#troubleshooting) |
| Scores all look similar | [Validation Guide](VALIDATION.md) and threshold settings |
| Want field-level AWS/Azure mapping | [CIM Reference](CIM.md) |
| Want circuit / data-flow detail | [Architecture](ARCHITECTURE.md) |
