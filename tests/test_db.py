"""Persistance SQLite : historique des appareils et statistiques réseau."""

from datetime import datetime, timedelta

from app import db


def _appareils_par_mac():
    return {a["mac"]: a for a in db.get_all_devices()}


def test_insertion_puis_relecture():
    db.upsert_device("AA:BB:CC:DD:EE:FF", "portable", "192.168.1.20")
    appareil = _appareils_par_mac()["AA:BB:CC:DD:EE:FF"]
    assert appareil["hostname"] == "portable"
    assert appareil["ip"] == "192.168.1.20"
    assert appareil["is_blocked"] == 0


def test_upsert_conserve_la_premiere_connexion_la_plus_ancienne():
    mac = "AA:BB:CC:DD:EE:01"
    db.upsert_device(mac, "pc", "192.168.1.10",
                     first_seen="2026-01-02 00:00:00", last_seen="2026-01-02 00:00:00")
    db.upsert_device(mac, "pc", "192.168.1.10",
                     first_seen="2026-01-01 00:00:00", last_seen="2026-01-03 00:00:00")

    appareil = _appareils_par_mac()[mac]
    assert appareil["first_seen"] == "2026-01-01 00:00:00"
    assert appareil["last_seen"] == "2026-01-03 00:00:00"


def test_upsert_ne_recule_pas_la_premiere_connexion():
    mac = "AA:BB:CC:DD:EE:02"
    db.upsert_device(mac, "pc", "192.168.1.10",
                     first_seen="2026-01-01 00:00:00", last_seen="2026-01-01 00:00:00")
    db.upsert_device(mac, "pc", "192.168.1.11",
                     first_seen="2026-06-01 00:00:00", last_seen="2026-06-01 00:00:00")

    appareil = _appareils_par_mac()[mac]
    assert appareil["first_seen"] == "2026-01-01 00:00:00"
    assert appareil["ip"] == "192.168.1.11"


def test_marquage_bloque():
    mac = "AA:BB:CC:DD:EE:03"
    db.upsert_device(mac, "tablette", "192.168.1.30")
    db.set_blocked(mac, True)
    assert _appareils_par_mac()[mac]["is_blocked"] == 1
    db.set_blocked(mac, False)
    assert _appareils_par_mac()[mac]["is_blocked"] == 0


def test_statistiques_reseau_filtrees_par_fenetre():
    maintenant = datetime.now()
    recent = maintenant.isoformat(sep=" ", timespec="seconds")
    ancien = (maintenant - timedelta(hours=48)).isoformat(sep=" ", timespec="seconds")

    db.insert_network_stat(ancien, 1, 1, 1, 1)
    db.insert_network_stat(recent, 2, 2, 2, 2)

    horodatages = [p["ts"] for p in db.get_network_stats(hours=24)]
    assert recent in horodatages
    assert ancien not in horodatages


def test_purge_des_statistiques_au_dela_de_30_jours():
    maintenant = datetime.now()
    tres_ancien = (maintenant - timedelta(days=40)).isoformat(sep=" ", timespec="seconds")

    db.insert_network_stat(tres_ancien, 1, 1, 1, 1)
    db.insert_network_stat(maintenant.isoformat(sep=" ", timespec="seconds"), 2, 2, 2, 2)

    # La seconde insertion purge les points antérieurs à la fenêtre de 30 jours.
    points = db.get_network_stats(hours=24 * 400)
    assert len(points) == 1
    assert points[0]["rx_bytes"] == 2
