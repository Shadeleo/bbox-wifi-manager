import ipaddress
import logging
import re
import secrets
import threading
import time
from datetime import datetime, timedelta
from functools import wraps

import requests as _req
from dotenv import load_dotenv
from flask import (
    Blueprint,
    Response,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from . import config
from .bbox import BboxClient
from .db import get_all_devices, get_network_stats, insert_network_stat, set_blocked, upsert_device

load_dotenv()

log = logging.getLogger(__name__)

bp = Blueprint("main", __name__)

# Identifiants actifs partagés avec le poller d'arrière-plan (pas d'accès à la
# session Flask en dehors d'une requête HTTP). Pré-remplis depuis .env, mis à
# jour à chaque connexion réussie via do_login().
_active_creds = {
    "host":     config.bbox_host(),
    "password": config.bbox_password(),
}

# Magasin de mots de passe côté serveur. Les sessions Flask sont signées mais
# NON chiffrées : y placer le mot de passe de la box le rendrait lisible par
# quiconque possède le cookie. Seul un identifiant opaque transite dans la
# session ; le mot de passe reste ici, en mémoire du processus.
_cred_store: dict[str, str] = {}
_cred_lock = threading.Lock()

# Limite de tentatives de connexion par IP (l'app écoute sur le réseau WiFi,
# pas seulement en local — on bloque le bruteforce du mot de passe Bbox).
_login_attempts: dict[str, list[float]] = {}
_LOGIN_MAX_ATTEMPTS = 5
_LOGIN_WINDOW_SECONDS = 300


def _store_password(password: str) -> str:
    """Enregistre le mot de passe côté serveur, retourne son identifiant opaque."""
    cred_id = secrets.token_urlsafe(32)
    with _cred_lock:
        _cred_store[cred_id] = password
    return cred_id


def _has_creds() -> bool:
    cred_id = session.get("cred_id")
    if not cred_id:
        return False
    with _cred_lock:
        return cred_id in _cred_store


def _session_password() -> str:
    cred_id = session.get("cred_id")
    if not cred_id:
        return config.bbox_password()
    with _cred_lock:
        return _cred_store.get(cred_id, config.bbox_password())


def _forget_password() -> None:
    cred_id = session.get("cred_id")
    if cred_id:
        with _cred_lock:
            _cred_store.pop(cred_id, None)


def _session_host() -> str:
    return session.get("bbox_host") or config.bbox_host()


def _render_login(**kwargs):
    return render_template("login.html", default_host=config.bbox_host(), **kwargs)


def _api_error(exc: Exception, status: int = 500):
    """Erreur API : détaillée en développement, générique en production."""
    log.exception("Erreur API : %s", exc)
    if config.is_production():
        return jsonify({"error": "Erreur interne — consultez les journaux du serveur."}), status
    return jsonify({"error": str(exc)}), status


def _client() -> BboxClient:
    """Client Bbox authentifié, réutilisant la session mise en cache (évite de
    refaire le handshake Bbox+Bytel à chaque appel API)."""
    host = _session_host()
    password = _session_password()
    client = BboxClient(host=host, password=password)
    client.session = _get_bbox_session(host, password)
    client._authenticated = True
    return client


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        # _has_creds() : après un redémarrage le magasin est vide, le cookie
        # seul ne suffit plus — on force une reconnexion.
        if not session.get("authenticated") or not _has_creds():
            session.clear()
            if request.path.startswith("/api/"):
                return jsonify({"error": "Non authentifié", "redirect": "/login"}), 401
            return redirect(url_for("main.login_page"))
        return f(*args, **kwargs)
    return decorated


def _calc_last_seen(lastseen_secs: int | None) -> str | None:
    if lastseen_secs is None:
        return None
    if lastseen_secs == 0:
        return datetime.now().isoformat(sep=" ", timespec="seconds")
    return (datetime.now() - timedelta(seconds=lastseen_secs)).isoformat(
        sep=" ", timespec="seconds"
    )


# ── Auth ──────────────────────────────────────────────────────────────────────

@bp.get("/login")
def login_page():
    if session.get("authenticated"):
        return redirect(url_for("main.index"))
    return _render_login()


@bp.post("/login")
def do_login():
    client_ip = request.remote_addr or "unknown"
    now = time.time()
    # Purge les IP dont la fenêtre est expirée : sans ça le dict croît sans fin.
    for ip_addr, stamps in list(_login_attempts.items()):
        if all(now - t >= _LOGIN_WINDOW_SECONDS for t in stamps):
            _login_attempts.pop(ip_addr, None)

    recent = [t for t in _login_attempts.get(client_ip, []) if now - t < _LOGIN_WINDOW_SECONDS]
    if len(recent) >= _LOGIN_MAX_ATTEMPTS:
        wait_min = int((_LOGIN_WINDOW_SECONDS - (now - recent[0])) / 60) + 1
        return _render_login(
            error=f"Trop de tentatives échouées. Réessaie dans {wait_min} min.",
        )
    _login_attempts[client_ip] = recent

    host     = request.form.get("host", config.DEFAULT_BBOX_HOST).strip()
    password = request.form.get("password", "").strip()
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_loopback:
            return _render_login(error="Adresse IP invalide")
    except ValueError:
        return _render_login(
            error=f"Adresse IP invalide (ex : {config.DEFAULT_BBOX_HOST})"
        )
    try:
        client = BboxClient(host=host, password=password)
        client.login()
        session["authenticated"] = True
        session["bbox_host"]     = host
        # Le mot de passe reste côté serveur : la session ne porte qu'un jeton.
        session["cred_id"]       = _store_password(password)
        _active_creds["host"]     = host
        _active_creds["password"] = password
        _login_attempts.pop(client_ip, None)
        return redirect(url_for("main.index"))
    except Exception as exc:
        _login_attempts.setdefault(client_ip, []).append(now)
        return _render_login(error=str(exc))


@bp.post("/logout")
def logout():
    _forget_password()
    session.clear()
    return redirect(url_for("main.login_page"))


# ── Pages ─────────────────────────────────────────────────────────────────────

@bp.get("/")
@login_required
def index():
    return render_template("index.html", bbox_host=session.get("bbox_host", ""))


# ── API ───────────────────────────────────────────────────────────────────────

@bp.get("/api/devices")
@login_required
def api_devices():
    try:
        client = _client()
        hosts = client.get_all_hosts()

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
            is_blocked = host.get("parentalcontrol", {}).get("enable") == 1
            wireless   = host.get("wireless") or {}
            try:
                rssi = int(wireless.get("rssi0"))
            except (TypeError, ValueError):
                rssi = None
            try:
                tx_usage = int(wireless.get("txUsage"))
            except (TypeError, ValueError):
                tx_usage = None
            try:
                rx_usage = int(wireless.get("rxUsage"))
            except (TypeError, ValueError):
                rx_usage = None

            if is_blocked:
                blocked_count += 1
                set_blocked(mac, True)

            devices.append({
                "hostname":   hostname,
                "ip":         host.get("ipaddress", ""),
                "mac":        mac,
                "link":       link,
                "active":     host.get("active", 0),
                "rssi":       rssi,
                "band":       wireless.get("band", ""),
                "tx_usage":   tx_usage,
                "rx_usage":   rx_usage,
                "is_wifi":    is_wifi,
                "is_blocked": is_blocked,
                "first_seen": host.get("firstseen") or db.get("first_seen"),
                "last_seen":  _calc_last_seen(host.get("lastseen")) or db.get("last_seen"),
            })

        return jsonify({"devices": devices, "blocked_count": blocked_count})

    except Exception as exc:
        return _api_error(exc)


@bp.get("/api/history")
@login_required
def api_history():
    try:
        return jsonify({"devices": get_all_devices()})
    except Exception as exc:
        return _api_error(exc)


def _get_device_activity() -> list[dict]:
    """Indice d'activité relatif (0-8) par appareil WiFi actif."""
    activity = []
    client = _client()
    for host in client.get_all_hosts():
        if not host.get("active"):
            continue
        wireless = host.get("wireless") or {}
        if not wireless:
            continue
        try:
            tx_usage = int(wireless.get("txUsage", 0))
            rx_usage = int(wireless.get("rxUsage", 0))
        except (TypeError, ValueError):
            continue
        activity.append({
            "hostname": str(host.get("hostname") or host.get("id") or "Inconnu"),
            "tx_usage": tx_usage,
            "rx_usage": rx_usage,
            "usage": max(tx_usage, rx_usage),
        })
    return activity


_activity_cache: dict = {"data": [], "ts": 0.0}
_ACTIVITY_CACHE_TTL = 5  # secondes — évite de réinterroger /hosts à chaque poll live (2s)


def _get_device_activity_cached() -> list[dict]:
    now = time.monotonic()
    if now - _activity_cache["ts"] > _ACTIVITY_CACHE_TTL:
        _activity_cache["data"] = _get_device_activity()
        _activity_cache["ts"] = now
    return _activity_cache["data"]


@bp.get("/api/network-stats/live")
@login_required
def api_network_stats_live():
    try:
        client = _client()
        stats = client.get_wan_stats()
        rx = stats.get("rx", {})
        tx = stats.get("tx", {})
        try:
            activity = _get_device_activity_cached()
        except Exception as exc:
            log.warning("Activité par appareil indisponible : %s", exc)
            activity = []
        return jsonify({
            "rx_kbps": int(rx.get("bandwidth", 0)),
            "tx_kbps": int(tx.get("bandwidth", 0)),
            "activity": activity,
        })
    except Exception as exc:
        return _api_error(exc)


@bp.get("/api/network-stats")
@login_required
def api_network_stats():
    try:
        points = get_network_stats(hours=24)

        total_gb = None
        peak_mbps = 0.0
        if points:
            last = points[-1]
            total_gb = (last["rx_bytes"] + last["tx_bytes"]) / 1e9
            peak_mbps = max(
                max(p["rx_kbps"], p["tx_kbps"]) for p in points
            ) / 1000

        try:
            activity = _get_device_activity()
        except Exception as exc:
            log.warning("Activité par appareil indisponible : %s", exc)
            activity = []

        return jsonify({
            "points": points,
            "total_gb": total_gb,
            "peak_mbps": round(peak_mbps, 2),
            "activity": activity,
        })
    except Exception as exc:
        return _api_error(exc)


@bp.post("/api/disconnect")
@login_required
def api_disconnect():
    data = request.get_json(force=True)
    mac  = data.get("mac", "").upper()
    try:
        client = _client()
        client.disconnect_mac(mac)
        return jsonify({"ok": True})
    except Exception as exc:
        return _api_error(exc)


@bp.post("/api/block")
@login_required
def api_block():
    data     = request.get_json(force=True)
    mac      = data.get("mac", "").upper()
    hostname = data.get("hostname", "")
    try:
        client = _client()
        client.block_mac(mac, hostname)
        set_blocked(mac, True)
        return jsonify({"ok": True})
    except Exception as exc:
        return _api_error(exc)


@bp.delete("/api/block")
@login_required
def api_unblock():
    mac = request.args.get("mac", "").upper()
    try:
        client = _client()
        client.unblock_mac(mac)
        set_blocked(mac, False)
        return jsonify({"ok": True})
    except Exception as exc:
        return _api_error(exc)


@bp.post("/api/kick-and-block")
@login_required
def api_kick_and_block():
    data     = request.get_json(force=True)
    mac      = data.get("mac", "").upper()
    hostname = data.get("hostname", "")
    try:
        client = _client()
        try:
            client.disconnect_mac(mac)
        except Exception:
            pass
        client.block_mac(mac, hostname)
        set_blocked(mac, True)
        return jsonify({"ok": True})
    except Exception as exc:
        return _api_error(exc)


# ── Bbox proxy ────────────────────────────────────────────────────────────────

_SKIP_HEADERS = {
    "x-frame-options", "content-security-policy", "content-security-policy-report-only",
    "transfer-encoding", "connection", "content-encoding",
    "etag", "last-modified", "cache-control", "expires",
}
_SKIP_REQUEST_HEADERS = {
    "host", "referer", "accept-encoding",
    "if-none-match", "if-modified-since", "if-unmodified-since",
    "if-match", "if-range",
}

_authed_sessions: dict[str, _req.Session] = {}
_sessions_lock = threading.Lock()

_asset_cache: dict[str, tuple[bytes, str, int, float]] = {}  # path → (body, type, status, ts)
_CACHEABLE_EXT = (".js", ".css", ".png", ".svg", ".woff", ".woff2", ".ttf", ".ico", ".webp", ".jpg", ".jpeg", ".gif")
_MAX_CACHE_ENTRIES = 200
_ASSET_CACHE_TTL = 3600  # 1 h — sans expiration, un asset périmé après mise à jour
                         # du firmware serait servi indéfiniment.


def _cache_key(path: str) -> str:
    return path.split("?")[0]


def _is_cacheable(path: str) -> bool:
    return request.method == "GET" and _cache_key(path).endswith(_CACHEABLE_EXT)


def _cache_get(path: str) -> tuple[bytes, str, int] | None:
    entry = _asset_cache.get(_cache_key(path))
    if entry is None:
        return None
    body, content_type, status, stored_at = entry
    if time.monotonic() - stored_at >= _ASSET_CACHE_TTL:
        _asset_cache.pop(_cache_key(path), None)
        return None
    return body, content_type, status


def _cache_put(path: str, body: bytes, content_type: str, status: int) -> None:
    now = time.monotonic()
    if len(_asset_cache) >= _MAX_CACHE_ENTRIES:
        for key, entry in list(_asset_cache.items()):
            if now - entry[3] >= _ASSET_CACHE_TTL:
                _asset_cache.pop(key, None)
    if len(_asset_cache) < _MAX_CACHE_ENTRIES:
        _asset_cache[_cache_key(path)] = (body, content_type, status, now)


def _is_safe_proxy_path(path: str) -> bool:
    """Refuse la traversée de répertoire et les URL absolues dans le proxy."""
    if "://" in path or path.startswith("//"):
        return False
    return ".." not in _cache_key(path).split("/")


def _get_bbox_session(bbox_host: str, password: str) -> _req.Session:
    """Return a cached, authenticated requests.Session for the Bbox."""
    with _sessions_lock:
        if bbox_host not in _authed_sessions:
            client = BboxClient(host=bbox_host, password=password)
            client.login()
            _authed_sessions[bbox_host] = client.session
        return _authed_sessions[bbox_host]


# ── Poller de bande passante (arrière-plan) ────────────────────────────────────

_POLL_INTERVAL_SECONDS = 300


def _poll_network_stats() -> None:
    """Récupère un point de conso WAN depuis la Bbox et le stocke en base."""
    try:
        host = _active_creds["host"]
        password = _active_creds["password"]
        sess = _get_bbox_session(host, password)
        client = BboxClient(host=host, password=password)
        client.session = sess
        client._authenticated = True
        stats = client.get_wan_stats()
        rx = stats.get("rx", {})
        tx = stats.get("tx", {})
        insert_network_stat(
            ts=datetime.now().isoformat(sep=" ", timespec="seconds"),
            rx_bytes=int(rx.get("bytes", 0)),
            tx_bytes=int(tx.get("bytes", 0)),
            rx_kbps=int(rx.get("bandwidth", 0)),
            tx_kbps=int(tx.get("bandwidth", 0)),
        )
    except Exception as exc:
        log.warning("Poll réseau échoué : %s", exc)


def _network_poll_loop() -> None:
    while True:
        _poll_network_stats()
        time.sleep(_POLL_INTERVAL_SECONDS)


def start_network_poller() -> None:
    """Démarre le thread d'arrière-plan qui collecte la conso réseau périodiquement."""
    threading.Thread(target=_network_poll_loop, daemon=True).start()


_PROXY_INTERCEPTOR = """
<script>
(function(){
  var P='/proxy/bbox';
  var O=window.location.origin;
  function rw(u){
    if(typeof u!=='string') return u;
    if(u.startsWith(O+'/')&&u.indexOf(P)<0) return P+u.slice(O.length);
    if(u.startsWith('/')&&!u.startsWith('//')&&u.indexOf(P)<0) return P+u;
    return u;
  }
  var oF=window.fetch;
  window.fetch=function(inp,init){
    if(typeof inp==='string') inp=rw(inp);
    else if(inp&&inp.url) inp=new Request(rw(inp.url),inp);
    return oF.call(this,inp,init);
  };
  var oO=XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open=function(m,u){
    return oO.apply(this,[m,rw(u)].concat(Array.prototype.slice.call(arguments,2)));
  };
  var iD=Object.getOwnPropertyDescriptor(HTMLImageElement.prototype,'src');
  if(iD&&iD.set){
    Object.defineProperty(HTMLImageElement.prototype,'src',{
      set:function(v){iD.set.call(this,rw(v));},
      get:function(){return iD.get.call(this);},
      configurable:true
    });
  }
  var oSA=Element.prototype.setAttribute;
  Element.prototype.setAttribute=function(name,val){
    if((name==='src'||name==='href')&&typeof val==='string') val=rw(val);
    return oSA.call(this,name,val);
  };
})();
</script>
"""


def _rewrite_urls(content: str, prefix: str, bbox_origin: str,
                  is_html: bool = False, is_css: bool = False) -> str:

    if is_html:
        # Rewrite HTML tag attributes (src=, href=, action=)
        def replace_attr(m):
            attr, quote, val = m.group(1), m.group(2), m.group(3)
            if val.startswith(bbox_origin):
                val = prefix + val[len(bbox_origin):]
            elif val.startswith("/") and not val.startswith("//"):
                val = prefix + val
            return f'{attr}={quote}{val}{quote}'

        content = re.sub(r'(src|href|action)=(["\'])([^"\']+)\2', replace_attr, content)

        # Inject runtime interceptor as first thing in <head>
        content = re.sub(
            r'(<head[^>]*>)',
            lambda m: m.group(0) + _PROXY_INTERCEPTOR,
            content, count=1, flags=re.IGNORECASE,
        )

    if is_css:
        # Rewrite CSS url() references only — do NOT run on JS to avoid breaking regex literals
        def replace_url(m):
            raw = m.group(1).strip()
            q = raw[0] if raw and raw[0] in ('"', "'") else ""
            val = raw[1:-1] if q else raw
            if val.startswith(bbox_origin):
                val = prefix + val[len(bbox_origin):]
            elif val.startswith("/") and not val.startswith("//"):
                val = prefix + val
            return f"url({q}{val}{q})"

        content = re.sub(r'url\(([^)]+)\)', replace_url, content)

    return content


def _proxy_to_bbox(path: str):
    """Shared proxy logic: fetch from Bbox using an authenticated session."""
    if not _is_safe_proxy_path(path):
        return Response("Chemin refusé", status=400, content_type="text/plain")

    # Serve cacheable assets from in-process cache to avoid hammering the router
    if _is_cacheable(path):
        cached = _cache_get(path)
        if cached is not None:
            body, ct, status = cached
            return Response(body, status=status, content_type=ct)

    bbox_host = _session_host()
    bbox_password = _session_password()
    target_url = f"http://{bbox_host}/{path}"
    if request.query_string:
        target_url += "?" + request.query_string.decode()

    fwd_headers = {k: v for k, v in request.headers if k.lower() not in _SKIP_REQUEST_HEADERS}
    fwd_headers["Accept-Encoding"] = "identity"

    def _do_request(bbox_sess: _req.Session) -> _req.Response:
        return bbox_sess.request(
            method=request.method,
            url=target_url,
            headers=fwd_headers,
            data=request.get_data(),
            allow_redirects=True,
            timeout=10,
            verify=config.verify_tls(),
        )

    try:
        bbox_sess = _get_bbox_session(bbox_host, bbox_password)
        upstream = _do_request(bbox_sess)
        if upstream.status_code == 401:
            # Session expired — re-authenticate once
            with _sessions_lock:
                _authed_sessions.pop(bbox_host, None)
            bbox_sess = _get_bbox_session(bbox_host, bbox_password)
            upstream = _do_request(bbox_sess)
    except Exception as exc:
        return Response(f"Erreur proxy : {exc}", status=502, content_type="text/plain")

    content_type = upstream.headers.get("Content-Type", "")
    resp_headers = {
        k: v for k, v in upstream.headers.items()
        if k.lower() not in _SKIP_HEADERS
    }

    if "text/html" in content_type or "text/css" in content_type or "javascript" in content_type:
        is_html = "text/html" in content_type
        is_css = "text/css" in content_type
        body_str = upstream.text
        if not is_html:
            body_str = re.sub(r'#\s*sourceMappingURL=\S+', '', body_str)
        body_str = _rewrite_urls(body_str, "/proxy/bbox", f"http://{bbox_host}",
                                 is_html=is_html, is_css=is_css)
        body_bytes = body_str.encode("utf-8", errors="replace")
        if _is_cacheable(path):
            _cache_put(path, body_bytes, content_type, upstream.status_code)
        return Response(body_bytes, status=upstream.status_code,
                        headers=resp_headers, content_type=content_type)

    raw = upstream.content
    if _is_cacheable(path):
        _cache_put(path, raw, content_type, upstream.status_code)
    return Response(raw, status=upstream.status_code,
                    headers=resp_headers, content_type=content_type)


_ALL_METHODS = ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"]


@bp.route("/proxy/bbox/", defaults={"path": ""}, methods=_ALL_METHODS)
@bp.route("/proxy/bbox/<path:path>", methods=_ALL_METHODS)
@login_required
def bbox_proxy(path):
    return _proxy_to_bbox(path)


@bp.route("/proxy/<path:path>", methods=_ALL_METHODS)
@login_required
def bbox_proxy_assets(path):
    """Catch-all for relative asset URLs the browser resolves under /proxy/ instead of /proxy/bbox/."""
    if path.startswith("bbox"):
        from flask import abort
        abort(404)
    return _proxy_to_bbox(path)


@bp.route("/api/v1/<path:path>", methods=_ALL_METHODS)
@login_required
def bbox_api_proxy(path):
    """Forward Bbox web-app API calls (/api/v1/…) to the real Bbox."""
    # The Bbox web app does PUT /api/v1/login to authenticate itself.
    # Our proxy already holds an authenticated BboxClient session, so we
    # return a fake success so the web app proceeds to make data calls.
    if path == "login" and request.method in ("PUT", "POST"):
        bbox_host = _session_host()
        bbox_password = _session_password()
        try:
            _get_bbox_session(bbox_host, bbox_password)
            return Response('[{"login":{"state":4}}]', status=200,
                            content_type="application/json")
        except Exception:
            return Response('[{"login":{"state":0}}]', status=401,
                            content_type="application/json")
    return _proxy_to_bbox(f"api/v1/{path}")


@bp.route("/medias/<path:path>", methods=["GET", "HEAD"])
@login_required
def bbox_medias_proxy(path):
    """Forward /medias/… paths (Bbox pictos/images) to the real Bbox."""
    return _proxy_to_bbox(f"medias/{path}")


@bp.route("/static/media/<path:filename>", methods=["GET", "HEAD"])
@login_required
def bbox_static_media_proxy(filename):
    """Forward /static/media/… webpack assets to the Bbox (bypasses Flask's own static handler)."""
    return _proxy_to_bbox(f"static/media/{filename}")
