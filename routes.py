import uuid
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
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        if token and token.startswith('Bearer '):
            token = token.split(" ")[1]
        else:
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
        return f(current_user, *args, **kwargs)
    return decorated

@api_bp.route('/api/login', methods=['POST'])
def login():
    data = request.json
    user = User.query.filter_by(username=data.get('username')).first()
    if user and user.check_password(data.get('password')):
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
            
        token = jwt.encode({
            'user_id': user.id,
            'role': user.role,
            'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=24)
        }, current_app.config['SECRET_KEY'])
        return jsonify({'token': token, 'role': user.role, 'username': user.username})
    return jsonify({'message': 'Invalid credentials'}), 401

@api_bp.route('/api/replay_attack', methods=['POST'])
@require_auth
def replay_attack():
    return jsonify({"status": "success", "message": "Synthetic attack sequence injected into the stream."}), 200

@api_bp.route('/api/playground/config', methods=['POST', 'GET'])
@require_auth
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
@require_auth
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
    a = Alert.query.filter_by(id=alert_id, tenant_id=current_user.tenant_id).first()
    if not a:
        return jsonify({"message": "Not found"}), 404
    return jsonify(a.to_dict())

@api_bp.route("/api/benchmark", methods=["GET"])
@require_auth
def get_benchmark_route(current_user):
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
        if not SuppressionRule.query.filter_by(tenant_id=current_user.tenant_id, rule_type='identity', value=identity).first():
            rule = SuppressionRule(tenant_id=current_user.tenant_id, rule_type='identity', value=identity)
            db.session.add(rule)
            
        audit = AuditLog(tenant_id=current_user.tenant_id, username=current_user.username, action="Cut Off Identity", target=identity)
        db.session.add(audit)
        db.session.commit()
        return jsonify({"status": "ok", "message": f"Identity {identity} has been cut off and suppressed."})
    
    return jsonify({"message": "Invalid action"}), 400

@api_bp.route("/api/alert/<alert_id>/action", methods=["POST"])
@require_auth
def update_alert_status(current_user, alert_id):
    action = request.args.get('action')
    a = Alert.query.filter_by(id=alert_id, tenant_id=current_user.tenant_id).first()
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
    rule = SuppressionRule(tenant_id=current_user.tenant_id, rule_type=data['rule_type'], value=data['value'])
    db.session.add(rule)
    db.session.commit()
    return jsonify(rule.to_dict())

@api_bp.route("/api/rules/<rule_id>", methods=["DELETE"])
@require_auth
def delete_rule(current_user, rule_id):
    if current_user.role != 'admin':
        return jsonify({"message": "Admin privileges required"}), 403
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

