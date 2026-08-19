"""Garde-fous du proxy vers la box et cache d'assets."""

import pytest

from app import routes


@pytest.mark.parametrize("chemin", [
    "../etc/passwd",
    "assets/../../secret",
    "a/b/../../../c",
    "http://evil.tld/x",
    "https://evil.tld/x",
    "//evil.tld/x",
])
def test_chemins_refuses(chemin):
    assert routes._is_safe_proxy_path(chemin) is False


@pytest.mark.parametrize("chemin", [
    "static/js/app.js",
    "medias/pictos/logo.png",
    "api/v1/hosts",
    "",
    "fichier..nom.js",
])
def test_chemins_acceptes(chemin):
    assert routes._is_safe_proxy_path(chemin) is True


def test_proxy_refuse_la_traversee(client, bbox_factice):
    client.post("/login", data={"host": "192.168.1.254", "password": "x"})
    reponse = client.get("/proxy/bbox/../../etc/passwd")
    assert reponse.status_code in (400, 404)


def test_cache_expire(monkeypatch):
    faux_temps = {"valeur": 1000.0}
    monkeypatch.setattr(routes.time, "monotonic", lambda: faux_temps["valeur"])

    routes._cache_put("app.js", b"contenu", "application/javascript", 200)
    assert routes._cache_get("app.js") is not None

    faux_temps["valeur"] += routes._ASSET_CACHE_TTL + 1
    assert routes._cache_get("app.js") is None, "un asset périmé ne doit plus être servi"


def test_cache_ignore_la_chaine_de_requete():
    routes._cache_put("app.js?v=2", b"contenu", "application/javascript", 200)
    assert routes._cache_get("app.js?v=9") is not None


def test_cache_plafonne():
    for i in range(routes._MAX_CACHE_ENTRIES + 50):
        routes._cache_put(f"fichier{i}.js", b"x", "application/javascript", 200)
    assert len(routes._asset_cache) <= routes._MAX_CACHE_ENTRIES
