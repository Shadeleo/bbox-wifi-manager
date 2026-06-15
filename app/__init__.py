import os
import secrets

from flask import Flask

from .db import init_db


def create_app() -> Flask:
    app = Flask(__name__)
    app.secret_key = os.getenv("SECRET_KEY", secrets.token_hex(32))
    init_db()
    from .routes import bp
    app.register_blueprint(bp)
    return app
