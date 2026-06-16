import ipaddress
import os
from datetime import datetime, timedelta
from functools import wraps

import re
import threading
import requests as _req
from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for, Response
from dotenv import load_dotenv

from .bbox import BboxClient
from .db import get_all_devices, set_blocked, upsert_device

load_dotenv()

bp = Blueprint("main", __name__)


def _client() -> BboxClient:
    return BboxClient(
        host=session.get("bbox_host", os.getenv("BBOX_HOST", "192.168.1.254")),
        password=session.get("bbox_password", os.getenv("BBOX_PASSWORD", "")),
    )


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("authenticated"):
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
    return render_template("login.html")


@bp.post("/login")
def do_login():
    host     = request.form.get("host", "192.168.1.254").strip()
    password = request.form.get("password", "").strip()
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_loopback:
            return render_template("login.html", error="Adresse IP invalide")
    except ValueError:
        return render_template("login.html", error="Adresse IP invalide (ex : 192.168.1.254)")
    try:
        client = BboxClient(host=host, password=password)
        client.login()
        session["authenticated"] = True
        session["bbox_host"]     = host
        session["bbox_password"] = password
        return redirect(url_for("main.index"))
    except Exception as exc:
        return render_template("login.html", error=str(exc))


@bp.post("/logout")
def logout():
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
        client.login()
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

        return jsonify({"devices": devices, "blocked_count": blocked_count})

    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@bp.get("/api/history")
@login_required
def api_history():
    try:
        return jsonify({"devices": get_all_devices()})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@bp.post("/api/disconnect")
@login_required
def api_disconnect():
    data = request.get_json(force=True)
    mac  = data.get("mac", "").upper()
    try:
        client = _client()
        client.login()
        client.disconnect_mac(mac)
        return jsonify({"ok": True})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@bp.post("/api/block")
@login_required
def api_block():
    data     = request.get_json(force=True)
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
@login_required
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
@login_required
def api_kick_and_block():
    data     = request.get_json(force=True)
    mac      = data.get("mac", "").upper()
    hostname = data.get("hostname", "")
    try:
        client = _client()
        client.login()
        try:
            client.disconnect_mac(mac)
        except Exception:
            pass
        client.block_mac(mac, hostname)
        set_blocked(mac, True)
        return jsonify({"ok": True})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


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

_asset_cache: dict[str, tuple[bytes, str, int]] = {}  # path → (body, content_type, status)
_CACHEABLE_EXT = (".js", ".css", ".png", ".svg", ".woff", ".woff2", ".ttf", ".ico", ".webp", ".jpg", ".jpeg", ".gif")
_MAX_CACHE_ENTRIES = 200


def _get_bbox_session(bbox_host: str, password: str) -> _req.Session:
    """Return a cached, authenticated requests.Session for the Bbox."""
    with _sessions_lock:
        if bbox_host not in _authed_sessions:
            client = BboxClient(host=bbox_host, password=password)
            client.login()
            _authed_sessions[bbox_host] = client.session
        return _authed_sessions[bbox_host]


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


def _rewrite_urls(content: str, prefix: str, is_html: bool = False, is_css: bool = False) -> str:
    bbox_origin = "http://192.168.1.254"

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
    # Serve cacheable assets from in-process cache to avoid hammering the router
    if request.method == "GET" and any(path.split("?")[0].endswith(ext) for ext in _CACHEABLE_EXT):
        cache_key = path.split("?")[0]
        if cache_key in _asset_cache:
            body, ct, status = _asset_cache[cache_key]
            return Response(body, status=status, content_type=ct)

    bbox_host = session.get("bbox_host", "192.168.1.254")
    bbox_password = session.get("bbox_password", os.getenv("BBOX_PASSWORD", ""))
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
            verify=False,
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
        body_str = _rewrite_urls(body_str, "/proxy/bbox", is_html=is_html, is_css=is_css)
        body_bytes = body_str.encode("utf-8", errors="replace")
        if request.method == "GET" and any(path.split("?")[0].endswith(ext) for ext in _CACHEABLE_EXT):
            if len(_asset_cache) < _MAX_CACHE_ENTRIES:
                _asset_cache[path.split("?")[0]] = (body_bytes, content_type, upstream.status_code)
        return Response(body_bytes, status=upstream.status_code,
                        headers=resp_headers, content_type=content_type)

    raw = upstream.content
    if request.method == "GET" and any(path.split("?")[0].endswith(ext) for ext in _CACHEABLE_EXT):
        if len(_asset_cache) < _MAX_CACHE_ENTRIES:
            _asset_cache[path.split("?")[0]] = (raw, content_type, upstream.status_code)
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
        bbox_host = session.get("bbox_host", "192.168.1.254")
        bbox_password = session.get("bbox_password", os.getenv("BBOX_PASSWORD", ""))
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
