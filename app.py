import logging
import os
import sqlite3
from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
from sqlalchemy import event, text
from sqlalchemy.engine import Engine
from models import db, User
from routes import api_bp
from simulation import start_background_loop

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-8s | %(message)s")
logger = logging.getLogger(__name__)

_DEFAULT_SECRET = 'quantum-dev-secret-key-2026'
_FLASK_ENV = (os.environ.get('FLASK_ENV') or os.environ.get('ENV') or 'development').lower()
_IS_PROD = _FLASK_ENV in ('production', 'prod') or os.environ.get('QUANTUM_STRICT_SECRETS') == '1'


@event.listens_for(Engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()


app = Flask(__name__, static_folder='static', static_url_path='/')

# CORS: deny-by-default in production; local Vite defaults for development.
_default_cors = 'http://localhost:5173,http://127.0.0.1:5173' if not _IS_PROD else ''
cors_origins = [o.strip() for o in os.environ.get('CORS_ORIGINS', _default_cors).split(',') if o.strip()]
if _IS_PROD and (not cors_origins or cors_origins == ['*']):
    raise RuntimeError("Set CORS_ORIGINS to an explicit allow-list in production (do not use '*').")
if cors_origins:
    CORS(app, origins=cors_origins)
else:
    CORS(app, origins=[])

app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///quantum.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'connect_args': {'check_same_thread': False, 'timeout': 30},
}
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', _DEFAULT_SECRET)
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = _IS_PROD

if app.config['SECRET_KEY'] in ('', _DEFAULT_SECRET):
    if _IS_PROD:
        raise RuntimeError("SECRET_KEY must be set to a strong non-default value in production.")
    logger.warning("SECRET_KEY is using the insecure default. Set SECRET_KEY before any shared deploy.")

db.init_app(app)
app.register_blueprint(api_bp)


@app.route('/healthz')
def healthz():
    return jsonify({"status": "ok"}), 200


@app.route('/readyz')
def readyz():
    from state import state
    try:
        db.session.execute(text('SELECT 1'))
    except Exception as exc:
        return jsonify({"status": "not_ready", "db": str(exc)}), 503
    ready = state.pipe is not None and state.ensemble is not None
    payload = {
        "status": "ready" if ready else "starting",
        "detectors_loaded": ready,
        "streaming": bool(state.streaming),
    }
    return jsonify(payload), (200 if ready else 503)


@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve_react(path):
    if path != "" and os.path.exists(app.static_folder + '/' + path):
        return send_from_directory(app.static_folder, path)
    return send_from_directory(app.static_folder, 'index.html')


def _ensure_user_columns():
    """Add lifecycle columns to pre-existing SQLite databases."""
    if not str(app.config['SQLALCHEMY_DATABASE_URI']).startswith('sqlite'):
        return
    additions = {
        'is_active': "ALTER TABLE users ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT 1",
        'created_at': "ALTER TABLE users ADD COLUMN created_at DATETIME",
        'last_login_at': "ALTER TABLE users ADD COLUMN last_login_at DATETIME",
        'token_version': "ALTER TABLE users ADD COLUMN token_version INTEGER NOT NULL DEFAULT 0",
        'must_change_password': "ALTER TABLE users ADD COLUMN must_change_password BOOLEAN NOT NULL DEFAULT 0",
    }
    existing = {row[1] for row in db.session.execute(text("PRAGMA table_info(users)"))}
    for column, statement in additions.items():
        if column not in existing:
            db.session.execute(text(statement))
            logger.info("Added users.%s column", column)
    db.session.commit()

    alert_cols = {row[1] for row in db.session.execute(text("PRAGMA table_info(alerts)"))}
    if 'assignee_id' not in alert_cols:
        db.session.execute(text("ALTER TABLE alerts ADD COLUMN assignee_id INTEGER"))
        logger.info("Added alerts.assignee_id column")
        db.session.commit()


with app.app_context():
    db.create_all()
    _ensure_user_columns()
    from models import Tenant
    default_tenant = Tenant.query.filter_by(name='Default Tenant').first()
    if not default_tenant:
        default_tenant = Tenant(name='Default Tenant', compliance_mode_enabled=False)
        db.session.add(default_tenant)
        db.session.commit()

    if not User.query.filter_by(username='admin').first():
        admin = User(username='admin', role='SUPER_ADMIN', tenant_id=default_tenant.id)
        admin_pass = os.environ.get('ADMIN_PASSWORD', 'quantum123')
        if _IS_PROD and admin_pass == 'quantum123':
            raise RuntimeError("ADMIN_PASSWORD must be set to a non-default value in production.")
        admin.set_password(admin_pass, require_change=(admin_pass == 'quantum123'))
        db.session.add(admin)
        db.session.commit()
        if admin_pass == 'quantum123':
            logger.warning("Created default admin with password 'quantum123'. Change it before sharing this instance.")
        else:
            logger.info("Created default admin user with password from environment.")

_should_start_bg = (
    os.environ.get('WERKZEUG_RUN_MAIN') == 'true'
    or os.environ.get('WERKZEUG_RUN_MAIN') is None and not app.debug
)
if _should_start_bg:
    start_background_loop(app)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, threaded=True)
