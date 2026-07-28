import uuid
import datetime
import json
import jwt
import csv
import io
import time
import os
import threading
from collections import defaultdict
from functools import wraps
from flask import Blueprint, request, jsonify, Response, current_app
from models import db, User, Alert, HistoryEvent, SuppressionRule
from state import state
from benchmark import run_benchmark
from cmdb import enrich_identity

api_bp = Blueprint('api', __name__)

ADMIN_ROLES = ('SUPER_ADMIN', 'TENANT_ADMIN')
ANALYST_WRITE_ROLES = ('SUPER_ADMIN', 'TENANT_ADMIN', 'TIER_1', 'TIER_2')


def _tenant_scope_query(model, current_user):
    """
    Tenant isolation for MSP surfaces.
    - Default: only the caller's tenant.
    - SUPER_ADMIN may pass scope=all (optional tenant_id=) to see every customer.
    """
    scope = (request.args.get('scope') or 'mine').lower()
    tenant_id = request.args.get('tenant_id', type=int)
    if current_user.role == 'SUPER_ADMIN' and scope == 'all':
        q = model.query
        if tenant_id:
            q = q.filter_by(tenant_id=tenant_id)
        return q
    return model.query.filter_by(tenant_id=current_user.tenant_id)

# Simple in-memory login rate limiter: key -> list of failure timestamps
_login_failures = defaultdict(list)
_login_lock = threading.Lock()
_LOGIN_WINDOW_SEC = 300
_LOGIN_MAX_FAILURES = 8


def _client_ip():
    forwarded = request.headers.get('X-Forwarded-For', '')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.remote_addr or 'unknown'


def _login_rate_limited(username: str) -> bool:
    key = f"{_client_ip()}:{username or ''}"
    now = time.time()
    with _login_lock:
        stamps = [t for t in _login_failures[key] if now - t < _LOGIN_WINDOW_SEC]
        _login_failures[key] = stamps
        return len(stamps) >= _LOGIN_MAX_FAILURES


def _record_login_failure(username: str) -> None:
    key = f"{_client_ip()}:{username or ''}"
    with _login_lock:
        _login_failures[key].append(time.time())


def _clear_login_failures(username: str) -> None:
    key = f"{_client_ip()}:{username or ''}"
    with _login_lock:
        _login_failures.pop(key, None)


def _resolve_user_from_token(allowed_types, *, allow_query_token=False):
    """Decode a Bearer/query JWT and return (user, error_response).

    Query-string tokens are only accepted when ``allow_query_token`` is True
    (SSE stream endpoint). All other APIs require an Authorization header.
    """
    token = request.headers.get('Authorization')
    if token and token.startswith('Bearer '):
        token = token.split(" ", 1)[1]
    elif allow_query_token:
        token = request.args.get('token')
    else:
        token = None
    if not token:
        return None, (jsonify({'message': 'Token is missing'}), 401)
    try:
        data = jwt.decode(token, current_app.config['SECRET_KEY'], algorithms=["HS256"])
        token_type = data.get('type') or 'session'
        if token_type not in allowed_types:
            return None, (jsonify({'message': 'Token type not allowed for this endpoint'}), 401)
        current_user = User.query.get(data['user_id'])
        if not current_user:
            return None, (jsonify({'message': 'User not found'}), 401)
        if not current_user.is_active:
            return None, (jsonify({'message': 'Account is deactivated'}), 403)
        if token_type == 'session':
            claimed = data.get('tv', 0)
            if int(claimed) != int(current_user.token_version or 0):
                return None, (jsonify({'message': 'Session has been revoked. Sign in again.'}), 401)
        return current_user, None
    except jwt.PyJWTError:
        return None, (jsonify({'message': 'Token is invalid'}), 401)


# Paths allowed while must_change_password is set (self-service only).
_PASSWORD_CHANGE_ALLOWLIST = (
    '/api/me',
    '/api/me/password',
    '/api/mfa/status',
)


