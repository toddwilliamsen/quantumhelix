"""
Classical feature reduction pipeline for Quantum Helix.

Converts normalized CloudSecurityEvent objects into a scaled feature matrix,
compresses to exactly four principal components via PCA (matching the 4-qubit
AngleEmbedding width), and supports streaming single-event transforms without
re-fitting the scaler or PCA models.
"""

from __future__ import annotations

import logging
from typing import List, Optional, Sequence

import numpy as np
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler

from normalization import CloudSecurityEvent

logger = logging.getLogger(__name__)

# Fixed PCA dimensionality — must equal qubit count in quantum_engine.N_QUBITS.
N_PRINCIPAL_COMPONENTS = 4


class ClassicalFeaturePipeline:
    """
    StandardScaler + PCA(n_components=4) feature reduction for QNN input.

    Typical lifecycle:
      1. fit_transform(batch) during warmup / bootstrap
      2. transform_single(event) for each real-time telemetry record
    """

    def __init__(self, n_components: int = N_PRINCIPAL_COMPONENTS) -> None:
        if n_components != N_PRINCIPAL_COMPONENTS:
            logger.warning(
                "n_components=%d requested; QNN expects exactly %d PCA features",
                n_components,
                N_PRINCIPAL_COMPONENTS,
            )
        self.n_components = n_components
        self.scaler: StandardScaler = StandardScaler()
        self.pca: PCA = PCA(n_components=n_components)
        self._is_fitted: bool = False
        self._feature_dim: Optional[int] = None

    @property
    def is_fitted(self) -> bool:
        return self._is_fitted

    def _events_to_matrix(self, events: Sequence[CloudSecurityEvent]) -> np.ndarray:
        if not events:
            raise ValueError("Cannot build feature matrix from an empty event list")
        rows = [event.to_feature_vector() for event in events]
        matrix = np.asarray(rows, dtype=np.float64)
        if matrix.ndim != 2:
            raise ValueError(f"Expected 2D feature matrix, got shape {matrix.shape}")
        return matrix

    def fit_transform(self, events: List[CloudSecurityEvent]) -> np.ndarray:
        """
        Fit StandardScaler and PCA on the batch, then return the reduced matrix.

        PCA is forced to exactly ``self.n_components`` (default 4) principal
        components so outputs align with the 4-qubit AngleEmbedding circuit.
        """
        if len(events) < self.n_components:
            raise ValueError(
                f"Need at least {self.n_components} events to fit PCA; got {len(events)}"
            )

        matrix = self._events_to_matrix(events)
        self._feature_dim = matrix.shape[1]
        logger.info(
            "Fitting classical pipeline on %d events with raw feature dim=%d",
            len(events),
            self._feature_dim,
        )

        scaled = self.scaler.fit_transform(matrix)
        reduced = self.pca.fit_transform(scaled)
        self._is_fitted = True

        explained = float(np.sum(self.pca.explained_variance_ratio_))
        logger.info(
            "PCA fit complete: components=%d explained_variance_ratio_sum=%.4f",
            reduced.shape[1],
            explained,
        )
        return np.asarray(reduced, dtype=np.float64)

    def transform(self, events: Sequence[CloudSecurityEvent]) -> np.ndarray:
        """Transform a batch of events using already-fitted scaler and PCA."""
        self._ensure_fitted()
        matrix = self._events_to_matrix(events)
        scaled = self.scaler.transform(matrix)
        reduced = self.pca.transform(scaled)
        return np.asarray(reduced, dtype=np.float64)

    def transform_single(self, event: CloudSecurityEvent) -> np.ndarray:
        """
        Transform one real-time event into a length-4 PCA feature vector.

        Returns a 1-D NumPy array of shape (4,) without re-fitting models.
        """
        self._ensure_fitted()
        vector = np.asarray(event.to_feature_vector(), dtype=np.float64).reshape(1, -1)
        if self._feature_dim is not None and vector.shape[1] != self._feature_dim:
            raise ValueError(
                f"Event feature dim {vector.shape[1]} != fitted dim {self._feature_dim}"
            )
        scaled = self.scaler.transform(vector)
        reduced = self.pca.transform(scaled)
        features = np.asarray(reduced, dtype=np.float64).reshape(-1)
        if features.shape[0] != self.n_components:
            raise RuntimeError(
                f"PCA produced {features.shape[0]} components; expected {self.n_components}"
            )
        return features

    def _ensure_fitted(self) -> None:
        if not self._is_fitted:
            raise RuntimeError(
                "ClassicalFeaturePipeline is not fitted. Call fit_transform() first."
            )

    def explained_variance_ratio(self) -> np.ndarray:
        """Return per-component explained variance ratios after fitting."""
        self._ensure_fitted()
        return np.asarray(self.pca.explained_variance_ratio_, dtype=np.float64)
