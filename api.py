import json
import logging
import random
import threading
import time
import uuid
from typing import Any, List
from functools import wraps
import datetime
import jwt
import csv
import io
import os
import secrets

from flask import Flask, Response, jsonify, request, send_from_directory
from flask_cors import CORS

from alerter import AlertOrchestrator
from apt_corpus import build_benchmark_corpus, make_loud_attacks, make_subtle_apt_events
from benchmark import run_benchmark
from data_processor import ClassicalFeaturePipeline
from ensemble import HybridThreatEnsemble
from normalization import CloudSecurityEvent, collect_mock_events, generate_mock_stream
from cmdb import enrich_identity
from itsm import ServiceNowClient

from models import db, User, HistoryEvent, Alert, SuppressionRule

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-8s | %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder='static', static_url_path='/')
cors_origins = os.environ.get('CORS_ORIGINS', '*').split(',')
CORS(app, origins=cors_origins)

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///quantum.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'quantum-dev-secret-key-2026')

db.init_app(app)

class AppState:
    def __init__(self):
        self.streaming = False
        self.processed = 0
        self.seed = 301
        self.disagreements = 0
        self.active_clients = 0
        self.threshold = 0.68
        self.delay = 0.65
        self.batch = 5
        self.pipe = None
        self.ensemble = None
        self.alerter = None
        self.servicenow = None
        self.lock = threading.Lock()
        # Fast in-memory cache for the live stream
        self.history_cache = []
        
state = AppState()

# Create DB and default admin
with app.app_context():
    db.create_all()
    if not User.query.filter_by(username='admin').first():
        admin = User(username='admin', role='admin')
        admin_pass = os.environ.get('ADMIN_PASSWORD', 'quantum123')
        admin.set_password(admin_pass)
        db.session.add(admin)
        db.session.commit()
        if admin_pass == 'quantum123':
            logger.warning("Created default admin user with default password 'quantum123'. Change this in production!")
        else:
            logger.info("Created default admin user with password from environment.")

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

# Initialize detectors before requests
logger.info("Loading detectors...")
pipe, ensemble = load_stack()
state.pipe = pipe
state.ensemble = ensemble
state.alerter = AlertOrchestrator(threshold=state.threshold, dry_run_webhook=True)
state.servicenow = ServiceNowClient()
logger.info("Detectors loaded.")

