# Azure Dummy Data Deployment Guide

Deploy disposable Activity Log–style and NSG Flow–style telemetry into your
Azure subscription so Quantum Helix can be tested against real Blob Storage
paths (still synthetic content).

---

## What gets created

| Resource | Name (default) | Purpose |
|----------|----------------|---------|
| Resource group | `rg-Quantum Helix-test` | Disposable test boundary |
| Storage account | `qssgdummy` + hash suffix | Hosts NDJSON / JSON blobs |
| Containers | `activity-logs`, `nsg-flow-logs`, `attack-scenarios`, `meta` | Telemetry layout |
| Log Analytics (optional) | `law-Quantum Helix-test` | Placeholder for future diag settings |

**Blobs**

- `activity-logs/normal.ndjson` — clean Azure traffic  
- `activity-logs/attacks.ndjson` — malicious Activity-style events  
- `nsg-flow-logs/*.ndjson` — NSG flow–adjacent records (same CIM fields)  
- `attack-scenarios/named_attacks.json` — privilege escalation / pivot / exfil  
- `meta/manifest.json` — counts and generation metadata  

All records are shaped for `MultiCloudLogParser.parse_azure` ([CIM.md](CIM.md)).

---

## Prerequisites

1. [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli) installed  
2. Logged in: `az login`  
3. Rights to create Resource Groups, Storage Accounts, and (optional) Log Analytics  
4. Project Python env (for generation / scoring): `./setup.sh` then `source .venv/bin/activate`

---

## Deploy

```bash
chmod +x azure/deploy_dummy_data.sh

# Use the currently selected az subscription
./azure/deploy_dummy_data.sh

# Or target a specific subscription / region
./azure/deploy_dummy_data.sh \
  --subscription 00000000-0000-0000-0000-000000000000 \
  --location eastus \
  --resource-group rg-Quantum Helix-test
```

### Useful flags

| Flag | Meaning |
|------|---------|
| `--subscription ID` | Target subscription |
| `--location LOC` | Azure region (default `eastus`) |
| `--normal-count N` | Normal events per channel (default 40) |
| `--attack-count N` | Attack events per channel (default 5) |
| `--no-law` | Skip Log Analytics workspace |
| `--skip-upload` | Generate files under `azure/.generated` only |
| `--dry-run` | Print plan without creating resources |
| `--destroy` | Delete the resource group (async) |

Environment overrides: `AZURE_SUBSCRIPTION_ID`, `AZURE_LOCATION`, `AZURE_RESOURCE_GROUP`, etc.

---

## Score the uploaded data

```bash
source .venv/bin/activate

python azure/fetch_and_score.py \
  --resource-group rg-Quantum Helix-test \
  --storage-account <name-from-deploy-output> \
  --threshold 0.70
```

Or score the local mirror without hitting Azure:

```bash
python azure/fetch_and_score.py \
  --resource-group rg-Quantum Helix-test \
  --storage-account unused \
  --local-dir azure/.generated \
  --threshold 0.70
```

Expect attack NDJSON rows to produce elevated threat scores and Slack/ASFF dry-run alerts.

---

## Tear down

```bash
./azure/deploy_dummy_data.sh --destroy --subscription <SUB_ID>
```

This deletes the entire resource group (`--no-wait`). Confirm with:

```bash
az group show -n rg-Quantum Helix-test
```

---

## Security notes

- Content is **synthetic** — no real tenant user traffic.  
- Storage is created with **public blob access disabled** and TLS 1.2+.  
- Deploy prints an optional short-lived **read-only SAS** for activity-logs; treat it as sensitive.  
- Account keys are used briefly by the script for upload and are **not** written to disk.  
- Deployment metadata is stored under `azure/.generated/` (gitignored).  

---

## Files

| Path | Role |
|------|------|
| `azure/deploy_dummy_data.sh` | Azure CLI deploy / destroy |
| `azure/generate_telemetry.py` | Build NDJSON/JSON locally |
| `azure/fetch_and_score.py` | Download blobs → parse → QNN score |
| `azure/.generated/` | Local mirror + `azure_deployment.json` |
