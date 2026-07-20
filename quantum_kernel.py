"""
Quantum kernel / QSVM anomaly detector (PennyLane).

Maps PCA feature vectors into a Hilbert-space feature map via AngleEmbedding,
estimates a fidelity kernel, and trains a classical SVM on the precomputed
kernel matrix. This is the primary *quantum* path for PoC+ (more suitable than
a variational QNN for small multi-cloud feature vectors).

The optional QNN in ``quantum_engine.py`` remains available as a research sidecar.
"""

from __future__ import annotations

import logging
import time
from typing import Optional, Sequence, Tuple, Union

import numpy as np
import pennylane as qml
from sklearn.svm import SVC

from classical_baselines import FitStats

logger = logging.getLogger(__name__)

N_QUBITS = 4
FeatureMatrix = Union[np.ndarray, Sequence[Sequence[float]]]

# Shared simulator for kernel evaluations (AngleEmbedding only — shallow / cheap).
_kernel_dev = qml.device("default.qubit", wires=N_QUBITS)


@qml.qnode(_kernel_dev)
def fidelity_kernel_circuit(x1: np.ndarray, x2: np.ndarray) -> np.ndarray:
    """
    Projection onto |0…0⟩ after U(x1) then U†(x2).

    probs[0] == |⟨φ(x2)|φ(x1)⟩|² for the AngleEmbedding feature map.
    """
    qml.AngleEmbedding(x1, wires=range(N_QUBITS), rotation="Y")
    qml.adjoint(qml.AngleEmbedding)(x2, wires=range(N_QUBITS), rotation="Y")
    return qml.probs(wires=range(N_QUBITS))


def quantum_kernel_entry(x1: Sequence[float], x2: Sequence[float]) -> float:
    """Scalar fidelity kernel between two PCA feature vectors."""
    a = np.asarray(x1, dtype=np.float64).reshape(-1)
    b = np.asarray(x2, dtype=np.float64).reshape(-1)
    if a.shape[0] != N_QUBITS or b.shape[0] != N_QUBITS:
        raise ValueError(f"Expected length-{N_QUBITS} feature vectors")
    # Bound angles for stable embedding.
    a = np.clip(a, -np.pi, np.pi)
    b = np.clip(b, -np.pi, np.pi)
    probs = fidelity_kernel_circuit(a, b)
    return float(np.real(probs[0]))


def compute_kernel_matrix(
    x_left: np.ndarray,
    x_right: Optional[np.ndarray] = None,
    *,
    symmetric: bool = True,
) -> np.ndarray:
    """
    Compute a (possibly rectangular) quantum kernel matrix.

    When ``x_right`` is None, builds the square Gram matrix on ``x_left``.
    For symmetric square matrices, only the upper triangle is evaluated.
    """
    left = np.asarray(x_left, dtype=np.float64)
    right = left if x_right is None else np.asarray(x_right, dtype=np.float64)
    n_l, n_r = len(left), len(right)
    matrix = np.zeros((n_l, n_r), dtype=np.float64)

    if x_right is None and symmetric:
        for i in range(n_l):
            matrix[i, i] = 1.0
            for j in range(i + 1, n_l):
                value = quantum_kernel_entry(left[i], left[j])
                matrix[i, j] = value
                matrix[j, i] = value
    else:
        for i in range(n_l):
            for j in range(n_r):
                matrix[i, j] = quantum_kernel_entry(left[i], right[j])
    return matrix


class QuantumKernelSVMDetector:
    """
    Quantum Support Vector Machine using a PennyLane fidelity kernel.

    Fit path:
      1. Build train Gram matrix K_train[i,j] = |⟨φ(x_i)|φ(x_j)⟩|²
      2. Train sklearn SVC(kernel='precomputed')
    Score path:
      1. Build K_test against support / training set
      2. Return attack-class probability (or normalized decision)
    """

    def __init__(self, seed: int = 42, c: float = 2.0) -> None:
        self.seed = seed
        self.c = c
        self.model = SVC(
            kernel="precomputed",
            C=c,
            class_weight="balanced",
            random_state=seed,
        )
        self._train_features: Optional[np.ndarray] = None
        self._is_fitted = False
        self.last_fit: Optional[FitStats] = None
        self.last_kernel_seconds: float = 0.0
        self.kernel_evaluations: int = 0
        self._decision_lo: float = -1.0
        self._decision_hi: float = 1.0

    @property
    def is_fitted(self) -> bool:
        return self._is_fitted

    def fit(self, features: FeatureMatrix, labels: np.ndarray) -> FitStats:
        matrix = np.asarray(features, dtype=np.float64)
        y = np.asarray(labels, dtype=np.float64).reshape(-1)
        if matrix.ndim != 2 or matrix.shape[1] != N_QUBITS:
            raise ValueError(f"features must have shape (n, {N_QUBITS})")
        if matrix.shape[0] != y.shape[0]:
            raise ValueError("features and labels length mismatch")
        if len(np.unique(y)) < 2:
            raise ValueError("QuantumKernelSVMDetector requires both class labels")

        started = time.perf_counter()
        gram = compute_kernel_matrix(matrix)
        kernel_seconds = time.perf_counter() - started
        self.kernel_evaluations = matrix.shape[0] * (matrix.shape[0] + 1) // 2
        self.last_kernel_seconds = kernel_seconds

        fit_started = time.perf_counter()
        self.model.fit(gram, y.astype(int))
        train_dec = self.model.decision_function(gram)
        self._decision_lo = float(np.min(train_dec))
        self._decision_hi = float(np.max(train_dec))
        if self._decision_hi - self._decision_lo < 1e-12:
            self._decision_hi = self._decision_lo + 1.0
        self._train_features = matrix
        self._is_fitted = True
        total = time.perf_counter() - started
        stats = FitStats(
            engine="quantum_kernel_svm",
            n_samples=len(matrix),
            fit_seconds=total,
        )
        self.last_fit = stats
        logger.info(
            "QSVM fitted samples=%d kernel_s=%.4f total_s=%.4f kernel_evals≈%d svm_s=%.4f",
            len(matrix),
            kernel_seconds,
            total,
            self.kernel_evaluations,
            time.perf_counter() - fit_started,
        )
        return stats

    def score(self, features: FeatureMatrix) -> float:
        return float(self.score_batch(features)[0])

    def score_batch(self, features: FeatureMatrix) -> np.ndarray:
        if not self._is_fitted or self._train_features is None:
            raise RuntimeError("QuantumKernelSVMDetector is not fitted")
        matrix = np.asarray(features, dtype=np.float64)
        if matrix.ndim == 1:
            matrix = matrix.reshape(1, -1)
        started = time.perf_counter()
        gram = compute_kernel_matrix(matrix, self._train_features, symmetric=False)
        self.last_kernel_seconds = time.perf_counter() - started
        self.kernel_evaluations = matrix.shape[0] * self._train_features.shape[0]

        decision = self.model.decision_function(gram)
        return np.clip(
            (decision - self._decision_lo) / (self._decision_hi - self._decision_lo),
            0.0,
            1.0,
        )
