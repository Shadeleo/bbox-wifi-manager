import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

_ENV_VARS = (
    "APP_ENV", "SECRET_KEY", "BBOX_HOST", "BBOX_PASSWORD",
    "BBOX_VERIFY_TLS", "SESSION_COOKIE_SECURE", "ENABLE_POLLER", "LOG_LEVEL",
)


@pytest.fixture(autouse=True)
def env_isole(tmp_path, monkeypatch):
    """Environnement neutre et base jetable pour chaque test.

    `app.routes` appelle load_dotenv() à l'import : on l'importe d'abord, puis
    on purge les variables, sinon le .env réel du poste contaminerait les tests.
    """
    import app.routes  # noqa: F401  (déclenche le load_dotenv du module)
    from app import db, routes

    for var in _ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("ENABLE_POLLER", "0")
    monkeypatch.setenv("SECRET_KEY", "cle-de-test")

    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "history.db"))
    db.init_db()

    routes._login_attempts.clear()
    routes._cred_store.clear()
    routes._asset_cache.clear()
    yield


@pytest.fixture
def flask_app():
    from app import create_app
    application = create_app()
    application.config.update(TESTING=True)
    return application


@pytest.fixture
def client(flask_app):
    return flask_app.test_client()


class FakeBboxClient:
    """Client Bbox factice : aucune requête réseau."""

    doit_echouer = False

    def __init__(self, host, password, verify_tls=None):
        self.host = host
        self.password = password

    def login(self):
        if type(self).doit_echouer:
            raise RuntimeError("Authentification refusée")


@pytest.fixture
def bbox_factice(monkeypatch):
    from app import routes
    FakeBboxClient.doit_echouer = False
    monkeypatch.setattr(routes, "BboxClient", FakeBboxClient)
    return FakeBboxClient
