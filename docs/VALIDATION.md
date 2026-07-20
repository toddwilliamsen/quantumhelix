# Validation Guide

How Quantum Helix proves that clean cloud traffic and advanced attacks are mathematically separable, and that SIEM alerting fires correctly.

---

## Purpose

`validate.py` is a **headless integration test**. It does not open a React app or require cloud accounts. It:

1. Fits the classical pipeline on synthetic **normal** traffic  
2. Warm-trains the QNN with benign + attack labels  
3. Scores held-out-style attack vectors  
4. Asserts score separation and alert payload integrity  
5. Exits `0` on success, `1` on failure  

Use it after setup, before demos, and as a quick regression check after code changes.

---

## How to run

```bash
./setup.sh
source .venv/bin/activate
python validate.py
echo $?    # expect 0
```

No CLI flags are required.

---

## Execution phases

### Phase 0 — Initialize engine

Instantiates:

- `ClassicalFeaturePipeline`
- `QuantumThreatDetector(backend="simulator", seed=42)`
- `AlertOrchestrator(threshold=0.55, dry_run_webhook=True)`

### Phase 1 — Baseline / clean traffic

| Step | Detail |
|------|--------|
| Synthesize | **20** normal events (low velocity, `auth_failures=0`, modest bytes) |
| Fit | StandardScaler + PCA(4) on baseline only |
| Warm-train | Baseline labeled `0` + three attack templates labeled `1` (12 Adam steps) |
| Score | All 20 normal events through QNN |
| Gate | **Average baseline score &lt; 0.40** |

### Phase 2 — Threat injection

Three fixed malicious scenarios:

| ID | Name | Cloud signal |
|----|------|--------------|
| A | AWS Credential Stuffing & Exfiltration | High velocity, many IAM errors, ~1.85 GB egress, suspicious IP |
| B | Azure Privilege Escalation | RBAC roleAssignment write denied, elevated failures, API spike |
| C | Cross-Cloud Pivoting | Fused `AWS+Azure` CIM with extreme correlated features |

Each event is transformed with the **pre-fitted** PCA (not refit) and scored.

### Phase 3 — Metrics & SIEM verification

Gates:

| Gate | Criterion |
|------|-----------|
| Separation | Each attack score `> baseline_avg + 0.20` |
| Alertability | Each attack score `≥ 0.55` |
| Aggregate | Mean attack score `> mean baseline` |
| ASFF | Package contains Security Hub schema `2018-10-08` |
| CEF | String starts with `CEF:0|` |
| Fan-out | Exactly **3** alert packages |

ASFF excerpts and CEF strings are printed for analyst inspection.

---

## What success looks like

```text
✓ PASS  Baseline average threat score < 0.40 (got 0.20xx)
✓ PASS  Attack A … score 0.83xx > baseline_avg … + 0.20
✓ PASS  Attack B …
✓ PASS  Attack C …
✓ PASS  Exactly 3 SIEM/Slack alerts fired (got 3)

VALIDATION SUMMARY
  RESULT: PASSED
```

Expect stdout blocks:

```text
🚨 CRITICAL QUANTUM THREAT DETECTED
```

once per attack (plus structured ASFF/CEF dumps).

---

## Interpreting failure modes

| Failure | Likely cause | Action |
|---------|--------------|--------|
| Baseline avg ≥ 0.40 | Scorer too sensitive / broken PCA fit | Inspect normal synthesizer ranges; check `score()` blend |
| Attack not above baseline + margin | Features not extreme enough / transform bug | Confirm attack bytes/velocity; print PCA vectors |
| Alert package missing | Score under threshold or orchestrator error | Lower `ALERT_THRESHOLD` only for debug; check exceptions |
| PennyLane / autoray import error | Env mismatch | Re-run `./setup.sh`; see [OPERATIONS.md](OPERATIONS.md) |
| Exit `1` with traceback | Unexpected runtime bug | Capture stack; open issue / fix module named in trace |

---

## Relationship to other entrypoints

| Entrypoint | Data | Asserts? |
|------------|------|----------|
| `validate.py` | Fixed normal + 3 attacks | Yes — hard gates |
| `cli.py scan` | Random mock stream (~5% anomalies) | No — observational |
| `main.py` | Warmup + stream | Logs alert counts |
| React UI / Flask API | Live mock stream | Visual only |

Prefer **`validate.py`** for “does detection still work?” Prefer CLI/GUI for demos.

---

## Extending the suite

Ideas for a stronger QA bar:

1. Add Attack D (low-and-slow exfiltration) with subtler features.  
2. Assert ASFF `ProductFields.QuantumThreatScore` parses as float.  
3. Parametrize seeds and require pass rate ≥ N/M.  
4. Wire `python validate.py` into CI after `pip install -r requirements.txt`.  
5. Snapshot CEF regex for required labels (`cs2Label=QuantumThreatScore`, etc.).

---

## Constants (in `validate.py`)

| Name | Default | Role |
|------|---------|------|
| `BASELINE_AVG_MAX` | `0.40` | Clean-traffic ceiling |
| `ATTACK_MARGIN` | `0.20` | Min attack − baseline gap |
| `ALERT_THRESHOLD` | `0.55` | Orchestrator gate during validation |
