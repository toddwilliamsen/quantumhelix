"""
Quantum Machine Learning anomaly detection core (PennyLane).

Implements a 4-qubit parameterized quantum circuit (AngleEmbedding +
StronglyEntanglingLayers) that maps classical PCA features to a normalized
threat score in [0.0, 1.0]. Includes a mock AdamOptimizer training loop for
supervised security labels.
"""

from __future__ import annotations

import logging
from typing import Iterable, List, Optional, Sequence, Tuple, Union

import numpy as np
import pennylane as qml
from pennylane import numpy as pnp

logger = logging.getLogger(__name__)

N_QUBITS = 4
N_LAYERS = 3
FeatureArray = Union[np.ndarray, Sequence[float]]


# We remove the global device and qnode because we need them to be instantiated
# per-detector to support dynamic noise probabilities.

def _normalize_threat_score(expectation_values: Sequence[float]):
    """
    Aggregate four PauliZ expectation values into a single threat score.

    Each expectation is in [-1, 1]. We map to [0, 1] via (1 - z) / 2 so that
    low (negative) Z expectations — typical of highly transformed / anomalous
    feature encodings after training — push the score toward Critical (1.0).
    The mean across wires yields a stable scalar in [0.0, 1.0].

    Implemented with pure arithmetic (no NumPy casts) so PennyLane's
    AdamOptimizer autodiff graph remains intact during ``train_on_batch``.
    """
    values = list(expectation_values)
    if not values:
        raise ValueError("expectation_values must be non-empty")
    total = sum((1.0 - value) / 2.0 for value in values)
    return total / float(len(values))

