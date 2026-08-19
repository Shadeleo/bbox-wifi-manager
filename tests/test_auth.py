"""Authentification : confinement du mot de passe, protection des routes,
limitation des tentatives."""

import base64
import zlib

import pytest

from app import routes

MOT_DE_PASSE = "mot-de-passe-admin-tres-secret-42"


def _valeur_cookie_session(reponse) -> str:
    for entete in reponse.headers.getlist("Set-Cookie"):
        if entete.startswith("session="):
            return entete.split("session=", 1)[1].split(";", 1)[0]
    return ""


def _charge_utile_decodee(cookie: str) -> str:
    """Décode la charge utile d'un cookie de session Flask.

    Les sessions Flask sont *signées* mais **non chiffrées** : n'importe qui
    possédant le cookie peut en lire le contenu. C'est toute la raison d'être
    du magasin de mots de passe côté serveur.
    """
    brut = cookie
    compresse = brut.startswith(".")
    if compresse:
        brut = brut[1:]
    charge = brut.split(".")[0]
    donnees = base64.urlsafe_b64decode(charge + "=" * (-len(charge) % 4))
    if compresse:
        donnees = zlib.decompress(donnees)
    return donnees.decode("utf-8", errors="replace")


def _connexion(client):
    return client.post(
        "/login",
        data={"host": "192.168.1.254", "password": MOT_DE_PASSE},
    )


def test_connexion_reussie_redirige(client, bbox_factice):
    reponse = _connexion(client)
    assert reponse.status_code == 302
    assert reponse.headers["Location"].endswith("/")


def test_le_mot_de_passe_n_est_jamais_dans_le_cookie(client, bbox_factice):
    """Régression : le mot de passe de la box était stocké dans la session."""
    reponse = _connexion(client)
    cookie = _valeur_cookie_session(reponse)
    assert cookie, "aucun cookie de session émis"

    assert MOT_DE_PASSE not in cookie
    charge = _charge_utile_decodee(cookie)
    assert MOT_DE_PASSE not in charge
    assert "bbox_password" not in charge
    # Ce qui doit s'y trouver : l'hôte (non secret) et un identifiant opaque.
    assert "cred_id" in charge


def test_le_mot_de_passe_reste_accessible_cote_serveur(client, bbox_factice):
    _connexion(client)
    assert MOT_DE_PASSE in routes._cred_store.values()


def test_deconnexion_purge_le_magasin(client, bbox_factice):
    _connexion(client)
    assert routes._cred_store
    client.post("/logout")
    assert routes._cred_store == {}


def test_cookie_perime_apres_redemarrage(client, bbox_factice):
    """Magasin vidé (redémarrage) : le cookie seul ne doit plus donner accès."""
    _connexion(client)
    assert client.get("/api/history").status_code == 200
    routes._cred_store.clear()
    assert client.get("/api/history").status_code == 401


@pytest.mark.parametrize("chemin", [
    "/api/devices", "/api/history", "/api/network-stats", "/api/network-stats/live",
])
def test_api_protegee_par_authentification(client, chemin):
    reponse = client.get(chemin)
    assert reponse.status_code == 401
    assert reponse.get_json()["redirect"] == "/login"


def test_page_index_redirige_vers_login(client):
    reponse = client.get("/")
    assert reponse.status_code == 302
    assert "/login" in reponse.headers["Location"]


@pytest.mark.parametrize("hote", ["127.0.0.1", "pas-une-ip", "", "192.168.1.999", "localhost"])
def test_hote_invalide_refuse(client, bbox_factice, hote):
    reponse = client.post("/login", data={"host": hote, "password": "x"})
    assert reponse.status_code == 200
    assert "Adresse IP invalide" in reponse.get_data(as_text=True)


def test_limitation_des_tentatives(client, bbox_factice):
    bbox_factice.doit_echouer = True
    for _ in range(routes._LOGIN_MAX_ATTEMPTS):
        reponse = client.post("/login", data={"host": "192.168.1.254", "password": "faux"})
        assert "Trop de tentatives" not in reponse.get_data(as_text=True)

    reponse = client.post("/login", data={"host": "192.168.1.254", "password": "faux"})
    assert "Trop de tentatives" in reponse.get_data(as_text=True)


def test_purge_des_tentatives_expirees(client, bbox_factice):
    """Sans purge, le dictionnaire des tentatives croît indéfiniment."""
    routes._login_attempts["10.0.0.9"] = [0.0]  # horodatage très ancien
    bbox_factice.doit_echouer = True
    client.post("/login", data={"host": "192.168.1.254", "password": "faux"})
    assert "10.0.0.9" not in routes._login_attempts


def test_page_de_login_utilise_l_hote_configure(client, monkeypatch):
    monkeypatch.setenv("BBOX_HOST", "192.168.7.7")
    corps = client.get("/login").get_data(as_text=True)
    assert "192.168.7.7" in corps
