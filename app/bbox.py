"""Client pour l'API locale de la Bbox Bouygues (F@st5688b)."""

import urllib.parse

import requests


class BboxClient:
    # Fréquences WiFi reconnues par l'API Bbox
    _WIFI_LINKS = {"wifi", "wireless"}

    def __init__(self, host: str, password: str) -> None:
        self.api_url = f"http://{host}/api/v1"
        self.password = password
        self.session = requests.Session()
        self._authenticated = False

    # ── Authentification ──────────────────────────────────────────────────

    def login(self) -> None:
        """Auth en deux étapes : Bbox → redirection Bytel → cookie BBOX_ID."""
        body = urllib.parse.urlencode({"password": self.password, "remember": "1"})
        hdrs = {
            "Content-Type": "application/x-www-form-urlencoded",
            "ForceData": body,
        }
        # Étape 1 : Bbox redirige vers le service cloud Bytel
        r1 = self.session.post(
            f"{self.api_url}/login",
            data=body,
            headers=hdrs,
            allow_redirects=False,
            timeout=5,
        )
        if r1.status_code != 302:
            r1.raise_for_status()

        bytel_url = r1.headers.get("Location", "")
        if not bytel_url:
            raise RuntimeError("Pas de redirection vers Bytel reçue.")

        # Étape 2 : POST vers Bytel → reçoit le cookie BBOX_ID
        r2 = self.session.post(bytel_url, data=body, headers=hdrs,
                               allow_redirects=False, timeout=10)
        if r2.status_code not in (200, 204):
            raise RuntimeError(
                f"Authentification Bytel échouée (HTTP {r2.status_code})"
            )
        self._authenticated = True

    def _ensure_auth(self) -> None:
        if not self._authenticated:
            self.login()

    # ── Jeton CSRF (btoken) ───────────────────────────────────────────────

    def _btoken(self) -> str:
        """Récupère un jeton CSRF frais pour les opérations d'écriture."""
        resp = self.session.get(f"{self.api_url}/device/token", timeout=5)
        resp.raise_for_status()
        return resp.json()[0]["device"]["token"]

    # ── Requêtes bas niveau ───────────────────────────────────────────────

    def _get(self, path: str) -> list | dict:
        self._ensure_auth()
        resp = self.session.get(f"{self.api_url}{path}", timeout=5)
        if resp.status_code == 401:
            self.login()
            resp = self.session.get(f"{self.api_url}{path}", timeout=5)
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, data: dict) -> requests.Response:
        self._ensure_auth()
        body = urllib.parse.urlencode(data)
        resp = self.session.post(
            f"{self.api_url}{path}?btoken={self._btoken()}",
            data=body,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "ForceData": body,
            },
            timeout=5,
        )
        resp.raise_for_status()
        return resp

    def _delete(self, path: str) -> requests.Response:
        self._ensure_auth()
        resp = self.session.delete(
            f"{self.api_url}{path}?btoken={self._btoken()}",
            timeout=5,
        )
        resp.raise_for_status()
        return resp

    # ── API publique ──────────────────────────────────────────────────────

    def get_all_hosts(self) -> list[dict]:
        """Retourne tous les appareils connus de la Bbox (actifs et inactifs)."""
        data = self._get("/hosts")
        return data[0].get("hosts", {}).get("list", [])

    def get_wifi_hosts(self) -> list[dict]:
        """Retourne uniquement les appareils connectés en WiFi."""
        return [
            h for h in self.get_all_hosts()
            if any(w in h.get("link", "").lower() for w in self._WIFI_LINKS)
        ]

    def get_acl_rules(self) -> list[dict]:
        data = self._get("/wireless/acl")
        return data[0].get("acl", {}).get("rules", [])

    def block_mac(self, mac: str, hostname: str = "") -> None:
        self._post(
            "/wireless/acl",
            {"mac": mac, "enable": "1", "type": "deny", "hostname": hostname},
        )

    def unblock_mac(self, rule_id: int) -> None:
        self._delete(f"/wireless/acl/{rule_id}")
