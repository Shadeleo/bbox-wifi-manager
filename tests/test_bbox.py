"""Client Bbox : politique TLS et signalement des effets de bord."""

from app.bbox import BboxClient


def test_tls_verifie_par_defaut(monkeypatch):
    """Le mot de passe transite par mabbox.bytel.fr lors de l'authentification."""
    monkeypatch.delenv("BBOX_VERIFY_TLS", raising=False)
    assert BboxClient("192.168.1.254", "secret").verify_tls is True


def test_tls_desactivable_explicitement(monkeypatch):
    monkeypatch.setenv("BBOX_VERIFY_TLS", "0")
    assert BboxClient("192.168.1.254", "secret").verify_tls is False


def test_parametre_explicite_prioritaire_sur_l_environnement(monkeypatch):
    monkeypatch.setenv("BBOX_VERIFY_TLS", "0")
    assert BboxClient("192.168.1.254", "secret", verify_tls=True).verify_tls is True


def test_url_api_construite_sur_l_hote():
    client = BboxClient("192.168.0.42", "secret")
    assert client.api_url == "http://192.168.0.42/api/v1"


def test_effet_de_bord_de_disconnect_documente():
    """Le repli coupe toute la bande WiFi : ça doit rester écrit noir sur blanc."""
    doc = BboxClient.disconnect_mac.__doc__ or ""
    assert "toute la bande" in doc
