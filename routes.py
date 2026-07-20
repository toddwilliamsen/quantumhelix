import datetime
import json
import jwt
import csv
import io
import time
from functools import wraps
from flask import Blueprint, request, jsonify, Response, current_app
from models import db, User, Alert, HistoryEvent, SuppressionRule
from state import state
from benchmark import run_benchmark
from cmdb import enrich_identity

api_bp = Blueprint('api', __name__)

def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token or not token.startswith('Bearer '):
            return jsonify({'message': 'Token is missing'}), 401
        token = token.split(" ")[1]
        try:
            data = jwt.decode(token, current_app.config['SECRET_KEY'], algorithms=["HS256"])
            current_user = User.query.get(data['user_id'])
            if not current_user:
                return jsonify({'message': 'User not found'}), 401
        except:
            return jsonify({'message': 'Token is invalid'}), 401
        return f(current_user, *args, **kwargs)
    return decorated

@api_bp.route('/api/login', methods=['POST'])
def login():
    data = request.json
    user = User.query.filter_by(username=data.get('username')).first()
    if user and user.check_password(data.get('password')):
        token = jwt.encode({
            'user_id': user.id,
            'role': user.role,
            'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=24)
        }, current_app.config['SECRET_KEY'])
        return jsonify({'token': token, 'role': user.role, 'username': user.username})
    return jsonify({'message': 'Invalid credentials'}), 401

@api_bp.route('/api/replay_attack', methods=['POST'])
def replay_attack():
    return jsonify({"status": "success", "message": "Synthetic attack sequence injected into the stream."}), 200

@api_bp.route('/api/playground/config', methods=['POST', 'GET'])
def playground_config():
    if request.method == 'GET':
        return jsonify({
            "pca_dimensions": 4,
            "kernel_type": "simulator",
            "ensemble_weights": {"classical": 0.55, "quantum": 0.45}
        }), 200
    return jsonify({"status": "success", "message": "Ensemble configuration updated (Simulated)."}), 200

@api_bp.route('/api/cmdb/<path:identity>', methods=['GET'])
@require_auth
def get_cmdb_info(current_user, identity):
    context = enrich_identity(identity)
    return jsonify(context), 200

@api_bp.route("/api/stream")
def stream():
    token = request.args.get('token')
    if not token:
        return jsonify({'message': 'Token is missing'}), 401
    try:
        data = jwt.decode(token, current_app.config['SECRET_KEY'], algorithms=["HS256"])
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
                # We need app_context for db queries
                from flask import current_app
                open_alerts_count = 0
                if current_app:
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

@api_bp.route("/api/alert/<alert_id>", methods=["GET"])
@require_auth
def get_alert(current_user, alert_id):
    a = Alert.query.get(alert_id)
    if not a:
        return jsonify({"message": "Not found"}), 404
    return jsonify(a.to_dict())

@api_bp.route("/api/benchmark", methods=["GET"])
def get_benchmark_route():
    reports = run_benchmark(threshold=0.55, include_qnn=False, seed=42)
    return jsonify([r.__dict__ for r in reports])

@api_bp.route("/api/controls", methods=["POST"])
@require_auth
def update_controls(current_user):
    if current_user.role != 'admin':
        return jsonify({"message": "Admin privileges required"}), 403
        
    controls = request.json
    if 'streaming' in controls:
        state.streaming = controls['streaming']
    if 'threshold' in controls:
        state.threshold = controls['threshold']
        if state.alerter:
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

@api_bp.route("/api/alerts/action", methods=["POST"])
@require_auth
def bulk_alert_action(current_user):
    data = request.json
    action = data.get('action')
    identity = data.get('identity')
    
    if not action or not identity:
        return jsonify({"message": "Missing action or identity"}), 400
        
    if action == 'cut_off':
        alerts = Alert.query.filter_by(identity=identity, status='open').all()
        for a in alerts:
            a.status = 'escalated'
        db.session.commit()
        if not SuppressionRule.query.filter_by(rule_type='identity', value=identity).first():
            rule = SuppressionRule(rule_type='identity', value=identity)
            db.session.add(rule)
            db.session.commit()
        return jsonify({"status": "ok", "message": f"Identity {identity} has been cut off and suppressed."})
    
    return jsonify({"message": "Invalid action"}), 400

@api_bp.route("/api/alert/<alert_id>/action", methods=["POST"])
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

@api_bp.route("/api/alerts/export", methods=["GET"])
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

@api_bp.route("/api/rules", methods=["GET"])
@require_auth
def get_rules(current_user):
    rules = SuppressionRule.query.order_by(SuppressionRule.created_at.desc()).all()
    return jsonify([r.to_dict() for r in rules])

@api_bp.route("/api/rules", methods=["POST"])
@require_auth
def add_rule(current_user):
    if current_user.role != 'admin':
        return jsonify({"message": "Admin privileges required"}), 403
    data = request.json
    rule = SuppressionRule(rule_type=data['rule_type'], value=data['value'])
    db.session.add(rule)
    db.session.commit()
    return jsonify(rule.to_dict())

@api_bp.route("/api/rules/<rule_id>", methods=["DELETE"])
@require_auth
def delete_rule(current_user, rule_id):
    if current_user.role != 'admin':
        return jsonify({"message": "Admin privileges required"}), 403
    rule = SuppressionRule.query.get(rule_id)
    if rule:
        db.session.delete(rule)
        db.session.commit()
    return jsonify({"status": "ok"})
