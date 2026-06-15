"""Client pour l'API locale de la Bbox Bouygues (F@st5688b)."""

import logging
import time
import urllib.parse

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

log = logging.getLogger(__name__)


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
        for attempt in range(3):
            try:
                resp = self.session.get(f"{self.api_url}/device/token", timeout=5)
                resp.raise_for_status()
                return resp.json()[0]["device"]["token"]
            except Exception:
                if attempt < 2:
                    time.sleep(5)
                else:
                    raise

    # ── Requêtes bas niveau ───────────────────────────────────────────────
    #
    # IMPORTANT : sur la F@st5688b avec firmware 25.x, toutes les écritures
    # (PUT/POST/DELETE) reçoivent d'abord un HTTP 302 vers
    # https://mabbox.bytel.fr/api/v1/<path>?btoken=...
    # Il faut rejouer la requête sur cette URL Bytel (avec le même corps)
    # pour que la modification soit effectivement appliquée.

    def _follow_write(
        self,
        method: str,
        path: str,
        body: str = "",
        extra_hdrs: dict | None = None,
    ) -> requests.Response:
        """Exécute une écriture en gérant la redirection 302 vers Bytel."""
        self._ensure_auth()
        url = f"{self.api_url}{path}?btoken={self._btoken()}"
        hdrs: dict = {"Content-Type": "application/x-www-form-urlencoded", "ForceData": body}
        if extra_hdrs:
            hdrs.update(extra_hdrs)

        fn = {
            "PUT": self.session.put,
            "POST": self.session.post,
            "DELETE": self.session.delete,
        }[method.upper()]

        kwargs: dict = {"allow_redirects": False, "timeout": 5}
        if method.upper() != "DELETE":
            kwargs["data"] = body
            kwargs["headers"] = hdrs

        r = fn(url, **kwargs)
        log.debug("%s %s → %s", method, path, r.status_code)

        if r.status_code in (301, 302, 303, 307, 308):
            redirect_url = r.headers.get("Location", "")
            log.debug("  redirect → %s", redirect_url[:80])
            r_kwargs: dict = {"allow_redirects": False, "timeout": 10, "verify": False}
            if method.upper() != "DELETE":
                r_kwargs["data"] = body
                r_kwargs["headers"] = hdrs
            r = fn(redirect_url, **r_kwargs)
            log.debug("  Bytel %s → %s  %s", method, r.status_code, r.text[:200])

        if r.status_code == 401:
            self.login()
            return self._follow_write(method, path, body, extra_hdrs)

        if not r.ok and r.status_code not in (201,):
            log.warning("%s %s réponse inattendue : %s %s", method, path, r.status_code, r.text[:200])

        return r

    def _get(self, path: str) -> list | dict:
        self._ensure_auth()
        resp = self.session.get(f"{self.api_url}{path}", timeout=5)
        if resp.status_code == 401:
            self.login()
            resp = self.session.get(f"{self.api_url}{path}", timeout=5)
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, data: dict) -> requests.Response:
        body = urllib.parse.urlencode(data)
        log.debug("POST %s  body=%s", path, body)
        return self._follow_write("POST", path, body)

    def _put(self, path: str, data: dict) -> requests.Response:
        body = urllib.parse.urlencode(data)
        log.debug("PUT %s  body=%s", path, body)
        return self._follow_write("PUT", path, body)

    def _delete(self, path: str) -> requests.Response:
        log.debug("DELETE %s", path)
        return self._follow_write("DELETE", path)

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

    # ── Contrôle parental (méthode qui fonctionne réellement) ────────────

    def _get_parental_scheduler(self) -> dict:
        data = self._get("/parentalcontrol/scheduler")
        return data[0].get("parentalcontrol", {}).get("scheduler", {})

    def block_mac(self, mac: str, hostname: str = "") -> None:
        """Bloque l'accès internet d'un appareil via le contrôle parental.

        Méthode confirmée sur F@st5688b firmware 25.1.22 :
        1. Active le planificateur de contrôle parental
        2. Crée une règle de blocage 24h/24 7j/7
        3. Assigne l'appareil au contrôle parental
        """
        mac_norm = mac.lower()

        # Étape 1 : active le planificateur parental
        self._put("/parentalcontrol", {"enable": "1"})

        # Étape 2 : crée une règle de blocage toute la semaine
        self._post("/parentalcontrol/scheduler/rule", {
            "enable": "1",
            "intervals": "00:00,24:00",
            "name": f"block_{mac_norm}",
            "occurency": "1,2,3,4,5,6,0",
        })

        # Étape 3 : assigne l'appareil au contrôle parental
        self._put("/parentalcontrol/hosts", {
            "enable": "1",
            "macaddress": mac_norm,
        })

    def unblock_mac(self, mac: str) -> None:
        """Débloque un appareil précédemment bloqué via le contrôle parental.

        Supprime l'assignation de l'appareil au contrôle parental, puis
        nettoie les règles créées pour cette MAC.
        """
        mac_norm = mac.lower()

        # Étape 1 : retire l'appareil du contrôle parental
        self._put("/parentalcontrol/hosts", {
            "enable": "0",
            "macaddress": mac_norm,
        })

        # Étape 2 : supprime les règles de blocage associées à cette MAC
        sched = self._get_parental_scheduler()
        rule_name = f"block_{mac_norm}"
        for saved in sched.get("savedRules", []):
            if saved.get("name") == rule_name:
                try:
                    self._delete(f"/parentalcontrol/scheduler/rule/{saved['id']}")
                except Exception:
                    pass

        # Étape 3 : désactive le planificateur s'il n'y a plus de règles actives
        sched = self._get_parental_scheduler()
        active_rules = [s for s in sched.get("savedRules", []) if s.get("enable") == 1]
        if not active_rules:
            self._put("/parentalcontrol", {"enable": "0"})

    def disconnect_mac(self, mac: str) -> None:
        """Expulse un appareil WiFi via la meilleure méthode disponible."""
        mac_norm = mac.upper()

        # Récupère les infos de l'hôte (id entier + bande WiFi)
        hosts = self.get_all_hosts()
        host = next(
            (h for h in hosts if h.get("macaddress", "").upper().replace("-", ":") == mac_norm.replace("-", ":")),
            None,
        )

        # Tentative 1 : DELETE /hosts/{id} — peut envoyer des trames deauth
        if host and host.get("id") is not None:
            try:
                self._delete(f"/hosts/{host['id']}")
                return
            except Exception:
                pass

        # Tentative 2 : couper/rallumer la radio de la bande de l'appareil
        if host:
            link = host.get("link", "")
            if "2.4" in link:
                band_key = "24"
            elif "6" in link:
                band_key = "6"
            elif "5" in link:
                band_key = "5"
            else:
                band_key = None

            if band_key:
                try:
                    self._put("/wireless", {f"radio.{band_key}.enable": "0"})
                    time.sleep(2)
                    self._put("/wireless", {f"radio.{band_key}.enable": "1"})
                    return
                except Exception:
                    pass
