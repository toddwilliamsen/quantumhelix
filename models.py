from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import datetime

db = SQLAlchemy()

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='analyst') # 'admin' or 'analyst'

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class HistoryEvent(db.Model):
    __tablename__ = 'history_events'
    id = db.Column(db.Integer, primary_key=True)
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
    actions = db.Column(db.JSON, nullable=False) # store list as JSON
    disagreement = db.Column(db.Text, nullable=True)
    attack_phase = db.Column(db.String(50), nullable=True) # Initial Access, Discovery, Credential Access, Exfiltration
    siem = db.Column(db.JSON, nullable=False)
    itsm_ticket = db.Column(db.String(50), nullable=True)
    
    # New Fields for 2.0 Feature Expansion
    feature_contributions = db.Column(db.JSON, nullable=True)
    linked_identities = db.Column(db.JSON, nullable=True)
    latency_ms = db.Column(db.Float, nullable=True, default=0.0)
    auto_response = db.Column(db.String(200), nullable=True)
    
    timestamp = db.Column(db.DateTime, default=datetime.datetime.utcnow, index=True)

    def to_dict(self):
        return {
            "id": self.id,
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
            "timestamp": self.timestamp.isoformat() + "Z"
        }

class SuppressionRule(db.Model):
    __tablename__ = 'suppression_rules'
    id = db.Column(db.Integer, primary_key=True)
    rule_type = db.Column(db.String(50), nullable=False) # 'identity', 'ip', 'cloud'
    value = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "rule_type": self.rule_type,
            "value": self.value,
            "created_at": self.created_at.isoformat() + "Z"
        }
