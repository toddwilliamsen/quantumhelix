"""
Subtle APT-style and loud attack corpora for PoC+ benchmarking.

Loud attacks are high-signal (easy for any model). Subtle APT sequences are
low-and-slow / multi-signal weak anomalies designed to stress classical vs
quantum-kernel separation on PCA features.
"""

from __future__ import annotations

import random
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from normalization import CloudSecurityEvent, MultiCloudLogParser, collect_mock_events


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _ip(rng: random.Random, suspicious: bool = False) -> str:
    if suspicious:
        return f"203.0.113.{rng.randint(1, 254)}"
    return (
        f"{rng.randint(10, 180)}.{rng.randint(0, 255)}."
        f"{rng.randint(0, 255)}.{rng.randint(1, 254)}"
    )


def make_normal_events(n: int = 80, seed: int = 7) -> List[CloudSecurityEvent]:
    """Mostly clean multi-cloud baseline traffic."""
    parser = MultiCloudLogParser()
    rng = random.Random(seed)
    events: List[CloudSecurityEvent] = []
    for i in range(n):
        vel = rng.uniform(1.0, 14.0)
        auth = 0.0 if rng.random() > 0.1 else rng.uniform(0.0, 1.0)
        volume = rng.uniform(5e3, 2.5e6)
        if i % 2 == 0:
            raw = {
                "eventID": f"bench-aws-n-{i:04d}",
                "eventTime": _utc_now(),
                "sourceIPAddress": _ip(rng),
                "userIdentity": {
                    "arn": f"arn:aws:iam::123456789012:user/ops-{i % 12}",
                    "userName": f"ops-{i % 12}",
                },
                "additionalEventData": {"bytesTransferred": volume},
                "apiVelocity": vel,
                "authFailureCount": auth,
                "requestParameters": {"bucketName": "corp-logs"},
            }
            events.append(parser.parse_aws(raw))
        else:
            raw = {
                "correlationId": f"bench-az-n-{i:04d}",
                "time": _utc_now(),
                "claims": {"name": f"ops-{i % 12}@corp.local"},
                "srcIP_s": _ip(rng),
                "bytesOut_d": volume,
                "apiVelocity": vel,
                "authFailureCount": auth,
                "ResultType": "Success",
                "Level": "Informational",
                "properties": {"statusCode": "200"},
            }
            events.append(parser.parse_azure(raw))
    return events


def make_loud_attacks(n: int = 8, seed: int = 99) -> List[CloudSecurityEvent]:
    """High-signal exfil / credential stuffing — classical models should catch these."""
    parser = MultiCloudLogParser()
    rng = random.Random(seed)
    events: List[CloudSecurityEvent] = []
    for i in range(n):
        if i % 2 == 0:
            raw = {
                "eventID": f"bench-aws-loud-{i:04d}",
                "eventTime": _utc_now(),
                "sourceIPAddress": _ip(rng, suspicious=True),
                "userIdentity": {
                    "arn": f"arn:aws:iam::123456789012:user/compromised-{i}",
                    "userName": f"compromised-{i}",
                },
                "additionalEventData": {"bytesTransferred": rng.uniform(8e8, 2e9)},
                "apiVelocity": rng.uniform(95.0, 130.0),
                "authFailureCount": rng.uniform(20.0, 40.0),
                "errorCode": "AccessDenied",
                "requestParameters": {"bucketName": "pii-export"},
            }
            events.append(parser.parse_aws(raw))
        else:
            raw = {
                "correlationId": f"bench-az-loud-{i:04d}",
                "time": _utc_now(),
                "claims": {"name": f"attacker-{i}@corp.local"},
                "srcIP_s": _ip(rng, suspicious=True),
                "bytesOut_d": rng.uniform(6e8, 2e9),
                "apiVelocity": rng.uniform(90.0, 125.0),
                "authFailureCount": rng.uniform(18.0, 38.0),
                "ResultType": "Failed",
                "Level": "Error",
                "operationName": "Microsoft.Authorization/roleAssignments/write",
                "properties": {"statusCode": "403"},
            }
            events.append(parser.parse_azure(raw))
    return events


