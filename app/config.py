"""Configuration centralisée, lue depuis l'environnement.

Les valeurs sont exposées via des fonctions plutôt que des constantes : le
`.env` est chargé au démarrage de `run.py`, et les tests doivent pouvoir
modifier l'environnement sans réimporter le module.
"""

import os

# Adresse par défaut d'une Bbox sur le réseau local.
DEFAULT_BBOX_HOST = "192.168.1.254"

_TRUE = {"1", "true", "yes", "on"}


def _flag(name: str, default: str) -> bool:
    return os.getenv(name, default).strip().lower() in _TRUE


def is_production() -> bool:
    return os.getenv("APP_ENV", "development").strip().lower() == "production"


def bbox_host() -> str:
    return os.getenv("BBOX_HOST", "").strip() or DEFAULT_BBOX_HOST


def bbox_password() -> str:
    return os.getenv("BBOX_PASSWORD", "")


def verify_tls() -> bool:
    """Vérification du certificat TLS lors de l'authentification Bytel.

    Le mot de passe de la box transite par `mabbox.bytel.fr` : la désactiver
    expose ce mot de passe à une interception active.
    """
    return _flag("BBOX_VERIFY_TLS", "1")


def session_cookie_secure() -> bool:
    return _flag("SESSION_COOKIE_SECURE", "0")


def poller_enabled() -> bool:
    return _flag("ENABLE_POLLER", "1")


def log_level() -> str:
    return os.getenv("LOG_LEVEL", "INFO").strip().upper()
