"""Unit tests for intrusion explanation helpers (no detector stack required)."""
from types import SimpleNamespace

from explanation import (
    build_explanation,
    format_ai_insight,
    infer_attack_phase,
    infer_techniques,
    interpret_disagreement,
)


def test_credential_access_phase_and_techniques():
    event = SimpleNamespace(
        auth_failures=14,
        api_velocity=22,
        data_volume_bytes=1e6,
        cloud_provider="AWS",
        normalized_identity="user@corp",
        source_ip="1.2.3.4",
    )
    assert infer_attack_phase(event) == "Credential Access"
    techs = infer_techniques(event, "Credential Access")
    assert any(t["id"] == "T1110" for t in techs)


def test_exfiltration_phase():
    event = SimpleNamespace(
        auth_failures=1,
        api_velocity=10,
        data_volume_bytes=2e9,
        cloud_provider="Azure",
        normalized_identity="svc",
        source_ip="10.0.0.1",
    )
    assert infer_attack_phase(event) == "Exfiltration"


def test_disagreement_interpretation():
    d = interpret_disagreement(0.91, 0.40, 0.55)
    assert d is not None
    assert d["bias"] == "quantum_elevated"
    assert d["delta"] == 0.51
    assert interpret_disagreement(0.5, 0.52, 0.4) is None


def test_build_explanation_payload():
    event = SimpleNamespace(
        auth_failures=12,
        api_velocity=55,
        data_volume_bytes=8e7,
        cloud_provider="GCP",
        normalized_identity="apt-user",
        source_ip="203.0.113.9",
    )
    detail = SimpleNamespace(
        ensemble=0.88,
        quantum_kernel=0.92,
        classical_svm=0.61,
        isolation_forest=0.70,
    )
    expl = build_explanation(event, detail, threshold=0.68, feats=[0.1, -0.2, 0.3, 0.0])
    assert expl["version"] == 1
    assert expl["attack_phase"] in ("Exfiltration", "Credential Access", "Discovery", "Collection")
    assert expl["signals"]
    assert expl["narrative"]
    assert expl["actions"]
    assert expl["engines"]["ensemble"] == 0.88


def test_format_ai_insight_uses_stored_explanation():
    alert = SimpleNamespace(
        short_identity="apt-user",
        identity="apt-user@corp",
        source_ip="1.1.1.1",
        score=0.9,
        quantum_kernel=0.91,
        classical_svm=0.5,
        isolation_forest=0.6,
        attack_phase="Credential Access",
        plain_english="Narrative here.",
        actions=["Step one"],
        feature_contributions={
            "version": 1,
            "hypothesis": "Most likely: Credential Access",
            "techniques": [{"id": "T1110", "name": "Brute Force", "confidence": "high", "evidence": "12 fails"}],
            "signals": [{
                "name": "auth_failures", "label": "Failed authentications",
                "value": 12, "baseline": 1.5, "unit": "count",
                "severity": "critical", "why": "spray",
            }],
            "engines": {
                "disagreement": {
                    "summary": "Disagreed",
                    "interpretation": "Quantum elevated.",
                }
            },
        },
    )
    text = format_ai_insight(alert)
    assert "Intrusion brief" in text
    assert "T1110" in text
    assert "Quantum elevated" in text