def make_subtle_apt_events(n: int = 12, seed: int = 123) -> List[CloudSecurityEvent]:
    """
    Low-and-slow APT-style events.

    Individually near-baseline on single features, but jointly odd in feature
    space (moderate velocity + intermittent auth friction + elevated-but-not-
    grotesque egress + suspicious spatial IP). Harder for shallow thresholds;
    useful for classical vs quantum-kernel comparison.
    """
    parser = MultiCloudLogParser()
    rng = random.Random(seed)
    events: List[CloudSecurityEvent] = []
    for i in range(n):
        # Stay below "loud" thresholds used by weak labelers, above quiet baseline.
        vel = rng.uniform(28.0, 48.0)
        auth = rng.uniform(3.0, 9.0)
        volume = rng.uniform(2.5e7, 9.5e7)
        use_aws = i % 2 == 0
        if use_aws:
            raw = {
                "eventID": f"bench-aws-apt-{i:04d}",
                "eventTime": _utc_now(),
                "sourceIPAddress": _ip(rng, suspicious=True),
                "userIdentity": {
                    "arn": f"arn:aws:iam::123456789012:user/svc-shadow-{i % 4}",
                    "userName": f"svc-shadow-{i % 4}",
                },
                "additionalEventData": {"bytesTransferred": volume},
                "apiVelocity": vel,
                "authFailureCount": auth,
                "requestParameters": {
                    "bucketName": "corp-analytics",
                    "key": f"batch/part-{i}.parquet",
                },
            }
            events.append(parser.parse_aws(raw))
        else:
            raw = {
                "correlationId": f"bench-az-apt-{i:04d}",
                "time": _utc_now(),
                "claims": {"name": f"svc-shadow-{i % 4}@corp.local"},
                "srcIP_s": _ip(rng, suspicious=True),
                "bytesOut_d": volume,
                "apiVelocity": vel,
                "authFailureCount": auth,
                "ResultType": "Success",
                "Level": "Warning",
                "operationName": "Microsoft.Storage/storageAccounts/listKeys/action",
                "properties": {"statusCode": "200", "slowExfil": True},
            }
            events.append(parser.parse_azure(raw))
    return events


def label_events(events: List[CloudSecurityEvent], *, attack: bool) -> List[float]:
    return [1.0 if attack else 0.0 for _ in events]


def build_benchmark_corpus(
    *,
    n_normal: int = 100,
    n_loud: int = 10,
    n_subtle: int = 14,
    seed: int = 42,
) -> Tuple[List[CloudSecurityEvent], np.ndarray, np.ndarray]:
    """
    Return events, binary labels, and subtle-mask (1 if subtle APT, else 0).

    Labels: 0 = benign, 1 = attack (loud or subtle).
    """
    import numpy as np

    normals = make_normal_events(n_normal, seed=seed)
    loud = make_loud_attacks(n_loud, seed=seed + 1)
    subtle = make_subtle_apt_events(n_subtle, seed=seed + 2)
    events = normals + loud + subtle
    labels = np.asarray(
        [0.0] * len(normals) + [1.0] * len(loud) + [1.0] * len(subtle),
        dtype=np.float64,
    )
    subtle_mask = np.asarray(
        [0.0] * len(normals) + [0.0] * len(loud) + [1.0] * len(subtle),
        dtype=np.float64,
    )
    return events, labels, subtle_mask


def weak_loud_labels(events: List[CloudSecurityEvent]) -> "np.ndarray":
    """Heuristic labels matching the original mock anomaly signature."""
    import numpy as np

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


# Late import typing for numpy without circular noise at module import for helpers above
import numpy as np  # noqa: E402
