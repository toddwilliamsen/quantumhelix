# Operations & Troubleshooting

Runbooks for environment setup, day-2 operation, known limitations, and production readiness.

---

## Environment bootstrap

```bash
chmod +x setup.sh
./setup.sh
source .venv/bin/activate
```

Windows:

| Shell | Activate |
|-------|----------|
| Git Bash / WSL | `source .venv/Scripts/activate` |
| PowerShell | `.\.venv\Scripts\Activate.ps1` |
| cmd.exe | `.venv\Scripts\activate.bat` |

Health check:

```bash
python validate.py
```

---

## Operational entrypoints

| Task | Command | Notes |
|------|---------|-------|
| Regression / QA | `python validate.py` | Exit `0` required |
| Batch demo scan | `python cli.py scan --duration 10 --threshold 0.70` | ASCII table |
| Live SOC API | `python api.py` | Default port 8000 |
| Live SOC UI | `cd frontend && npm run dev` | Default port 5173 |
| Pipeline debug | `python main.py -v` | Verbose stage logs |
| Reinstall deps | `pip install -r requirements.txt` | Inside `.venv` |

---

## Logging

Modules use the standard library `logging` package.

| Entrypoint | Default level | Format |
|------------|---------------|--------|
| `cli.py` | INFO (`-v` → DEBUG) | time \| level \| logger \| message |
| `main.py` | INFO (`-v` → DEBUG) | same |
| `api.py` | INFO | same |
| `validate.py` | INFO | compact time \| level \| message |

Alert path also prints human-readable Slack-style banners to **stdout** (separate from logger handlers in some paths).

PennyLane may emit DEBUG spam when root level is DEBUG; filter with:

```bash
python main.py -v 2>&1 | grep -v pennylane
```

---

## Troubleshooting

### Python version too old

```text
[ERROR] Python 3.9+ is required
```

Install Python 3.9+ and re-run `./setup.sh`.

### `externally-managed-environment`

Always use the project virtualenv (`.venv`). Do not `pip install` into system Python on Homebrew/PEP-668 hosts.

### PennyLane / `autoray` `NumpyMimic` error

Seen on newer Python (e.g. 3.14) with bleeding-edge `autoray`.

**Fix:** `requirements.txt` pins `autoray==0.6.12` alongside `pennylane==0.36.0`. Reinstall:

```bash
pip install -r requirements.txt
```

### PCA fit errors (`Need at least 4 events`)

Increase `--warmup` (CLI) or warmup args in `main.py` / Flask state.

### All scores near 0.5 / no alerts

1. Confirm mock anomalies exist (`generate_mock_stream` ~5%).  
2. Lower `--threshold` temporarily (e.g. `0.55`).  
3. Run `python validate.py` — if that passes, CLI threshold/warmup is the issue.  
4. Ensure `fit_transform` ran before `transform_single`.

### Port in use (Flask or Vite)

```bash
python api.py # Address already in use
npm run dev # Port in use
```
Kill the existing process or run Flask with `flask run --port=8001` and Vite with `npm run dev -- --port 5174`.

### `backend=qpu` appears to do nothing different

Expected. Hardware path is a **placeholder**; inference remains on `default.qubit` with a warning log.

### Slack POST failures

Default `dry_run_webhook=True` skips HTTP. If you set `dry_run_webhook=False`, provide a real webhook URL; failures are logged and return `False` without crashing the scan loop.

---

## Performance notes

| Path | Characteristics |
|------|-----------------|
| QNode eval | Dominates per-event latency on CPU simulator |
| Adam `train_on_batch` | O(steps × samples × circuit); keep warmup modest for demos |
| React UI | Fetches paginated history; limited caching |
| API | Threads lock around SQLite reads/writes for SSE streams |

For higher throughput prototypes: shrink `N_LAYERS`, reduce train steps, or batch QNode execution.

---

## Security & data handling

- Prototype ships with **synthetic** identities and IPs only.  
- Treat real CloudTrail/Activity payloads as sensitive; restrict log retention.  
- Do not commit `.env` files containing live Slack tokens or cloud keys (none are required today).  
- ASFF examples use placeholder account `123456789012` — replace before Security Hub import.

---

## Production readiness checklist

Use this before wiring a real SOC:

- [ ] Replace mock generators with authenticated AWS/Azure log sinks  
- [ ] Version and persist `StandardScaler`, `PCA`, and QNN `weights`  
- [ ] Configure real ASFF import (`securityhub:BatchImportFindings`)  
- [ ] Configure Sentinel CEF / AMA / Data Connector path  
- [ ] Set real Slack (or Teams/PagerDuty) endpoints; disable dry-run deliberately  
- [ ] Deploy Flask API (`api.py`) behind a WSGI server (e.g., Gunicorn) and Nginx
- [ ] Build the React frontend (`npm run build`) and serve statically via CDN or Nginx
- [ ] Migrate SQLite to PostgreSQL for concurrent threaded write-scaling 
- [ ] Add SSO/SAML auth to the React surface
- [ ] Redact secrets from logs; structured audit trail for score decisions  
- [ ] Swap `default.qubit` for Braket/Azure Quantum device factory behind `backend`  
- [ ] Load / latency test classical path at production EPS  
- [ ] Keep `python validate.py` (extended) in CI  

---

## Dependency inventory

See root `requirements.txt` and [DEPENDENCIES.md](DEPENDENCIES.md). Critical pins (as of last refresh):

| Package | Role |
|---------|------|
| `pennylane` | QNN runtime (lead quantum dependency) |
| `autoray` | Locked exactly to PennyLane’s declared requirement |
| `numpy` / `scikit-learn` / `pandas` | Classical feature pipeline |
| `flask` / `react` / `click` | API, UI, CLI |

**Continuous freshness**

```bash
python check_deps.py                 # exit 1 if pins lag PyPI targets
python check_deps.py --update        # rewrite pins
pip install -r requirements.txt
python validate.py
```

GitHub Dependabot (weekly) and `.github/workflows/deps-freshness.yml` also monitor for drift.

Upgrade PennyLane only with a full `validate.py` pass afterward.

---

## Support matrix (prototype)

| Platform | Status |
|----------|--------|
| macOS (zsh/bash) | Supported |
| Linux | Supported |
| Windows Git Bash / WSL | Supported via `setup.sh` |
| Windows PowerShell | Activate script documented; prefer WSL for bash setup |
| Python 3.11–3.12 | Recommended |
| Python 3.13–3.14 | Supported when pinned deps resolve (run `validate.py`) |

---

## Related docs

- [User Guide](USER_GUIDE.md)  
- [Architecture](ARCHITECTURE.md)  
- [Validation](VALIDATION.md)  
- [API Reference](API_REFERENCE.md)  
