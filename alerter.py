"""
Enterprise incident response and SIEM output wrapper for Quantum Helix.

Converts high-scoring quantum detections into AWS Security Hub (ASFF) and
Microsoft Sentinel CEF payloads, and mocks a SOC Slack webhook notification.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests

from normalization import CloudSecurityEvent

logger = logging.getLogger(__name__)

DEFAULT_THRESHOLD = 0.75
MOCK_SLACK_WEBHOOK = "https://hooks.slack.example.local/services/QUANTUM/SAFEGUARD/mock"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class AlertOrchestrator:
    """Evaluate threat scores and emit multi-SIEM + Slack SOC notifications."""

    def __init__(
        self,
        threshold: float = DEFAULT_THRESHOLD,
        slack_webhook_url: str = MOCK_SLACK_WEBHOOK,
        product_arn: str = (
            "arn:aws:securityhub:us-east-1:123456789012:product/Quantum Helix/qml-detector"
        ),
        dry_run_webhook: bool = True,
    ) -> None:
        self.threshold = float(threshold)
        self.slack_webhook_url = slack_webhook_url
        self.product_arn = product_arn
        self.dry_run_webhook = dry_run_webhook
        self.alert_history: List[Dict[str, Any]] = []

    def evaluate_and_alert(
        self,
        event: CloudSecurityEvent,
        threat_score: float,
        threshold: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        If ``threat_score`` exceeds the threshold, build ASFF + CEF payloads
        and push a mocked Slack SOC alert. Returns the alert package or None.
        """
        active_threshold = float(self.threshold if threshold is None else threshold)
        score = float(threat_score)

        if score < active_threshold:
            logger.debug(
                "Score %.4f below threshold %.2f — no alert for identity=%s",
                score,
                active_threshold,
                event.normalized_identity,
            )
            return None

        asff_payload = self.build_asff_finding(event, score, active_threshold)
        cef_payload = self.build_cef_event(event, score, active_threshold)
        package = {
            "alert_id": str(uuid.uuid4()),
            "triggered_at": _utc_now_iso(),
            "threshold": active_threshold,
            "threat_score": score,
            "cloud_provider": event.cloud_provider,
            "normalized_identity": event.normalized_identity,
            "source_ip": event.source_ip,
            "asff": asff_payload,
            "cef": cef_payload,
        }
        self.alert_history.append(package)
        self.notify_slack_soc(package, event)
        logger.warning(
            "Alert raised alert_id=%s provider=%s score=%.4f identity=%s",
            package["alert_id"],
            event.cloud_provider,
            score,
            event.normalized_identity,
        )
        return package

    def build_asff_finding(
        self,
        event: CloudSecurityEvent,
        threat_score: float,
        threshold: float,
    ) -> Dict[str, Any]:
        """Construct an AWS Security Finding Format (ASFF) JSON finding."""
        severity_normalized = int(round(threat_score * 100))
        finding_id = str(uuid.uuid4())
        return {
            "SchemaVersion": "2018-10-08",
            "Id": finding_id,
            "ProductArn": self.product_arn,
            "GeneratorId": "Quantum Helix/qml-threat-detector",
            "AwsAccountId": "123456789012",
            "Types": [
                "TTPs/Defense Evasion",
                "Effects/Data Exposure",
                "Unusual Behaviors/User",
            ],
            "CreatedAt": event.timestamp or _utc_now_iso(),
            "UpdatedAt": _utc_now_iso(),
            "Severity": {
                "Product": severity_normalized,
                "Normalized": severity_normalized,
                "Label": "CRITICAL" if threat_score >= 0.9 else "HIGH",
            },
            "Title": "Quantum Helix QNN Zero-Day Cloud Anomaly",
            "Description": (
                f"Parameterized quantum circuit flagged multi-cloud telemetry for "
                f"identity '{event.normalized_identity}' from {event.source_ip} with "
                f"threat score {threat_score:.4f} (threshold {threshold:.2f}). "
                f"Correlated signals: api_velocity={event.api_velocity:.2f}, "
                f"auth_failures={event.auth_failures:.2f}, "
                f"data_volume_bytes={event.data_volume_bytes:.0f}."
            ),
            "ProductFields": {
                "ProviderName": "Quantum Helix",
                "ProviderVersion": "1.0.0",
                "CloudProvider": event.cloud_provider,
                "QuantumThreatScore": f"{threat_score:.6f}",
                "DetectionThreshold": f"{threshold:.2f}",
                "RawEventId": event.raw_event_id,
            },
            "Resources": [
                {
                    "Type": "Other",
                    "Id": event.normalized_identity,
                    "Partition": "aws" if event.cloud_provider == "AWS" else "azure",
                    "Region": "us-east-1",
                    "Details": {
                        "Other": {
                            "SourceIp": event.source_ip,
                            "ApiVelocity": str(event.api_velocity),
                            "AuthFailures": str(event.auth_failures),
                            "DataVolumeBytes": str(event.data_volume_bytes),
                        }
                    },
                }
            ],
            "RecordState": "ACTIVE",
            "WorkflowState": "NEW",
        }

    def build_cef_event(
        self,
        event: CloudSecurityEvent,
        threat_score: float,
        threshold: float,
    ) -> str:
        """
        Construct a Microsoft Sentinel-compatible Common Event Format (CEF) string.
        """
        severity = int(round(threat_score * 10))
        severity = max(0, min(10, severity))
        extension = (
            f"src={event.source_ip} "
            f"suser={event.normalized_identity} "
            f"cs1={event.cloud_provider} cs1Label=CloudProvider "
            f"cs2={threat_score:.6f} cs2Label=QuantumThreatScore "
            f"cs3={threshold:.2f} cs3Label=DetectionThreshold "
            f"cn1={event.api_velocity:.2f} cn1Label=ApiVelocity "
            f"cn2={event.auth_failures:.2f} cn2Label=AuthFailures "
            f"cn3={event.data_volume_bytes:.0f} cn3Label=DataVolumeBytes "
            f"externalId={event.raw_event_id or uuid.uuid4()}"
        )
        cef = (
            f"CEF:0|Quantum Helix|QMLThreatDetector|1.0.0|"
            f"QNN-ANOMALY|Quantum Cloud Threat Detected|{severity}|{extension}"
        )
        return cef

    def notify_slack_soc(self, package: Dict[str, Any], event: CloudSecurityEvent) -> bool:
        """
        Mock SOC Slack webhook. Always logs a clean emoji-formatted critical
        alert to stdout; optionally attempts the HTTP POST when dry_run is False.
        """
        score = float(package["threat_score"])
        message_lines = [
            "🚨 CRITICAL QUANTUM THREAT DETECTED",
            f"   • Alert ID     : {package['alert_id']}",
            f"   • Provider     : {event.cloud_provider}",
            f"   • Identity     : {event.normalized_identity}",
            f"   • Source IP    : {event.source_ip}",
            f"   • Threat Score : {score:.4f} (threshold {package['threshold']:.2f})",
            f"   • API Velocity : {event.api_velocity:.2f}",
            f"   • Auth Failures: {event.auth_failures:.2f}",
            f"   • Data Volume  : {event.data_volume_bytes:,.0f} bytes",
            f"   • Time         : {package['triggered_at']}",
        ]
        formatted = "\n".join(message_lines)
        # stdout-facing operational log for SOC analysts watching the CLI/GUI.
        print(formatted)
        logger.critical(formatted)

        slack_body = {
            "text": "🚨 CRITICAL QUANTUM THREAT DETECTED",
            "blocks": [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": "🚨 CRITICAL QUANTUM THREAT DETECTED",
                    },
                },
                {
                    "type": "section",
                    "fields": [
                        {"type": "mrkdwn", "text": f"*Provider:*\n{event.cloud_provider}"},
                        {"type": "mrkdwn", "text": f"*Score:*\n{score:.4f}"},
                        {"type": "mrkdwn", "text": f"*Identity:*\n`{event.normalized_identity}`"},
                        {"type": "mrkdwn", "text": f"*Source IP:*\n`{event.source_ip}`"},
                    ],
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": (
                            f"```{json.dumps({'asff_id': package['asff']['Id'], 'cef': package['cef']}, indent=2)}```"
                        ),
                    },
                },
            ],
        }

        if self.dry_run_webhook:
            logger.info(
                "Slack webhook dry-run enabled — payload prepared for %s (%d bytes)",
                self.slack_webhook_url,
                len(json.dumps(slack_body)),
            )
            return True

        try:
            response = requests.post(
                self.slack_webhook_url,
                json=slack_body,
                timeout=5,
            )
            response.raise_for_status()
            logger.info("Slack SOC webhook delivered status=%s", response.status_code)
            return True
        except requests.RequestException as exc:
            logger.error("Slack SOC webhook failed: %s", exc)
            return False

    def export_asff_batch(self) -> List[Dict[str, Any]]:
        """Return all ASFF findings accumulated during this process lifetime."""
        return [item["asff"] for item in self.alert_history]

    def reset(self) -> None:
        """Clear in-memory alert history (useful between Streamlit sessions)."""
        self.alert_history.clear()
