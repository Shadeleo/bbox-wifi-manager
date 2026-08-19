"""Calcul de la date de dernière connexion à partir du champ `lastseen`.

Sur F@st5688b, la box renvoie `lastseen` en secondes (int) pour presque tous
les hôtes, mais la chaîne '-1' pour un hôte hors ligne jamais revu. C'est une
valeur sentinelle, pas une durée : elle ne doit ni faire planter l'API, ni
produire une date inventée.
"""

from datetime import datetime

import pytest

from app.routes import _calc_last_seen


def test_sentinelle_chaine_moins_un():
    """Régression : '-1' faisait planter timedelta et donc toute la page."""
    assert _calc_last_seen("-1") is None


def test_sentinelle_entiere_moins_un():
    assert _calc_last_seen(-1) is None


def test_valeur_absente():
    assert _calc_last_seen(None) is None


def test_zero_signifie_maintenant():
    resultat = _calc_last_seen(0)
    ecart = abs((datetime.now() - datetime.fromisoformat(resultat)).total_seconds())
    assert ecart < 5


def test_secondes_entieres():
    resultat = _calc_last_seen(3600)
    ecart = (datetime.now() - datetime.fromisoformat(resultat)).total_seconds()
    assert 3595 < ecart < 3605


def test_secondes_en_chaine_numerique():
    """La box mélange les types : une chaîne numérique doit rester exploitable."""
    resultat = _calc_last_seen("3600")
    ecart = (datetime.now() - datetime.fromisoformat(resultat)).total_seconds()
    assert 3595 < ecart < 3605


@pytest.mark.parametrize("valeur", ["", "   ", "inconnu", "12.5.3", [], {}])
def test_valeurs_inexploitables_ignorees(valeur):
    assert _calc_last_seen(valeur) is None


def test_api_devices_survit_a_la_sentinelle(client, bbox_factice, monkeypatch):
    """Reproduction du symptôme : la page entière tombait en erreur 500."""
    from app import routes

    class ClientFactice:
        def get_all_hosts(self):
            return [
                {"macaddress": "AA:BB:CC:DD:EE:01", "hostname": "en-ligne",
                 "ipaddress": "192.168.1.10", "link": "Wifi 5GHz", "active": 1,
                 "lastseen": 0, "firstseen": "2026-01-01T10:00:00+0100"},
                {"macaddress": "AA:BB:CC:DD:EE:42", "hostname": "hors-ligne",
                 "ipaddress": "", "link": "Offline", "active": 0,
                 "lastseen": "-1", "firstseen": "2026-08-12T16:14:33+0200"},
            ]

    monkeypatch.setattr(routes, "_client", lambda: ClientFactice())
    client.post("/login", data={"host": "192.168.1.254", "password": "x"})

    reponse = client.get("/api/devices")
    assert reponse.status_code == 200, reponse.get_json()
    appareils = {a["hostname"]: a for a in reponse.get_json()["devices"]}

    # Hôte hors ligne : aucune date inventée. _calc_last_seen rend None, et
    # l'appelant retombe sur le seul fait avéré, la première connexion.
    hors_ligne = appareils["hors-ligne"]
    assert hors_ligne["last_seen"] == "2026-08-12T16:14:33+0200"
    assert not hors_ligne["last_seen"].startswith(datetime.now().strftime("%Y-%m-%d")),         "un appareil hors ligne ne doit pas etre date a aujourd'hui"

    # Hôte en ligne (lastseen=0) : daté de maintenant.
    assert appareils["en-ligne"]["last_seen"].startswith(datetime.now().strftime("%Y-%m-%d"))
