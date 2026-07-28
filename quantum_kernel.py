"""
Quantum kernel / QSVM anomaly detector (PennyLane).

Maps PCA feature vectors into a Hilbert-space feature map,
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
from sklearn.linear_model import LogisticRegression

logger = logging.getLogger(__name__)

N_QUBITS = 4
FeatureMatrix = Union[np.ndarray, Sequence[Sequence[float]]]


def _fit_platt(decisions: np.ndarray, labels: np.ndarray) -> LogisticRegression:
    x = np.asarray(decisions, dtype=np.float64).reshape(-1, 1)
    y = np.asarray(labels, dtype=int).reshape(-1)
    cal = LogisticRegression(max_iter=200)
    cal.fit(x, y)
    return cal


def _apply_platt(calibrator: LogisticRegression, decisions: np.ndarray) -> np.ndarray:
    x = np.asarray(decisions, dtype=np.float64).reshape(-1, 1)
    classes = list(calibrator.classes_)
    attack_idx = classes.index(1) if 1 in classes else -1
    return calibrator.predict_proba(x)[:, attack_idx]


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

    def __init__(self, seed: int = 42, c: float = 2.0, encoding: str = "angle", noise_prob: float = 0.0) -> None:
        self.seed = seed
        self.c = c
        self.encoding = encoding.lower()
        self.noise_prob = noise_prob
        self.model = SVC(
            kernel="precomputed",
            C=c,
            class_weight="balanced",
            random_state=seed,
        )
        self._train_features: Optional[np.ndarray] = None
        self._calibrator: Optional[LogisticRegression] = None
        self._is_fitted = False
        self.last_fit: Optional[FitStats] = None
        self.last_kernel_seconds: float = 0.0
        self.kernel_evaluations: int = 0
        
        self._setup_kernel_circuit()

    def _setup_kernel_circuit(self):
        if self.noise_prob > 0.0:
            dev = qml.device("default.mixed", wires=N_QUBITS)
        else:
            dev = qml.device("default.qubit", wires=N_QUBITS)
            
        @qml.qnode(dev)
        def kernel_circuit(x1, x2):
            if self.encoding == "angle":
                qml.AngleEmbedding(x1, wires=range(N_QUBITS), rotation="Y")
                qml.adjoint(qml.AngleEmbedding)(x2, wires=range(N_QUBITS), rotation="Y")
            elif self.encoding == "iqp":
                qml.IQPEmbedding(x1, wires=range(N_QUBITS))
                qml.adjoint(qml.IQPEmbedding)(x2, wires=range(N_QUBITS))
            elif self.encoding == "amplitude":
                qml.AmplitudeEmbedding(x1, wires=range(N_QUBITS), normalize=True, pad_with=0.0)
                qml.adjoint(qml.AmplitudeEmbedding)(x2, wires=range(N_QUBITS), normalize=True, pad_with=0.0)
            else:
                raise ValueError(f"Unknown encoding {self.encoding}")
                
            if self.noise_prob > 0.0:
                for w in range(N_QUBITS):
                    qml.DepolarizingChannel(self.noise_prob, wires=w)
                    
            return qml.probs(wires=range(N_QUBITS))
            
        self.kernel_circuit = kernel_circuit
        
    def _prepare_vector(self, x: np.ndarray) -> np.ndarray:
        a = np.asarray(x, dtype=np.float64).reshape(-1)
        if self.encoding == "amplitude":
            required_len = 2**N_QUBITS
            if len(a) < required_len:
                a = np.pad(a, (0, required_len - len(a)), "constant")
            elif len(a) > required_len:
                a = a[:required_len]
        else:
            if a.shape[0] != N_QUBITS:
                raise ValueError(f"Expected length-{N_QUBITS} feature vectors")
            a = np.clip(a, -np.pi, np.pi)
        return a

    def quantum_kernel_entry(self, x1: Sequence[float], x2: Sequence[float]) -> float:
        a = self._prepare_vector(x1)
        b = self._prepare_vector(x2)
        probs = self.kernel_circuit(a, b)
        return float(np.real(probs[0]))

    def compute_kernel_matrix(
        self,
        x_left: np.ndarray,
        x_right: Optional[np.ndarray] = None,
        *,
        symmetric: bool = True,
    ) -> np.ndarray:
        left = np.asarray(x_left, dtype=np.float64)
        right = left if x_right is None else np.asarray(x_right, dtype=np.float64)
        n_l, n_r = len(left), len(right)
        matrix = np.zeros((n_l, n_r), dtype=np.float64)

        if x_right is None and symmetric:
            for i in range(n_l):
                matrix[i, i] = 1.0
                for j in range(i + 1, n_l):
                    value = self.quantum_kernel_entry(left[i], left[j])
                    matrix[i, j] = value
                    matrix[j, i] = value
        else:
            for i in range(n_l):
                for j in range(n_r):
                    matrix[i, j] = self.quantum_kernel_entry(left[i], right[j])
        return matrix

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
        gram = self.compute_kernel_matrix(matrix)
        kernel_seconds = time.perf_counter() - started
        self.kernel_evaluations = matrix.shape[0] * (matrix.shape[0] + 1) // 2
        self.last_kernel_seconds = kernel_seconds

        fit_started = time.perf_counter()
        self.model.fit(gram, y.astype(int))
        train_dec = self.model.decision_function(gram)
        self._calibrator = _fit_platt(train_dec, y)
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
            "QSVM fitted samples=%d kernel_s=%.4f total_s=%.4f kernel_evals≈%d svm_s=%.4f encoding=%s noise=%.2f",
            len(matrix),
            kernel_seconds,
            total,
            self.kernel_evaluations,
            time.perf_counter() - fit_started,
            self.encoding,
            self.noise_prob,
        )
        return stats

    def score(self, features: FeatureMatrix) -> float:
        return float(self.score_batch(features)[0])

    def score_batch(self, features: FeatureMatrix) -> np.ndarray:
        if not self._is_fitted or self._train_features is None or self._calibrator is None:
            raise RuntimeError("QuantumKernelSVMDetector is not fitted")
        matrix = np.asarray(features, dtype=np.float64)
        if matrix.ndim == 1:
            matrix = matrix.reshape(1, -1)

        support = getattr(self.model, "support_", None)
        n_train = self._train_features.shape[0]
        started = time.perf_counter()
        if support is not None and len(support) > 0 and len(support) < n_train:
            gram_sv = self.compute_kernel_matrix(matrix, self._train_features[support], symmetric=False)
            gram = np.zeros((matrix.shape[0], n_train), dtype=np.float64)
            gram[:, support] = gram_sv
            self.kernel_evaluations = matrix.shape[0] * len(support)
        else:
            gram = self.compute_kernel_matrix(matrix, self._train_features, symmetric=False)
            self.kernel_evaluations = matrix.shape[0] * n_train
        self.last_kernel_seconds = time.perf_counter() - started

        decision = self.model.decision_function(gram)
        return _apply_platt(self._calibrator, decision)
