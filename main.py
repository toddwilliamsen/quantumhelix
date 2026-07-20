"""
Quantum Helix orchestration entry point.

Wires normalization → classical PCA reduction → PennyLane QNN scoring →
SIEM / Slack alerting into a single debug-friendly executable path.

Architectural scale-out notes (simulator → real QPU):
----------------------------------------------------
1. Device abstraction
   ``quantum_engine.dev`` currently binds to ``qml.device("default.qubit", wires=4)``.
   In production, swap this for:
     - AWS Braket: ``qml.device("braket.aws.qubit", device_arn=..., wires=4)``
     - Azure Quantum: ``qml.device("azure.quantum", ...)`` via the PennyLane plugin
   The ``QuantumThreatDetector(backend=...)`` flag is the control-plane switch;
   QNode bodies and weight shapes remain identical because templates are backend-
   agnostic — only shot statistics and queue latency change.

2. Classical pre-processing remains the hot path
   High-throughput CloudTrail / Activity Log ingest should stay on CPU/GPU Spark
   or Flink jobs. Only the 4-dimensional PCA vector crosses the quantum boundary,
   keeping QPU circuit depth and shot budgets commercially viable.

3. Weight checkpointing
   Persist ``detector.weights`` (numpy) to object storage after ``train_on_batch``.
   On hardware, prefer gradient-free optimizers or parameter-shift with modest
   learning rates; Adam on ``default.qubit`` is for lab prototyping.

4. Alert fan-out
   ``AlertOrchestrator`` already emits ASFF (Security Hub) and CEF (Sentinel).
   Replace ``dry_run_webhook=False`` and real webhook URLs / boto3 ``batch_import_findings``
   calls when wiring to a production SOC.

Run:
  python main.py
  python main.py --events 60 --threshold 0.70 --train-steps 20
"""

from __future__ import annotations

import argparse
import logging
import sys
from typing import List

import numpy as np

from alerter import AlertOrchestrator
from data_processor import ClassicalFeaturePipeline
from normalization import CloudSecurityEvent, collect_mock_events, generate_mock_stream
from quantum_engine import QuantumThreatDetector

logger = logging.getLogger("quantum_helix.main")


