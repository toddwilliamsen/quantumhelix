import time
import random
import uuid
import logging
import threading
from typing import Any, List
from models import db, HistoryEvent, SuppressionRule, Alert, PlaybookRule, AuditLog
from state import state
from alerter import AlertOrchestrator
from apt_corpus import build_benchmark_corpus, make_loud_attacks, make_subtle_apt_events
from data_processor import ClassicalFeaturePipeline
from ensemble import HybridThreatEnsemble
from normalization import CloudSecurityEvent, collect_mock_events, generate_mock_stream
from cmdb import enrich_identity
from itsm import ServiceNowClient

logger = logging.getLogger(__name__)

def _labels(events: List[Any]) -> __import__('numpy').ndarray:
    import numpy as np
    return np.asarray(
        [
            1.0 if (e.auth_failures >= 10 and e.data_volume_bytes >= 1e8 and e.api_velocity >= 50) else 0.0
            for e in events
        ],
        dtype=np.float64,
    )

def load_stack(seed: int = 42):
    import numpy as np
    warmup = collect_mock_events(80, seed=seed)
    extra, extra_y, _ = build_benchmark_corpus(n_normal=40, n_loud=8, n_subtle=10, seed=seed + 3)
    events = warmup + extra
    pipe = ClassicalFeaturePipeline()
    x = pipe.fit_transform(events)
    y = np.concatenate([_labels(warmup), extra_y])
    ens = HybridThreatEnsemble(seed=seed, include_qnn=False)
    ens.fit(x, y)
    return pipe, ens

def _severity(score: float, threshold: float) -> str:
    if score >= max(threshold, 0.75):
        return "CRITICAL"
    if score >= threshold:
        return "HIGH"
    if score >= threshold * 0.7:
        return "WATCH"
    return "CLEAR"

def _plain_english(event: CloudSecurityEvent, detail: Any, threshold: float) -> str:
    bits = []
    if event.auth_failures >= 8:
        bits.append(f"many failed logins ({event.auth_failures:.0f})")
    if event.data_volume_bytes >= 5e7:
        bits.append(f"a large data transfer out ({event.data_volume_bytes / 1e6:.0f} MB)")
    if event.api_velocity >= 40:
        bits.append(f"unusually fast API activity ({event.api_velocity:.0f} calls)")
    if abs(detail.quantum_kernel - detail.classical_svm) >= 0.18:
        bits.append("detectors disagreed on how serious this looks")
    if not bits:
        bits.append("behavior that does not match normal patterns")
    return (
        f"On **{event.cloud_provider}**, account `{event.normalized_identity}` "
        f"from IP `{event.source_ip}` showed {', '.join(bits)}. "
        f"Our risk score is **{detail.ensemble:.2f}** (alert line is {threshold:.2f})."
    )

def _recommended_actions(event: CloudSecurityEvent, severity: str) -> List[str]:
    actions = [
        f"Confirm whether `{event.normalized_identity}` should be active right now.",
        f"Check recent activity from IP `{event.source_ip}` in {event.cloud_provider} logs.",
    ]
    if event.auth_failures >= 8:
        actions.append("Review failed sign-ins and consider temporary MFA / password reset.")
    if event.data_volume_bytes >= 5e7:
        actions.append("Verify the outbound data transfer destination and volume are expected.")
    if severity == "CRITICAL":
        actions.append("If unexpected: isolate the identity (disable key / revoke session) and escalate.")
    else:
        actions.append("If expected: mark as acknowledged false positive so the queue stays clean.")
    return actions

def _next_event(rng: random.Random) -> CloudSecurityEvent:
    roll = rng.random()
    if roll < 0.07:
        return rng.choice(make_loud_attacks(4, seed=rng.randint(1, 10_000)))
    if roll < 0.14:
        return rng.choice(make_subtle_apt_events(6, seed=rng.randint(1, 10_000)))
    return next(generate_mock_stream(num_events=1, seed=rng.randint(1, 10_000), anomaly_rate=0.03))


