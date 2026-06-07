from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_bootstrap import Bootstrap5

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = 'main.login'   # Updated to include blueprint
bootstrap = Bootstrap5()

@login_manager.user_loader
def load_user(user_id):
    from app.models import User   # Import here to avoid circular imports
    return User.query.get(int(user_id))

def create_app():
    app = Flask(__name__)
    app.config.from_object('config.Config')
    
    db.init_app(app)
    login_manager.init_app(app)
    bootstrap.init_app(app)
    
    from app.routes import bp as main_bp
    app.register_blueprint(main_bp)
    
    with app.app_context():
        db.create_all()
    
    return app