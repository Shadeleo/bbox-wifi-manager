import os
from datetime import datetime, timedelta

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


def _calc_last_seen(lastseen_secs: int | None) -> str | None:
    """Convertit un delta en secondes en timestamp ISO lisible."""
    if lastseen_secs is None:
        return None
    if lastseen_secs == 0:
        return datetime.now().isoformat(sep=" ", timespec="seconds")
    return (datetime.now() - timedelta(seconds=lastseen_secs)).isoformat(
        sep=" ", timespec="seconds"
    )


@bp.get("/")
def index():
    return render_template("index.html")


@bp.get("/api/devices")
def api_devices():
    try:
        client = _client()
        client.login()
        hosts    = client.get_all_hosts()
        acl_rules = client.get_acl_rules()
        blocked_macs = {r.get("mac", "").upper() for r in acl_rules}

        # Mise à jour de l'historique pour chaque appareil
        for host in hosts:
            mac      = host.get("macaddress", "").upper()
            hostname = host.get("hostname") or host.get("id", "Inconnu")
            ip       = host.get("ipaddress", "")
            first    = host.get("firstseen")
            last     = _calc_last_seen(host.get("lastseen"))
            if mac:
                upsert_device(mac, hostname, ip, first, last)

        db_index = {d["mac"]: d for d in get_all_devices()}

        devices = []
        for host in hosts:
            mac      = host.get("macaddress", "").upper()
            hostname = host.get("hostname") or host.get("id", "Inconnu")
            db       = db_index.get(mac, {})
            link     = host.get("link", "")
            is_wifi  = any(w in link.lower() for w in ("wifi", "wireless"))

            devices.append({
                "hostname":   hostname,
                "ip":         host.get("ipaddress", ""),
                "mac":        mac,
                "link":       link,
                "active":     host.get("active", 0),
                "rssi":       host.get("rssi"),
                "band":       host.get("wifitechnology") or host.get("band", ""),
                "is_wifi":    is_wifi,
                "is_blocked": mac in blocked_macs,
                "first_seen": host.get("firstseen") or db.get("first_seen"),
                "last_seen":  _calc_last_seen(host.get("lastseen")) or db.get("last_seen"),
            })

        acl = [
            {
                "rule_id":  r.get("id"),
                "mac":      r.get("mac", "").upper(),
                "hostname": r.get("hostname", ""),
            }
            for r in acl_rules
        ]

        return jsonify({
            "devices":       devices,
            "acl":           acl,
            "blocked_count": len(blocked_macs),
        })

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
    mac      = data.get("mac", "").upper()
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