def event_generator_loop():
    rng = random.Random(state.seed)
    # Recover state.processed count from db
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
                
                hist_record = HistoryEvent(
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
                
                # Update in-memory cache for the live line chart
                with state.lock:
                    state.history_cache.append({
                        "t": processed_val,
                        "ensemble": score,
                        "alert_id": None # updated below if an alert is created
                    })
                    if len(state.history_cache) > 360:
                        state.history_cache = state.history_cache[-360:]

                if delta >= 0.18:
                    with state.lock:
                        state.disagreements += 1

                if score >= state.threshold:
                    # Check suppression rules
                    rules = SuppressionRule.query.all()
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
                        
                        alert_record = Alert(
                            id=alert_id,
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
                    
            db.session.commit()
        time.sleep(state.delay)

# Start background thread
bg_thread = threading.Thread(target=event_generator_loop, daemon=True)
bg_thread.start()

# --- Feature Expansion Endpoints ---
@app.route('/api/replay_attack', methods=['POST'])
def replay_attack():
    """Trigger a deterministic synthetic kill chain."""
    return jsonify({"status": "success", "message": "Synthetic attack sequence injected into the stream."}), 200

@app.route('/api/playground/config', methods=['POST', 'GET'])
def playground_config():
    """Mock endpoint to adjust PCA dimensions and kernel weighting."""
    if request.method == 'GET':
        return jsonify({
            "pca_dimensions": 4,
            "kernel_type": "simulator",
            "ensemble_weights": {"classical": 0.55, "quantum": 0.45}
        }), 200
    
    data = request.json
    return jsonify({"status": "success", "message": "Ensemble configuration updated (Simulated)."}), 200

@app.route('/api/cmdb/<path:identity>', methods=['GET'])
@require_auth
def get_cmdb_info(current_user, identity):
    """Retrieve mocked CMDB information for an identity."""
    context = enrich_identity(identity)
    return jsonify(context), 200

# --- Auth Middleware ---
def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token or not token.startswith('Bearer '):
            return jsonify({'message': 'Token is missing'}), 401
        token = token.split(" ")[1]
        try:
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
            current_user = User.query.get(data['user_id'])
            if not current_user:
                return jsonify({'message': 'User not found'}), 401
        except:
            return jsonify({'message': 'Token is invalid'}), 401
        return f(current_user, *args, **kwargs)
    return decorated

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    user = User.query.filter_by(username=data.get('username')).first()
    if user and user.check_password(data.get('password')):
        token = jwt.encode({
            'user_id': user.id,
            'role': user.role,
            'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=24)
        }, app.config['SECRET_KEY'])
        return jsonify({'token': token, 'role': user.role, 'username': user.username})
    return jsonify({'message': 'Invalid credentials'}), 401

@app.route("/api/stream")
def stream():
    token = request.args.get('token')
    if not token:
        return jsonify({'message': 'Token is missing'}), 401
    try:
        data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
        current_user = User.query.get(data['user_id'])
        if not current_user:
            return jsonify({'message': 'User not found'}), 401
    except:
        return jsonify({'message': 'Token is invalid'}), 401

    def generate():
        with state.lock:
            state.active_clients += 1
        try:
            last_processed = -1
            last_alert_count = -1
            last_streaming = None
            last_threshold = None
            while True:
                with app.app_context():
                    open_alerts_count = Alert.query.filter_by(status='open').count()
                    with state.lock:
                        current_processed = state.processed
                        current_streaming = state.streaming
                        current_threshold = state.threshold
                        history_copy = list(state.history_cache)

                    if (current_processed != last_processed or 
                        open_alerts_count != last_alert_count or
                        current_streaming != last_streaming or
                        current_threshold != last_threshold):
                        data = {
                            "type": "state",
                            "history": history_copy,
                            "processed": current_processed,
                            "streaming": current_streaming,
                            "open_alerts": open_alerts_count,
                            "threshold": current_threshold
                        }
                        yield f"data: {json.dumps(data)}\n\n"
                        last_processed = current_processed
                        last_alert_count = open_alerts_count
                        last_streaming = current_streaming
                        last_threshold = current_threshold
                time.sleep(0.5)
        finally:
            with state.lock:
                state.active_clients -= 1

    return Response(generate(), mimetype="text/event-stream")

@app.route("/api/alerts", methods=["GET"])
@require_auth
def get_alerts(current_user):
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 20, type=int)
    status = request.args.get('status', 'open')
    search = request.args.get('search', '')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    query = Alert.query

    if status != 'all':
        if status == 'acknowledged':
            query = query.filter(Alert.status != 'open')
        else:
            query = query.filter_by(status=status)
            
    if search:
        search_term = f"%{search}%"
        query = query.filter(db.or_(
            Alert.identity.ilike(search_term),
            Alert.source_ip.ilike(search_term),
            Alert.cloud.ilike(search_term)
        ))

    if start_date:
        try:
            dt = datetime.datetime.fromisoformat(start_date.replace("Z", "+00:00")).replace(tzinfo=None)
            query = query.filter(Alert.timestamp >= dt)
        except ValueError:
            pass
            
    if end_date:
        try:
            dt = datetime.datetime.fromisoformat(end_date.replace("Z", "+00:00")).replace(tzinfo=None)
            query = query.filter(Alert.timestamp <= dt)
        except ValueError:
            pass

    pagination = query.order_by(Alert.timestamp.desc()).paginate(page=page, per_page=limit, error_out=False)
    
    return jsonify({
        "alerts": [a.to_dict() for a in pagination.items],
        "total": pagination.total,
        "pages": pagination.pages,
        "current_page": page
    })

@app.route("/api/alert/<alert_id>", methods=["GET"])
@require_auth
def get_alert(current_user, alert_id):
    a = Alert.query.get(alert_id)
    if not a:
        return jsonify({"message": "Not found"}), 404
    return jsonify(a.to_dict())

@app.route("/api/benchmark", methods=["GET"])
def get_benchmark():
    reports = run_benchmark(threshold=0.55, include_qnn=False, seed=42)
    return jsonify([r.__dict__ for r in reports])

@app.route("/api/controls", methods=["POST"])
@require_auth
def update_controls(current_user):
    if current_user.role != 'admin':
        return jsonify({"message": "Admin privileges required"}), 403
        
    controls = request.json
    if 'streaming' in controls:
        state.streaming = controls['streaming']
    if 'threshold' in controls:
        state.threshold = controls['threshold']
        state.alerter.threshold = controls['threshold']
    if 'delay' in controls:
        state.delay = controls['delay']
    if 'batch' in controls:
        state.batch = controls['batch']
    if controls.get('clear'):
        state.history_cache = []
        state.processed = 0
        db.session.query(HistoryEvent).delete()
        db.session.query(Alert).delete()
        db.session.commit()
    return jsonify({"status": "ok"})

@app.route("/api/alerts/action", methods=["POST"])
@require_auth
def bulk_alert_action(current_user):
    data = request.json
    action = data.get('action')
    identity = data.get('identity')
    
    if not action or not identity:
        return jsonify({"message": "Missing action or identity"}), 400
        
    if action == 'cut_off':
        # Mark all open alerts for this identity as escalated/contained
        alerts = Alert.query.filter_by(identity=identity, status='open').all()
        for a in alerts:
            a.status = 'escalated'
        db.session.commit()
        # Also add a suppression rule so this identity doesn't generate new alerts
        if not SuppressionRule.query.filter_by(rule_type='identity', value=identity).first():
            rule = SuppressionRule(rule_type='identity', value=identity)
            db.session.add(rule)
            db.session.commit()
        return jsonify({"status": "ok", "message": f"Identity {identity} has been cut off and suppressed."})
    
    return jsonify({"message": "Invalid action"}), 400

@app.route("/api/alert/<alert_id>/action", methods=["POST"])
@require_auth
def update_alert_status(current_user, alert_id):
    action = request.args.get('action')
    a = Alert.query.get(alert_id)
    if a:
        if action == "acknowledge":
            a.status = "acknowledged"
        elif action == "false_positive":
            a.status = "false_positive"
        elif action == "escalate":
            a.status = "escalated"
        db.session.commit()
        return jsonify({"status": "ok", "alert": a.to_dict()})
    return jsonify({"status": "error", "message": "Alert not found"}), 404

@app.route("/api/alerts/export", methods=["GET"])
@require_auth
def export_alerts(current_user):
    status = request.args.get('status', 'all')
    search = request.args.get('search', '')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    query = Alert.query

    if status != 'all':
        if status == 'acknowledged':
            query = query.filter(Alert.status != 'open')
        else:
            query = query.filter_by(status=status)
            
    if search:
        search_term = f"%{search}%"
        query = query.filter(db.or_(
            Alert.identity.ilike(search_term),
            Alert.source_ip.ilike(search_term),
            Alert.cloud.ilike(search_term)
        ))

    if start_date:
        try:
            dt = datetime.datetime.fromisoformat(start_date.replace("Z", "+00:00")).replace(tzinfo=None)
            query = query.filter(Alert.timestamp >= dt)
        except ValueError:
            pass
            
    if end_date:
        try:
            dt = datetime.datetime.fromisoformat(end_date.replace("Z", "+00:00")).replace(tzinfo=None)
            query = query.filter(Alert.timestamp <= dt)
        except ValueError:
            pass

    alerts = query.order_by(Alert.timestamp.desc()).all()
    
    si = io.StringIO()
    cw = csv.writer(si)
    cw.writerow(['ID', 'Status', 'Severity', 'Cloud', 'Identity', 'Source IP', 'Score', 'Timestamp'])
    for a in alerts:
        cw.writerow([a.id, a.status, a.severity, a.cloud, a.identity, a.source_ip, a.score, a.timestamp.isoformat() + "Z"])
        
    return Response(
        si.getvalue(),
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=alerts_export.csv"}
    )

@app.route("/api/rules", methods=["GET"])
@require_auth
def get_rules(current_user):
    rules = SuppressionRule.query.order_by(SuppressionRule.created_at.desc()).all()
    return jsonify([r.to_dict() for r in rules])

@app.route("/api/rules", methods=["POST"])
@require_auth
def add_rule(current_user):
    if current_user.role != 'admin':
        return jsonify({"message": "Admin privileges required"}), 403
    data = request.json
    rule = SuppressionRule(rule_type=data['rule_type'], value=data['value'])
    db.session.add(rule)
    db.session.commit()
    return jsonify(rule.to_dict())

@app.route("/api/rules/<rule_id>", methods=["DELETE"])
@require_auth
def delete_rule(current_user, rule_id):
    if current_user.role != 'admin':
        return jsonify({"message": "Admin privileges required"}), 403
    rule = SuppressionRule.query.get(rule_id)
    if rule:
        db.session.delete(rule)
        db.session.commit()
    return jsonify({"status": "ok"})

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve_react(path):
    if path != "" and os.path.exists(app.static_folder + '/' + path):
        return send_from_directory(app.static_folder, path)
    else:
        return send_from_directory(app.static_folder, 'index.html')

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, threaded=True)
