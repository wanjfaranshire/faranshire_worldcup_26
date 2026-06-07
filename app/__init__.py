import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager

db = SQLAlchemy()
login_manager = LoginManager()

def create_app():
    app = Flask(__name__)

    # === FORCE POSTGRESQL ON RENDER ===
    database_url = os.environ.get('DATABASE_URL')

    if database_url:
        # Fix Render's postgres:// prefix
        if database_url.startswith("postgres://"):
            database_url = database_url.replace("postgres://", "postgresql://", 1)
        app.config['SQLALCHEMY_DATABASE_URI'] = database_url
        print("🚀 Using PostgreSQL (Render)")
    else:
        # Local development fallback
        instance_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), '..', 'instance')
        if not os.path.exists(instance_path):
            os.makedirs(instance_path)
        db_path = os.path.join(instance_path, 'worldcup.db')
        app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
        print("💻 Using SQLite (Local)")

    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key')

    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'main.login'

    from .models import User

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    from . import routes
    app.register_blueprint(routes.bp)

    return app