import os
import time
import random
import uuid
import logging
import threading
from typing import Any, List, Optional
from models import db, HistoryEvent, SuppressionRule, Alert, PlaybookRule, AuditLog
from state import state
from alerter import AlertOrchestrator
from apt_corpus import build_benchmark_corpus, make_loud_attacks, make_subtle_apt_events
from data_processor import ClassicalFeaturePipeline
from ensemble import HybridThreatEnsemble, EnsembleWeights
from normalization import CloudSecurityEvent, collect_mock_events, generate_mock_stream
from cmdb import enrich_identity
from itsm import ServiceNowClient
from explanation import build_explanation

logger = logging.getLogger(__name__)

def _labels(events: List[Any]):
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
    # Keep CRITICAL above HIGH even when the operator raises the alert threshold.
    critical_cut = max(threshold + 0.15, 0.85)
    if score >= critical_cut:
        return "CRITICAL"
    if score >= threshold:
        return "HIGH"
    if score >= threshold * 0.7:
        return "WATCH"
    return "CLEAR"

def _next_event(rng: random.Random) -> CloudSecurityEvent:
    with state.lock:
        if state.replay_queue:
            return state.replay_queue.popleft()

    roll = rng.random()
    if roll < 0.07:
        return rng.choice(make_loud_attacks(4, seed=rng.randint(1, 10_000)))
    if roll < 0.14:
        return rng.choice(make_subtle_apt_events(6, seed=rng.randint(1, 10_000)))
    return next(generate_mock_stream(num_events=1, seed=rng.randint(1, 10_000), anomaly_rate=0.03))


def _tenant_id() -> int:
    with state.lock:
        return int(state.sim_tenant_id)