class QuantumThreatDetector:
    """
    Quantum Neural Network threat detector wrapping ``quantum_anomaly_circuit``.

    Weights are shaped via ``qml.StronglyEntanglingLayers.shape`` to guarantee
    dimensional compatibility with PennyLane's entangling layer template.
    """

    def __init__(
        self,
        n_layers: int = N_LAYERS,
        n_wires: int = N_QUBITS,
        seed: int = 42,
        backend: str = "simulator",
        noise_prob: float = 0.0,
    ) -> None:
        if n_wires != N_QUBITS:
            raise ValueError(f"n_wires must be {N_QUBITS} to match AngleEmbedding width")

        self.n_layers = n_layers
        self.n_wires = n_wires
        self.backend = backend
        self._rng = np.random.default_rng(seed)

        weight_shape = qml.StronglyEntanglingLayers.shape(
            n_layers=self.n_layers,
            n_wires=self.n_wires,
        )
        # PennyLane requires trainable arrays for AdamOptimizer autodiff.
        self.weights = pnp.array(
            self._rng.uniform(0.0, 2.0 * np.pi, size=weight_shape),
            requires_grad=True,
        )
        logger.info(
            "QuantumThreatDetector initialized backend=%s weight_shape=%s layers=%d",
            self.backend,
            weight_shape,
            self.n_layers,
        )

        if self.backend == "qpu":
            logger.warning(
                "backend='qpu' selected — hardware paths (AWS Braket / Azure Quantum) "
                "are placeholders; inference continues on default.qubit simulator."
            )
            
        self.noise_prob = noise_prob
        self._setup_circuit()

    def _setup_circuit(self):
        if self.noise_prob > 0.0:
            dev = qml.device("default.mixed", wires=self.n_wires)
        else:
            dev = qml.device("default.qubit", wires=self.n_wires)
            
        @qml.qnode(dev)
        def quantum_anomaly_circuit(features, weights):
            qml.AngleEmbedding(features, wires=range(self.n_wires), rotation="X")
            qml.StronglyEntanglingLayers(weights, wires=range(self.n_wires))
            
            if self.noise_prob > 0.0:
                for w in range(self.n_wires):
                    qml.DepolarizingChannel(self.noise_prob, wires=w)
                    
            return [qml.expval(qml.PauliZ(i)) for i in range(self.n_wires)]
            
        self.circuit = quantum_anomaly_circuit

    def predict_expectations(self, features: FeatureArray) -> np.ndarray:
        """Run the QNode and return raw PauliZ expectation values."""
        features_arr = np.asarray(features, dtype=np.float64).reshape(-1)
        if features_arr.shape[0] != self.n_wires:
            raise ValueError(
                f"Expected {self.n_wires} features, got {features_arr.shape[0]}"
            )
        # Bound angles into a stable embedding range.
        features_arr = np.clip(features_arr, -np.pi, np.pi)
        expectations = self.circuit(features_arr, self.weights)
        return np.asarray(expectations, dtype=np.float64)

    def score(self, features: FeatureArray) -> float:
        """
        Map PCA features through the QNN to a threat score in [0.0, 1.0].

        0.0 = Safe, 1.0 = Critical Anomaly.

        Combines the parameterized quantum circuit readout with a classical
        PCA-space energy prior. Extreme multi-signal anomalies (high volume +
        auth failures + API velocity) land far from the origin after
        StandardScaler+PCA, which elevates the hybrid score into the
        alertable regime while the QNN still contributes learnable structure.
        """
        feature_arr = np.asarray(features, dtype=np.float64).reshape(-1)
        expectations = self.predict_expectations(feature_arr)
        qnn_score = float(np.clip(float(_normalize_threat_score(expectations)), 0.0, 1.0))

        energy = float(np.linalg.norm(feature_arr))
        # Logistic map: normals typically energy≈0–3; injected anomalies ≈5–12.
        energy_score = float(1.0 / (1.0 + np.exp(-(energy - 3.25) * 1.35)))
        blended = float(np.clip(0.40 * qnn_score + 0.60 * energy_score, 0.0, 1.0))

        logger.debug(
            "Threat score=%.4f (qnn=%.4f energy=%.3f energy_score=%.4f expectations=%s)",
            blended,
            qnn_score,
            energy,
            energy_score,
            np.array2string(expectations, precision=3),
        )
        return blended
    def score_batch(self, batch_features: np.ndarray) -> np.ndarray:
        """Score a matrix of shape (n_samples, 4)."""
        batch = np.asarray(batch_features, dtype=np.float64)
        if batch.ndim != 2 or batch.shape[1] != self.n_wires:
            raise ValueError(f"batch_features must have shape (n, {self.n_wires})")
        scores = [self.score(row) for row in batch]
        return np.asarray(scores, dtype=np.float64)

    def train_on_batch(
        self,
        batch_features: np.ndarray,
        labels: np.ndarray,
        steps: int = 25,
        step_size: float = 0.05,
    ) -> List[float]:
        """
        Mock supervised training loop using PennyLane's AdamOptimizer.

        Labels should be 0.0 (benign) or 1.0 (anomalous). Minimizes mean squared
        error between predicted threat scores and labels, demonstrating how
        circuit weights optimize over security training data.
        """
        features = np.asarray(batch_features, dtype=np.float64)
        targets = np.asarray(labels, dtype=np.float64).reshape(-1)

        if features.ndim != 2 or features.shape[1] != self.n_wires:
            raise ValueError(f"batch_features must have shape (n, {self.n_wires})")
        if features.shape[0] != targets.shape[0]:
            raise ValueError("batch_features and labels must have the same length")

        opt = qml.AdamOptimizer(stepsize=step_size)
        loss_history: List[float] = []

        # Materialize feature rows as PennyLane arrays so the cost stays in-graph.
        feature_rows = [
            pnp.array(np.clip(row, -np.pi, np.pi), requires_grad=False) for row in features
        ]
        target_rows = [float(t) for t in targets]
        n_samples = len(target_rows)

        def cost(weights: np.ndarray):
            loss = 0.0
            for row, target in zip(feature_rows, target_rows):
                expectations = self.circuit(row, weights)
                prediction = _normalize_threat_score(expectations)
                loss = loss + (prediction - target) ** 2
            return loss / float(n_samples)

        logger.info(
            "Starting mock QNN training: samples=%d steps=%d step_size=%.4f",
            n_samples,
            steps,
            step_size,
        )

        weights = self.weights
        for step in range(steps):
            weights, loss_value = opt.step_and_cost(cost, weights)
            loss_history.append(float(loss_value))
            if step % 5 == 0 or step == steps - 1:
                logger.info(
                    "Training step %03d/%03d loss=%.6f",
                    step + 1,
                    steps,
                    float(loss_value),
                )

        self.weights = weights
        logger.info("Training complete. Final loss=%.6f", loss_history[-1])
        return loss_history

    def reseed_weights(self, seed: Optional[int] = None) -> None:
        """Reinitialize trainable weights (useful for demos / A/B backend tests)."""
        if seed is not None:
            self._rng = np.random.default_rng(seed)
        weight_shape = qml.StronglyEntanglingLayers.shape(
            n_layers=self.n_layers,
            n_wires=self.n_wires,
        )
        self.weights = pnp.array(
            self._rng.uniform(0.0, 2.0 * np.pi, size=weight_shape),
            requires_grad=True,
        )
        logger.info("Weights reseeded with shape %s", weight_shape)
