"""
Hybrid multi-engine threat ensemble for PoC+.

Default production-oriented blend for streaming:
  - Isolation Forest (fast classical)
  - Classical RBF SVM (supervised control)
  - Quantum Kernel SVM (primary quantum path)

Optional research sidecar:
  - Variational QNN (``quantum_engine.QuantumThreatDetector``)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

import numpy as np

from classical_baselines import ClassicalSVMDetector, IsolationForestDetector
from quantum_engine import QuantumThreatDetector
from quantum_kernel import QuantumKernelSVMDetector

logger = logging.getLogger(__name__)


@dataclass
class EngineScores:
    isolation_forest: float
    classical_svm: float
    quantum_kernel: float
    qnn: Optional[float] = None
    ensemble: float = 0.0


@dataclass
class EnsembleWeights:
    isolation_forest: float = 0.25
    classical_svm: float = 0.30
    quantum_kernel: float = 0.35
    qnn: float = 0.10


class HybridThreatEnsemble:
    """
    Fit / score multiple detectors on the same PCA feature matrix.
    """

    def __init__(
        self,
        *,
        seed: int = 42,
        include_qnn: bool = False,
        weights: Optional[EnsembleWeights] = None,
        qnn_backend: str = "simulator",
    ) -> None:
        self.seed = seed
        self.include_qnn = include_qnn
        self.weights = weights or EnsembleWeights()
        self.isolation_forest = IsolationForestDetector(seed=seed)
        self.classical_svm = ClassicalSVMDetector(seed=seed)
        self.quantum_kernel = QuantumKernelSVMDetector(seed=seed)
        self.qnn: Optional[QuantumThreatDetector] = (
            QuantumThreatDetector(backend=qnn_backend, seed=seed) if include_qnn else None
        )
        self._is_fitted = False

    @property
    def is_fitted(self) -> bool:
        return self._is_fitted

    def fit(self, features: np.ndarray, labels: np.ndarray) -> Dict[str, float]:
        features = np.asarray(features, dtype=np.float64)
        labels = np.asarray(labels, dtype=np.float64).reshape(-1)
        timing: Dict[str, float] = {}

        stats = self.isolation_forest.fit(features, labels)
        timing["isolation_forest_fit_s"] = stats.fit_seconds

        stats = self.classical_svm.fit(features, labels)
        timing["classical_svm_fit_s"] = stats.fit_seconds

        stats = self.quantum_kernel.fit(features, labels)
        timing["quantum_kernel_fit_s"] = stats.fit_seconds

        if self.qnn is not None:
            loss = self.qnn.train_on_batch(features, labels, steps=10, step_size=0.08)
            timing["qnn_final_loss"] = float(loss[-1]) if loss else float("nan")

        self._is_fitted = True
        logger.info("HybridThreatEnsemble fitted engines=%s", list(timing.keys()))
        return timing

    def score_detail(self, features: Sequence[float]) -> EngineScores:
        if not self._is_fitted:
            raise RuntimeError("HybridThreatEnsemble is not fitted")
        vec = np.asarray(features, dtype=np.float64).reshape(1, -1)
        if_score = float(self.isolation_forest.score_batch(vec)[0])
        svm_score = float(self.classical_svm.score_batch(vec)[0])
        qk_score = float(self.quantum_kernel.score_batch(vec)[0])
        qnn_score = float(self.qnn.score(vec.reshape(-1))) if self.qnn is not None else None

        w = self.weights
        if self.include_qnn and qnn_score is not None:
            total_w = w.isolation_forest + w.classical_svm + w.quantum_kernel + w.qnn
            ensemble = (
                w.isolation_forest * if_score
                + w.classical_svm * svm_score
                + w.quantum_kernel * qk_score
                + w.qnn * qnn_score
            ) / total_w
        else:
            total_w = w.isolation_forest + w.classical_svm + w.quantum_kernel
            ensemble = (
                w.isolation_forest * if_score
                + w.classical_svm * svm_score
                + w.quantum_kernel * qk_score
            ) / total_w

        return EngineScores(
            isolation_forest=if_score,
            classical_svm=svm_score,
            quantum_kernel=qk_score,
            qnn=qnn_score,
            ensemble=float(np.clip(ensemble, 0.0, 1.0)),
        )

    def score(self, features: Sequence[float]) -> float:
        return self.score_detail(features).ensemble

    def score_batch(self, features: np.ndarray) -> np.ndarray:
        matrix = np.asarray(features, dtype=np.float64)
        return np.asarray([self.score(row) for row in matrix], dtype=np.float64)
