"""
Quantum Helix native CLI.

Usage:
  python cli.py scan --duration 10 --threshold 0.70 --engine ensemble
  python cli.py benchmark --include-qnn
"""

from __future__ import annotations

import logging
import sys
import time
from typing import Any, List, Optional, Tuple

import click
import numpy as np

from alerter import AlertOrchestrator
from apt_corpus import build_benchmark_corpus
from classical_baselines import ClassicalSVMDetector, IsolationForestDetector
from data_processor import ClassicalFeaturePipeline
from ensemble import HybridThreatEnsemble
from normalization import CloudSecurityEvent, collect_mock_events, generate_mock_stream
from quantum_engine import QuantumThreatDetector
from quantum_kernel import QuantumKernelSVMDetector

logger = logging.getLogger(__name__)

ENGINE_CHOICES = [
    "ensemble",
    "quantum_kernel",
    "classical_svm",
    "isolation_forest",
    "qnn",
]


def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )


def _labels_from_events(events: List[CloudSecurityEvent]) -> np.ndarray:
    return np.asarray(
        [
            1.0
            if (
                e.auth_failures >= 10.0
                and e.data_volume_bytes >= 1e8
                and e.api_velocity >= 50.0
            )
            else 0.0
            for e in events
        ],
        dtype=np.float64,
    )


def _bootstrap_scorer(
    engine: str,
    warmup_events: int,
    backend: str,
    seed: int,
) -> Tuple[ClassicalFeaturePipeline, Any]:
    """Fit PCA + selected threat engine."""
    # Richer warmup: mock stream + loud/subtle corpus for supervised engines.
    warmup = collect_mock_events(num_events=warmup_events, seed=seed)
    extra_events, extra_labels, _ = build_benchmark_corpus(
        n_normal=40,
        n_loud=6,
        n_subtle=8,
        seed=seed + 5,
    )
    events = warmup + extra_events
    pipeline = ClassicalFeaturePipeline()
    reduced = pipeline.fit_transform(events)
    labels = np.concatenate([_labels_from_events(warmup), extra_labels])

    engine = engine.lower()
    if engine == "ensemble":
        scorer = HybridThreatEnsemble(seed=seed, include_qnn=False, qnn_backend=backend)
        scorer.fit(reduced, labels)
    elif engine == "quantum_kernel":
        scorer = QuantumKernelSVMDetector(seed=seed)
        scorer.fit(reduced, labels)
    elif engine == "classical_svm":
        scorer = ClassicalSVMDetector(seed=seed)
        scorer.fit(reduced, labels)
    elif engine == "isolation_forest":
        scorer = IsolationForestDetector(seed=seed)
        scorer.fit(reduced, labels)
    elif engine == "qnn":
        scorer = QuantumThreatDetector(backend=backend, seed=seed)
        if float(np.sum(labels)) >= 1.0:
            scorer.train_on_batch(reduced, labels, steps=12, step_size=0.08)
    else:
        raise click.ClickException(f"Unknown engine: {engine}")

    return pipeline, scorer


def _render_ascii_table(
    rows: List[Tuple[str, str, str, str, float, str]],
) -> str:
    """Render a clean ASCII summary table of scanned events."""
    headers = ("#", "Cloud", "Identity", "Source IP", "Score", "Status")
    str_rows = [
        (
            idx,
            cloud,
            identity[:42] + ("…" if len(identity) > 42 else ""),
            ip,
            f"{score:.4f}",
            status,
        )
        for idx, cloud, identity, ip, score, status in rows
    ]
    widths = [max(len(str(cell)) for cell in col) for col in zip(*([headers] + str_rows))]

    def fmt(row: Tuple[str, ...]) -> str:
        return "| " + " | ".join(str(cell).ljust(widths[i]) for i, cell in enumerate(row)) + " |"

    sep = "+" + "+".join("-" * (w + 2) for w in widths) + "+"
    lines = [sep, fmt(headers), sep]
    for row in str_rows:
        lines.append(fmt(row))
    lines.append(sep)
    return "\n".join(lines)


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.option("--verbose", "-v", is_flag=True, help="Enable debug logging.")
@click.pass_context
def cli(ctx: click.Context, verbose: bool) -> None:
    """Quantum Helix — Multi-Cloud Hybrid Quantum-Classical Threat Detection."""
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    _configure_logging(verbose)


