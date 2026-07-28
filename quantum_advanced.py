"""
Advanced Quantum Machine Learning anomaly detectors.

Contains purely unsupervised and distance-based quantum approaches.
"""

from __future__ import annotations

import logging
from typing import List, Optional, Sequence, Union

import numpy as np
import pennylane as qml
from pennylane import numpy as pnp

logger = logging.getLogger(__name__)

FeatureArray = Union[np.ndarray, Sequence[float]]

# ---------------------------------------------------------------------------
# Quantum Autoencoder
# ---------------------------------------------------------------------------

class QuantumAutoencoderDetector:
    """
    Unsupervised Quantum Autoencoder for anomaly detection.
    
    Compresses N-qubit features into a bottleneck. By training on normal data
    to maximize the probability of measuring |0> on the 'trash' qubits, the
    network learns the normal distribution. Anomalies fail to compress and
    result in a higher probability of measuring |1> on the trash qubits.
    """
    def __init__(self, n_wires: int = 4, n_trash: int = 2, layers: int = 3, seed: int = 42):
        self.n_wires = n_wires
        self.n_trash = n_trash
        self.n_latent = n_wires - n_trash
        self.layers = layers
        self._rng = np.random.default_rng(seed)
        
        weight_shape = qml.StronglyEntanglingLayers.shape(n_layers=self.layers, n_wires=self.n_wires)
        self.weights = pnp.array(self._rng.uniform(0.0, 2.0 * np.pi, size=weight_shape), requires_grad=True)
        
        self.dev = qml.device("default.qubit", wires=self.n_wires)
        
        @qml.qnode(self.dev)
        def _autoencoder_circuit(features, weights):
            # Encode classical data
            qml.AngleEmbedding(features, wires=range(self.n_wires), rotation="X")
            # Apply parameterized compression
            qml.StronglyEntanglingLayers(weights, wires=range(self.n_wires))
            # Return probabilities of the trash qubits
            trash_wires = range(self.n_latent, self.n_wires)
            return qml.probs(wires=trash_wires)
            
        self.circuit = _autoencoder_circuit

    def score(self, features: FeatureArray) -> float:
        """Score a single feature vector. 0.0 = Normal, 1.0 = Anomaly."""
        arr = np.asarray(features, dtype=np.float64).reshape(-1)
        arr = np.clip(arr, -np.pi, np.pi)
        
        probs = self.circuit(arr, self.weights)
        # probs[0] is the probability of measuring |0...0> on the trash qubits.
        # High prob = normal, low prob = anomaly.
        fidelity = float(np.real(probs[0]))
        return float(np.clip(1.0 - fidelity, 0.0, 1.0))
        
    def score_batch(self, batch_features: np.ndarray) -> np.ndarray:
        return np.array([self.score(row) for row in batch_features], dtype=np.float64)

    def train_on_batch(self, features: np.ndarray, steps: int = 20, step_size: float = 0.05) -> List[float]:
        """Train the autoencoder on mostly normal data to minimize compression loss."""
        data = np.asarray(features, dtype=np.float64)
        if data.ndim != 2 or data.shape[1] != self.n_wires:
            raise ValueError(f"features must have shape (n, {self.n_wires})")
            
        opt = qml.AdamOptimizer(stepsize=step_size)
        loss_history = []
        
        feature_rows = [
            pnp.array(np.clip(row, -np.pi, np.pi), requires_grad=False) for row in data
        ]
        
        def cost(weights):
            loss = 0.0
            for row in feature_rows:
                probs = self.circuit(row, weights)
                # Minimize 1 - prob(|0...0>)
                loss += (1.0 - probs[0])
            return loss / len(feature_rows)
            
        logger.info("Starting Autoencoder training: samples=%d steps=%d", len(data), steps)
        
        w = self.weights
        for step in range(steps):
            w, loss_val = opt.step_and_cost(cost, w)
            loss_history.append(float(loss_val))
            if step % 5 == 0 or step == steps - 1:
                logger.info("Autoencoder step %03d loss=%.6f", step + 1, float(loss_val))
                
        self.weights = w
        return loss_history

# ---------------------------------------------------------------------------
# Quantum SWAP Test Anomaly Detector
# ---------------------------------------------------------------------------

class SwapTestAnomalyDetector:
    """
    Measures the distance from a new event to a baseline average profile
    using a quantum SWAP test circuit.
    """
    def __init__(self, n_features: int = 4):
        self.n_features = n_features
        # 1 ancilla + 2 * n_features
        self.total_wires = 1 + 2 * self.n_features
        self.dev = qml.device("default.qubit", wires=self.total_wires)
        self.baseline_features: Optional[np.ndarray] = None
        
        @qml.qnode(self.dev)
        def _swap_test_circuit(state_a, state_b):
            ancilla = 0
            wires_a = range(1, 1 + self.n_features)
            wires_b = range(1 + self.n_features, self.total_wires)
            
            # Encode states
            qml.AngleEmbedding(state_a, wires=wires_a, rotation="X")
            qml.AngleEmbedding(state_b, wires=wires_b, rotation="X")
            
            # SWAP test
            qml.Hadamard(wires=ancilla)
            for wa, wb in zip(wires_a, wires_b):
                qml.CSWAP(wires=[ancilla, wa, wb])
            qml.Hadamard(wires=ancilla)
            
            return qml.probs(wires=ancilla)
            
        self.circuit = _swap_test_circuit
        
    def fit(self, features: np.ndarray, labels: Optional[np.ndarray] = None) -> None:
        """
        Fit the baseline by taking the mean of the normal features.
        If labels are provided, only use label 0 (normal).
        """
        data = np.asarray(features, dtype=np.float64)
        if labels is not None:
            normal_mask = np.asarray(labels) == 0.0
            if np.any(normal_mask):
                data = data[normal_mask]
        
        self.baseline_features = np.clip(np.mean(data, axis=0), -np.pi, np.pi)
        logger.info("SWAP test detector fitted baseline vector")
        
    def score(self, features: FeatureArray) -> float:
        if self.baseline_features is None:
            raise RuntimeError("SwapTestAnomalyDetector is not fitted")
            
        arr = np.asarray(features, dtype=np.float64).reshape(-1)
        arr = np.clip(arr, -np.pi, np.pi)
        
        probs = self.circuit(self.baseline_features, arr)
        # prob(|0>) = 0.5 + 0.5 * |<A|B>|^2
        # |<A|B>|^2 = 2 * prob(|0>) - 1
        overlap = 2.0 * float(probs[0]) - 1.0
        overlap = np.clip(overlap, 0.0, 1.0)
        
        # 0 distance = 1 overlap -> score 0
        # High distance = 0 overlap -> score 1
        return float(1.0 - overlap)

    def score_batch(self, batch_features: np.ndarray) -> np.ndarray:
        return np.array([self.score(row) for row in batch_features], dtype=np.float64)