def event_generator_loop(app):
    rng = random.Random(state.seed)
    with app.app_context():
        last_event = HistoryEvent.query.order_by(HistoryEvent.t.desc()).first()
        if last_event:
            state.processed = last_event.t
            
    logger.info("Started background event generator.")
    while True:
        with state.lock:
            streaming = state.streaming
            clients = state.active_clients
        
        if streaming and clients == 0:
            with state.lock:
                state.streaming = False
            logger.info("Auto-paused stream because 0 clients are connected.")
            streaming = False
            
        if not streaming:
            time.sleep(1)
            continue
            
        with app.app_context():
            for _ in range(state.batch):
                event = _next_event(rng)
                feats = state.pipe.transform_single(event)
                start_t = time.perf_counter()
                detail = state.ensemble.score_detail(feats)
                latency_ms = (time.perf_counter() - start_t) * 1000.0
                score = float(detail.ensemble)
                delta = abs(float(detail.quantum_kernel) - float(detail.classical_svm))
                sev = _severity(score, state.threshold)
                with state.lock:
                    state.processed += 1
                    processed_val = state.processed
                
                hist_record = HistoryEvent(tenant_id=1, 
                    t=processed_val,
                    ensemble=score,
                    isolation_forest=float(detail.isolation_forest),
                    classical_svm=float(detail.classical_svm),
                    quantum_kernel=float(detail.quantum_kernel),
                    cloud_provider=event.cloud_provider,
                    severity=sev,
                    latency_ms=latency_ms
                )
                db.session.add(hist_record)
                
                with state.lock:
                    state.history_cache.append({
                        "t": processed_val,
                        "ensemble": score,
                        "alert_id": None
                    })
                    if len(state.history_cache) > 360:
                        state.history_cache = state.history_cache[-360:]

                if delta >= 0.18:
                    with state.lock:
                        state.disagreements += 1

                if score >= state.threshold:
                    rules = SuppressionRule.query.filter_by(tenant_id=1).all()
                    is_suppressed = False
                    for rule in rules:
                        if rule.rule_type == 'identity' and rule.value.lower() in event.normalized_identity.lower():
                            is_suppressed = True
                            break
                        elif rule.rule_type == 'ip' and rule.value == event.source_ip:
                            is_suppressed = True
                            break
                        elif rule.rule_type == 'cloud' and rule.value.lower() == event.cloud_provider.lower():
                            is_suppressed = True
                            break
                            
                    if not is_suppressed:
                        package = state.alerter.evaluate_and_alert(event, score, threshold=state.threshold)
                        alert_id = str(uuid.uuid4())
                        
                        phase = "Initial Access"
                        if event.data_volume_bytes > 5e7:
                            phase = "Exfiltration"
                        elif event.auth_failures > 5.0:
                            phase = "Credential Access"
                        elif event.api_velocity > 40.0:
                            phase = "Discovery"
                        
                        
                        # Correlation Engine
                        existing_alert = Alert.query.filter_by(tenant_id=1, status='open', identity=event.normalized_identity).first()
                        if existing_alert:
                            # Append to existing alert (deduplication)
                            existing_alert.score = min(0.99, existing_alert.score + 0.05)
                            existing_alert.actions.append(f"Repeated anomalous behavior detected from {event.source_ip}")
                            alert_id = existing_alert.id
                        else:
                            alert_record = Alert(
                                id=alert_id,
                                tenant_id=1,
                                status="open",
                            severity=sev,
                            cloud=event.cloud_provider,
                            identity=event.normalized_identity,
                            short_identity=event.normalized_identity.split("/")[-1][:40],
                            source_ip=event.source_ip,
                            score=round(score, 3),
                            ensemble=round(score, 4),
                            quantum_kernel=round(float(detail.quantum_kernel), 4),
                            classical_svm=round(float(detail.classical_svm), 4),
                            isolation_forest=round(float(detail.isolation_forest), 4),
                            attack_phase=phase,
                            plain_english=_plain_english(event, detail, state.threshold),
                            actions=_recommended_actions(event, sev),
                            disagreement=(
                                f"Detectors disagreed: quantum kernel {detail.quantum_kernel:.2f} vs "
                                f"classical SVM {detail.classical_svm:.2f}. Worth a closer look."
                                if delta >= 0.18
                                else None
                            ),
                            siem=package,
                            feature_contributions={
                                "api_velocity": float(event.api_velocity),
                                "auth_failures": float(event.auth_failures),
                                "data_volume_bytes": float(event.data_volume_bytes),
                                "pca_components": [float(x) for x in feats]
                            },
                            linked_identities=(
                                ["svc-shadow-0", "svc-shadow-1@corp.local", "compromised-azure-user-0@corp.local"]
                                if "svc-shadow" in event.normalized_identity else []
                            ),
                            latency_ms=latency_ms,
                            auto_response="Auto-isolated identity due to high ensemble score (>0.90)" if score > 0.90 else None
                        )

                        
                        # Evaluate SOAR Playbooks
                        playbooks = PlaybookRule.query.filter_by(tenant_id=1).all()
                        for pb in playbooks:
                            match = False
                            val = getattr(alert_record, pb.condition_field, None)
                            if val is not None:
                                try:
                                    # Convert to float for numerical comparison if possible
                                    val_f = float(val)
                                    cond_f = float(pb.condition_value)
                                    if pb.condition_operator == '>': match = val_f > cond_f
                                    elif pb.condition_operator == '<': match = val_f < cond_f
                                    elif pb.condition_operator == '==': match = val_f == cond_f
                                except:
                                    # String comparison
                                    if pb.condition_operator == '==': match = str(val).lower() == pb.condition_value.lower()
                            
                            if match:
                                if pb.action == 'auto_isolate':
                                    alert_record.status = 'escalated'
                                    alert_record.auto_response = f"SOAR Playbook executed: auto-isolated identity."
                                    if not SuppressionRule.query.filter_by(rule_type='identity', value=alert_record.identity).first():
                                        rule = SuppressionRule(tenant_id=1, rule_type='identity', value=alert_record.identity)
                                        db.session.add(rule)
                                    audit = AuditLog(tenant_id=1, username="SOAR_BOT", action="Playbook Execution: Auto Isolate", target=alert_record.identity)
                                    db.session.add(audit)
                                elif pb.action == 'create_ticket':
                                    if not alert_record.itsm_ticket:
                                        alert_record.itsm_ticket = "SOAR-" + str(10000 + random.randint(1, 9999))
                                    audit = AuditLog(tenant_id=1, username="SOAR_BOT", action="Playbook Execution: Create Ticket", target=alert_record.id)
                                    db.session.add(audit)

                        if score > 0.90:
                            cmdb_context = enrich_identity(event.normalized_identity)
                            details = alert_record.disagreement if alert_record.disagreement else "Quantum and Classical models in consensus."
                            ticket_number = state.servicenow.create_incident(
                                alert_id=alert_id,
                                identity=event.normalized_identity,
                                score=round(score, 4),
                                cmdb_context=cmdb_context,
                                details=details
                            )
                            alert_record.itsm_ticket = ticket_number

                        db.session.add(alert_record)
                        with state.lock:
                            state.history_cache[-1]["alert_id"] = alert_id
                            
            # Moved commit out of the for-loop but inside app_context to batch them properly
            try:
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                logger.error(f"DB commit error in simulation thread: {e}")
                
        time.sleep(state.delay)

def start_background_loop(app):
    logger.info("Loading detectors...")
    pipe, ensemble = load_stack()
    state.pipe = pipe
    state.ensemble = ensemble
    state.alerter = AlertOrchestrator(threshold=state.threshold, dry_run_webhook=True)
    state.servicenow = ServiceNowClient()
    logger.info("Detectors loaded.")
    
    bg_thread = threading.Thread(target=event_generator_loop, args=(app,), daemon=True)
    bg_thread.start()
