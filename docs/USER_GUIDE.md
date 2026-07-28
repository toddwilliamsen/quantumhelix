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
python app.py
```
*(Runs on http://localhost:8000)*

On first start the app creates a default tenant and an `admin` user (`SUPER_ADMIN`). The default password is `quantum123` unless you set `ADMIN_PASSWORD`. Change it before any shared demo.

**Step 2: Start the frontend UI**
Open a new terminal and run:
```bash
cd frontend
npm install
npm run dev
```
*(Runs on http://localhost:5173 or similar; API calls proxy to port 8000)*

Opens a full SOC intelligence surface wired to the **same hybrid ensemble** as the CLI — Isolation Forest + classical SVM + quantum kernel.

**What you get**

| Panel | Purpose |
|-------|---------|
| Dashboard | Live ensemble score, engine votes, cloud mix |
| Triage Inbox | Queue with claim / My queue / escalate-to-case / false positive; full investigation modal |
| Cases | Incident cases, assignment, comments, PEAK / kill-chain notes (opens from escalate) |
| Threat Map | Identity progression and containment actions |
| Model controls | Ensemble weight playground (**admins only**) |
| Analytics | Overview metrics and classical vs quantum benchmark |
| My account | Self-service password change and MFA enrollment (required on first login after admin reset) |
| Administration | Suppression, playbooks, audit, tenants, **user management** |

**Sidebar**

| Control | Purpose |
|---------|---------|
| Alert threshold | Incident gate (admins) |
| Start / Pause / Clear | Stream lifecycle (admins) |
| Theme | Light / dark for all roles |
| My account | Password + MFA for the signed-in user |
| Administration | Policy and access (admins only) |

First load fits PCA + the ensemble (a few seconds). Click **Start monitoring** in the sidebar.

The backend intentionally injects a mix of normal traffic, loud attacks, and subtle APT-style events so the **threat theater**, **engine disagreement**, and **red alert markers** show up during a short demo — not only rare mock anomalies.

### 3.3.1 Roles and permissions

| Role | Typical use | Notes |
|------|-------------|-------|
| `SUPER_ADMIN` | Platform owner | All tenants, user/tenant admin, stream controls |
| `TENANT_ADMIN` | Tenant owner | Users and policy inside their tenant; cannot create/promote admins |
| `TIER_2` | Senior analyst | Full case/alert mutation in tenant |
| `TIER_1` | Analyst | Case/alert mutation in tenant |
| `READ_ONLY` | Auditor / observer | View data; mutations and inject-test actions are disabled |

Deactivated accounts cannot sign in, and any existing session is rejected on the next authenticated request (including the live SSE ticket). Password reset and MFA clear also revoke outstanding sessions.

**Triage workflow:** Claim an alert into **My queue**, acknowledge or mark false positive, or **Escalate to case** (creates `CASE-####` and opens Cases). New open alerts toast when you are not already on Triage.

### 3.3.2 My account

Every signed-in user can open **My account** to:

1. Change their password (current password required; new password ≥ 10 characters)
2. Enroll an authenticator app (TOTP)
3. Register a security key (WebAuthn)

New accounts and admin password resets set `must_change_password`; the console routes to **My account** until the password is updated.

If a user loses MFA access, an administrator can clear enrollment under **Administration → Users**.

### 3.3.3 Administration → Users

Visible to `SUPER_ADMIN` and `TENANT_ADMIN`. From this tab you can:

| Action | Detail |
|--------|--------|
| Create user | Username, initial password (≥ 10 chars), role; tenant picker for super admins |
| Change role | Inline role select (tenant admins limited to Tier 1 / Tier 2 / Read Only) |
| Move tenant | Super admin only |
| Reset password | Sets a new password; share it out of band |
| Clear MFA | Removes TOTP / WebAuthn so the user can re-enroll |
| Activate / Deactivate | Immediate access revoke without deleting history |
| Delete | Permanent removal; case assignments cleared, comments retained as “Deleted user” |

Guardrails:

- You cannot administer your own account from this table (use **My account**)
- Tenant admins cannot manage other admins or users in other tenants
- The last active super admin cannot be demoted, deactivated, or deleted
- Creates, updates, password resets, MFA clears, and deletes are written to the audit log

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

### Identity & source

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
4. Start the backend (`python app.py`) and frontend (`cd frontend && npm run dev`), log in as `admin`, open **Administration → Users** if you need additional analyst accounts, start the stream, watch Triage Inbox

### B. Threshold tuning

1. Run CLI with `--threshold 0.90` — fewer alerts  
2. Run with `--threshold 0.50` — more sensitive  
3. Use dashboard slider to find the operating point for your demo audience  

### C. Investigate an alert

1. Note `Identity`, `Source IP`, `Provider`, and score  
2. Correlate with CIM features (velocity, auth failures, bytes)  
3. In a production extension, open the ASFF `Id` in Security Hub or CEF in Sentinel  

### D. Provision an analyst

1. Sign in as `admin` (or a tenant admin)  
2. Open **Administration → Users**  
3. Create the account with the appropriate role and initial password  
4. Have the analyst sign in, open **My account**, change the password, and enroll MFA  

### E. Offboard an analyst

1. Prefer **Deactivate** so history and audit attribution remain  
2. Use **Delete** only when the account must be removed permanently  
3. Confirm the user can no longer sign in and that any open session is ended on the next API call  

---

## 6. Interfaces cheatsheet

| Goal | Command |
|------|---------|
| Install | `./setup.sh` |
| Prove loud-attack path | `python validate.py` |
| Classical vs quantum scoreboard | `python benchmark.py` |
| Batch scan (ensemble) | `python cli.py scan --engine ensemble --duration 10` |
| Live UI | `python app.py` AND `cd frontend && npm run dev` |
| Debug QNN path | `python main.py -v` |
| PoC+ status doc | See [POC_PLUS.md](POC_PLUS.md) |
| User management API | See [API Reference — Auth & users](API_REFERENCE.md#auth--users) |

---

## 7. Getting help

| Symptom | Where to look |
|---------|----------------|
| Import / PennyLane errors | [Operations — Troubleshooting](OPERATIONS.md#troubleshooting) |
| Scores all look similar | [Validation Guide](VALIDATION.md) and threshold settings |
| Login / roles / MFA | [Operations — Access control](OPERATIONS.md#access-control) and §3.3 above |
| Want field-level AWS/Azure mapping | [CIM Reference](CIM.md) |
| Want circuit / data-flow detail | [Architecture](ARCHITECTURE.md) |
