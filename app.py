import logging
import os
from flask import Flask, send_from_directory
from flask_cors import CORS
from models import db, User
from routes import api_bp
from simulation import start_background_loop

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-8s | %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder='static', static_url_path='/')
cors_origins = os.environ.get('CORS_ORIGINS', '*').split(',')
CORS(app, origins=cors_origins)

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///quantum.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'quantum-dev-secret-key-2026')

db.init_app(app)

# Register routes
app.register_blueprint(api_bp)

# Serve React App
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve_react(path):
    if path != "" and os.path.exists(app.static_folder + '/' + path):
        return send_from_directory(app.static_folder, path)
    else:
        return send_from_directory(app.static_folder, 'index.html')

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

# Start simulation loop
start_background_loop(app)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, threaded=True)
