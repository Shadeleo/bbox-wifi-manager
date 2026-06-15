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
        hosts = client.get_all_hosts()

        # Mise à jour de l'historique
        for host in hosts:
            mac      = host.get("macaddress", "").upper()
            hostname = str(host.get("hostname") or host.get("id") or "Inconnu")
            ip       = host.get("ipaddress", "")
            if mac:
                upsert_device(mac, hostname, ip,
                              host.get("firstseen"),
                              _calc_last_seen(host.get("lastseen")))

        db_index = {d["mac"]: d for d in get_all_devices()}

        devices = []
        blocked_count = 0
        for host in hosts:
            mac        = host.get("macaddress", "").upper()
            hostname   = str(host.get("hostname") or host.get("id") or "Inconnu")
            db         = db_index.get(mac, {})
            link       = host.get("link", "")
            is_wifi    = any(w in link.lower() for w in ("wifi", "wireless"))
            # Blocage détecté via contrôle parental (confirmé sur firmware 25.x)
            is_blocked = host.get("parentalcontrol", {}).get("enable") == 1

            if is_blocked:
                blocked_count += 1
                set_blocked(mac, True)

            devices.append({
                "hostname":   hostname,
                "ip":         host.get("ipaddress", ""),
                "mac":        mac,
                "link":       link,
                "active":     host.get("active", 0),
                "rssi":       host.get("rssi"),
                "band":       host.get("wifitechnology") or host.get("band", ""),
                "is_wifi":    is_wifi,
                "is_blocked": is_blocked,
                "first_seen": host.get("firstseen") or db.get("first_seen"),
                "last_seen":  _calc_last_seen(host.get("lastseen")) or db.get("last_seen"),
            })

        return jsonify({
            "devices":       devices,
            "blocked_count": blocked_count,
        })

    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@bp.get("/api/history")
def api_history():
    try:
        return jsonify({"devices": get_all_devices()})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@bp.post("/api/disconnect")
def api_disconnect():
    data = request.get_json(force=True)
    mac = data.get("mac", "").upper()
    try:
        client = _client()
        client.login()
        client.disconnect_mac(mac)
        return jsonify({"ok": True})
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


@bp.delete("/api/block")
def api_unblock():
    mac = request.args.get("mac", "").upper()
    try:
        client = _client()
        client.login()
        client.unblock_mac(mac)
        set_blocked(mac, False)
        return jsonify({"ok": True})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@bp.post("/api/kick-and-block")
def api_kick_and_block():
    data = request.get_json(force=True)
    mac      = data.get("mac", "").upper()
    hostname = data.get("hostname", "")
    try:
        client = _client()
        client.login()
        try:
            client.disconnect_mac(mac)
        except Exception:
            pass  # Le kick peut échouer (Ethernet, déjà déconnecté…), on bloque quand même
        client.block_mac(mac, hostname)
        set_blocked(mac, True)
        return jsonify({"ok": True})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
