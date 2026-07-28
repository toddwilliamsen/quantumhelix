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
from sklearn.linear_model import LogisticRegression
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


def _sigmoid_from_train(raw: np.ndarray, train_raw: np.ndarray) -> np.ndarray:
    """Soft map using training mean/std — no hard clip saturation."""
    mid = float(np.median(train_raw))
    scale = float(np.std(train_raw))
    if scale < 1e-8:
        scale = 1.0
    return 1.0 / (1.0 + np.exp(-(np.asarray(raw, dtype=np.float64) - mid) / scale))


def _fit_platt(decisions: np.ndarray, labels: np.ndarray) -> LogisticRegression:
    """1-D Platt calibrator: maps decision_function → P(attack)."""
    x = np.asarray(decisions, dtype=np.float64).reshape(-1, 1)
    y = np.asarray(labels, dtype=int).reshape(-1)
    cal = LogisticRegression(max_iter=200)
    cal.fit(x, y)
    return cal


def _calibrate_holdout(
    model: SVC,
    features: np.ndarray,
    labels: np.ndarray,
    *,
    seed: int = 42,
    min_samples: int = 24,
) -> LogisticRegression:
    """Fit SVM then Platt-calibrate on a held-out slice (avoids train-set leakage).

    When too few samples are available, falls back to in-sample calibration and
    logs a warning — callers should prefer larger corpuses for credible probs.
    """
    y = np.asarray(labels, dtype=int).reshape(-1)
    if len(features) < min_samples or len(np.unique(y)) < 2:
        model.fit(features, y)
        logger.warning(
            "Platt calibration used in-sample decisions (n=%d < %d); probabilities may be overconfident",
            len(features),
            min_samples,
        )
        return _fit_platt(model.decision_function(features), y)

    from sklearn.model_selection import train_test_split

    try:
        x_fit, x_cal, y_fit, y_cal = train_test_split(
            features, y, test_size=0.25, random_state=seed, stratify=y
        )
    except ValueError:
        x_fit, x_cal, y_fit, y_cal = train_test_split(
            features, y, test_size=0.25, random_state=seed
        )
    if len(np.unique(y_fit)) < 2 or len(np.unique(y_cal)) < 2:
        model.fit(features, y)
        logger.warning("Platt calibration fell back to in-sample (class imbalance on split)")
        return _fit_platt(model.decision_function(features), y)

    model.fit(x_fit, y_fit)
    return _fit_platt(model.decision_function(x_cal), y_cal)


def _apply_platt(calibrator: LogisticRegression, decisions: np.ndarray) -> np.ndarray:
    x = np.asarray(decisions, dtype=np.float64).reshape(-1, 1)
    # Class 1 = attack
    classes = list(calibrator.classes_)
    attack_idx = classes.index(1) if 1 in classes else -1
    return calibrator.predict_proba(x)[:, attack_idx]


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
        self._train_raw: Optional[np.ndarray] = None
        self.last_fit: Optional[FitStats] = None

    @property
    def is_fitted(self) -> bool:
        return self._is_fitted

    def fit(self, features: FeatureMatrix, labels: Optional[np.ndarray] = None) -> FitStats:
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
        self._train_raw = -self.model.decision_function(train)
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
        if not self._is_fitted or self._train_raw is None:
            raise RuntimeError("IsolationForestDetector is not fitted")
        matrix = _as_2d(features)
        raw = -self.model.decision_function(matrix)
        return _sigmoid_from_train(raw, self._train_raw)


class ClassicalSVMDetector:
    """
    Supervised classical RBF-SVM control group on PCA feature vectors.
    Scores are Platt-calibrated attack probabilities.
    """

    def __init__(self, seed: int = 42, c: float = 2.0, gamma: Union[str, float] = "scale") -> None:
        self.model = SVC(
            kernel="rbf",
            C=c,
            gamma=gamma,
            class_weight="balanced",
            random_state=seed,
        )
        self._calibrator: Optional[LogisticRegression] = None
        self._is_fitted = False
        self.last_fit: Optional[FitStats] = None

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
        self._calibrator = _calibrate_holdout(self.model, matrix, y, seed=getattr(self.model, "random_state", 42) or 42)
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
        if not self._is_fitted or self._calibrator is None:
            raise RuntimeError("ClassicalSVMDetector is not fitted")
        matrix = _as_2d(features)
        decision = self.model.decision_function(matrix)
        return _apply_platt(self._calibrator, decision)
