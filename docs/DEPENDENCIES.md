# Dependency policy for Quantum Helix.
#
# This stack (PennyLane, NumPy scientific ecosystem, Flask, React) moves quickly.
# Pins must always target the latest *compatible* stable releases.

## Active mechanisms

| Mechanism | Cadence | Behavior |
|-----------|---------|----------|
| `python check_deps.py` | On demand / after `./setup.sh` | Compares `requirements.txt` to PyPI targets; exit `1` on drift |
| `python check_deps.py --update` | On demand | Rewrites pins to latest compatible stables |
| GitHub Dependabot (`.github/dependabot.yml`) | Weekly (Monday) | Opens PRs for pip dependency bumps |
| GitHub Actions (`deps-freshness.yml`) | Weekly + on pin changes | Fails if pins lag; runs `validate.py` |

## Compatibility rules

1. Prefer the newest **stable** PyPI release (no `rc`, `dev`, `a`, `b` tags).
2. **PennyLane** is the lead quantum dependency (`>= 0.45` requires **Python 3.11+**).
3. **`autoray`** is locked to the exact version declared by the pinned PennyLane release
   (for example PennyLane 0.45.1 requires `autoray==0.8.4`). Do not float `autoray`
   to an absolute-latest version that breaks PennyLane resolution.
4. After any bump: `pip install -r requirements.txt && python validate.py`.

## Operator workflow

```bash
source .venv/bin/activate
python check_deps.py                 # see what drifted
python check_deps.py --update        # rewrite requirements.txt
pip install -r requirements.txt
python validate.py                   # prove detection still works
python check_deps.py --check-install # confirm venv matches pins
```

### Frontend dependencies
For the React SPA in the `frontend/` directory, we use npm to manage dependencies (`package.json`).
```bash
cd frontend
npm install
npm update
```

## Current stable pins (see `requirements.txt`)

Managed packages are listed in `check_deps.py` → `MANAGED_PACKAGES`.
Always treat `requirements.txt` as the source of truth for installed versions.
