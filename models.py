from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.ext.mutable import MutableDict, MutableList
from werkzeug.security import generate_password_hash, check_password_hash
import datetime

db = SQLAlchemy()

class Tenant(db.Model):
    __tablename__ = 'tenants'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    compliance_mode_enabled = db.Column(db.Boolean, default=False)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "compliance_mode_enabled": bool(self.compliance_mode_enabled),
        }

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=False)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.Text, nullable=False)
    role = db.Column(db.String(20), nullable=False, default='TIER_1') # SUPER_ADMIN, TENANT_ADMIN, TIER_1, TIER_2, READ_ONLY
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    token_version = db.Column(db.Integer, nullable=False, default=0)
    must_change_password = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    last_login_at = db.Column(db.DateTime, nullable=True)

    def set_password(self, password, *, require_change=False):
        self.password_hash = generate_password_hash(password)
        self.token_version = int(self.token_version or 0) + 1
        self.must_change_password = bool(require_change)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def bump_token_version(self):
        self.token_version = int(self.token_version or 0) + 1

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "role": self.role,
            "tenant_id": self.tenant_id,
            "is_active": bool(self.is_active),
            "must_change_password": bool(self.must_change_password),
            "created_at": self.created_at.isoformat() + "Z" if self.created_at else None,
            "last_login_at": self.last_login_at.isoformat() + "Z" if self.last_login_at else None,
        }

class UserSecurity(db.Model):
    __tablename__ = 'user_security'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, unique=True)
    totp_secret = db.Column(db.String(32), nullable=True)
    mfa_enabled = db.Column(db.Boolean, default=False)
    webauthn_enabled = db.Column(db.Boolean, default=False)
    
class WebAuthnCredential(db.Model):
    __tablename__ = 'webauthn_credentials'
    id = db.Column(db.String(255), primary_key=True) # credential ID
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    public_key = db.Column(db.LargeBinary, nullable=False)
    sign_count = db.Column(db.Integer, default=0)
    transports = db.Column(db.JSON, nullable=True)

class IncidentCase(db.Model):
    __tablename__ = 'incident_cases'
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    status = db.Column(db.String(20), nullable=False, default='Open') # Open, Pending, Resolved
    assignee_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    priority = db.Column(db.String(20), nullable=False, default='Medium')
    peak_framework = db.Column(db.Text, nullable=True)
    kill_chain = db.Column(db.Text, nullable=True)
    diamond_model = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    tenant = db.relationship('Tenant', lazy='joined')

    def to_dict(self):
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "tenant_name": self.tenant.name if self.tenant else None,
            "title": self.title,
            "status": self.status,
            "assignee_id": self.assignee_id,
            "priority": self.priority,
            "peak_framework": self.peak_framework,
            "kill_chain": self.kill_chain,
            "diamond_model": self.diamond_model,
            "created_at": self.created_at.isoformat() + "Z"
        }