def configure_logging(verbose: bool = False) -> None:
    """Configure process-wide structured logging for the orchestration path."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )


def label_events(events: List[CloudSecurityEvent]) -> np.ndarray:
    """
    Derive weak supervision labels for the mock training loop.

    Correlated anomaly signature matches ``generate_mock_stream`` injected outliers:
    elevated API velocity + auth failures + exfiltration-scale data volume.
    """
    labels = []
    for event in events:
        is_anomaly = (
            event.auth_failures >= 10.0
            and event.data_volume_bytes >= 1e8
            and event.api_velocity >= 50.0
        )
        labels.append(1.0 if is_anomaly else 0.0)
    return np.asarray(labels, dtype=np.float64)


def run_pipeline(
    warmup_events: int = 100,
    stream_events: int = 50,
    threshold: float = 0.75,
    backend: str = "simulator",
    train_steps: int = 20,
    seed: int = 42,
) -> int:
    """
    Execute the full hybrid quantum-classical detection pipeline.

    Returns the number of alerts raised (useful for CI / smoke tests).
    """
    logger.info("=" * 72)
    logger.info("Quantum Helix orchestration starting")
    logger.info(
        "config warmup=%d stream=%d threshold=%.2f backend=%s train_steps=%d",
        warmup_events,
        stream_events,
        threshold,
        backend,
        train_steps,
    )
    logger.info("=" * 72)

    # ------------------------------------------------------------------
    # Stage 1 — Multi-cloud CIM normalization (AWS CloudTrail + Azure)
    # ------------------------------------------------------------------
    # At enterprise scale this stage is a streaming consumer (Kinesis / Event
    # Hub). Here we bootstrap with a labeled mock corpus for PCA + QNN warm-start.
    logger.info("Stage 1/4: Collecting and normalizing warmup telemetry")
    warmup = collect_mock_events(num_events=warmup_events, seed=seed)
    n_aws = sum(1 for e in warmup if e.cloud_provider == "AWS")
    n_azure = sum(1 for e in warmup if e.cloud_provider == "Azure")
    logger.info("Warmup corpus ready: total=%d aws=%d azure=%d", len(warmup), n_aws, n_azure)

    # ------------------------------------------------------------------
    # Stage 2 — Classical dimensionality reduction (StandardScaler + PCA→4)
    # ------------------------------------------------------------------
    # Four components == four qubits. Keeping the quantum feature width small
    # is what makes Braket / Azure Quantum cost models tractable under bursty
    # cloud telemetry rates (millions of events → thousands of PCA vectors).
    logger.info("Stage 2/4: Fitting classical StandardScaler + PCA(n=4)")
    pipeline = ClassicalFeaturePipeline()
    reduced = pipeline.fit_transform(warmup)
    explained = pipeline.explained_variance_ratio()
    logger.info(
        "PCA explained variance ratios=%s (sum=%.4f)",
        np.array2string(explained, precision=4),
        float(np.sum(explained)),
    )

    # ------------------------------------------------------------------
    # Stage 3 — Quantum Neural Network training & inference
    # ------------------------------------------------------------------
    # On default.qubit, expectation values are exact (analytic). On real QPUs,
    # set `shots=` on the device and increase shot counts for lower-variance
    # gradients when using parameter-shift rules. Circuit topology does not
    # change — only the PennyLane device plugin binding changes.
    logger.info("Stage 3/4: Initializing QuantumThreatDetector (backend=%s)", backend)
    detector = QuantumThreatDetector(backend=backend, seed=seed)
    labels = label_events(warmup)
    positive = int(np.sum(labels))
    logger.info("Weak labels for training: positives=%d / %d", positive, len(labels))
    if positive > 0:
        loss_curve = detector.train_on_batch(
            reduced,
            labels,
            steps=train_steps,
            step_size=0.08,
        )
        logger.info(
            "QNN training finished: initial_loss=%.6f final_loss=%.6f",
            loss_curve[0],
            loss_curve[-1],
        )
    else:
        logger.warning("No positive labels in warmup — skipping supervised train loop")

    # ------------------------------------------------------------------
    # Stage 4 — Live stream scoring + ASFF/CEF/Slack alerting
    # ------------------------------------------------------------------
    # AlertOrchestrator dual-writes AWS Security Hub ASFF and Microsoft
    # Sentinel CEF so a single QNN detection lands in both cloud SOCs.
    logger.info("Stage 4/4: Streaming live mock telemetry and evaluating threats")
    alerter = AlertOrchestrator(threshold=threshold, dry_run_webhook=True)
    alert_count = 0
    scored = 0

    for event in generate_mock_stream(num_events=stream_events, seed=seed + 1000):
        features = pipeline.transform_single(event)
        threat_score = detector.score(features)
        scored += 1
        package = alerter.evaluate_and_alert(event, threat_score, threshold=threshold)
        if package is not None:
            alert_count += 1
            logger.info(
                "ALERT provider=%s score=%.4f identity=%s asff_id=%s",
                event.cloud_provider,
                threat_score,
                event.normalized_identity,
                package["asff"]["Id"],
            )
        else:
            logger.debug(
                "benign provider=%s score=%.4f identity=%s",
                event.cloud_provider,
                threat_score,
                event.normalized_identity,
            )

    logger.info("=" * 72)
    logger.info(
        "Pipeline complete: scored=%d alerts=%d asff_findings=%d",
        scored,
        alert_count,
        len(alerter.export_asff_batch()),
    )
    logger.info(
        "Scale note: replace default.qubit with Braket/Azure Quantum device plugins "
        "without changing CIM, PCA width, or ASFF/CEF contracts."
    )
    logger.info("=" * 72)
    return alert_count


def parse_args(argv: List[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Quantum Helix hybrid quantum-classical threat detection orchestrator",
    )
    parser.add_argument("--warmup", type=int, default=100, help="Bootstrap events for PCA/QNN fit")
    parser.add_argument("--events", type=int, default=50, help="Live stream event count")
    parser.add_argument("--threshold", type=float, default=0.75, help="Alert threshold [0,1]")
    parser.add_argument(
        "--backend",
        choices=["simulator", "qpu"],
        default="simulator",
        help="Quantum backend selector (qpu is a hardware placeholder)",
    )
    parser.add_argument("--train-steps", type=int, default=20, help="AdamOptimizer training steps")
    parser.add_argument("--seed", type=int, default=42, help="RNG seed for reproducibility")
    parser.add_argument("-v", "--verbose", action="store_true", help="Debug logging")
    return parser.parse_args(argv)


def main(argv: List[str] | None = None) -> int:
    args = parse_args(argv)
    configure_logging(verbose=args.verbose)
    alerts = run_pipeline(
        warmup_events=args.warmup,
        stream_events=args.events,
        threshold=args.threshold,
        backend=args.backend,
        train_steps=args.train_steps,
        seed=args.seed,
    )
    # Non-zero alerts are expected in a healthy demo (≈5% anomaly injection).
    logger.info("Exiting orchestration with alert_count=%d", alerts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
