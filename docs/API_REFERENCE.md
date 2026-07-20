# Quantum Helix API Reference

Developer-facing reference for core modules, public classes, CLI options, and entrypoints.

---

## Module map

| Module | Public symbols |
|--------|----------------|
| `normalization` | `CloudSecurityEvent`, `MultiCloudLogParser`, `generate_mock_stream`, `collect_mock_events`, `iter_infinite_mock_stream` |
| `data_processor` | `ClassicalFeaturePipeline`, `N_PRINCIPAL_COMPONENTS` |
| `quantum_engine` | `quantum_anomaly_circuit`, `QuantumThreatDetector`, `N_QUBITS`, `N_LAYERS` |
| `alerter` | `AlertOrchestrator`, `DEFAULT_THRESHOLD` |
| `models` | `User`, `HistoryEvent`, `Alert`, `SuppressionRule` |
| `api` | Flask REST API & SSE endpoints |
| `cli` | `cli`, `scan`, `main` |
| `main` | `run_pipeline`, `main` |
| `validate` | `run_validation`, `main` |

---

## `normalization`

### `CloudSecurityEvent`

Dataclass CIM record.

| Field | Type | Description |
|-------|------|-------------|
| `timestamp` | `str` | ISO-8601 style event time |
| `normalized_identity` | `str` | Principal (ARN, UPN, etc.) |
| `source_ip` | `str` | IPv4 string |
| `api_velocity` | `float` | Request/burst intensity feature |
| `auth_failures` | `float` | Failure / denial count |
| `data_volume_bytes` | `float` | Bytes transferred / egress |
| `cloud_provider` | `str` | `AWS`, `Azure`, … |
| `raw_event_id` | `str` | Source correlation id |

**Methods**

- `to_feature_vector() -> List[float]` — `[api_velocity, auth_failures, data_volume_bytes, ip_hash]`
- `to_dict() -> Dict[str, Any]` — `dataclasses.asdict` serialization

### `MultiCloudLogParser`

| Method | Input | Output |
|--------|-------|--------|
| `parse_aws(raw_json)` | `Dict[str, Any]` | `CloudSecurityEvent` (`cloud_provider="AWS"`) |
| `parse_azure(raw_json)` | `Dict[str, Any]` | `CloudSecurityEvent` (`cloud_provider="Azure"`) |

Graceful fallbacks exist when nested fields are missing. See [CIM.md](CIM.md).

### Generators

```python
generate_mock_stream(num_events=100, seed=42, anomaly_rate=0.05)
    -> Generator[CloudSecurityEvent, None, None]

collect_mock_events(num_events=100, seed=42) -> List[CloudSecurityEvent]

iter_infinite_mock_stream(seed=42, batch_size=50)
    -> Iterator[CloudSecurityEvent]
```

---

## `data_processor`

### `ClassicalFeaturePipeline`

```python
ClassicalFeaturePipeline(n_components: int = 4)
```

| Method | Description |
|--------|-------------|
| `fit_transform(events)` | Fit scaler+PCA; return `(n, 4)` matrix |
| `transform(events)` | Transform batch with fitted models |
| `transform_single(event)` | Return length-4 `np.ndarray` |
| `explained_variance_ratio()` | Per-component variance ratios |
| `is_fitted` | Property — `True` after successful fit |

**Raises**

- `ValueError` if fewer than `n_components` events on fit  
- `RuntimeError` if `transform*` called before fit  

---

## `quantum_engine`

### Constants

- `N_QUBITS = 4`
- `N_LAYERS = 3`

### `quantum_anomaly_circuit(features, weights)`

PennyLane `@qml.qnode` on `default.qubit` (4 wires).

Returns list of 4 Pauli-Z expectation values.

### `QuantumThreatDetector`

```python
QuantumThreatDetector(
    n_layers: int = 3,
    n_wires: int = 4,
    seed: int = 42,
    backend: str = "simulator",  # "simulator" | "qpu" (placeholder)
)
```

| Method | Description |
|--------|-------------|
| `predict_expectations(features)` | Raw ⟨Z⟩ vector |
| `score(features)` | Threat score ∈ `[0, 1]` |
| `score_batch(batch_features)` | Vectorized scoring over `(n, 4)` |
| `train_on_batch(batch_features, labels, steps=25, step_size=0.05)` | Adam MSE loop; returns loss history |
| `reseed_weights(seed=None)` | Reinitialize variational parameters |

Weights are allocated with:

```python
qml.StronglyEntanglingLayers.shape(n_layers=…, n_wires=…)
```

---

## `alerter`

### `AlertOrchestrator`

```python
AlertOrchestrator(
    threshold: float = 0.75,
    slack_webhook_url: str = "https://hooks.slack.example.local/...",
    product_arn: str = "arn:aws:securityhub:…:product/Quantum Helix/qml-detector",
    dry_run_webhook: bool = True,
)
```

