"""
Analyst-facing intrusion explanations for Quantum Helix alerts.

Turns raw CIM signals + ensemble engine scores into:
  - plain-English narrative
  - ranked signal contributions vs simple baselines
  - attack-phase / technique hypotheses
  - quantum↔classical disagreement interpretation
  - recommended next steps

This is explainability for the hybrid ensemble — not a claim of MITRE-certified
detection coverage. Technique IDs are hypotheses for analyst orientation.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence


# Simple operational baselines for demo / synthetic traffic.
# In production these would be identity- or tenant-cohort percentiles.
BASELINES = {
    "auth_failures": 1.5,
    "api_velocity": 12.0,
    "data_volume_mb": 5.0,
}


def _mb(bytes_out: float) -> float:
    return float(bytes_out) / 1e6


def _signal(
    name: str,
    label: str,
    value: float,
    baseline: float,
    unit: str,
    why: str,
) -> Dict[str, Any]:
    ratio = (value / baseline) if baseline > 0 else (1.0 if value > 0 else 0.0)
    if ratio >= 8:
        severity = "critical"
    elif ratio >= 3:
        severity = "high"
    elif ratio >= 1.5:
        severity = "elevated"
    else:
        severity = "normal"
    return {
        "name": name,
        "label": label,
        "value": round(value, 2),
        "baseline": baseline,
        "unit": unit,
        "ratio": round(ratio, 2),
        "severity": severity,
        "why": why,
    }


def infer_attack_phase(event: Any) -> str:
    auth = float(getattr(event, "auth_failures", 0) or 0)
    api = float(getattr(event, "api_velocity", 0) or 0)
    volume = float(getattr(event, "data_volume_bytes", 0) or 0)

    if volume >= 1e9:
        return "Exfiltration"
    if volume >= 5e7 and api >= 30:
        return "Exfiltration"
    if auth >= 10 and api >= 40:
        return "Credential Access"
    if auth >= 8:
        return "Credential Access"
    if api >= 60:
        return "Discovery"
    if api >= 40 and volume >= 1e7:
        return "Collection"
    if volume >= 5e7:
        return "Exfiltration"
    if api >= 25:
        return "Discovery"
    return "Initial Access"


def infer_techniques(event: Any, phase: str) -> List[Dict[str, str]]:
    """Heuristic ATT&CK-oriented hypotheses for analyst orientation."""
    auth = float(getattr(event, "auth_failures", 0) or 0)
    api = float(getattr(event, "api_velocity", 0) or 0)
    volume = float(getattr(event, "data_volume_bytes", 0) or 0)
    techniques: List[Dict[str, str]] = []

    if auth >= 8:
        techniques.append({
            "id": "T1110",
            "name": "Brute Force / password spraying",
            "confidence": "high" if auth >= 12 else "medium",
            "evidence": f"{auth:.0f} failed authentications in the observation window",
        })
    if volume >= 5e7:
        techniques.append({
            "id": "T1567",
            "name": "Exfiltration over web service / cloud storage",
            "confidence": "high" if volume >= 1e9 else "medium",
            "evidence": f"{_mb(volume):.0f} MB outbound data volume",
        })
    if api >= 40:
        techniques.append({
            "id": "T1580" if getattr(event, "cloud_provider", "") == "AWS" else "T1526",
            "name": "Cloud service discovery / enumeration",
            "confidence": "medium",
            "evidence": f"{api:.0f} API calls (elevated velocity)",
        })
    if phase == "Collection" and volume >= 1e7:
        techniques.append({
            "id": "T1530",
            "name": "Data from cloud storage",
            "confidence": "medium",
            "evidence": "Elevated read/transfer volume prior to clear exfil threshold",
        })
    if not techniques:
        techniques.append({
            "id": "T1078",
            "name": "Valid accounts (anomalous use)",
            "confidence": "low",
            "evidence": "Behavior diverges from baseline without a single dominant signal",
        })
    return techniques


def interpret_disagreement(
    quantum: float,
    classical: float,
    isolation: float,
    *,
    threshold: float = 0.18,
) -> Optional[Dict[str, Any]]:
    delta = abs(float(quantum) - float(classical))
    if delta < threshold:
        return None

    if quantum >= classical + threshold:
        meaning = (
            "The quantum kernel scored this higher than the classical SVM. "
            "That often means a subtle multi-feature pattern the linear/RBF control "
            "under-weighted — worth investigating even if classical looks quieter."
        )
        bias = "quantum_elevated"
    else:
        meaning = (
            "The classical SVM scored this higher than the quantum kernel. "
            "That often means a loud, axis-aligned outlier (volume, failures, or velocity) "
            "that classical models catch cleanly — confirm it is not a known batch job."
        )
        bias = "classical_elevated"

    if isolation >= 0.75 and max(quantum, classical) < 0.55:
        meaning += " Isolation Forest also flags novelty relative to benign training traffic."

    return {
        "delta": round(delta, 3),
        "bias": bias,
        "quantum_kernel": round(float(quantum), 3),
        "classical_svm": round(float(classical), 3),
        "isolation_forest": round(float(isolation), 3),
        "summary": (
            f"Detectors disagreed: quantum {quantum:.2f} vs classical {classical:.2f} "
            f"(Δ={delta:.2f})."
        ),
        "interpretation": meaning,
    }


def build_signal_contributions(event: Any) -> List[Dict[str, Any]]:
    auth = float(getattr(event, "auth_failures", 0) or 0)
    api = float(getattr(event, "api_velocity", 0) or 0)
    volume_mb = _mb(float(getattr(event, "data_volume_bytes", 0) or 0))

    signals = [
        _signal(
            "auth_failures",
            "Failed authentications",
            auth,
            BASELINES["auth_failures"],
            "count",
            "Spike often indicates password spraying, stuffed credentials, or a misconfigured client.",
        ),
        _signal(
            "api_velocity",
            "API call velocity",
            api,
            BASELINES["api_velocity"],
            "calls",
            "Burst API activity can indicate discovery, enumeration, or automated tooling.",
        ),
        _signal(
            "data_volume_mb",
            "Outbound data volume",
            volume_mb,
            BASELINES["data_volume_mb"],
            "MB",
            "Large egress is a primary exfiltration indicator — verify destination and business need.",
        ),
    ]
    # Rank anomalous signals first.
    order = {"critical": 0, "high": 1, "elevated": 2, "normal": 3}
    signals.sort(key=lambda s: (order.get(s["severity"], 9), -s["ratio"]))
    return signals


def build_narrative(
    event: Any,
    detail: Any,
    *,
    threshold: float,
    phase: str,
    techniques: Sequence[Dict[str, str]],
    disagreement: Optional[Dict[str, Any]],
) -> str:
    cloud = getattr(event, "cloud_provider", "cloud")
    identity = getattr(event, "normalized_identity", "unknown")
    ip = getattr(event, "source_ip", "unknown")
    score = float(getattr(detail, "ensemble", 0) or 0)

    top = [t["name"] for t in techniques[:2]]
    tech_clause = f" Technique hypothesis: {', '.join(top)}." if top else ""

    signals = []
    auth = float(getattr(event, "auth_failures", 0) or 0)
    api = float(getattr(event, "api_velocity", 0) or 0)
    volume = float(getattr(event, "data_volume_bytes", 0) or 0)
    if auth >= 8:
        signals.append(f"{auth:.0f} failed logins")
    if api >= 40:
        signals.append(f"{api:.0f} API calls")
    if volume >= 5e7:
        signals.append(f"{_mb(volume):.0f} MB outbound")
    if not signals:
        signals.append("behavior outside the learned baseline")

    narrative = (
        f"On {cloud}, identity `{identity}` from `{ip}` triggered an "
        f"**{phase}** intrusion hypothesis after showing {', '.join(signals)}. "
        f"Hybrid ensemble risk is **{score:.2f}** (alert threshold {threshold:.2f})."
        f"{tech_clause}"
    )
    if disagreement:
        narrative += f" {disagreement['summary']} {disagreement['interpretation']}"
    return narrative


def recommended_actions(event: Any, severity: str, phase: str) -> List[str]:
    identity = getattr(event, "normalized_identity", "the identity")
    ip = getattr(event, "source_ip", "the source IP")
    cloud = getattr(event, "cloud_provider", "the cloud")
    actions = [
        f"Validate whether `{identity}` should be active in {cloud} right now.",
        f"Pull recent auth and API history for `{ip}` in {cloud} audit logs.",
    ]
    auth = float(getattr(event, "auth_failures", 0) or 0)
    volume = float(getattr(event, "data_volume_bytes", 0) or 0)
    if auth >= 8:
        actions.append("Force MFA step-up / password reset and review failed sign-in geography.")
    if volume >= 5e7:
        actions.append("Identify egress destination (bucket, partner, personal storage) and freeze transfers if unexpected.")
    if phase in ("Credential Access", "Exfiltration"):
        actions.append("Revoke active sessions/keys for the identity until investigation completes.")
    if severity == "CRITICAL":
        actions.append("Open/claim a case, notify on-call, and treat as active intrusion until proven otherwise.")
    else:
        actions.append("If expected (batch job, migration), acknowledge as false positive with a note.")
    return actions


def build_explanation(
    event: Any,
    detail: Any,
    *,
    threshold: float,
    feats: Optional[Sequence[float]] = None,
) -> Dict[str, Any]:
    """Full structured explanation payload stored on Alert.feature_contributions."""
    phase = infer_attack_phase(event)
    techniques = infer_techniques(event, phase)
    q = float(getattr(detail, "quantum_kernel", 0) or 0)
    c = float(getattr(detail, "classical_svm", 0) or 0)
    iso = float(getattr(detail, "isolation_forest", 0) or 0)
    disagreement = interpret_disagreement(q, c, iso)
    signals = build_signal_contributions(event)
    narrative = build_narrative(
        event, detail, threshold=threshold, phase=phase,
        techniques=techniques, disagreement=disagreement,
    )
    severity_hint = "CRITICAL" if float(getattr(detail, "ensemble", 0) or 0) >= max(threshold + 0.15, 0.85) else (
        "HIGH" if float(getattr(detail, "ensemble", 0) or 0) >= threshold else "WATCH"
    )

    return {
        "version": 1,
        "attack_phase": phase,
        "narrative": narrative,
        "hypothesis": (
            f"Most likely intrusion story: {phase} via {techniques[0]['name']} "
            f"({techniques[0]['id']})."
        ),
        "techniques": techniques,
        "signals": signals,
        "engines": {
            "ensemble": round(float(getattr(detail, "ensemble", 0) or 0), 4),
            "quantum_kernel": round(q, 4),
            "classical_svm": round(c, 4),
            "isolation_forest": round(iso, 4),
            "disagreement": disagreement,
        },
        "pca_components": [round(float(x), 4) for x in (feats or [])],
        "actions": recommended_actions(event, severity_hint, phase),
        "disagreement_text": disagreement["summary"] + " " + disagreement["interpretation"] if disagreement else None,
    }


def format_ai_insight(alert: Any) -> str:
    """Deterministic analyst brief from stored alert fields (no external LLM)."""
    contrib = alert.feature_contributions if isinstance(alert.feature_contributions, dict) else {}
    techniques = contrib.get("techniques") or []
    signals = contrib.get("signals") or []
    engines = contrib.get("engines") or {}
    disagreement = engines.get("disagreement") if isinstance(engines, dict) else None

    lines = [
        f"### Intrusion brief — `{alert.short_identity}`",
        "",
        alert.plain_english or contrib.get("narrative") or "No narrative stored.",
        "",
        f"**Phase hypothesis:** {alert.attack_phase or contrib.get('attack_phase') or 'Unknown'}",
        f"**Ensemble risk:** {float(alert.score):.2f} "
        f"(Q={float(alert.quantum_kernel):.2f} · SVM={float(alert.classical_svm):.2f} · IF={float(alert.isolation_forest):.2f})",
    ]

    if techniques:
        lines.append("")
        lines.append("**Technique hypotheses**")
        for t in techniques:
            lines.append(
                f"- `{t.get('id', '?')}` {t.get('name', 'Unknown')} "
                f"({t.get('confidence', 'n/a')}): {t.get('evidence', '')}"
            )

    anomalous = [s for s in signals if s.get("severity") in ("critical", "high", "elevated")]
    if anomalous:
        lines.append("")
        lines.append("**Driving signals**")
        for s in anomalous:
            lines.append(
                f"- {s.get('label')}: {s.get('value')} {s.get('unit', '')} "
                f"(baseline {s.get('baseline')}, {s.get('severity')}) — {s.get('why', '')}"
            )

    if disagreement and isinstance(disagreement, dict):
        lines.append("")
        lines.append("**Detector disagreement**")
        lines.append(disagreement.get("interpretation") or disagreement.get("summary") or "")

    actions = alert.actions if isinstance(alert.actions, list) else contrib.get("actions") or []
    if actions:
        lines.append("")
        lines.append("**Recommended remediation**")
        for i, act in enumerate(actions, 1):
            lines.append(f"{i}. {act}")

    lines.append("")
    lines.append(
        "_Generated from hybrid ensemble scores and CIM signals — not an external LLM._"
    )
    return "\n".join(lines)
