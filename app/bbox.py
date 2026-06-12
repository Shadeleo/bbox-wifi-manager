"""Client pour l'API locale de la Bbox Bouygues."""

import requests


class BboxClient:
    def __init__(self, host: str, password: str) -> None:
        self.base_url = f"http://{host}/api/v1"
        self.password = password
        self.session = requests.Session()
        self._authenticated = False

    def login(self) -> None:
        resp = self.session.post(
            f"{self.base_url}/login",
            data={"password": self.password},
            timeout=5,
        )
        resp.raise_for_status()
        self._authenticated = True

    def _get(self, path: str) -> list | dict:
        if not self._authenticated:
            self.login()
        resp = self.session.get(f"{self.base_url}{path}", timeout=5)
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, data: dict) -> requests.Response:
        if not self._authenticated:
            self.login()
        resp = self.session.post(f"{self.base_url}{path}", data=data, timeout=5)
        resp.raise_for_status()
        return resp

    def _delete(self, path: str) -> requests.Response:
        if not self._authenticated:
            self.login()
        resp = self.session.delete(f"{self.base_url}{path}", timeout=5)
        resp.raise_for_status()
        return resp

    def get_connected_hosts(self) -> list[dict]:
        data = self._get("/hosts")
        hosts = data[0].get("hosts", {}).get("list", [])
        return [h for h in hosts if h.get("link") == "Wireless"]

    def get_acl_rules(self) -> list[dict]:
        data = self._get("/wireless/acl")
        return data[0].get("wireless", {}).get("acl", {}).get("rules", [])

    def block_mac(self, mac: str, hostname: str = "") -> None:
        self._post(
            "/wireless/acl",
            {"mac": mac, "enable": 1, "type": "deny", "hostname": hostname},
        )

    def unblock_mac(self, rule_id: int) -> None:
        self._delete(f"/wireless/acl/{rule_id}")