class CaseComment(db.Model):
    __tablename__ = 'case_comments'
    id = db.Column(db.Integer, primary_key=True)
    case_id = db.Column(db.Integer, db.ForeignKey('incident_cases.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

class HistoryEvent(db.Model):
    __tablename__ = 'history_events'
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=False)
    t = db.Column(db.Integer, nullable=False, index=True)
    ensemble = db.Column(db.Float, nullable=False)
    isolation_forest = db.Column(db.Float, nullable=False)
    classical_svm = db.Column(db.Float, nullable=False)
    quantum_kernel = db.Column(db.Float, nullable=False)
    cloud_provider = db.Column(db.String(50), nullable=False)
    severity = db.Column(db.String(20), nullable=False)
    latency_ms = db.Column(db.Float, nullable=True, default=0.0)
    timestamp = db.Column(db.DateTime, default=datetime.datetime.utcnow)

class Alert(db.Model):
    __tablename__ = 'alerts'
    id = db.Column(db.String(36), primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=False)
    case_id = db.Column(db.Integer, db.ForeignKey('incident_cases.id'), nullable=True)
    status = db.Column(db.String(20), nullable=False, default='open', index=True) # open, acknowledged, false_positive, escalated
    severity = db.Column(db.String(20), nullable=False)
    cloud = db.Column(db.String(50), nullable=False)
    identity = db.Column(db.String(200), nullable=False)
    short_identity = db.Column(db.String(100), nullable=False)
    source_ip = db.Column(db.String(50), nullable=False)
    score = db.Column(db.Float, nullable=False)
    ensemble = db.Column(db.Float, nullable=False)
    quantum_kernel = db.Column(db.Float, nullable=False)
    classical_svm = db.Column(db.Float, nullable=False)
    isolation_forest = db.Column(db.Float, nullable=False)
    plain_english = db.Column(db.Text, nullable=False)
    actions = db.Column(MutableList.as_mutable(db.JSON), nullable=False) # store list as JSON
    disagreement = db.Column(db.Text, nullable=True)
    attack_phase = db.Column(db.String(50), nullable=True) # Initial Access, Discovery, Credential Access, Exfiltration
    siem = db.Column(MutableDict.as_mutable(db.JSON), nullable=False)
    itsm_ticket = db.Column(db.String(50), nullable=True)
    feature_contributions = db.Column(MutableDict.as_mutable(db.JSON), nullable=True)
    linked_identities = db.Column(MutableList.as_mutable(db.JSON), nullable=True)
    latency_ms = db.Column(db.Float, nullable=True, default=0.0)
    auto_response = db.Column(db.String(200), nullable=True)
    assignee_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.datetime.utcnow, index=True)

    tenant = db.relationship('Tenant', lazy='joined')

    def to_dict(self):
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "tenant_name": self.tenant.name if self.tenant else None,
            "case_id": self.case_id,
            "status": self.status,
            "severity": self.severity,
            "cloud": self.cloud,
            "identity": self.identity,
            "short_identity": self.short_identity,
            "source_ip": self.source_ip,
            "score": self.score,
            "ensemble": self.ensemble,
            "quantum_kernel": self.quantum_kernel,
            "classical_svm": self.classical_svm,
            "isolation_forest": self.isolation_forest,
            "plain_english": self.plain_english,
            "actions": self.actions,
            "disagreement": self.disagreement,
            "attack_phase": self.attack_phase,
            "siem": self.siem,
            "itsm_ticket": self.itsm_ticket,
            "feature_contributions": self.feature_contributions,
            "linked_identities": self.linked_identities,
            "latency_ms": self.latency_ms,
            "auto_response": self.auto_response,
            "assignee_id": self.assignee_id,
            "timestamp": self.timestamp.isoformat() + "Z"
        }

class SuppressionRule(db.Model):
    __tablename__ = 'suppression_rules'
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=False)
    rule_type = db.Column(db.String(50), nullable=False) # 'identity', 'ip', 'cloud'
    value = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "rule_type": self.rule_type,
            "value": self.value,
            "created_at": self.created_at.isoformat() + "Z"
        }

class PlaybookRule(db.Model):
    __tablename__ = 'playbook_rules'
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=False)
    condition_field = db.Column(db.String(50), nullable=False) # 'score', 'attack_phase', 'severity'
    condition_operator = db.Column(db.String(10), nullable=False) # '>', '==', '<'
    condition_value = db.Column(db.String(100), nullable=False)
    action = db.Column(db.String(50), nullable=False) # 'auto_isolate', 'create_ticket'
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "condition_field": self.condition_field,
            "condition_operator": self.condition_operator,
            "condition_value": self.condition_value,
            "action": self.action,
            "created_at": self.created_at.isoformat() + "Z"
        }

class AuditLog(db.Model):
    __tablename__ = 'audit_logs'
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=False)
    username = db.Column(db.String(80), nullable=False)
    action = db.Column(db.String(255), nullable=False)
    target = db.Column(db.String(255), nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "username": self.username,
            "action": self.action,
            "target": self.target,
            "timestamp": self.timestamp.isoformat() + "Z"
        }