@cli.command("scan")
@click.option(
    "--duration",
    default=10,
    show_default=True,
    type=click.IntRange(1, 3600),
    help="Approximate scan window in seconds (also scales event count).",
)
@click.option(
    "--threshold",
    default=0.75,
    show_default=True,
    type=click.FloatRange(0.0, 1.0),
    help="Threat score threshold for alerting (0.0–1.0).",
)
@click.option(
    "--engine",
    type=click.Choice(ENGINE_CHOICES, case_sensitive=False),
    default="ensemble",
    show_default=True,
    help="Detection engine (ensemble = IF + SVM + quantum kernel).",
)
@click.option(
    "--backend",
    type=click.Choice(["simulator", "qpu"], case_sensitive=False),
    default="simulator",
    show_default=True,
    help="Quantum backend placeholder (used by qnn / ensemble notes).",
)
@click.option(
    "--warmup",
    default=60,
    show_default=True,
    type=click.IntRange(16, 5000),
    help="Bootstrap events for PCA / model fit.",
)
@click.option(
    "--events-per-second",
    default=5,
    show_default=True,
    type=click.IntRange(1, 100),
    help="Mock telemetry ingest rate.",
)
@click.pass_context
def scan(
    ctx: click.Context,
    duration: int,
    threshold: float,
    engine: str,
    backend: str,
    warmup: int,
    events_per_second: int,
) -> None:
    """
    Stream mock multi-cloud logs through PCA + the selected threat engine,
    then emit SIEM / Slack alerts for scores at or above the threshold.
    """
    backend = backend.lower()
    engine = engine.lower()
    total_events = max(duration * events_per_second, 1)
    click.echo(
        click.style(
            f"\n⚛️  Quantum Helix scan starting "
            f"(engine={engine}, duration={duration}s, events≈{total_events}, "
            f"threshold={threshold:.2f})\n",
            fg="cyan",
            bold=True,
        )
    )

    pipeline, scorer = _bootstrap_scorer(
        engine=engine,
        warmup_events=warmup,
        backend=backend,
        seed=42,
    )
    alerter = AlertOrchestrator(threshold=threshold, dry_run_webhook=True)

    table_rows: List[Tuple[str, str, str, str, float, str]] = []
    alert_count = 0
    scores: List[float] = []
    started = time.time()
    sleep_interval = 1.0 / float(events_per_second)

    for index, event in enumerate(
        generate_mock_stream(num_events=total_events, seed=100),
        start=1,
    ):
        features = pipeline.transform_single(event)
        threat_score = float(scorer.score(features))
        scores.append(threat_score)
        package = alerter.evaluate_and_alert(event, threat_score, threshold=threshold)
        status = "ALERT" if package is not None else "ok"
        if package is not None:
            alert_count += 1

        table_rows.append(
            (
                str(index),
                event.cloud_provider,
                event.normalized_identity,
                event.source_ip,
                threat_score,
                status,
            )
        )

        elapsed = time.time() - started
        if elapsed < duration:
            time.sleep(min(sleep_interval, max(0.0, duration - elapsed)))
        elif index >= total_events:
            break

    click.echo("\n" + _render_ascii_table(table_rows))
    mean_score = float(np.mean(scores)) if scores else 0.0
    max_score = float(np.max(scores)) if scores else 0.0
    click.echo(
        "\n"
        + click.style(
            f"Scan complete — engine={engine} processed={len(scores)} alerts={alert_count} "
            f"mean_score={mean_score:.4f} max_score={max_score:.4f} "
            f"elapsed={time.time() - started:.1f}s",
            fg="green" if alert_count == 0 else "yellow",
            bold=True,
        )
        + "\n"
    )


@cli.command("benchmark")
@click.option("--threshold", default=0.55, show_default=True, type=click.FloatRange(0.0, 1.0))
@click.option("--include-qnn", is_flag=True, help="Also benchmark variational QNN sidecar.")
@click.option("--seed", default=42, show_default=True, type=int)
@click.pass_context
def benchmark_cmd(ctx: click.Context, threshold: float, include_qnn: bool, seed: int) -> None:
    """Run classical vs quantum-kernel head-to-head benchmark."""
    from benchmark import print_report, run_benchmark

    reports = run_benchmark(threshold=threshold, include_qnn=include_qnn, seed=seed)
    print_report(reports, threshold)


def main(argv: Optional[List[str]] = None) -> None:
    """Entrypoint compatible with ``python cli.py`` and console scripts."""
    cli.main(args=argv, prog_name="Quantum Helix", standalone_mode=True)


if __name__ == "__main__":
    main()
