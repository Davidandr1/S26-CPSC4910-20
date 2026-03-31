import os
from flask import Flask
from app.config import Config
from app.db import db_is_ok


def create_app() -> Flask:
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

    app = Flask(
        __name__,
        template_folder=os.path.join(root_dir, "templates"),
        static_folder=os.path.join(root_dir, "static"),
    )

    app.config.from_object(Config)

    # Blueprints
    from app.auth.routes import auth_bp
    from app.main import main_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)

    # Inject db_down flag into all templates
    @app.context_processor
    def inject_globals():
        return {"db_down": (not db_is_ok())}

    return app