def require_role(allowed_roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(current_user, *args, **kwargs):
            if current_user.role not in allowed_roles and current_user.role != 'SUPER_ADMIN':
                return jsonify({'message': 'Permission denied'}), 403
            return f(current_user, *args, **kwargs)
        return decorated_function
    return decorator

def require_auth(f):
    """Require a session JWT. Rejects mfa_temp and stream tokens (MFA bypass guard)."""
    @wraps(f)
    def decorated(*args, **kwargs):
        current_user, error = _resolve_user_from_token(('session',))
        if error:
            return error
        if current_user.must_change_password:
            path = request.path.rstrip('/') or request.path
            if path not in _PASSWORD_CHANGE_ALLOWLIST and not path.startswith('/api/mfa/'):
                return jsonify({
                    'message': 'Password change required before continuing.',
                    'must_change_password': True,
                }), 403
        return f(current_user, *args, **kwargs)
    return decorated


def require_stream_auth(f):
    """Auth for SSE: accepts session JWT or short-lived stream ticket (query token OK)."""
    @wraps(f)
    def decorated(*args, **kwargs):
        current_user, error = _resolve_user_from_token(('session', 'stream'), allow_query_token=True)
        if error:
            return error
        return f(current_user, *args, **kwargs)
    return decorated


def _session_token(user):
    return jwt.encode({
        'user_id': user.id,
        'role': user.role,
        'type': 'session',
        'tv': int(user.token_version or 0),
        'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=12)
    }, current_app.config['SECRET_KEY'])

def _login_payload(user):
    return {
        'token': _session_token(user),
        'role': user.role,
        'username': user.username,
        'must_change_password': bool(user.must_change_password),
    }

@api_bp.route('/api/login', methods=['POST'])
def login():
    data = request.json or {}
    username = (data.get('username') or '').strip()
    if _login_rate_limited(username):
        return jsonify({'message': 'Too many failed attempts. Try again in a few minutes.'}), 429

    user = User.query.filter_by(username=username).first()
    if user and user.check_password(data.get('password')):
        if not user.is_active:
            return jsonify({'message': 'This account has been deactivated. Contact an administrator.'}), 403
        _clear_login_failures(username)
        from models import UserSecurity
        user_sec = UserSecurity.query.filter_by(user_id=user.id).first()
        
        if user_sec and (user_sec.mfa_enabled or user_sec.webauthn_enabled):
            temp_token = jwt.encode({
                'user_id': user.id,
                'type': 'mfa_temp',
                'exp': datetime.datetime.utcnow() + datetime.timedelta(minutes=10)
            }, current_app.config['SECRET_KEY'])
            return jsonify({
                'mfa_required': True, 
                'temp_token': temp_token,
                'totp_enabled': user_sec.mfa_enabled,
                'webauthn_enabled': user_sec.webauthn_enabled
            })
            
        token = _session_token(user)
        user.last_login_at = datetime.datetime.utcnow()
        db.session.commit()
        return jsonify(_login_payload(user))
    _record_login_failure(username)
    return jsonify({'message': 'Invalid credentials'}), 401

@api_bp.route('/api/stream/ticket', methods=['POST'])
@require_auth
def stream_ticket(current_user):
    """Mint a short-lived token for EventSource (avoids putting the session JWT in logs)."""
    ticket = jwt.encode({
        'user_id': current_user.id,
        'type': 'stream',
        'exp': datetime.datetime.utcnow() + datetime.timedelta(minutes=2)
    }, current_app.config['SECRET_KEY'])
    return jsonify({'token': ticket, 'expires_in': 120})

@api_bp.route('/api/replay_attack', methods=['POST'])
@require_auth
@require_role(list(ADMIN_ROLES))
def replay_attack(current_user):
    from simulation import enqueue_replay
    from models import Tenant
    data = request.json or {}
    kind = data.get('kind', 'mixed')
    if kind not in ('mixed', 'loud', 'subtle'):
        return jsonify({"message": "kind must be mixed, loud, or subtle"}), 400
    try:
        count = max(1, min(30, int(data.get('count', 8))))
    except (TypeError, ValueError):
        return jsonify({"message": "Invalid count"}), 400

    # Stamp simulation onto the operator's tenant so MSP demos land on the right customer.
    target_tenant_id = current_user.tenant_id
    if current_user.role == 'SUPER_ADMIN' and data.get('tenant_id') is not None:
        try:
            target_tenant_id = int(data['tenant_id'])
        except (TypeError, ValueError):
            return jsonify({"message": "Invalid tenant_id"}), 400
        if not Tenant.query.get(target_tenant_id):
            return jsonify({"message": "Unknown tenant"}), 404

    with state.lock:
        state.sim_tenant_id = int(target_tenant_id)

    queued = enqueue_replay(kind=kind, count=count)
    tenant = Tenant.query.get(target_tenant_id)
    from models import AuditLog
    db.session.add(AuditLog(
        tenant_id=target_tenant_id,
        username=current_user.username,
        action=f"Replay attack queued ({kind})",
        target=str(queued),
    ))
    db.session.commit()
    return jsonify({
        "status": "success",
        "message": (
            f"Queued {queued} synthetic attack events for tenant "
            f"'{tenant.name if tenant else target_tenant_id}'."
        ),
        "queued": queued,
        "tenant_id": target_tenant_id,
        "tenant_name": tenant.name if tenant else None,
    }), 200

@api_bp.route('/api/playground/config', methods=['POST', 'GET'])
@require_auth
def playground_config(current_user):
    from simulation import apply_playground_config
    if request.method == 'GET':
        with state.lock:
            cfg = dict(state.playground)
        return jsonify(cfg), 200

    if current_user.role not in ADMIN_ROLES and current_user.role != 'SUPER_ADMIN':
        return jsonify({'message': 'Permission denied'}), 403

    data = request.json or {}
    applied = apply_playground_config(data)
    from models import AuditLog
    db.session.add(AuditLog(
        tenant_id=current_user.tenant_id,
        username=current_user.username,
        action="Updated playground config",
        target=json.dumps(applied.get('ensemble_weights', {})),
    ))
    db.session.commit()
    return jsonify({"status": "success", "message": "Ensemble configuration updated.", "config": applied}), 200

@api_bp.route('/api/cmdb/<path:identity>', methods=['GET'])
@require_auth
def get_cmdb_info(current_user, identity):
    context = enrich_identity(identity)
    return jsonify(context), 200

@api_bp.route("/api/stream")
@require_stream_auth
def stream(current_user):
    def generate():
        with state.lock:
            state.active_clients += 1
        try:
            last_processed = -1
            last_alert_count = -1
            last_streaming = None
            last_threshold = None
            while True:
                # We need app_context for db queries
                from flask import current_app
                open_alerts_count = 0
                if current_app:
                    open_alerts_count = Alert.query.filter_by(tenant_id=current_user.tenant_id, status='open').count()
                
                with state.lock:
                    current_processed = state.processed
                    current_streaming = state.streaming
                    current_threshold = state.threshold
                    history_copy = list(state.history_cache)

                if (current_processed != last_processed or 
                    open_alerts_count != last_alert_count or
                    current_streaming != last_streaming or
                    current_threshold != last_threshold):
                    data_out = {
                        "type": "state",
                        "history": history_copy,
                        "processed": current_processed,
                        "streaming": current_streaming,
                        "open_alerts": open_alerts_count,
                        "threshold": current_threshold
                    }
                    yield f"data: {json.dumps(data_out)}\n\n"
                    last_processed = current_processed
                    last_alert_count = open_alerts_count
                    last_streaming = current_streaming
                    last_threshold = current_threshold
                time.sleep(0.5)
        finally:
            with state.lock:
                state.active_clients -= 1

    return Response(generate(), mimetype="text/event-stream")

@api_bp.route("/api/alerts", methods=["GET"])
@require_auth
def get_alerts(current_user):
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 20, type=int)
    status = request.args.get('status', 'open')
    search = request.args.get('search', '')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    assignee = request.args.get('assignee')

    query = _tenant_scope_query(Alert, current_user)

    if status != 'all':
        query = query.filter_by(status=status)

    if assignee == 'me':
        query = query.filter_by(assignee_id=current_user.id)
    elif assignee == 'unassigned':
        query = query.filter(Alert.assignee_id.is_(None))

    if search:
        search_term = f"%{search}%"
        query = query.filter(db.or_(
            Alert.identity.ilike(search_term),
            Alert.source_ip.ilike(search_term),
            Alert.cloud.ilike(search_term),
            Alert.short_identity.ilike(search_term),
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

@api_bp.route("/api/alert/<alert_id>", methods=["GET"])
@require_auth
def get_alert(current_user, alert_id):
    if current_user.role == 'SUPER_ADMIN' and (request.args.get('scope') or '').lower() == 'all':
        a = Alert.query.filter_by(id=alert_id).first()
    else:
        a = Alert.query.filter_by(id=alert_id, tenant_id=current_user.tenant_id).first()
    if not a:
        return jsonify({"message": "Not found"}), 404
    return jsonify(a.to_dict())

@api_bp.route("/api/benchmark", methods=["GET"])
@require_auth
def get_benchmark_route(current_user):
    reports = run_benchmark(threshold=0.55, include_qnn=False, seed=42)
    return jsonify([r.__dict__ for r in reports])

@api_bp.route("/api/analytics/overview", methods=["GET"])
@require_auth
def analytics_overview(current_user):
    """Live PCA sample, latency stats, and detector-disagreement alerts."""
    import numpy as np
    from apt_corpus import build_benchmark_corpus
    from normalization import collect_mock_events

    # Feature-space sample from the fitted pipeline (or synthetic fallback).
    scatter = []
    if state.pipe is not None and state.pipe.is_fitted:
        try:
            warmup = collect_mock_events(40, seed=7)
            extra, extra_y, _ = build_benchmark_corpus(n_normal=20, n_loud=6, n_subtle=8, seed=11)
            events = warmup + extra
            labels = np.concatenate([
                np.zeros(len(warmup)),
                extra_y,
            ])
            feats = state.pipe.transform(events)
            for i, row in enumerate(feats):
                scatter.append({
                    "x": float(row[0]),
                    "y": float(row[1]) if len(row) > 1 else 0.0,
                    "z": float(abs(row[2])) * 100 + 60 if len(row) > 2 else 100.0,
                    "type": "anomaly" if float(labels[i]) >= 0.5 else "normal",
                })
        except Exception as exc:
            current_app.logger.warning("analytics feature space failed: %s", exc)

    # Latency from recent history for this tenant
    hist = (
        HistoryEvent.query
        .filter_by(tenant_id=current_user.tenant_id)
        .order_by(HistoryEvent.t.desc())
        .limit(200)
        .all()
    )
    latencies = [h.latency_ms for h in hist if h.latency_ms is not None]
    latency_stats = {
        "samples": len(latencies),
        "mean_ms": round(float(np.mean(latencies)), 3) if latencies else 0.0,
        "p95_ms": round(float(np.percentile(latencies, 95)), 3) if latencies else 0.0,
        "max_ms": round(float(np.max(latencies)), 3) if latencies else 0.0,
    }
    # Approximate per-engine cost from last known scoring (ensemble latency is total)
    latency_bars = [
        {"name": "Ensemble (end-to-end)", "cost_ms": latency_stats["mean_ms"], "type": "Hybrid"},
        {"name": "Isolation Forest", "cost_ms": round(latency_stats["mean_ms"] * 0.05, 3), "type": "Classical"},
        {"name": "Classical SVM", "cost_ms": round(latency_stats["mean_ms"] * 0.1, 3), "type": "Classical"},
        {"name": "Quantum Kernel (Sim)", "cost_ms": round(latency_stats["mean_ms"] * 0.85, 3), "type": "Quantum"},
    ]

    disagree_q = _tenant_scope_query(Alert, current_user).filter(Alert.disagreement.isnot(None))
    disagree_alerts = (
        disagree_q
        .order_by(Alert.timestamp.desc())
        .limit(25)
        .all()
    )
    disagreements = []
    for a in disagree_alerts:
        delta = abs(float(a.quantum_kernel) - float(a.classical_svm))
        disagreements.append({
            "id": a.id,
            "tenant_id": a.tenant_id,
            "tenant_name": a.tenant.name if a.tenant else None,
            "identity": a.identity,
            "short_identity": a.short_identity,
            "classical_svm": a.classical_svm,
            "quantum_kernel": a.quantum_kernel,
            "delta": round(delta, 3),
            "status": a.status,
            "severity": a.severity,
            "disagreement": a.disagreement,
            "timestamp": a.timestamp.isoformat() + "Z",
        })

    with state.lock:
        disagreement_count = state.disagreements

    return jsonify({
        "feature_space": scatter,
        "latency": latency_bars,
        "latency_stats": latency_stats,
        "disagreements": disagreements,
        "disagreement_count": disagreement_count,
    })

@api_bp.route("/api/controls", methods=["POST"])
@require_auth
@require_role(list(ADMIN_ROLES))
def update_controls(current_user):
    controls = request.json or {}
    with state.lock:
        if 'streaming' in controls:
            state.streaming = bool(controls['streaming'])
        if 'threshold' in controls:
            try:
                state.threshold = float(controls['threshold'])
            except (TypeError, ValueError):
                return jsonify({"message": "Invalid threshold"}), 400
            if state.alerter:
                state.alerter.threshold = state.threshold
        if 'delay' in controls:
            try:
                state.delay = max(0.05, float(controls['delay']))
            except (TypeError, ValueError):
                return jsonify({"message": "Invalid delay"}), 400
        if 'batch' in controls:
            try:
                state.batch = max(1, int(controls['batch']))
            except (TypeError, ValueError):
                return jsonify({"message": "Invalid batch"}), 400
        if controls.get('clear'):
            state.history_cache = []
            state.processed = 0
            db.session.query(HistoryEvent).filter_by(tenant_id=current_user.tenant_id).delete()
            db.session.query(Alert).filter_by(tenant_id=current_user.tenant_id).delete()
            db.session.commit()
    return jsonify({"status": "ok"})

@api_bp.route("/api/alerts/action", methods=["POST"])
@require_auth
@require_role(['SUPER_ADMIN', 'TENANT_ADMIN', 'TIER_1', 'TIER_2'])
def bulk_alert_action(current_user):
    data = request.json
    action = data.get('action')
    identity = data.get('identity')
    
    if not action or not identity:
        return jsonify({"message": "Missing action or identity"}), 400
        
    if action == 'cut_off':
        alerts = Alert.query.filter_by(
            tenant_id=current_user.tenant_id, identity=identity, status='open'
        ).all()
        for a in alerts:
            a.status = 'escalated'
        db.session.commit()
        if not SuppressionRule.query.filter_by(tenant_id=current_user.tenant_id, rule_type='identity', value=identity).first():
            rule = SuppressionRule(tenant_id=current_user.tenant_id, rule_type='identity', value=identity)
            db.session.add(rule)
            
        from models import AuditLog
        audit = AuditLog(tenant_id=current_user.tenant_id, username=current_user.username, action="Cut Off Identity", target=identity)
        db.session.add(audit)
        db.session.commit()
        return jsonify({"status": "ok", "message": f"Identity {identity} has been cut off and suppressed."})
    
    return jsonify({"message": "Invalid action"}), 400

@api_bp.route("/api/alert/<alert_id>/action", methods=["POST"])
@require_auth
@require_role(list(ANALYST_WRITE_ROLES))
def update_alert_status(current_user, alert_id):
    action = request.args.get('action') or (request.json or {}).get('action')
    a = Alert.query.filter_by(id=alert_id, tenant_id=current_user.tenant_id).first()
    if not a:
        return jsonify({"status": "error", "message": "Alert not found"}), 404

    case_id = None
    if action == "acknowledge":
        a.status = "acknowledged"
        if not a.assignee_id:
            a.assignee_id = current_user.id
    elif action == "false_positive":
        a.status = "false_positive"
    elif action == "escalate":
        if a.case_id:
            return jsonify({
                "status": "ok",
                "alert": a.to_dict(),
                "case_id": a.case_id,
                "message": f"Already linked to CASE-{a.case_id:04d}",
            })
        a.status = "escalated"
        a.assignee_id = current_user.id
        from models import IncidentCase, CaseComment
        case = IncidentCase(
            tenant_id=current_user.tenant_id,
            title=f"Escalated: {a.short_identity} ({a.attack_phase or a.severity})",
            priority='High' if a.score >= 0.85 else 'Medium',
            assignee_id=current_user.id,
            status='Open',
        )
        db.session.add(case)
        db.session.flush()
        a.case_id = case.id
        case_id = case.id
        db.session.add(CaseComment(
            case_id=case.id,
            user_id=current_user.id,
            content=f"Escalated from alert {a.id} by {current_user.username}. Score={a.score:.2f}.",
        ))
    elif action == "claim":
        a.assignee_id = current_user.id
        if a.status == 'open':
            a.status = 'acknowledged'
    elif action == "release":
        if a.assignee_id not in (None, current_user.id) and current_user.role not in ADMIN_ROLES:
            return jsonify({"message": "Only the assignee or an admin can release this alert"}), 403
        a.assignee_id = None
    else:
        return jsonify({"status": "error", "message": "Invalid action"}), 400

    from models import AuditLog
    db.session.add(AuditLog(
        tenant_id=current_user.tenant_id,
        username=current_user.username,
        action=f"Alert {action}",
        target=alert_id,
    ))
    db.session.commit()
    payload = {"status": "ok", "alert": a.to_dict()}
    if case_id:
        payload["case_id"] = case_id
        payload["message"] = f"Escalated into CASE-{case_id:04d}"
    return jsonify(payload)

@api_bp.route("/api/alerts/export", methods=["GET"])
@require_auth
def export_alerts(current_user):
    status = request.args.get('status', 'all')
    search = request.args.get('search', '')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    assignee = request.args.get('assignee')

    query = _tenant_scope_query(Alert, current_user)

    if status != 'all':
        query = query.filter_by(status=status)

    if assignee == 'me':
        query = query.filter_by(assignee_id=current_user.id)
    elif assignee == 'unassigned':
        query = query.filter(Alert.assignee_id.is_(None))
            
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

    alerts = query.order_by(Alert.timestamp.desc()).limit(5000).all()
    
    si = io.StringIO()
    cw = csv.writer(si)
    cw.writerow(['ID', 'Tenant', 'Tenant ID', 'Status', 'Severity', 'Cloud', 'Identity', 'Source IP', 'Score', 'Assignee', 'Timestamp'])
    for a in alerts:
        cw.writerow([
            a.id,
            a.tenant.name if a.tenant else '',
            a.tenant_id,
            a.status,
            a.severity,
            a.cloud,
            a.identity,
            a.source_ip,
            a.score,
            a.assignee_id or '',
            a.timestamp.isoformat() + "Z",
        ])
        
    return Response(
        si.getvalue(),
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=alerts_export.csv"}
    )

@api_bp.route("/api/rules", methods=["GET"])
@require_auth
def get_rules(current_user):
    rules = (
        SuppressionRule.query
        .filter_by(tenant_id=current_user.tenant_id)
        .order_by(SuppressionRule.created_at.desc())
        .all()
    )
    return jsonify([r.to_dict() for r in rules])

@api_bp.route("/api/rules", methods=["POST"])
@require_auth
@require_role(list(ADMIN_ROLES))
def add_rule(current_user):
    data = request.json or {}
    rule_type = data.get('rule_type')
    value = data.get('value')
    if not rule_type or not value:
        return jsonify({"message": "rule_type and value are required"}), 400
    if rule_type not in ('identity', 'ip', 'cloud'):
        return jsonify({"message": "Invalid rule_type"}), 400
    rule = SuppressionRule(tenant_id=current_user.tenant_id, rule_type=rule_type, value=value)
    db.session.add(rule)
    db.session.commit()
    return jsonify(rule.to_dict())

@api_bp.route("/api/rules/<rule_id>", methods=["DELETE"])
@require_auth
@require_role(list(ADMIN_ROLES))
def delete_rule(current_user, rule_id):
    rule = SuppressionRule.query.filter_by(id=rule_id, tenant_id=current_user.tenant_id).first()
    if rule:
        db.session.delete(rule)
        db.session.commit()
    return jsonify({"status": "ok"})

import pyotp
import qrcode
import base64
from io import BytesIO
from flask import session
from webauthn import (
    generate_registration_options,
    verify_registration_response,
    generate_authentication_options,
    verify_authentication_response,
    options_to_json,
    base64url_to_bytes,
)
from webauthn.helpers.structs import (
    AttestationConveyancePreference,
    AuthenticatorSelectionCriteria,
    AuthenticatorAttachment,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)
from models import UserSecurity, WebAuthnCredential

RP_ID = os.environ.get('WEBAUTHN_RP_ID', 'localhost')
RP_ORIGIN = os.environ.get('WEBAUTHN_RP_ORIGIN', 'http://localhost:5173')
RP_NAME = os.environ.get('WEBAUTHN_RP_NAME', 'Quantum Helix')

@api_bp.route('/api/mfa/setup-totp', methods=['POST'])
@require_auth
def setup_totp(current_user):
    user_sec = UserSecurity.query.filter_by(user_id=current_user.id).first()
    if not user_sec:
        user_sec = UserSecurity(user_id=current_user.id)
        db.session.add(user_sec)
    
    secret = pyotp.random_base32()
    user_sec.totp_secret = secret
    db.session.commit()
    
    totp = pyotp.TOTP(secret)
    provisioning_uri = totp.provisioning_uri(name=current_user.username, issuer_name=RP_NAME)
    
    img = qrcode.make(provisioning_uri)
    buffered = BytesIO()
    img.save(buffered, format="PNG")
    img_str = base64.b64encode(buffered.getvalue()).decode()
    
    return jsonify({"qr_code": img_str, "secret": secret})

@api_bp.route('/api/mfa/verify-totp', methods=['POST'])
@require_auth
def verify_totp(current_user):
    data = request.json
    code = data.get('code')
    
    user_sec = UserSecurity.query.filter_by(user_id=current_user.id).first()
    if not user_sec or not user_sec.totp_secret:
        return jsonify({"message": "TOTP not setup"}), 400
        
    totp = pyotp.TOTP(user_sec.totp_secret)
    if totp.verify(code):
        user_sec.mfa_enabled = True
        db.session.commit()
        return jsonify({"message": "TOTP verified and MFA enabled"})
    return jsonify({"message": "Invalid code"}), 400

@api_bp.route('/api/mfa/register-webauthn', methods=['POST'])
@require_auth
def register_webauthn(current_user):
    options = generate_registration_options(
        rp_id=RP_ID,
        rp_name=RP_NAME,
        user_id=str(current_user.id).encode(),
        user_name=current_user.username,
        authenticator_selection=AuthenticatorSelectionCriteria(
            user_verification=UserVerificationRequirement.PREFERRED
        )
    )
    session['webauthn_registration_challenge'] = options.challenge
    return Response(options_to_json(options), mimetype='application/json')

@api_bp.route('/api/mfa/verify-webauthn-registration', methods=['POST'])
@require_auth
def verify_webauthn_registration(current_user):
    data = request.json
    challenge = session.get('webauthn_registration_challenge')
    if not challenge:
        return jsonify({"message": "No challenge found"}), 400
        
    try:
        verification = verify_registration_response(
            credential=data,
            expected_challenge=challenge,
            expected_rp_id=RP_ID,
            expected_origin=RP_ORIGIN,
        )
        
        user_sec = UserSecurity.query.filter_by(user_id=current_user.id).first()
        if not user_sec:
            user_sec = UserSecurity(user_id=current_user.id)
            db.session.add(user_sec)
        user_sec.webauthn_enabled = True
        
        cred = WebAuthnCredential(
            id=verification.credential_id.hex(),
            user_id=current_user.id,
            public_key=verification.credential_public_key,
            sign_count=verification.sign_count
        )
        db.session.add(cred)
        db.session.commit()
        
        return jsonify({"message": "Hardware key registered!"})
    except Exception as e:
        return jsonify({"message": f"Verification failed: {str(e)}"}), 400

@api_bp.route('/api/login/mfa', methods=['POST'])
def login_mfa():
    data = request.json or {}
    temp_token = data.get('temp_token')
    
    try:
        token_data = jwt.decode(temp_token, current_app.config['SECRET_KEY'], algorithms=["HS256"])
        if token_data.get('type') != 'mfa_temp':
            return jsonify({'message': 'Invalid token type'}), 401
        user = User.query.get(token_data['user_id'])
        if not user:
            return jsonify({'message': 'User not found'}), 401
        if not user.is_active:
            return jsonify({'message': 'This account has been deactivated. Contact an administrator.'}), 403
    except jwt.PyJWTError:
        return jsonify({'message': 'Invalid or expired temporary token'}), 401

    user_sec = UserSecurity.query.filter_by(user_id=user.id).first()
    
    # Handle TOTP Verification
    if data.get('type') == 'totp':
        if not user_sec or not user_sec.totp_secret:
            return jsonify({'message': 'TOTP not configured'}), 400
        totp = pyotp.TOTP(user_sec.totp_secret)
        if not totp.verify(data.get('code')):
            return jsonify({'message': 'Invalid TOTP code'}), 401
            
    # Handle WebAuthn Verification
    elif data.get('type') == 'webauthn':
        challenge = session.get('webauthn_auth_challenge')
        credential = data.get('credential') or {}
        cred_id = credential.get('id')
        if not cred_id:
            return jsonify({'message': 'Credential id required'}), 400
        cred = WebAuthnCredential.query.filter_by(id=cred_id, user_id=user.id).first()
        if not cred:
            return jsonify({'message': 'Credential not found'}), 401
            
        try:
            verification = verify_authentication_response(
                credential=credential,
                expected_challenge=challenge,
                expected_rp_id=RP_ID,
                expected_origin=RP_ORIGIN,
                credential_public_key=cred.public_key,
                credential_current_sign_count=cred.sign_count,
            )
            cred.sign_count = verification.new_sign_count
            db.session.commit()
        except Exception as e:
            return jsonify({'message': f'WebAuthn failed: {str(e)}'}), 401
    else:
        return jsonify({'message': 'Invalid MFA type'}), 400
        
    # Issue real session token
    user.last_login_at = datetime.datetime.utcnow()
    db.session.commit()
    return jsonify(_login_payload(user))

@api_bp.route('/api/login/webauthn-options', methods=['POST'])
def login_webauthn_options():
    data = request.json or {}
    temp_token = data.get('temp_token')
    try:
        token_data = jwt.decode(temp_token, current_app.config['SECRET_KEY'], algorithms=["HS256"])
        if token_data.get('type') != 'mfa_temp':
            return jsonify({'message': 'Invalid token type'}), 401
        user = User.query.get(token_data['user_id'])
        if not user:
            return jsonify({'message': 'User not found'}), 401
    except jwt.PyJWTError:
        return jsonify({'message': 'Invalid or expired temporary token'}), 401
        
    creds = WebAuthnCredential.query.filter_by(user_id=user.id).all()
    if not creds:
        return jsonify({'message': 'No hardware keys found'}), 400
        
    options = generate_authentication_options(
        rp_id=RP_ID,
        allow_credentials=[
            {"type": "public-key", "id": bytes.fromhex(c.id)} for c in creds
        ]
    )
    session['webauthn_auth_challenge'] = options.challenge
    return Response(options_to_json(options), mimetype='application/json')

@api_bp.route('/api/mfa/status', methods=['GET'])
@require_auth
def mfa_status(current_user):
    user_sec = UserSecurity.query.filter_by(user_id=current_user.id).first()
    return jsonify({'totp_enabled': user_sec.mfa_enabled if user_sec else False, 'webauthn_enabled': user_sec.webauthn_enabled if user_sec else False})

from models import PlaybookRule, AuditLog

@api_bp.route("/api/playbooks", methods=["GET"])
@require_auth
def get_playbooks(current_user):
    rules = PlaybookRule.query.filter_by(tenant_id=current_user.tenant_id).order_by(PlaybookRule.created_at.desc()).all()
    return jsonify([r.to_dict() for r in rules])

@api_bp.route("/api/playbooks", methods=["POST"])
@require_auth
@require_role(list(ADMIN_ROLES))
def create_playbook(current_user):
    data = request.json or {}
    condition_field = data.get('condition_field')
    condition_operator = data.get('condition_operator')
    condition_value = data.get('condition_value')
    action = data.get('action')
    allowed_fields = ('score', 'ensemble', 'quantum_kernel', 'classical_svm', 'isolation_forest', 'attack_phase', 'severity')
    allowed_ops = ('>', '<', '==')
    allowed_actions = ('auto_isolate', 'create_ticket')
    if condition_field not in allowed_fields:
        return jsonify({"message": f"condition_field must be one of {allowed_fields}"}), 400
    if condition_operator not in allowed_ops:
        return jsonify({"message": f"condition_operator must be one of {allowed_ops}"}), 400
    if action not in allowed_actions:
        return jsonify({"message": f"action must be one of {allowed_actions}"}), 400
    if condition_value is None or condition_value == '':
        return jsonify({"message": "condition_value is required"}), 400
    rule = PlaybookRule(
        tenant_id=current_user.tenant_id,
        condition_field=condition_field,
        condition_operator=condition_operator,
        condition_value=str(condition_value),
        action=action,
    )
    db.session.add(rule)
    audit = AuditLog(tenant_id=current_user.tenant_id, username=current_user.username, action="Created Playbook Rule", target=f"{rule.condition_field} {rule.condition_operator} {rule.condition_value}")
    db.session.add(audit)
    db.session.commit()
    return jsonify({"status": "ok", "id": rule.id})

@api_bp.route("/api/playbooks/<rule_id>", methods=["DELETE"])
@require_auth
@require_role(list(ADMIN_ROLES))
def delete_playbook(current_user, rule_id):
    rule = PlaybookRule.query.filter_by(id=rule_id, tenant_id=current_user.tenant_id).first()
    if rule:
        db.session.delete(rule)
        audit = AuditLog(tenant_id=current_user.tenant_id, username=current_user.username, action="Deleted Playbook Rule", target=str(rule_id))
        db.session.add(audit)
        db.session.commit()
    return jsonify({"status": "ok"})

@api_bp.route("/api/audit", methods=["GET"])
@require_auth
def get_audit_logs(current_user):
    logs = AuditLog.query.filter_by(tenant_id=current_user.tenant_id).order_by(AuditLog.timestamp.desc()).limit(100).all()
    return jsonify([l.to_dict() for l in logs])

@api_bp.route("/api/ai-insight", methods=["POST"])
@require_auth
def get_ai_insight(current_user):
    data = request.json or {}
    alert_id = data.get('alert_id')
    alert = Alert.query.filter_by(id=alert_id, tenant_id=current_user.tenant_id).first()
    if not alert:
        return jsonify({"message": "Alert not found"}), 404

    from explanation import format_ai_insight, build_explanation
    from normalization import CloudSecurityEvent

    # Prefer stored structured explanation; rebuild if older alerts lack it.
    contrib = alert.feature_contributions if isinstance(alert.feature_contributions, dict) else {}
    if contrib.get("version") != 1:
        event = CloudSecurityEvent(
            timestamp=alert.timestamp.isoformat() if alert.timestamp else "",
            normalized_identity=alert.identity,
            source_ip=alert.source_ip,
            api_velocity=float((contrib.get("api_velocity") if isinstance(contrib, dict) else None) or 0),
            auth_failures=float((contrib.get("auth_failures") if isinstance(contrib, dict) else None) or 0),
            data_volume_bytes=float((contrib.get("data_volume_bytes") if isinstance(contrib, dict) else None) or 0),
            cloud_provider=alert.cloud,
        )
        # If legacy raw values missing, leave zeros — narrative still uses scores.
        rebuilt = build_explanation(
            event,
            type("D", (), {
                "ensemble": alert.ensemble,
                "quantum_kernel": alert.quantum_kernel,
                "classical_svm": alert.classical_svm,
                "isolation_forest": alert.isolation_forest,
            })(),
            threshold=float(state.threshold or 0.68),
        )
        alert.feature_contributions = rebuilt
        alert.plain_english = rebuilt["narrative"]
        alert.disagreement = rebuilt.get("disagreement_text")
        alert.attack_phase = rebuilt["attack_phase"]
        if not alert.actions:
            alert.actions = rebuilt["actions"]
        db.session.commit()

    insight = format_ai_insight(alert)
    from models import AuditLog
    audit = AuditLog(
        tenant_id=current_user.tenant_id,
        username=current_user.username,
        action="Requested intrusion explanation",
        target=str(alert.id),
    )
    db.session.add(audit)
    db.session.commit()

    return jsonify({"insight": insight, "explanation": alert.feature_contributions})

@api_bp.route("/api/osint/<ip>", methods=["GET"])
@require_auth
def get_osint(current_user, ip):
    import time
    import hashlib
    time.sleep(1) # Simulate API latency
    
    # Deterministic mock based on IP
    hash_val = int(hashlib.md5(ip.encode()).hexdigest(), 16)
    score = (hash_val % 100)
    
    tags = ["Botnet", "Spam", "Scanner", "Tor Exit Node", "Cobalt Strike", "APT29", "Mirai"]
    tag1 = tags[hash_val % len(tags)]
    tag2 = tags[(hash_val + 1) % len(tags)]
    
    if score < 20:
        malicious = 0
        reputation = "Clean"
    elif score < 60:
        malicious = (hash_val % 15) + 1
        reputation = "Suspicious"
    else:
        malicious = (hash_val % 40) + 20
        reputation = "Malicious"
        
    audit = AuditLog(tenant_id=current_user.tenant_id, username=current_user.username, action="Performed OSINT Lookup", target=ip)
    db.session.add(audit)
    db.session.commit()
        
    return jsonify({
        "ip": ip,
        "reputation": reputation,
        "vendors_flagged": malicious,
        "total_vendors": 89,
        "tags": [tag1, tag2] if malicious > 0 else []
    })

from models import IncidentCase, CaseComment

@api_bp.route("/api/cases", methods=["GET"])
@require_auth
def get_cases(current_user):
    cases = (
        _tenant_scope_query(IncidentCase, current_user)
        .order_by(IncidentCase.created_at.desc())
        .all()
    )
    return jsonify([c.to_dict() for c in cases])

@api_bp.route("/api/cases", methods=["POST"])
@require_auth
@require_role(list(ANALYST_WRITE_ROLES))
def create_case(current_user):
    data = request.json
    case = IncidentCase(
        tenant_id=current_user.tenant_id,
        title=data.get('title'),
        priority=data.get('priority', 'Medium')
    )
    db.session.add(case)
    audit = AuditLog(tenant_id=current_user.tenant_id, username=current_user.username, action="Created Case", target=data.get('title'))
    db.session.add(audit)
    db.session.commit()
    return jsonify({"status": "ok", "id": case.id})

@api_bp.route("/api/cases/<case_id>/alerts", methods=["GET"])
@require_auth
def get_case_alerts(current_user, case_id):
    case = IncidentCase.query.filter_by(id=case_id, tenant_id=current_user.tenant_id).first()
    if not case:
        return jsonify({"message": "Not found"}), 404
    alerts = Alert.query.filter_by(tenant_id=current_user.tenant_id, case_id=case_id).all()
    return jsonify([a.to_dict() for a in alerts])

@api_bp.route("/api/cases/<case_id>/alerts", methods=["POST"])
@require_auth
@require_role(list(ANALYST_WRITE_ROLES))
def link_alerts_to_case(current_user, case_id):
    """Attach one or more alerts to a case (tenant-scoped)."""
    case = IncidentCase.query.filter_by(id=case_id, tenant_id=current_user.tenant_id).first()
    if not case:
        return jsonify({"message": "Not found"}), 404
    data = request.json or {}
    alert_ids = data.get('alert_ids') or ([data['alert_id']] if data.get('alert_id') else [])
    if not alert_ids:
        return jsonify({"message": "alert_id or alert_ids required"}), 400

    linked = []
    for aid in alert_ids:
        alert = Alert.query.filter_by(id=aid, tenant_id=current_user.tenant_id).first()
        if alert:
            alert.case_id = case.id
            linked.append(aid)

    if not linked:
        return jsonify({"message": "No matching alerts found"}), 404

    from models import AuditLog
    db.session.add(AuditLog(
        tenant_id=current_user.tenant_id,
        username=current_user.username,
        action="Linked alerts to case",
        target=f"case={case_id};alerts={','.join(linked)}",
    ))
    db.session.commit()
    return jsonify({"status": "ok", "linked": linked, "case_id": case.id})

@api_bp.route("/api/cases/<case_id>/alerts/<alert_id>", methods=["DELETE"])
@require_auth
@require_role(list(ANALYST_WRITE_ROLES))
def unlink_alert_from_case(current_user, case_id, alert_id):
    case = IncidentCase.query.filter_by(id=case_id, tenant_id=current_user.tenant_id).first()
    if not case:
        return jsonify({"message": "Not found"}), 404
    alert = Alert.query.filter_by(id=alert_id, tenant_id=current_user.tenant_id, case_id=case.id).first()
    if not alert:
        return jsonify({"message": "Alert not linked to this case"}), 404
    alert.case_id = None
    db.session.commit()
    return jsonify({"status": "ok"})

from normalization import CloudSecurityEvent

@api_bp.route("/api/ingest/webhook", methods=["POST"])
def ingest_webhook():
    """Ingest a SIEM event. Requires X-API-Key matching INGEST_API_KEY, or a session JWT."""
    data = request.json
    if not isinstance(data, dict):
        return jsonify({"message": "JSON body required"}), 400

    tenant_id = None
    expected_key = os.environ.get('INGEST_API_KEY')
    api_key = request.headers.get('X-API-Key')
    flask_env = (os.environ.get('FLASK_ENV') or os.environ.get('ENV') or 'development').lower()
    is_prod = flask_env in ('production', 'prod') or os.environ.get('QUANTUM_STRICT_SECRETS') == '1'

    if expected_key and api_key and api_key == expected_key:
        try:
            tenant_id = int(os.environ.get('INGEST_TENANT_ID', '1'))
        except ValueError:
            tenant_id = 1
    elif api_key and not expected_key:
        return jsonify({"message": "INGEST_API_KEY is not configured on the server"}), 401
    else:
        user, error = _resolve_user_from_token(('session',))
        if error:
            if is_prod and not expected_key:
                return jsonify({
                    "message": "Unauthorized. Configure INGEST_API_KEY or provide a session Bearer token."
                }), 401
            return error
        tenant_id = user.tenant_id

    if tenant_id is None:
        return jsonify({
            "message": "Unauthorized. Provide X-API-Key (INGEST_API_KEY) or Bearer session token."
        }), 401

    from state import state
    if state.pipe is None or state.ensemble is None:
        return jsonify({"message": "Detectors are still starting. Retry shortly."}), 503

    try:
        auth_failures = float(data.get('auth_failures', 0))
        data_volume_bytes = float(data.get('bytes_out', 0))
        api_velocity = float(data.get('api_calls', 0))
    except (TypeError, ValueError):
        return jsonify({"message": "auth_failures, bytes_out, and api_calls must be numeric"}), 400

    event = CloudSecurityEvent(
        cloud_provider=data.get('cloud', 'Unknown'),
        source_ip=data.get('src_ip', '0.0.0.0'),
        normalized_identity=data.get('user', 'unknown_user'),
        auth_failures=auth_failures,
        data_volume_bytes=data_volume_bytes,
        api_velocity=api_velocity,
        timestamp=data.get('timestamp', datetime.datetime.utcnow().isoformat())
    )

    try:
        feats = state.pipe.transform_single(event)
        detail = state.ensemble.score_detail(feats)
        raw_score = float(detail.ensemble)
        detail_q = float(detail.quantum_kernel)
        detail_c = float(detail.classical_svm)
        detail_if = float(detail.isolation_forest)
    except Exception as exc:
        logger = __import__('logging').getLogger(__name__)
        logger.warning("Ingest scoring failed: %s", exc)
        return jsonify({"message": "Failed to score ingested event"}), 500

    from explanation import build_explanation

    threshold = float(state.threshold or 0.68)
    policy_adjusted = False
    score = raw_score
    action_label = getattr(event, 'action', None) or data.get('action', 'SIEM event')

    # Policy override (separate from model output): mass egress forces CRITICAL.
    if event.data_volume_bytes > 1e9:
        score = max(raw_score, 0.99)
        policy_adjusted = True
        action_label = "MASSIVE DATA EXFILTRATION"

    explanation = build_explanation(
        event, type("D", (), {
            "ensemble": raw_score,
            "quantum_kernel": detail_q,
            "classical_svm": detail_c,
            "isolation_forest": detail_if,
        })(),
        threshold=threshold,
    )
    # Keep narrative honest about policy override.
    if policy_adjusted:
        explanation = dict(explanation)
        explanation["narrative"] = (
            f"{explanation['narrative']} Policy override: mass egress "
            f"raised disposition score to {score:.2f} (model ensemble {raw_score:.2f})."
        )
        explanation["hypothesis"] = "Exfiltration — mass egress policy override."
        explanation["attack_phase"] = "Exfiltration"

    if score >= max(threshold + 0.15, 0.85):
        sev = "CRITICAL"
    elif score >= threshold:
        sev = "HIGH"
    elif score >= threshold * 0.7:
        sev = "WATCH"
    else:
        # Below watch band — acknowledge without creating an open alert.
        return jsonify({
            "status": "scored",
            "alert_created": False,
            "score": raw_score,
            "threshold": threshold,
            "explanation": explanation,
        }), 200

    # Honor tenant suppression rules
    rules = SuppressionRule.query.filter_by(tenant_id=tenant_id).all()
    for rule in rules:
        if rule.rule_type == 'identity' and rule.value.lower() in event.normalized_identity.lower():
            return jsonify({"status": "suppressed", "reason": "identity"}), 200
        if rule.rule_type == 'ip' and rule.value == event.source_ip:
            return jsonify({"status": "suppressed", "reason": "ip"}), 200
        if rule.rule_type == 'cloud' and rule.value.lower() == event.cloud_provider.lower():
            return jsonify({"status": "suppressed", "reason": "cloud"}), 200

    alert_record = Alert(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        status="open",
        severity=sev,
        cloud=event.cloud_provider,
        identity=event.normalized_identity,
        short_identity=event.normalized_identity[:100],
        source_ip=event.source_ip,
        score=score,
        ensemble=raw_score,
        quantum_kernel=detail_q,
        classical_svm=detail_c,
        isolation_forest=detail_if,
        plain_english=explanation["narrative"],
        actions=explanation["actions"],
        disagreement=explanation.get("disagreement_text"),
        siem={**data, "raw_ensemble_score": raw_score, "policy_adjusted": policy_adjusted},
        feature_contributions=explanation,
        attack_phase=explanation["attack_phase"],
    )

    db.session.add(alert_record)
    db.session.commit()

    return jsonify({
        "status": "ingested",
        "alert_id": alert_record.id,
        "score": score,
        "raw_ensemble_score": raw_score,
        "policy_adjusted": policy_adjusted,
        "attack_phase": explanation["attack_phase"],
        "hypothesis": explanation.get("hypothesis"),
    })

from models import Tenant

@api_bp.route("/api/tenants", methods=["GET"])
@require_auth
@require_role(['SUPER_ADMIN'])
def get_tenants(current_user):
    tenants = Tenant.query.all()
    return jsonify([{"id": t.id, "name": t.name, "compliance_mode_enabled": t.compliance_mode_enabled} for t in tenants])

@api_bp.route("/api/tenants", methods=["POST"])
@require_auth
@require_role(['SUPER_ADMIN'])
def create_tenant(current_user):
    data = request.json
    tenant = Tenant(name=data.get('name'))
    db.session.add(tenant)
    db.session.commit()
    return jsonify({"status": "ok", "id": tenant.id})

@api_bp.route("/api/tenants/<tenant_id>/compliance", methods=["POST"])
@require_auth
@require_role(['SUPER_ADMIN', 'TENANT_ADMIN'])
def toggle_compliance(current_user, tenant_id):
    if current_user.role == 'TENANT_ADMIN' and str(current_user.tenant_id) != str(tenant_id):
        return jsonify({"message": "Permission denied"}), 403
        
    tenant = Tenant.query.get(tenant_id)
    if not tenant: return jsonify({"message": "Not found"}), 404
    tenant.compliance_mode_enabled = not tenant.compliance_mode_enabled
    db.session.commit()
    return jsonify({"status": "ok", "compliance_mode_enabled": tenant.compliance_mode_enabled})

ASSIGNABLE_ROLES = ('SUPER_ADMIN', 'TENANT_ADMIN', 'TIER_1', 'TIER_2', 'READ_ONLY')
TENANT_ADMIN_ASSIGNABLE_ROLES = ('TIER_1', 'TIER_2', 'READ_ONLY')
MIN_PASSWORD_LENGTH = 10


def _mfa_flags(user_ids):
    from models import UserSecurity
    if not user_ids:
        return {}
    rows = UserSecurity.query.filter(UserSecurity.user_id.in_(user_ids)).all()
    return {r.user_id: bool(r.mfa_enabled or r.webauthn_enabled) for r in rows}


def _assignable_roles(current_user):
    if current_user.role == 'SUPER_ADMIN':
        return ASSIGNABLE_ROLES
    return TENANT_ADMIN_ASSIGNABLE_ROLES


def _load_managed_user(current_user, user_id):
    """Resolve a target user the caller is allowed to administer.

    Returns (user, error_response). Tenant admins are scoped to their own tenant and
    cannot administer other admins; nobody may administer their own account.
    """
    target = User.query.get(user_id)
    if not target:
        return None, (jsonify({"message": "User not found"}), 404)
    if target.id == current_user.id:
        return None, (jsonify({"message": "You cannot modify your own account here"}), 403)
    if current_user.role != 'SUPER_ADMIN':
        if target.tenant_id != current_user.tenant_id:
            return None, (jsonify({"message": "Permission denied"}), 403)
        if target.role in ADMIN_ROLES:
            return None, (jsonify({"message": "Only a super admin can administer admin accounts"}), 403)
    return target, None


def _would_orphan_super_admin(target, new_role=None, new_active=None):
    """True when the change would leave no active super admin."""
    if target.role != 'SUPER_ADMIN':
        return False
    still_super = (new_role or target.role) == 'SUPER_ADMIN'
    still_active = target.is_active if new_active is None else new_active
    if still_super and still_active:
        return False
    remaining = User.query.filter(
        User.role == 'SUPER_ADMIN',
        User.is_active.is_(True),
        User.id != target.id,
    ).count()
    return remaining == 0


def _audit_user_action(current_user, action, target):
    db.session.add(AuditLog(
        tenant_id=current_user.tenant_id,
        username=current_user.username,
        action=action,
        target=target,
    ))


@api_bp.route("/api/users", methods=["GET"])
@require_auth
def get_users(current_user):
    """Full directory for admins; name-only roster for analysts (case assignment)."""
    if current_user.role in ADMIN_ROLES:
        query = User.query if current_user.role == 'SUPER_ADMIN' else User.query.filter_by(tenant_id=current_user.tenant_id)
        users = query.order_by(User.username.asc()).all()
        mfa = _mfa_flags([u.id for u in users])
        payload = []
        for u in users:
            entry = u.to_dict()
            entry['mfa_enabled'] = mfa.get(u.id, False)
            entry['manageable'] = u.id != current_user.id and (
                current_user.role == 'SUPER_ADMIN' or u.role not in ADMIN_ROLES
            )
            payload.append(entry)
        return jsonify(payload)

    users = (
        User.query
        .filter_by(tenant_id=current_user.tenant_id, is_active=True)
        .order_by(User.username.asc())
        .all()
    )
    return jsonify([{"id": u.id, "username": u.username, "role": u.role} for u in users])

@api_bp.route("/api/users", methods=["POST"])
@require_auth
@require_role(['SUPER_ADMIN', 'TENANT_ADMIN'])
def create_user(current_user):
    data = request.json or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''
    role = data.get('role', 'TIER_1')
    if not username or not password:
        return jsonify({"message": "username and password are required"}), 400
    if len(password) < MIN_PASSWORD_LENGTH:
        return jsonify({"message": f"Password must be at least {MIN_PASSWORD_LENGTH} characters"}), 400
    if role not in ASSIGNABLE_ROLES:
        return jsonify({"message": "Invalid role"}), 400
    if role not in _assignable_roles(current_user):
        return jsonify({"message": "Permission denied"}), 403
    if User.query.filter_by(username=username).first():
        return jsonify({"message": "Username already exists"}), 409

    tenant_id = data.get('tenant_id')
    if current_user.role != 'SUPER_ADMIN':
        tenant_id = current_user.tenant_id
    # Super admins may target any tenant; default to their own when unspecified.
    if not tenant_id:
        tenant_id = current_user.tenant_id
    if not tenant_id:
        return jsonify({"message": "tenant_id is required"}), 400
    try:
        tenant_id = int(tenant_id)
    except (TypeError, ValueError):
        return jsonify({"message": "Invalid tenant_id"}), 400
    from models import Tenant
    if not Tenant.query.get(tenant_id):
        return jsonify({"message": "Tenant not found"}), 400
        
    user = User(
        username=username,
        role=role,
        tenant_id=tenant_id
    )
    user.set_password(password, require_change=True)
    db.session.add(user)
    _audit_user_action(current_user, "Created user", f"{username} ({role})")
    db.session.commit()
    return jsonify({"status": "ok", "id": user.id, "user": user.to_dict()})


@api_bp.route("/api/me", methods=["GET"])
@require_auth
def get_me(current_user):
    return jsonify({
        **current_user.to_dict(),
        "role": current_user.role,
    })


@api_bp.route("/api/me/password", methods=["POST"])
@require_auth
def change_own_password(current_user):
    data = request.json or {}
    if not current_user.check_password(data.get('current_password') or ''):
        return jsonify({"message": "Current password is incorrect"}), 401
    new_password = data.get('new_password') or ''
    if len(new_password) < MIN_PASSWORD_LENGTH:
        return jsonify({"message": f"Password must be at least {MIN_PASSWORD_LENGTH} characters"}), 400
    if new_password == (data.get('current_password') or ''):
        return jsonify({"message": "New password must differ from the current one"}), 400

    current_user.set_password(new_password)
    _audit_user_action(current_user, "Changed own password", current_user.username)
    db.session.commit()
    return jsonify({
        "status": "ok",
        "message": "Password updated",
        "token": _session_token(current_user),
    })


@api_bp.route("/api/users/<int:user_id>", methods=["PUT", "PATCH"])
@require_auth
@require_role(list(ADMIN_ROLES))
def update_user(current_user, user_id):
    target, error = _load_managed_user(current_user, user_id)
    if error:
        return error

    data = request.json or {}
    changes = []

    if 'role' in data:
        role = data['role']
        if role not in ASSIGNABLE_ROLES:
            return jsonify({"message": "Invalid role"}), 400
        if role not in _assignable_roles(current_user):
            return jsonify({"message": "Permission denied"}), 403
        if _would_orphan_super_admin(target, new_role=role):
            return jsonify({"message": "At least one active super admin must remain"}), 409
        if role != target.role:
            changes.append(f"role {target.role}->{role}")
            target.role = role

    if 'is_active' in data:
        is_active = bool(data['is_active'])
        if _would_orphan_super_admin(target, new_active=is_active):
            return jsonify({"message": "At least one active super admin must remain"}), 409
        if is_active != bool(target.is_active):
            changes.append("activated" if is_active else "deactivated")
            target.is_active = is_active
            target.bump_token_version()

    if 'username' in data:
        username = (data['username'] or '').strip()
        if not username:
            return jsonify({"message": "username cannot be empty"}), 400
        if username != target.username:
            if User.query.filter(User.username == username, User.id != target.id).first():
                return jsonify({"message": "Username already exists"}), 409
            changes.append(f"username {target.username}->{username}")
            target.username = username

    if 'tenant_id' in data:
        if current_user.role != 'SUPER_ADMIN':
            return jsonify({"message": "Only a super admin can move users between tenants"}), 403
        from models import Tenant
        tenant_id = data['tenant_id']
        if not Tenant.query.get(tenant_id):
            return jsonify({"message": "Tenant not found"}), 404
        if tenant_id != target.tenant_id:
            changes.append(f"tenant {target.tenant_id}->{tenant_id}")
            target.tenant_id = tenant_id

    if not changes:
        return jsonify({"status": "ok", "user": target.to_dict()})

    _audit_user_action(current_user, "Updated user", f"{target.username}: {', '.join(changes)}")
    db.session.commit()
    return jsonify({"status": "ok", "user": target.to_dict()})


@api_bp.route("/api/users/<int:user_id>/password", methods=["POST"])
@require_auth
@require_role(list(ADMIN_ROLES))
def reset_user_password(current_user, user_id):
    target, error = _load_managed_user(current_user, user_id)
    if error:
        return error

    password = (request.json or {}).get('password') or ''
    if len(password) < MIN_PASSWORD_LENGTH:
        return jsonify({"message": f"Password must be at least {MIN_PASSWORD_LENGTH} characters"}), 400

    target.set_password(password, require_change=True)
    _audit_user_action(current_user, "Reset user password", target.username)
    db.session.commit()
    return jsonify({"status": "ok", "message": f"Password reset for {target.username}"})


@api_bp.route("/api/users/<int:user_id>/mfa", methods=["DELETE"])
@require_auth
@require_role(list(ADMIN_ROLES))
def reset_user_mfa(current_user, user_id):
    """Clear MFA enrollment so a user who lost their device can re-enroll."""
    target, error = _load_managed_user(current_user, user_id)
    if error:
        return error

    from models import UserSecurity, WebAuthnCredential
    UserSecurity.query.filter_by(user_id=target.id).delete()
    WebAuthnCredential.query.filter_by(user_id=target.id).delete()
    target.bump_token_version()
    _audit_user_action(current_user, "Reset user MFA", target.username)
    db.session.commit()
    return jsonify({"status": "ok", "message": f"MFA enrollment cleared for {target.username}"})


@api_bp.route("/api/users/<int:user_id>", methods=["DELETE"])
@require_auth
@require_role(list(ADMIN_ROLES))
def delete_user(current_user, user_id):
    target, error = _load_managed_user(current_user, user_id)
    if error:
        return error
    if _would_orphan_super_admin(target, new_active=False):
        return jsonify({"message": "At least one active super admin must remain"}), 409

    from models import UserSecurity, WebAuthnCredential
    username = target.username
    UserSecurity.query.filter_by(user_id=target.id).delete()
    WebAuthnCredential.query.filter_by(user_id=target.id).delete()
    # Keep case history intact: drop assignments, leave comments attributed by id.
    IncidentCase.query.filter_by(assignee_id=target.id).update({"assignee_id": None})
    db.session.delete(target)
    _audit_user_action(current_user, "Deleted user", username)
    db.session.commit()
    return jsonify({"status": "ok", "message": f"{username} deleted"})

@api_bp.route("/api/cases/<case_id>/comments", methods=["GET"])
@require_auth
def get_case_comments(current_user, case_id):
    comments = (
        CaseComment.query
        .join(IncidentCase)
        .filter(IncidentCase.tenant_id == current_user.tenant_id, CaseComment.case_id == case_id)
        .order_by(CaseComment.created_at.asc())
        .all()
    )
    user_ids = {c.user_id for c in comments}
    users = {u.id: u for u in User.query.filter(User.id.in_(user_ids)).all()} if user_ids else {}
    res = []
    for c in comments:
        u = users.get(c.user_id)
        res.append({
            "id": c.id,
            "content": c.content,
            "username": u.username if u else 'Deleted user',
            "created_at": c.created_at.isoformat() + "Z"
        })
    return jsonify(res)

@api_bp.route("/api/cases/<case_id>/comments", methods=["POST"])
@require_auth
@require_role(list(ANALYST_WRITE_ROLES))
def add_case_comment(current_user, case_id):
    data = request.json
    case = IncidentCase.query.filter_by(id=case_id, tenant_id=current_user.tenant_id).first()
    if not case: return jsonify({"message": "Not found"}), 404
    comment = CaseComment(case_id=case_id, user_id=current_user.id, content=data.get('content'))
    db.session.add(comment)
    db.session.commit()
    return jsonify({"status": "ok"})

@api_bp.route("/api/cases/<case_id>", methods=["PUT"])
@require_auth
@require_role(list(ANALYST_WRITE_ROLES))
def update_case(current_user, case_id):
    data = request.json or {}
    case = IncidentCase.query.filter_by(id=case_id, tenant_id=current_user.tenant_id).first()
    if not case:
        return jsonify({"message": "Not found"}), 404
    if 'status' in data:
        case.status = data['status']
    if 'assignee_id' in data:
        raw = data['assignee_id']
        if raw in (None, '', 'null'):
            case.assignee_id = None
        else:
            try:
                assignee_id = int(raw)
            except (TypeError, ValueError):
                return jsonify({"message": "Invalid assignee_id"}), 400
            assignee = User.query.filter_by(
                id=assignee_id, tenant_id=current_user.tenant_id, is_active=True
            ).first()
            if not assignee:
                return jsonify({"message": "Assignee must be an active user in this tenant"}), 400
            case.assignee_id = assignee_id
    if 'peak_framework' in data:
        case.peak_framework = data['peak_framework']
    if 'kill_chain' in data:
        case.kill_chain = data['kill_chain']
    if 'diamond_model' in data:
        case.diamond_model = data['diamond_model']
    from models import AuditLog
    db.session.add(AuditLog(
        tenant_id=current_user.tenant_id,
        username=current_user.username,
        action="Updated case",
        target=str(case_id),
    ))
    db.session.commit()
    return jsonify({"status": "ok", "case": case.to_dict()})
