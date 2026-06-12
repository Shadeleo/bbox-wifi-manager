from flask import Flask
from .db import init_db


def create_app() -> Flask:
    app = Flask(__name__)
    init_db()
    from .routes import bp
    app.register_blueprint(bp)
    return app
