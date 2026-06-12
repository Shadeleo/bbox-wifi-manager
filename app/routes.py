import os

from flask import Blueprint, jsonify, render_template, request
from dotenv import load_dotenv

from .bbox import BboxClient
from .db import get_all_devices, set_blocked, upsert_device

load_dotenv()

bp = Blueprint("main", __name__)


def _client() -> BboxClient:
    return BboxClient(
        host=os.getenv("BBOX_HOST", "192.168.1.254"),
        password=os.getenv("BBOX_PASSWORD", ""),
    )


@bp.get("/")
def index():
    return render_template("index.html")


@bp.get("/api/devices")
def api_devices():
    try:
        client = _client()
        client.login()
        hosts = client.get_connected_hosts()
        acl_rules = client.get_acl_rules()
        blocked_macs = {r.get("mac", "").upper() for r in acl_rules}

        # Mise à jour de l'historique pour chaque appareil connecté
        for host in hosts:
            upsert_device(
                mac=host.get("macaddress", "").upper(),
                hostname=host.get("hostname") or host.get("id", "Inconnu"),
                ip=host.get("ipaddress", ""),
            )

        db_index = {d["mac"]: d for d in get_all_devices()}

        devices = []
        for host in hosts:
            mac = host.get("macaddress", "").upper()
            db = db_index.get(mac, {})
            devices.append({
                "hostname": host.get("hostname") or host.get("id", "Inconnu"),
                "ip": host.get("ipaddress", ""),
                "mac": mac,
                "rssi": host.get("rssi"),
                "band": host.get("band", ""),
                "is_blocked": mac in blocked_macs,
                "first_seen": db.get("first_seen"),
                "last_seen": db.get("last_seen"),
            })

        acl = [
            {
                "rule_id": r.get("id"),
                "mac": r.get("mac", "").upper(),
                "hostname": r.get("hostname", ""),
            }
            for r in acl_rules
        ]

        return jsonify({"devices": devices, "acl": acl, "blocked_count": len(blocked_macs)})

    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@bp.get("/api/history")
def api_history():
    try:
        return jsonify({"devices": get_all_devices()})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@bp.post("/api/block")
def api_block():
    data = request.get_json(force=True)
    mac = data.get("mac", "").upper()
    hostname = data.get("hostname", "")
    try:
        client = _client()
        client.login()
        client.block_mac(mac, hostname)
        set_blocked(mac, True)
        return jsonify({"ok": True})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@bp.delete("/api/block/<int:rule_id>")
def api_unblock(rule_id: int):
    mac = request.args.get("mac", "").upper()
    try:
        client = _client()
        client.login()
        client.unblock_mac(rule_id)
        if mac:
            set_blocked(mac, False)
        return jsonify({"ok": True})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
