# Quantum Helix Documentation Index

| Document | Description |
|----------|-------------|
| [../README.md](../README.md) | Project overview and quick start |
| [USER_GUIDE.md](USER_GUIDE.md) | Install, CLI, React/Flask UI, roles, user management, interpreting scores |
| [ARCHITECTURE.md](ARCHITECTURE.md) | System design, ensemble, quantum kernel, app RBAC, scale-out |
| [POC_PLUS.md](POC_PLUS.md) | Beyond-MVP implementation status and non-claims |
| [DEPENDENCIES.md](DEPENDENCIES.md) | Latest-stable pin policy, watcher, Dependabot |
| [API_REFERENCE.md](API_REFERENCE.md) | Modules, auth/user APIs, CLI flags, code samples |
| [CIM.md](CIM.md) | AWS / Azure field mapping into the CIM |
| [VALIDATION.md](VALIDATION.md) | Automated clean vs. attack verification |
| [AZURE_DUMMY_DATA.md](AZURE_DUMMY_DATA.md) | Deploy dummy Activity/NSG data to Azure |
| [OPERATIONS.md](OPERATIONS.md) | Bootstrap admin, access control, troubleshooting, production checklist |
| [GLOSSARY.md](GLOSSARY.md) | Terms used across security and QML docs |

## Suggested reading order

1. **New operator** → README → User Guide (§3.3 dashboard / users) → Validation Guide  
2. **Security architect** → Architecture → CIM → Operations checklist  
3. **Developer** → Architecture → API Reference (Auth & users) → Validation Guide  
4. **Maintainer** → Dependencies → `check_deps.py` → Dependabot / CI  
5. **Tenant admin** → User Guide §3.3.3 → Operations — Access control  
