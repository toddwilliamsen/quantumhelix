"""
Classical control-group anomaly detectors for Quantum Helix.

These models establish the performance / cost baseline that any quantum
component must beat (or usefully complement) to move beyond novelty.

Engines:
  - IsolationForestDetector — unsupervised, fast streaming baseline
  - ClassicalSVMDetector — supervised RBF SVM on PCA feature vectors
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import List, Optional, Sequence, Union

import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.svm import SVC

logger = logging.getLogger(__name__)

FeatureMatrix = Union[np.ndarray, Sequence[Sequence[float]]]


@dataclass
class FitStats:
    engine: str
    n_samples: int
    fit_seconds: float


def _as_2d(features: FeatureMatrix) -> np.ndarray:
    arr = np.asarray(features, dtype=np.float64)
    if arr.ndim == 1:
        arr = arr.reshape(1, -1)
    if arr.ndim != 2:
        raise ValueError(f"Expected 2D feature matrix, got shape {arr.shape}")
    return arr


def _normalize_scores(raw: np.ndarray, *, higher_is_threat: bool = True) -> np.ndarray:
    """Map model outputs to threat scores in [0, 1]."""
    values = np.asarray(raw, dtype=np.float64).reshape(-1)
    if values.size == 0:
        return values
    if not higher_is_threat:
        values = -values
    lo = float(np.min(values))
    hi = float(np.max(values))
    if hi - lo < 1e-12:
        return np.clip(values * 0.0 + 0.5, 0.0, 1.0)
    return np.clip((values - lo) / (hi - lo), 0.0, 1.0)


class IsolationForestDetector:
    """
    Unsupervised classical baseline.

    Fit primarily on benign traffic. Higher score ⇒ more anomalous.
    """

    def __init__(
        self,
        n_estimators: int = 200,
        contamination: float = 0.05,
        seed: int = 42,
    ) -> None:
        self.model = IsolationForest(
            n_estimators=n_estimators,
            contamination=contamination,
            random_state=seed,
            n_jobs=-1,
        )
        self._is_fitted = False
        self._score_lo: float = 0.0
        self._score_hi: float = 1.0
        self.last_fit: Optional[FitStats] = None

    @property
    def is_fitted(self) -> bool:
        return self._is_fitted

    def fit(self, features: FeatureMatrix, labels: Optional[np.ndarray] = None) -> FitStats:
        """
        Fit the forest.

        If ``labels`` are provided, prefer fitting on benign rows (label == 0)
        when enough benign samples exist — mirrors SOC baseline modeling.
        """
        matrix = _as_2d(features)
        train = matrix
        if labels is not None:
            y = np.asarray(labels, dtype=np.float64).reshape(-1)
            benign = matrix[y < 0.5]
            if len(benign) >= max(8, matrix.shape[1] * 2):
                train = benign
                logger.info(
                    "IsolationForest fitting on %d benign rows (of %d)",
                    len(train),
                    len(matrix),
                )
        started = time.perf_counter()
        self.model.fit(train)
        # decision_function: larger ⇒ more normal; we invert for threat.
        raw = -self.model.decision_function(train)
        self._score_lo = float(np.min(raw))
        self._score_hi = float(np.max(raw))
        if self._score_hi - self._score_lo < 1e-12:
            self._score_hi = self._score_lo + 1.0
        self._is_fitted = True
        stats = FitStats(
            engine="isolation_forest",
            n_samples=len(train),
            fit_seconds=time.perf_counter() - started,
        )
        self.last_fit = stats
        logger.info("IsolationForest fitted in %.4fs on %d samples", stats.fit_seconds, stats.n_samples)
        return stats

    def score(self, features: FeatureMatrix) -> float:
        return float(self.score_batch(features)[0])

    def score_batch(self, features: FeatureMatrix) -> np.ndarray:
        if not self._is_fitted:
            raise RuntimeError("IsolationForestDetector is not fitted")
        matrix = _as_2d(features)
        raw = -self.model.decision_function(matrix)
        return np.clip((raw - self._score_lo) / (self._score_hi - self._score_lo), 0.0, 1.0)


class ClassicalSVMDetector:
    """
    Supervised classical RBF-SVM control group on PCA feature vectors.
    """

    def __init__(self, seed: int = 42, c: float = 2.0, gamma: Union[str, float] = "scale") -> None:
        self.model = SVC(
            kernel="rbf",
            C=c,
            gamma=gamma,
            class_weight="balanced",
            random_state=seed,
        )
        self._is_fitted = False
        self.last_fit: Optional[FitStats] = None
        self._decision_lo: float = -1.0
        self._decision_hi: float = 1.0

    @property
    def is_fitted(self) -> bool:
        return self._is_fitted

    def fit(self, features: FeatureMatrix, labels: np.ndarray) -> FitStats:
        matrix = _as_2d(features)
        y = np.asarray(labels, dtype=np.float64).reshape(-1)
        if matrix.shape[0] != y.shape[0]:
            raise ValueError("features and labels length mismatch")
        if len(np.unique(y)) < 2:
            raise ValueError("ClassicalSVMDetector requires both benign and attack labels")
        started = time.perf_counter()
        self.model.fit(matrix, y.astype(int))
        train_dec = self.model.decision_function(matrix)
        self._decision_lo = float(np.min(train_dec))
        self._decision_hi = float(np.max(train_dec))
        if self._decision_hi - self._decision_lo < 1e-12:
            self._decision_hi = self._decision_lo + 1.0
        self._is_fitted = True
        stats = FitStats(
            engine="classical_svm",
            n_samples=len(matrix),
            fit_seconds=time.perf_counter() - started,
        )
        self.last_fit = stats
        logger.info("Classical SVM fitted in %.4fs on %d samples", stats.fit_seconds, stats.n_samples)
        return stats

    def score(self, features: FeatureMatrix) -> float:
        return float(self.score_batch(features)[0])

    def score_batch(self, features: FeatureMatrix) -> np.ndarray:
        if not self._is_fitted:
            raise RuntimeError("ClassicalSVMDetector is not fitted")
        matrix = _as_2d(features)
        decision = self.model.decision_function(matrix)
        return np.clip(
            (decision - self._decision_lo) / (self._decision_hi - self._decision_lo),
            0.0,
            1.0,
        )