RP_ID = "localhost"
RP_ORIGIN = "http://localhost:5173"
RP_NAME = "Quantum Helix"

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
    data = request.json
    temp_token = data.get('temp_token')
    
    try:
        token_data = jwt.decode(temp_token, current_app.config['SECRET_KEY'], algorithms=["HS256"])
        if token_data.get('type') != 'mfa_temp':
            return jsonify({'message': 'Invalid token type'}), 401
        user = User.query.get(token_data['user_id'])
    except:
        return jsonify({'message': 'Invalid or expired temporary token'}), 401

    user_sec = UserSecurity.query.filter_by(user_id=user.id).first()
    
    # Handle TOTP Verification
    if data.get('type') == 'totp':
        totp = pyotp.TOTP(user_sec.totp_secret)
        if not totp.verify(data.get('code')):
            return jsonify({'message': 'Invalid TOTP code'}), 401
            
    # Handle WebAuthn Verification
    elif data.get('type') == 'webauthn':
        challenge = session.get('webauthn_auth_challenge')
        cred_id = data.get('credential').get('id')
        cred = WebAuthnCredential.query.filter_by(id=cred_id).first()
        if not cred:
            return jsonify({'message': 'Credential not found'}), 401
            
        try:
            verification = verify_authentication_response(
                credential=data.get('credential'),
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
        
    # Issue real token
    real_token = jwt.encode({
        'user_id': user.id,
        'role': user.role,
        'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=24)
    }, current_app.config['SECRET_KEY'])
    return jsonify({'token': real_token, 'role': user.role, 'username': user.username})

@api_bp.route('/api/login/webauthn-options', methods=['POST'])
def login_webauthn_options():
    data = request.json
    temp_token = data.get('temp_token')
    try:
        token_data = jwt.decode(temp_token, current_app.config['SECRET_KEY'], algorithms=["HS256"])
        user = User.query.get(token_data['user_id'])
    except:
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
def create_playbook(current_user):
    data = request.json
    rule = PlaybookRule(tenant_id=current_user.tenant_id, 
        condition_field=data.get('condition_field'),
        condition_operator=data.get('condition_operator'),
        condition_value=data.get('condition_value'),
        action=data.get('action')
    )
    db.session.add(rule)
    audit = AuditLog(tenant_id=current_user.tenant_id, username=current_user.username, action="Created Playbook Rule", target=f"{rule.condition_field} {rule.condition_operator} {rule.condition_value}")
    db.session.add(audit)
    db.session.commit()
    return jsonify({"status": "ok", "id": rule.id})

@api_bp.route("/api/playbooks/<rule_id>", methods=["DELETE"])
@require_auth
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
    data = request.json
    alert_id = data.get('alert_id')
    alert = Alert.query.filter_by(id=alert_id, tenant_id=current_user.tenant_id).first()
    if not alert:
        return jsonify({"message": "Alert not found"}), 404
        
    # Mock LLM Logic
    import time
    time.sleep(1.5) # Simulate API latency
    
    explanation = f"Based on the payload, the identity **{alert.identity}** executed an anomalous sequence of events matching the **{alert.attack_phase}** phase. "
    
    if alert.score > 0.8:
        explanation += "The Quantum-simulated kernel detected high-dimensional correlations indicative of a sophisticated attack pattern (likely automated credential stuffing or rapid exfiltration). "
    
    explanation += f"\n\n**Recommended Remediation:**\n1. Immediately revoke active session tokens for `{alert.short_identity}`.\n2. Inspect CloudWatch logs for source IP `{alert.source_ip}`.\n3. Rotate affected credentials."
    
    audit = AuditLog(tenant_id=current_user.tenant_id, username=current_user.username, action="Requested AI Insight", target=str(alert.id))
    db.session.add(audit)
    db.session.commit()
    
    return jsonify({"insight": explanation})

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
    cases = IncidentCase.query.filter_by(tenant_id=current_user.tenant_id).order_by(IncidentCase.created_at.desc()).all()
    return jsonify([c.to_dict() for c in cases])

@api_bp.route("/api/cases", methods=["POST"])
@require_auth
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
    alerts = Alert.query.filter_by(tenant_id=current_user.tenant_id, case_id=case_id).all()
    return jsonify([a.to_dict() for a in alerts])

from normalization import CloudSecurityEvent

@api_bp.route("/api/ingest/webhook", methods=["POST"])
def ingest_webhook():
    # Allow any SIEM JSON payload
    data = request.json
    
    event = CloudSecurityEvent(
        cloud_provider=data.get('cloud', 'Unknown'),
        source_ip=data.get('src_ip', '0.0.0.0'),
        normalized_identity=data.get('user', 'unknown_user'),
        action=data.get('action', 'UnknownAction'),
        auth_failures=float(data.get('auth_failures', 0)),
        data_volume_bytes=float(data.get('bytes_out', 0)),
        api_velocity=float(data.get('api_calls', 0)),
        timestamp=data.get('timestamp', datetime.datetime.utcnow().isoformat())
    )
    
    # Process with model (mock scores for now if pipe not loaded)
    from state import state
    try:
        feats = state.pipe.transform_single(event)
        detail = state.ensemble.score_detail(feats)
        score = float(detail.ensemble)
    except:
        score = 0.85 # Mock if ML isn't ready
        
    sev = "HIGH" if score > 0.75 else "WATCH"
    
    # Check DLP-Lite (Automated Exfiltration)
    if event.data_volume_bytes > 1e9: # > 1 GB
        score = 0.99
        sev = "CRITICAL"
        event.action = "MASSIVE DATA EXFILTRATION"
        
    alert_record = Alert(
        id=str(uuid.uuid4()) if 'uuid' in globals() else "SIEM-" + str(int(time.time())),
        tenant_id=1, # Default to tenant 1 for webhook
        status="open",
        severity=sev,
        cloud=event.cloud_provider,
        identity=event.normalized_identity,
        short_identity=event.normalized_identity,
        source_ip=event.source_ip,
        score=score,
        ensemble=score,
        quantum_kernel=score,
        classical_svm=score,
        isolation_forest=score,
        plain_english=f"Ingested via SIEM Webhook: {event.action} from {event.source_ip}",
        actions=["Review SIEM logs manually"],
        siem=data,
        attack_phase="Exfiltration" if event.data_volume_bytes > 5e7 else "Initial Access"
    )
    
    db.session.add(alert_record)
    db.session.commit()
    
    return jsonify({"status": "ingested", "alert_id": alert_record.id})

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

@api_bp.route("/api/users", methods=["GET"])
@require_auth
@require_role(['SUPER_ADMIN', 'TENANT_ADMIN'])
def get_users(current_user):
    if current_user.role == 'SUPER_ADMIN':
        users = User.query.all()
    else:
        users = User.query.filter_by(tenant_id=current_user.tenant_id).all()
    return jsonify([{"id": u.id, "username": u.username, "role": u.role, "tenant_id": u.tenant_id} for u in users])

@api_bp.route("/api/users", methods=["POST"])
@require_auth
@require_role(['SUPER_ADMIN', 'TENANT_ADMIN'])
def create_user(current_user):
    data = request.json
    tenant_id = data.get('tenant_id')
    if current_user.role != 'SUPER_ADMIN':
        tenant_id = current_user.tenant_id
        
    user = User(
        username=data.get('username'),
        role=data.get('role', 'TIER_1'),
        tenant_id=tenant_id
    )
    user.set_password(data.get('password'))
    db.session.add(user)
    db.session.commit()
    return jsonify({"status": "ok", "id": user.id})

@api_bp.route("/api/cases/<case_id>/comments", methods=["GET"])
@require_auth
def get_case_comments(current_user, case_id):
    comments = CaseComment.query.join(IncidentCase).filter(IncidentCase.tenant_id==current_user.tenant_id, CaseComment.case_id==case_id).all()
    res = []
    for c in comments:
        u = User.query.get(c.user_id)
        res.append({
            "id": c.id,
            "content": c.content,
            "username": u.username if u else 'Unknown',
            "created_at": c.created_at.isoformat() + "Z"
        })
    return jsonify(res)

@api_bp.route("/api/cases/<case_id>/comments", methods=["POST"])
@require_auth
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
def update_case(current_user, case_id):
    data = request.json
    case = IncidentCase.query.filter_by(id=case_id, tenant_id=current_user.tenant_id).first()
    if not case: return jsonify({"message": "Not found"}), 404
    if 'status' in data: case.status = data['status']
    if 'assignee_id' in data: case.assignee_id = data['assignee_id'] or None
    db.session.commit()
    return jsonify({"status": "ok"})
