import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager

db = SQLAlchemy()
login_manager = LoginManager()

def create_app():
    app = Flask(__name__)

    # Get absolute path to the project root
    basedir = os.path.abspath(os.path.dirname(__file__))
    project_root = os.path.dirname(basedir)           # Go up from 'app' folder
    instance_dir = os.path.join(project_root, 'instance')

    # Create instance folder if it doesn't exist
    if not os.path.exists(instance_dir):
        os.makedirs(instance_dir)

    # Database configuration
    database_url = os.environ.get('DATABASE_URL')

    if database_url and database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
        app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    else:
        # Use absolute path for SQLite (more reliable)
        db_file = os.path.join(instance_dir, 'worldcup.db')
        app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_file}'

    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key')

    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'main.login'

    from . import routes
    app.register_blueprint(routes.bp)

    from .models import User

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    return app