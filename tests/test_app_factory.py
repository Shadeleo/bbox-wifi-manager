"""Fabrique d'application : clé de signature et durcissement des cookies."""

import pytest

from app import create_app


def test_secret_key_obligatoire_en_production(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        create_app()


def test_secret_key_vide_refusee_en_production(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "   ")
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        create_app()


def test_cle_aleatoire_toleree_en_developpement(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("SECRET_KEY", raising=False)
    assert create_app().secret_key != create_app().secret_key


def test_cle_fournie_utilisee_telle_quelle(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "ma-cle-fixe")
    assert create_app().secret_key == "ma-cle-fixe"


def test_cookies_durcis(flask_app):
    assert flask_app.config["SESSION_COOKIE_HTTPONLY"] is True
    assert flask_app.config["SESSION_COOKIE_SAMESITE"] == "Lax"
    assert flask_app.config["SESSION_COOKIE_SECURE"] is False


def test_cookie_secure_activable(monkeypatch):
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "1")
    assert create_app().config["SESSION_COOKIE_SECURE"] is True


def test_entetes_de_securite(client):
    resp = client.get("/login")
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "SAMEORIGIN"
    assert resp.headers["Referrer-Policy"] == "same-origin"
