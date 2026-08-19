"""Lecture de la configuration depuis l'environnement."""

import pytest

from app import config


def test_hote_par_defaut(monkeypatch):
    assert config.bbox_host() == config.DEFAULT_BBOX_HOST
    monkeypatch.setenv("BBOX_HOST", "192.168.0.1")
    assert config.bbox_host() == "192.168.0.1"


def test_hote_vide_retombe_sur_le_defaut(monkeypatch):
    monkeypatch.setenv("BBOX_HOST", "   ")
    assert config.bbox_host() == config.DEFAULT_BBOX_HOST


@pytest.mark.parametrize("valeur,attendu", [
    ("1", True), ("true", True), ("YES", True), ("on", True),
    ("0", False), ("false", False), ("non", False), ("", False),
])
def test_lecture_des_drapeaux(monkeypatch, valeur, attendu):
    monkeypatch.setenv("BBOX_VERIFY_TLS", valeur)
    assert config.verify_tls() is attendu


def test_tls_verifie_par_defaut(monkeypatch):
    """Le défaut doit être le choix sûr : le mot de passe transite par Bytel."""
    monkeypatch.delenv("BBOX_VERIFY_TLS", raising=False)
    assert config.verify_tls() is True


def test_cookie_secure_desactive_par_defaut(monkeypatch):
    """L'app tourne en HTTP local : l'activer par défaut casserait la session."""
    monkeypatch.delenv("SESSION_COOKIE_SECURE", raising=False)
    assert config.session_cookie_secure() is False


@pytest.mark.parametrize("valeur,attendu", [
    ("production", True), ("PRODUCTION", True), (" production ", True),
    ("development", False), ("prod", False),
])
def test_detection_de_la_production(monkeypatch, valeur, attendu):
    monkeypatch.setenv("APP_ENV", valeur)
    assert config.is_production() is attendu
