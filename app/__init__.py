import logging
import os
import secrets
from datetime import timedelta

from flask import Flask

from . import config

log = logging.getLogger(__name__)


def _resolve_secret_key() -> str:
    """Clé de signature des sessions.

    En production elle est obligatoire : une clé régénérée à chaque démarrage
    invalide toutes les sessions, et avec plusieurs workers chacun signerait
    avec une clé différente.
    """
    key = os.getenv("SECRET_KEY", "").strip()
    if key:
        return key
    if config.is_production():
        raise RuntimeError(
            "SECRET_KEY est obligatoire quand APP_ENV=production. "
            'Génère-la avec : python -c "import secrets; print(secrets.token_hex(32))"'
        )
    log.warning(
        "SECRET_KEY absente : clé aléatoire générée pour cette session. "
        "Toutes les sessions seront invalidées au redémarrage."
    )
    return secrets.token_hex(32)


def create_app() -> Flask:
    app = Flask(__name__)
    app.secret_key = _resolve_secret_key()

    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=config.session_cookie_secure(),
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
    )

    from .db import init_db
    init_db()

    from .routes import bp, start_network_poller
    app.register_blueprint(bp)
    if config.poller_enabled():
        start_network_poller()

    @app.after_request
    def _security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        return response

    return app