def enqueue_replay(kind: str = "mixed", count: int = 8) -> int:
    """Queue synthetic attack events for the generator to consume next."""
    seed = random.randint(1, 10_000)
    events: List[CloudSecurityEvent] = []
    if kind == "loud":
        events = make_loud_attacks(count, seed=seed)
    elif kind == "subtle":
        events = make_subtle_apt_events(count, seed=seed)
    else:
        half = max(1, count // 2)
        events = make_loud_attacks(half, seed=seed) + make_subtle_apt_events(count - half, seed=seed + 1)
        random.shuffle(events)
    with state.lock:
        state.replay_queue.extend(events)
        queued = len(events)
        if not state.streaming:
            state.streaming = True
    return queued


def apply_playground_config(cfg: dict) -> dict:
    """Apply playground settings to live ensemble weights / delay profile."""
    classical_pct = cfg.get("ensemble_weights", {}).get("classical", 0.55)
    quantum_pct = cfg.get("ensemble_weights", {}).get("quantum", 0.45)
    # Accept either 0–1 or 0–100 from the UI.
    if classical_pct > 1 or quantum_pct > 1:
        classical_pct = float(classical_pct) / 100.0
        quantum_pct = float(quantum_pct) / 100.0
    total = classical_pct + quantum_pct
    if total <= 0:
        classical_pct, quantum_pct = 0.55, 0.45
        total = 1.0
    classical_pct /= total
    quantum_pct /= total

    # Split classical weight between IF and SVM (existing default ratio ~0.25:0.30).
    if_w = classical_pct * (0.25 / 0.55)
    svm_w = classical_pct * (0.30 / 0.55)
    qk_w = quantum_pct

    latency = cfg.get("latency_profile", "balanced")
    delay_map = {"fast": 0.25, "balanced": 0.65, "thorough": 1.2}
    delay = delay_map.get(latency, 0.65)

    with state.lock:
        # PCA width is locked to 4 to match quantum AngleEmbedding qubit count.
        state.playground = {
            "pca_dimensions": 4,
            "kernel_type": cfg.get("kernel_type", state.playground.get("kernel_type", "simulator")),
            "ensemble_weights": {"classical": round(classical_pct, 4), "quantum": round(quantum_pct, 4)},
            "latency_profile": latency,
        }
        state.delay = delay
        if state.ensemble is not None:
            state.ensemble.weights = EnsembleWeights(
                isolation_forest=if_w,
                classical_svm=svm_w,
                quantum_kernel=qk_w,
                qnn=0.0,
            )
        return dict(state.playground)


def event_generator_loop(app):
    rng = random.Random(state.seed)
    tenant_id = _tenant_id()
    with app.app_context():
        last_event = (
            HistoryEvent.query
            .filter_by(tenant_id=tenant_id)
            .order_by(HistoryEvent.t.desc())
            .first()
        )
        if last_event:
            with state.lock:
                state.processed = last_event.t
            
    logger.info("Started background event generator (tenant_id=%s).", tenant_id)
    while True:
        with state.lock:
            streaming = state.streaming
            clients = state.active_clients
            batch = state.batch
            threshold = state.threshold
            delay = state.delay
            tenant_id = int(state.sim_tenant_id)
        
        if streaming and clients == 0:
            with state.lock:
                # Don't auto-pause if replay events are still queued.
                if not state.replay_queue:
                    state.streaming = False
                    streaming = False
                    logger.info("Auto-paused stream because 0 clients are connected.")
            
        if not streaming:
            time.sleep(1)
            continue
            
        with app.app_context():
            for _ in range(batch):
                if state.pipe is None or state.ensemble is None:
                    break
                event = _next_event(rng)
                feats = state.pipe.transform_single(event)
                start_t = time.perf_counter()
                detail = state.ensemble.score_detail(feats)
                latency_ms = (time.perf_counter() - start_t) * 1000.0
                score = float(detail.ensemble)
                delta = abs(float(detail.quantum_kernel) - float(detail.classical_svm))
                sev = _severity(score, threshold)
                with state.lock:
                    state.processed += 1
                    processed_val = state.processed
                
                hist_record = HistoryEvent(
                    tenant_id=tenant_id,
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

                if score >= threshold:
                    rules = SuppressionRule.query.filter_by(tenant_id=tenant_id).all()
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
                        package = state.alerter.evaluate_and_alert(event, score, threshold=threshold)
                        alert_id = str(uuid.uuid4())
                        explanation = build_explanation(
                            event, detail, threshold=threshold, feats=feats
                        )
                        phase = explanation["attack_phase"]
                        sev = _severity(score, threshold)
                        
                        # Correlation Engine
                        existing_alert = Alert.query.filter_by(
                            tenant_id=tenant_id, status='open', identity=event.normalized_identity
                        ).first()
                        if existing_alert:
                            existing_alert.score = min(0.99, existing_alert.score + 0.05)
                            existing_alert.severity = _severity(existing_alert.score, threshold)
                            actions = list(existing_alert.actions or [])
                            actions.append(f"Repeated anomalous behavior detected from {event.source_ip}")
                            existing_alert.actions = actions
                            # Refresh explanation on repeat hits.
                            existing_alert.feature_contributions = explanation
                            existing_alert.plain_english = explanation["narrative"]
                            existing_alert.disagreement = explanation.get("disagreement_text")
                            existing_alert.attack_phase = phase
                            alert_record = existing_alert
                            alert_id = existing_alert.id
                        else:
                            alert_record = Alert(
                                id=alert_id,
                                tenant_id=tenant_id,
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
                                plain_english=explanation["narrative"],
                                actions=explanation["actions"],
                                disagreement=explanation.get("disagreement_text"),
                                siem=package,
                                feature_contributions=explanation,
                                linked_identities=(
                                    ["svc-shadow-0", "svc-shadow-1@corp.local", "compromised-azure-user-0@corp.local"]
                                    if "svc-shadow" in event.normalized_identity else []
                                ),
                                latency_ms=latency_ms,
                                auto_response="Auto-isolated identity due to high ensemble score (>0.90)" if score > 0.90 else None
                            )

                        # Evaluate SOAR Playbooks
                        playbooks = PlaybookRule.query.filter_by(tenant_id=tenant_id).all()
                        for pb in playbooks:
                            match = False
                            val = getattr(alert_record, pb.condition_field, None)
                            if val is not None:
                                if pb.condition_field in ('score', 'ensemble', 'quantum_kernel', 'classical_svm', 'isolation_forest'):
                                    try:
                                        val_f = float(val)
                                        cond_f = float(pb.condition_value)
                                    except (TypeError, ValueError):
                                        continue
                                    if pb.condition_operator == '>':
                                        match = val_f > cond_f
                                    elif pb.condition_operator == '<':
                                        match = val_f < cond_f
                                    elif pb.condition_operator == '==':
                                        match = val_f == cond_f
                                elif pb.condition_operator == '==':
                                    match = str(val).lower() == pb.condition_value.lower()
                            
                            if match:
                                if pb.action == 'auto_isolate':
                                    alert_record.status = 'escalated'
                                    alert_record.auto_response = "SOAR Playbook executed: auto-isolated identity."
                                    if not SuppressionRule.query.filter_by(
                                        tenant_id=tenant_id, rule_type='identity', value=alert_record.identity
                                    ).first():
                                        rule = SuppressionRule(
                                            tenant_id=tenant_id, rule_type='identity', value=alert_record.identity
                                        )
                                        db.session.add(rule)
                                    audit = AuditLog(
                                        tenant_id=tenant_id,
                                        username="SOAR_BOT",
                                        action="Playbook Execution: Auto Isolate",
                                        target=alert_record.identity,
                                    )
                                    db.session.add(audit)
                                elif pb.action == 'create_ticket':
                                    if not alert_record.itsm_ticket:
                                        alert_record.itsm_ticket = "SOAR-" + str(10000 + random.randint(1, 9999))
                                    audit = AuditLog(
                                        tenant_id=tenant_id,
                                        username="SOAR_BOT",
                                        action="Playbook Execution: Create Ticket",
                                        target=alert_record.id,
                                    )
                                    db.session.add(audit)

                        if score > 0.90 and not alert_record.itsm_ticket:
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

                        if not existing_alert:
                            db.session.add(alert_record)
                        with state.lock:
                            state.history_cache[-1]["alert_id"] = alert_id
                            
            try:
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                logger.error(f"DB commit error in simulation thread: {e}")
                
        time.sleep(delay)

def _load_detectors(app):
    """Fit the detector stack for this process. Idempotent and safe to run in a thread.

    Every API-serving process needs detectors loaded to score events; this must NOT
    be gated behind generator leadership (otherwise non-leader workers can never score).
    """
    with state.lock:
        if state.pipe is not None and state.ensemble is not None:
            return

    logger.info("Loading detectors...")
    pipe, ensemble = load_stack()
    alerter = AlertOrchestrator(threshold=state.threshold, dry_run_webhook=True)
    servicenow = ServiceNowClient()

    # Prefer DB default tenant id when SIM_TENANT_ID is unset and a tenant exists.
    tenant_id = None
    with app.app_context():
        from models import Tenant
        env_tid = os.environ.get("SIM_TENANT_ID")
        if env_tid:
            tenant_id = int(env_tid)
        else:
            default_tenant = Tenant.query.filter_by(name='Default Tenant').first() or Tenant.query.first()
            if default_tenant:
                tenant_id = default_tenant.id

    with state.lock:
        state.pipe = pipe
        state.ensemble = ensemble
        state.alerter = alerter
        state.servicenow = servicenow
        if tenant_id is not None:
            state.sim_tenant_id = tenant_id

    logger.info("Detectors loaded (sim_tenant_id=%s).", state.sim_tenant_id)


def start_background_loop(app):
    # Explicit opt-out for tests: skip detectors and generator entirely.
    if os.environ.get("QUANTUM_SKIP_DETECTORS") == "1":
        logger.info("QUANTUM_SKIP_DETECTORS=1 — skipping detectors and event generator.")
        return

    # Detectors load in EVERY serving process (decoupled from generator leadership).
    # Done off the main thread so the server can bind immediately; /readyz reports
    # "starting" until state.pipe / state.ensemble are populated.
    threading.Thread(
        target=_load_detectors, args=(app,), daemon=True, name="detector-loader"
    ).start()

    # The synthetic event generator is single-leader across processes.
    # SIM_LEADER=0 → never generate; SIM_LEADER=1 → always try; unset → file lock.
    leader = os.environ.get("SIM_LEADER")
    if leader == "0":
        logger.info("SIM_LEADER=0 — detectors loading; event generator disabled in this process.")
        return

    with state.lock:
        if state._bg_started:
            logger.warning("Background loop already started in this process; skipping duplicate.")
            return

    lock_fh = None
    if leader != "1":
        # Cross-process advisory lock so only one gunicorn worker runs the generator.
        try:
            import fcntl
            lock_path = os.environ.get("SIM_LOCK_PATH", os.path.join(os.getcwd(), ".quantum_generator.lock"))
            lock_fh = open(lock_path, "w")
            fcntl.flock(lock_fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            lock_fh.write(str(os.getpid()))
            lock_fh.flush()
            state._generator_lock_fh = lock_fh
        except (BlockingIOError, OSError) as exc:
            if lock_fh:
                lock_fh.close()
            logger.info("Another process holds the generator lock (%s); detectors still load, generator skipped.", exc)
            return

    with state.lock:
        state._bg_started = True

    bg_thread = threading.Thread(target=event_generator_loop, args=(app,), daemon=True, name="event-generator")
    bg_thread.start()
