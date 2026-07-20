"""
Multi-cloud Common Information Model (CIM) and normalization engine.

Maps AWS CloudTrail / VPC Flow Log style records and Azure Activity / NSG Flow
Log style records into a single CloudSecurityEvent schema consumed by the
classical PCA pipeline and Quantum Neural Network anomaly detector.
"""

from __future__ import annotations

import logging
import random
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Generator, Iterator, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class CloudSecurityEvent:
    """Normalized multi-cloud security telemetry (Common Information Model)."""

    timestamp: str
    normalized_identity: str
    source_ip: str
    api_velocity: float
    auth_failures: float
    data_volume_bytes: float
    cloud_provider: str = "unknown"
    raw_event_id: str = ""

    def to_feature_vector(self) -> List[float]:
        """Return the four numeric CIM features used by classical reduction."""
        return [
            float(self.api_velocity),
            float(self.auth_failures),
            float(self.data_volume_bytes),
            _ip_octet_hash(self.source_ip),
        ]

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the event for alerting and UI display."""
        return asdict(self)


def _ip_octet_hash(ip: str) -> float:
    """Derive a stable numeric feature from an IPv4 address string."""
    try:
        parts = [int(p) for p in ip.split(".")]
        if len(parts) != 4:
            return 0.0
        return float(parts[0] * 256**3 + parts[1] * 256**2 + parts[2] * 256 + parts[3])
    except (ValueError, AttributeError):
        return 0.0


def _safe_get(mapping: Dict[str, Any], *keys: str, default: Any = None) -> Any:
    """Walk nested dict keys; return default if any hop is missing."""
    current: Any = mapping
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current


class MultiCloudLogParser:
    """Parse raw AWS and Azure JSON security logs into CloudSecurityEvent objects."""

    def parse_aws(self, raw_json: Dict[str, Any]) -> CloudSecurityEvent:
        """
        Map AWS CloudTrail / VPC Flow Log style fields to the CIM.

        Expected fields (with graceful fallbacks):
          - userIdentity.arn
          - sourceIPAddress
          - additionalEventData.bytesTransferred
          - eventTime
          - eventName / eventID (for velocity proxy and identity)
        """
        identity = _safe_get(raw_json, "userIdentity", "arn", default="")
        if not identity:
            identity = _safe_get(raw_json, "userIdentity", "userName", default="aws:unknown")

        source_ip = str(raw_json.get("sourceIPAddress", "0.0.0.0"))
        bytes_transferred = float(
            _safe_get(raw_json, "additionalEventData", "bytesTransferred", default=0) or 0
        )
        auth_failures = float(raw_json.get("authFailureCount", 0) or 0)
        api_velocity = float(raw_json.get("apiVelocity", 0) or 0)
        if api_velocity == 0.0:
            # Derive a lightweight velocity proxy from requestParameters when absent.
            request_params = raw_json.get("requestParameters") or {}
            api_velocity = float(len(request_params) * 2 + int(raw_json.get("errorCode") is not None))

        timestamp = str(raw_json.get("eventTime", _utc_now_iso()))
        event_id = str(raw_json.get("eventID", raw_json.get("eventId", "")))

        event = CloudSecurityEvent(
            timestamp=timestamp,
            normalized_identity=str(identity),
            source_ip=source_ip,
            api_velocity=api_velocity,
            auth_failures=auth_failures,
            data_volume_bytes=bytes_transferred,
            cloud_provider="AWS",
            raw_event_id=event_id,
        )
        logger.debug("Parsed AWS event id=%s identity=%s", event_id, identity)
        return event

    def parse_azure(self, raw_json: Dict[str, Any]) -> CloudSecurityEvent:
        """
        Map Azure Activity Log / NSG Flow Log style fields to the CIM.

        Expected fields (with graceful fallbacks):
          - claims.name
          - srcIP_s
          - bytesOut_d
          - time / TimeGenerated
          - operationName (activity context)
        """
        identity = _safe_get(raw_json, "claims", "name", default="")
        if not identity:
            identity = str(raw_json.get("caller", raw_json.get("Caller", "azure:unknown")))

        source_ip = str(raw_json.get("srcIP_s", raw_json.get("callerIpAddress", "0.0.0.0")))
        bytes_out = float(raw_json.get("bytesOut_d", raw_json.get("bytesOut", 0)) or 0)
        auth_failures = float(raw_json.get("authFailureCount", 0) or 0)
        if auth_failures == 0.0 and isinstance(raw_json.get("ResultType"), str):
            # Fall back to ResultType only when an explicit failure count is absent.
            result = str(raw_json.get("ResultType", "")).lower()
            auth_failures = 1.0 if result in {"failed", "failure", "unauthorized"} else 0.0

        api_velocity = float(raw_json.get("apiVelocity", 0) or 0)
        if api_velocity == 0.0:
            properties = raw_json.get("properties") or {}
            api_velocity = float(len(properties) * 2 + int(bool(raw_json.get("Level") == "Error")))

        timestamp = str(
            raw_json.get("time")
            or raw_json.get("TimeGenerated")
            or raw_json.get("eventTimestamp")
            or _utc_now_iso()
        )
        event_id = str(raw_json.get("correlationId", raw_json.get("id", "")))

        event = CloudSecurityEvent(
            timestamp=timestamp,
            normalized_identity=str(identity),
            source_ip=source_ip,
            api_velocity=api_velocity,
            auth_failures=float(auth_failures),
            data_volume_bytes=bytes_out,
            cloud_provider="Azure",
            raw_event_id=event_id,
        )
        logger.debug("Parsed Azure event id=%s identity=%s", event_id, identity)
        return event

    def parse_gcp(self, raw_json: Dict[str, Any]) -> CloudSecurityEvent:
        """
        Map GCP Cloud Audit Logs style fields to the CIM.
        """
        identity = _safe_get(raw_json, "protoPayload", "authenticationInfo", "principalEmail", default="")
        if not identity:
            identity = str(raw_json.get("principalEmail", "gcp:unknown"))

        source_ip = _safe_get(raw_json, "protoPayload", "requestMetadata", "callerIp", default="0.0.0.0")
        
        bytes_out = float(raw_json.get("bytesOut", 0))
        auth_failures = float(raw_json.get("authFailureCount", 0))
        api_velocity = float(raw_json.get("apiVelocity", 0))

        timestamp = str(raw_json.get("timestamp", _utc_now_iso()))
        event_id = str(raw_json.get("insertId", ""))

        event = CloudSecurityEvent(
            timestamp=timestamp,
            normalized_identity=str(identity),
            source_ip=source_ip,
            api_velocity=api_velocity,
            auth_failures=auth_failures,
            data_volume_bytes=bytes_out,
            cloud_provider="GCP",
            raw_event_id=event_id,
        )
        logger.debug("Parsed GCP event id=%s identity=%s", event_id, identity)
        return event


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _random_ip(rng: random.Random) -> str:
    return f"{rng.randint(1, 223)}.{rng.randint(0, 255)}.{rng.randint(0, 255)}.{rng.randint(1, 254)}"


def _build_aws_record(
    rng: random.Random,
    *,
    anomalous: bool,
    index: int,
) -> Dict[str, Any]:
    """Construct a synthetic AWS CloudTrail-like JSON record."""
    if anomalous:
        api_velocity = rng.uniform(85.0, 120.0)
        auth_failures = rng.uniform(12.0, 40.0)
        bytes_transferred = rng.uniform(5e8, 2e9)
        identity = f"arn:aws:iam::123456789012:user/svc-shadow-{index}"
    else:
        api_velocity = rng.uniform(1.0, 25.0)
        auth_failures = rng.uniform(0.0, 2.0)
        bytes_transferred = rng.uniform(1e3, 5e6)
        identity = f"arn:aws:iam::123456789012:user/svc-account-{rng.randint(1, 20)}"

    return {
        "eventVersion": "1.08",
        "eventID": f"aws-evt-{index:06d}",
        "eventTime": _utc_now_iso(),
        "eventSource": "s3.amazonaws.com",
        "eventName": "GetObject" if not anomalous else "DeleteBucket",
        "awsRegion": rng.choice(["us-east-1", "us-west-2", "eu-west-1"]),
        "sourceIPAddress": _random_ip(rng),
        "userIdentity": {
            "type": "IAMUser",
            "arn": identity,
            "userName": identity.split("/")[-1],
        },
        "additionalEventData": {
            "bytesTransferred": bytes_transferred,
        },
        "requestParameters": {
            "bucketName": f"corp-data-{rng.randint(1, 5)}",
            "key": f"objects/file-{rng.randint(1, 1000)}.bin",
        },
        "apiVelocity": api_velocity,
        "authFailureCount": auth_failures,
        "errorCode": "AccessDenied" if anomalous and auth_failures > 15 else None,
    }


def _build_azure_record(
    rng: random.Random,
    *,
    anomalous: bool,
    index: int,
) -> Dict[str, Any]:
    """Construct a synthetic Azure Activity / NSG Flow Log-like JSON record."""
    if anomalous:
        api_velocity = rng.uniform(90.0, 130.0)
        auth_failures = rng.uniform(15.0, 45.0)
        bytes_out = rng.uniform(6e8, 2.5e9)
        identity = f"svc-shadow-{index}@corp.local"
    else:
        api_velocity = rng.uniform(1.0, 22.0)
        auth_failures = rng.uniform(0.0, 1.5)
        bytes_out = rng.uniform(2e3, 4e6)
        identity = f"ops-user-{rng.randint(1, 25)}@corp.local"

    return {
        "id": f"/subscriptions/00000000-0000-0000-0000-000000000000/events/azure-evt-{index:06d}",
        "correlationId": f"azure-corr-{index:06d}",
        "time": _utc_now_iso(),
        "TimeGenerated": _utc_now_iso(),
        "operationName": "Microsoft.Storage/storageAccounts/listKeys/action"
        if anomalous
        else "Microsoft.Compute/virtualMachines/read",
        "Level": "Error" if anomalous else "Informational",
        "ResultType": "Failed" if anomalous else "Success",
        "caller": identity,
        "claims": {"name": identity},
        "srcIP_s": _random_ip(rng),
        "bytesOut_d": bytes_out,
        "apiVelocity": api_velocity,
        "authFailureCount": auth_failures,
        "properties": {
            "resource": f"/subscriptions/0000/resourceGroups/rg-{rng.randint(1, 8)}",
            "statusCode": "403" if anomalous else "200",
        },
    }


def _build_gcp_record(
    rng: random.Random,
    *,
    anomalous: bool,
    index: int,
) -> Dict[str, Any]:
    """Construct a synthetic GCP Cloud Audit Log-like JSON record."""
    if anomalous:
        api_velocity = rng.uniform(80.0, 115.0)
        auth_failures = rng.uniform(10.0, 35.0)
        bytes_out = rng.uniform(4e8, 1.8e9)
        identity = f"svc-shadow-{index}@gcp-project.iam.gserviceaccount.com"
    else:
        api_velocity = rng.uniform(1.0, 20.0)
        auth_failures = rng.uniform(0.0, 1.0)
        bytes_out = rng.uniform(1e3, 3e6)
        identity = f"dev-user-{rng.randint(1, 15)}@gcp-project.iam.gserviceaccount.com"

    return {
        "insertId": f"gcp-evt-{index:06d}",
        "timestamp": _utc_now_iso(),
        "resource": {
            "type": "gce_instance",
            "labels": {"instance_id": f"{rng.randint(1000, 9999)}"}
        },
        "protoPayload": {
            "authenticationInfo": {
                "principalEmail": identity
            },
            "requestMetadata": {
                "callerIp": _random_ip(rng)
            },
            "methodName": "v1.compute.instances.insert" if anomalous else "v1.compute.instances.get"
        },
        "bytesOut": bytes_out,
        "apiVelocity": api_velocity,
        "authFailureCount": auth_failures
    }


def generate_mock_stream(
    num_events: int = 100,
    seed: Optional[int] = 42,
    anomaly_rate: float = 0.05,
) -> Generator[CloudSecurityEvent, None, None]:
    """
    Yield a continuous mixed stream of AWS and Azure normalized events.

    Approximately ``anomaly_rate`` (default 5%) of events are hardcoded with
    highly correlated anomalies: massive data volume, elevated authentication
    failures, and unusual API velocity — suitable for QNN detector evaluation.
    """
    if num_events < 1:
        raise ValueError("num_events must be >= 1")

    rng = random.Random(seed)
    parser = MultiCloudLogParser()
    anomaly_indices = set()
    target_anomalies = max(1, int(round(num_events * anomaly_rate)))
    while len(anomaly_indices) < target_anomalies and len(anomaly_indices) < num_events:
        anomaly_indices.add(rng.randint(0, num_events - 1))

    logger.info(
        "Generating mock multi-cloud stream: events=%d anomalies=%d rate=%.2f",
        num_events,
        len(anomaly_indices),
        anomaly_rate,
    )

    for index in range(num_events):
        anomalous = index in anomaly_indices
        cloud_choice = rng.choice(["AWS", "Azure", "GCP"])
        if cloud_choice == "AWS":
            raw = _build_aws_record(rng, anomalous=anomalous, index=index)
            event = parser.parse_aws(raw)
        elif cloud_choice == "Azure":
            raw = _build_azure_record(rng, anomalous=anomalous, index=index)
            event = parser.parse_azure(raw)
        else:
            raw = _build_gcp_record(rng, anomalous=anomalous, index=index)
            event = parser.parse_gcp(raw)
        yield event


def collect_mock_events(num_events: int = 100, seed: Optional[int] = 42) -> List[CloudSecurityEvent]:
    """Materialize the mock stream into a list (training / batch convenience)."""
    return list(generate_mock_stream(num_events=num_events, seed=seed))


def iter_infinite_mock_stream(
    seed: Optional[int] = 42,
    batch_size: int = 50,
) -> Iterator[CloudSecurityEvent]:
    """Infinite iterator used by the Streamlit live dashboard."""
    offset = 0
    while True:
        for event in generate_mock_stream(num_events=batch_size, seed=(seed or 0) + offset):
            yield event
        offset += batch_size
