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
| Live SOC API | `python app.py` | Default port 8000 |
| Live SOC UI | `cd frontend && npm run dev` | Default port 5173; proxies `/api` to 8000 |
| Pipeline debug | `python main.py -v` | Verbose stage logs |
| Reinstall deps | `pip install -r requirements.txt` | Inside `.venv` |

---

## Access control

### Bootstrap admin

On first `python app.py` start:

1. A **Default Tenant** row is created if missing.
2. An `admin` user with role `SUPER_ADMIN` is created if missing.
3. Password comes from `ADMIN_PASSWORD`, otherwise the insecure default `quantum123` (logged as a warning).

Also set a strong `SECRET_KEY` for JWT signing. The development default is rejected for production use.

```bash
export ADMIN_PASSWORD='choose-a-strong-password'
export SECRET_KEY='long-random-string'
export CORS_ORIGINS='https://your-console.example.com'
python app.py
```

Existing SQLite databases automatically receive lifecycle columns (`is_active`, `created_at`, `last_login_at`, `token_version`, `must_change_password`) and `alerts.assignee_id` on startup.

### Production posture

| Variable | Purpose |
|----------|---------|
| `FLASK_ENV=production` or `QUANTUM_STRICT_SECRETS=1` | Reject default `SECRET_KEY` / wildcard CORS |
| `SECRET_KEY` | JWT signing (required in production) |
| `ADMIN_PASSWORD` | Bootstrap admin (required non-default in production) |
| `CORS_ORIGINS` | Explicit allow-list (required in production; no `*`) |
| `DATABASE_URL` | SQLAlchemy URI (default `sqlite:///quantum.db`) |
| `INGEST_API_KEY` / `INGEST_TENANT_ID` | SIEM webhook auth |
| `WEBAUTHN_RP_ID` / `WEBAUTHN_RP_ORIGIN` / `WEBAUTHN_RP_NAME` | Passkey / security-key RP |
| `SIM_LEADER=0` | Disable the background event generator (workers / tests) |

Health probes: `GET /healthz` (liveness), `GET /readyz` (DB + detectors).

Session JWTs carry a `tv` (token version) claim. Password changes, MFA clears, and deactivation bump the version and revoke outstanding sessions.

### Day-2 user administration

| Task | Where |
|------|-------|
| Create / role-change / deactivate / delete | UI: **Administration → Users** · API: `/api/users` |
| Reset a forgotten password | UI action or `POST /api/users/<id>/password` |
| Clear lost MFA | UI action or `DELETE /api/users/<id>/mfa` |
| Self-service password / MFA | UI: **My account** · API: `/api/me/password`, `/api/mfa/*` |
| Review who did what | **Administration → Audit** |

Prefer **deactivate** for leavers. Deactivation blocks login immediately and returns `403` on subsequent authenticated calls (the SPA signs the user out when the stream ticket fails).

### Roles (application RBAC)

`SUPER_ADMIN` → `TENANT_ADMIN` → `TIER_2` / `TIER_1` → `READ_ONLY`

- Tenant admins manage only non-admin users in their own tenant.
- Analysts receive a reduced `/api/users` roster for case assignment, not the management directory.
- At least one active super admin must always remain.

See [User Guide §3.3](USER_GUIDE.md#33-react-soc-dashboard-poc) and [API Reference — Auth & users](API_REFERENCE.md#auth--users).

---

## Logging

Modules use the standard library `logging` package.

| Entrypoint | Default level | Format |
|------------|---------------|--------|
| `cli.py` | INFO (`-v` → DEBUG) | time \| level \| logger \| message |
| `main.py` | INFO (`-v` → DEBUG) | same |
| `app.py` | INFO | same |
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
python app.py # Address already in use
npm run dev # Port in use
```
Kill the existing process or run Flask with a different port (`python -c "import app; app.app.run(port=8001)"`) and Vite with `npm run dev -- --port 5174`.

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
- Rotate `ADMIN_PASSWORD` and `SECRET_KEY` before any shared or networked demo.
- Prefer deactivating accounts over deleting them when audit attribution must remain intact.
- User lifecycle actions (create, role change, password reset, MFA clear, delete) are recorded in `audit_logs`.

---

## Production readiness checklist

Use this before wiring a real SOC:

- [ ] Replace mock generators with authenticated AWS/Azure log sinks  
- [ ] Version and persist `StandardScaler`, `PCA`, and QNN `weights`  
- [ ] Configure real ASFF import (`securityhub:BatchImportFindings`)  
- [ ] Configure Sentinel CEF / AMA / Data Connector path  
- [ ] Set real Slack (or Teams/PagerDuty) endpoints; disable dry-run deliberately  
- [ ] Deploy Flask API (`app.py` / WSGI entry) behind Gunicorn (or similar) and Nginx
- [ ] Build the React frontend (`npm run build`) and serve statically via CDN or Nginx
- [ ] Migrate SQLite to PostgreSQL for concurrent threaded write-scaling  
- [ ] Set strong `SECRET_KEY` and `ADMIN_PASSWORD`; remove default credentials  
- [ ] Enroll MFA for all admin accounts; document MFA recovery via admin clear  
- [ ] Add SSO/SAML (or OIDC) auth to the React surface when moving beyond local users  
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
