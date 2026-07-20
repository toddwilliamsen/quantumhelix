#!/usr/bin/env python3
"""
Head-to-head detector benchmark for Quantum Helix (PoC+).

Compares:
  - Isolation Forest (classical unsupervised)
  - RBF SVM (classical supervised control)
  - Quantum Kernel SVM (primary quantum path)
  - Variational QNN (optional research sidecar)

Metrics: detection rate, false-positive rate, subtle-APT recall, fit latency,
per-event score latency, and a crude relative compute-cost proxy.

Usage:
  python benchmark.py
  python benchmark.py --include-qnn --threshold 0.55
  python cli.py benchmark
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from dataclasses import asdict, dataclass
from typing import Callable, Dict, List, Optional

import numpy as np
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split

from apt_corpus import build_benchmark_corpus
from classical_baselines import ClassicalSVMDetector, IsolationForestDetector
from data_processor import ClassicalFeaturePipeline
from quantum_engine import QuantumThreatDetector
from quantum_kernel import QuantumKernelSVMDetector

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("quantum_helix.benchmark")


@dataclass
class EngineReport:
    name: str
    detection_rate: float
    false_positive_rate: float
    subtle_apt_recall: float
    loud_attack_recall: float
    roc_auc: float
    fit_seconds: float
    mean_score_ms: float
    cost_proxy: float
    notes: str = ""


def _rates(
    y_true: np.ndarray,
    scores: np.ndarray,
    threshold: float,
    subtle_mask: np.ndarray,
) -> Dict[str, float]:
    y_hat = (scores >= threshold).astype(np.float64)
    positives = y_true >= 0.5
    negatives = ~positives
    tp = float(np.sum((y_hat >= 0.5) & positives))
    fp = float(np.sum((y_hat >= 0.5) & negatives))
    fn = float(np.sum((y_hat < 0.5) & positives))
    tn = float(np.sum((y_hat < 0.5) & negatives))
    detection_rate = tp / max(tp + fn, 1.0)
    fpr = fp / max(fp + tn, 1.0)

    subtle = subtle_mask >= 0.5
    loud = positives & (~subtle)
    subtle_recall = float(np.sum((y_hat >= 0.5) & subtle)) / max(float(np.sum(subtle)), 1.0)
    loud_recall = float(np.sum((y_hat >= 0.5) & loud)) / max(float(np.sum(loud)), 1.0)

    try:
        auc = float(roc_auc_score(y_true, scores)) if len(np.unique(y_true)) > 1 else float("nan")
    except ValueError:
        auc = float("nan")

    return {
        "detection_rate": detection_rate,
        "false_positive_rate": fpr,
        "subtle_apt_recall": subtle_recall,
        "loud_attack_recall": loud_recall,
        "roc_auc": auc,
    }


def _time_scores(fn: Callable[[np.ndarray], np.ndarray], x: np.ndarray) -> tuple[np.ndarray, float]:
    started = time.perf_counter()
    scores = fn(x)
    elapsed = time.perf_counter() - started
    mean_ms = (elapsed / max(len(x), 1)) * 1000.0
    return np.asarray(scores, dtype=np.float64), mean_ms


def run_benchmark(
    *,
    threshold: float = 0.55,
    include_qnn: bool = False,
    seed: int = 42,
    n_normal: int = 100,
    n_loud: int = 10,
    n_subtle: int = 14,
) -> List[EngineReport]:
    events, labels, subtle_mask = build_benchmark_corpus(
        n_normal=n_normal,
        n_loud=n_loud,
        n_subtle=n_subtle,
        seed=seed,
    )
    pipeline = ClassicalFeaturePipeline()
    features = pipeline.fit_transform(events)

    (
        x_train,
        x_test,
        y_train,
        y_test,
        s_train,
        s_test,
    ) = train_test_split(
        features,
        labels,
        subtle_mask,
        test_size=0.35,
        random_state=seed,
        stratify=labels,
    )

    reports: List[EngineReport] = []

    # --- Isolation Forest ---
    if_model = IsolationForestDetector(seed=seed, contamination=max(0.05, float(np.mean(y_train))))
    fit_started = time.perf_counter()
    if_model.fit(x_train, y_train)
    if_fit = time.perf_counter() - fit_started
    if_scores, if_ms = _time_scores(if_model.score_batch, x_test)
    metrics = _rates(y_test, if_scores, threshold, s_test)
    reports.append(
        EngineReport(
            name="isolation_forest",
            fit_seconds=if_fit,
            mean_score_ms=if_ms,
            cost_proxy=1.0,
            notes="Classical unsupervised baseline (streaming-friendly)",
            **metrics,
        )
    )

    # --- Classical SVM ---
    svm = ClassicalSVMDetector(seed=seed)
    fit_started = time.perf_counter()
    svm.fit(x_train, y_train)
    svm_fit = time.perf_counter() - fit_started
    svm_scores, svm_ms = _time_scores(svm.score_batch, x_test)
    metrics = _rates(y_test, svm_scores, threshold, s_test)
    reports.append(
        EngineReport(
            name="classical_svm",
            fit_seconds=svm_fit,
            mean_score_ms=svm_ms,
            cost_proxy=1.5,
            notes="Classical supervised RBF-SVM control group",
            **metrics,
        )
    )

    # --- Quantum Kernel SVM ---
    qsvm = QuantumKernelSVMDetector(seed=seed)
    fit_started = time.perf_counter()
    qsvm.fit(x_train, y_train)
    qsvm_fit = time.perf_counter() - fit_started
    qsvm_scores, qsvm_ms = _time_scores(qsvm.score_batch, x_test)
    metrics = _rates(y_test, qsvm_scores, threshold, s_test)
    # Cost proxy ~ kernel evaluations relative to classical SVM.
    kernel_proxy = max(2.0, (len(x_train) ** 2) / 500.0)
    reports.append(
        EngineReport(
            name="quantum_kernel_svm",
            fit_seconds=qsvm_fit,
            mean_score_ms=qsvm_ms,
            cost_proxy=kernel_proxy,
            notes="PennyLane fidelity kernel + classical SVM (primary quantum path)",
            **metrics,
        )
    )

    # --- Optional QNN sidecar ---
    if include_qnn:
        qnn = QuantumThreatDetector(seed=seed, backend="simulator")
        fit_started = time.perf_counter()
        qnn.train_on_batch(x_train, y_train, steps=8, step_size=0.08)
        qnn_fit = time.perf_counter() - fit_started

        def _qnn_batch(x: np.ndarray) -> np.ndarray:
            return np.asarray([qnn.score(row) for row in x], dtype=np.float64)

        qnn_scores, qnn_ms = _time_scores(_qnn_batch, x_test)
        metrics = _rates(y_test, qnn_scores, threshold, s_test)
        reports.append(
            EngineReport(
                name="variational_qnn",
                fit_seconds=qnn_fit,
                mean_score_ms=qnn_ms,
                cost_proxy=max(5.0, qnn_fit / max(svm_fit, 1e-6)),
                notes="Optional research sidecar — not the default PoC+ engine",
                **metrics,
            )
        )

    return reports


def print_report(reports: List[EngineReport], threshold: float) -> None:
    width = 108
    print("\n" + "=" * width)
    print(" Quantum Helix PoC+ BENCHMARK — Classical Control vs Quantum Kernel")
    print("=" * width)
    print(f" Decision threshold: {threshold:.2f}")
    print(
        f"{'Engine':<22} {'Detect':>8} {'FPR':>8} {'Subtle':>8} {'Loud':>8} "
        f"{'AUC':>8} {'Fit(s)':>8} {'ms/evt':>8} {'Cost~':>8}"
    )
    print("-" * width)
    for r in reports:
        print(
            f"{r.name:<22} {r.detection_rate:>8.3f} {r.false_positive_rate:>8.3f} "
            f"{r.subtle_apt_recall:>8.3f} {r.loud_attack_recall:>8.3f} "
            f"{r.roc_auc:>8.3f} {r.fit_seconds:>8.3f} {r.mean_score_ms:>8.2f} {r.cost_proxy:>8.2f}"
        )
    print("-" * width)
    for r in reports:
        print(f"  • {r.name}: {r.notes}")
    print()
    classical = next((r for r in reports if r.name == "classical_svm"), None)
    quantum = next((r for r in reports if r.name == "quantum_kernel_svm"), None)
    if classical and quantum:
        delta_subtle = quantum.subtle_apt_recall - classical.subtle_apt_recall
        delta_fpr = quantum.false_positive_rate - classical.false_positive_rate
        print(" Quantum vs classical SVM deltas:")
        print(f"   subtle APT recall Δ = {delta_subtle:+.3f}")
        print(f"   false-positive rate Δ = {delta_fpr:+.3f}")
        if delta_subtle > 0.02 and delta_fpr <= 0.05:
            print("   Interpretation: quantum kernel shows a potential niche on subtle APTs (PoC signal).")
        elif abs(delta_subtle) <= 0.02 and abs(delta_fpr) <= 0.05:
            print("   Interpretation: parity with classical SVM on this corpus — useful but not yet advantage.")
        else:
            print("   Interpretation: mixed; expand APT corpus / kernel feature map before claiming advantage.")
    print("=" * width + "\n")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Benchmark classical vs quantum threat detectors")
    parser.add_argument("--threshold", type=float, default=0.55)
    parser.add_argument("--include-qnn", action="store_true", help="Also bench variational QNN sidecar")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--n-normal", type=int, default=100)
    parser.add_argument("--n-loud", type=int, default=10)
    parser.add_argument("--n-subtle", type=int, default=14)
    parser.add_argument("--json-out", type=str, default="", help="Optional path to write JSON report")
    args = parser.parse_args(argv)

    reports = run_benchmark(
        threshold=args.threshold,
        include_qnn=args.include_qnn,
        seed=args.seed,
        n_normal=args.n_normal,
        n_loud=args.n_loud,
        n_subtle=args.n_subtle,
    )
    print_report(reports, args.threshold)
    if args.json_out:
        payload = [asdict(r) for r in reports]
        with open(args.json_out, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
        logger.info("Wrote JSON report to %s", args.json_out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
