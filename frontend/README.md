# Quantum Helix frontend

React 19 + Vite SPA for the SOC console. Talks to the Flask API in `app.py` / `routes.py`.

## Develop

From the repo root, start the API, then:

```bash
cd frontend
npm install
npm run dev
```

Vite proxies `/api` to `http://127.0.0.1:8000` (see `vite.config.js`).

Default sign-in after first backend start: `admin` / `quantum123` (or `ADMIN_PASSWORD`).

## Scripts

| Command | Purpose |
|---------|---------|
| `npm run dev` | Local UI with HMR |
| `npm run build` | Production bundle → `frontend/dist` (also copy/serve via Flask `static/`) |
| `npm run lint` | Oxlint |
| `npm run preview` | Preview the production build |

## Surfaces that matter for access control

| Route | Who | Purpose |
|-------|-----|---------|
| `/account` | All signed-in roles | Change password; enroll TOTP / WebAuthn |
| `/settings` | `SUPER_ADMIN`, `TENANT_ADMIN` | Administration (Users, tenants, playbooks, audit, …) |

Shared role vocabulary lives in `src/roles.js`. API helpers live in `src/api.js`.

Operator docs: [User Guide — React SOC dashboard](../docs/USER_GUIDE.md#33-react-soc-dashboard-poc).
API docs: [Auth & users](../docs/API_REFERENCE.md#auth--users).
