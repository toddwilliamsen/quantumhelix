# Glossary

Shared vocabulary for Quantum Helix documentation.

| Term | Meaning |
|------|---------|
| **ASFF** | AWS Security Finding Format — JSON schema for Security Hub findings |
| **CEF** | Common Event Format — pipe-delimited event string used by many SIEMs, including Microsoft Sentinel integrations |
| **CIM** | Common Information Model — normalized multi-cloud event schema (`CloudSecurityEvent`) |
| **CloudTrail** | AWS API audit log service (prototype uses CloudTrail-*style* JSON) |
| **NSG Flow Logs** | Azure Network Security Group flow telemetry (prototype maps related fields) |
| **PCA** | Principal Component Analysis — classical dimensionality reduction to 4 features |
| **QNN** | Quantum Neural Network — variational circuit used for threat scoring |
| **QNode** | PennyLane quantum node — Python function bound to a device that executes a circuit |
| **QPU** | Quantum Processing Unit — real quantum hardware (placeholder backend in this prototype) |
| **StronglyEntanglingLayers** | PennyLane template of trainable rotation + CNOT entangling layers |
| **AngleEmbedding** | Encodes classical features as qubit rotation angles |
| **Threat Score** | Scalar in `[0, 1]` from hybrid QNN + PCA-energy scoring (`0` safe → `1` critical) |
| **Warmup** | Initial batch used to fit scaler/PCA and optionally train QNN weights |
| **Dry-run webhook** | Slack notification path that logs the payload without a live HTTP POST |
| **EPS** | Events per second — mock ingest rate in the CLI |
| **SOC** | Security Operations Center |
| **SIEM** | Security Information and Event Management platform |
| **RBAC** | Role-Based Access Control — (1) Azure privilege-related *attacks* in the corpus, and (2) application roles that gate the React console (`SUPER_ADMIN`, `TENANT_ADMIN`, `TIER_1`, `TIER_2`, `READ_ONLY`) |
| **Tenant** | Isolation boundary for alerts, cases, rules, and audit; users belong to one tenant |
| **Session JWT** | HS256 bearer token (`type=session`) issued after login / MFA; required for API calls |
| **MFA** | Multi-factor authentication — TOTP authenticator apps and/or WebAuthn security keys |
| **Deactivate** | Soft revoke: `users.is_active=false` blocks login and live sessions without deleting history |
| **Exfiltration** | Unauthorized bulk data egress (high `data_volume_bytes`) |
| **Credential stuffing** | High-volume auth attempts using stolen credential sets |
| **Cross-cloud pivoting** | Lateral movement that spans AWS and Azure control/data planes |
| **`default.qubit`** | PennyLane local statevector simulator device |
| **Parameter-shift** | Hardware-friendly gradient estimation method for variational circuits |
| **Weak labels** | Heuristic 0/1 labels derived from feature thresholds for demo training |