| Method | Description |
|--------|-------------|
| `evaluate_and_alert(event, threat_score, threshold=None)` | Returns alert package `dict` or `None` |
| `build_asff_finding(event, threat_score, threshold)` | ASFF finding dict |
| `build_cef_event(event, threat_score, threshold)` | CEF string |
| `notify_slack_soc(package, event)` | Print + optional POST |
| `export_asff_batch()` | All ASFF findings this process |
| `reset()` | Clear `alert_history` |

**Alert package keys:** `alert_id`, `triggered_at`, `threshold`, `threat_score`, `cloud_provider`, `normalized_identity`, `source_ip`, `asff`, `cef`.

---

## CLI (`cli.py`)

```bash
python cli.py [--verbose] scan [OPTIONS]
python cli.py benchmark [--include-qnn] [--threshold 0.55]
```

Prog name: `Quantum Helix`.

### `scan` options

| Option | Type | Default | Notes |
|--------|------|---------|-------|
| `--duration` | int 1–3600 | `10` | Seconds / scale factor |
| `--threshold` | float 0–1 | `0.75` | Alert gate |
| `--engine` | choice | `ensemble` | `ensemble` \| `quantum_kernel` \| `classical_svm` \| `isolation_forest` \| `qnn` |
| `--backend` | `simulator`\|`qpu` | `simulator` | QPU is placeholder |
| `--warmup` | int 16–5000 | `60` | Fit / train cohort |
| `--events-per-second` | int 1–100 | `5` | Mock rate |

### PoC+ engines

| Module | Classes |
|--------|---------|
| `classical_baselines` | `IsolationForestDetector`, `ClassicalSVMDetector` |
| `quantum_kernel` | `QuantumKernelSVMDetector`, `compute_kernel_matrix` |
| `ensemble` | `HybridThreatEnsemble`, `EngineScores` |
| `apt_corpus` | `build_benchmark_corpus`, `make_subtle_apt_events` |
| `benchmark` | `run_benchmark`, `print_report` |

---

## Flask REST API (`api.py`)

Run via: `python api.py`

### Endpoints

| Method | Route | Description |
|--------|-------|-------------|
| `POST` | `/api/login` | Returns JWT token |
| `GET`  | `/api/stream` | Server-Sent Events (SSE) stream for live dashboard |
| `GET`  | `/api/alerts` | Paginated alerts (supports `search`, `status`, `start_date`, `end_date`) |
| `GET`  | `/api/alerts/export` | Download alerts as CSV |
| `POST` | `/api/alert/<id>/action` | Update alert status (`acknowledge`, `escalate`, `false_positive`) |
| `GET`  | `/api/rules` | Fetch suppression rules |
| `POST` | `/api/rules` | Add suppression rule |
| `DELETE`| `/api/rules/<id>` | Remove suppression rule |
| `POST` | `/api/controls` | Update backend state (`streaming`, `threshold`, `clear`) |

---

## Orchestrator (`main.py`)

```bash
python main.py [--warmup N] [--events N] [--threshold F]
               [--backend simulator|qpu] [--train-steps N]
               [--seed N] [-v]
```

| Function | Returns |
|----------|---------|
| `run_pipeline(...)` | `int` alert count |
| `main(argv=None)` | process exit code (`0`) |
| `label_events(events)` | weak label vector |

---

## Validator (`validate.py`)

```bash
python validate.py
```

| Exit code | Meaning |
|-----------|---------|
| `0` | All gates passed |
| `1` | Assertion failure or unexpected exception |

Internal helpers: `synthesize_normal_events`, `synthesize_attack_events`, `run_validation`.

Gates (defaults):

- Baseline average `< 0.40`
- Each attack `> baseline_avg + 0.20`
- Each attack `≥ 0.55` alert threshold
- Exactly 3 ASFF+CEF alert packages

---

## Minimal embedding example

```python
from normalization import collect_mock_events
from data_processor import ClassicalFeaturePipeline
from quantum_engine import QuantumThreatDetector
from alerter import AlertOrchestrator

events = collect_mock_events(80)
pipe = ClassicalFeaturePipeline()
X = pipe.fit_transform(events)

detector = QuantumThreatDetector(seed=42)
# optional: detector.train_on_batch(X, labels, steps=15)

alerter = AlertOrchestrator(threshold=0.75)
for event in events[:10]:
    score = detector.score(pipe.transform_single(event))
    alerter.evaluate_and_alert(event, score)
```

---

## Dependencies

Pinned / declared in `requirements.txt` (latest compatible stables). Refresh with:

```bash
python check_deps.py --update
pip install -r requirements.txt
```

See [DEPENDENCIES.md](DEPENDENCIES.md) for the continuous-update policy. Managed packages include:

- `pennylane` (QNN; requires Python ≥ 3.11)
- `autoray` (exact companion lock from PennyLane metadata)
- `pandas`, `scikit-learn`, `numpy`, `flask`, `flask-cors`, `flask-sqlalchemy`, `pyjwt`, `click`, `requests`
- `autograd>=1.8,<1.9` (PennyLane compatibility constraint)
