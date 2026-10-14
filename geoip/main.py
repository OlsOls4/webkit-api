"""GeoIP: IP to country, continent, ASN and ISP, plus caller IP lookup. Data: DB-IP Lite (CC BY 4.0)."""
import ipaddress, os
import maxminddb
from flask import jsonify

PROXY_SECRET = os.getenv("RAPIDAPI_PROXY_SECRET", "")
HERE = os.path.dirname(__file__)
ATTR = "IP geolocation by DB-IP (https://db-ip.com), CC BY 4.0"
_dbs = {}

class ApiError(Exception):
    def __init__(self, code, msg): self.code, self.msg = code, msg

def db(name):
    if name not in _dbs:
        p = os.path.join(HERE, f"{name}.mmdb")
        if not os.path.exists(p): raise ApiError(503, "Geo database unavailable")
        _dbs[name] = maxminddb.open_database(p)
    return _dbs[name]

def lookup(ip):
    try: addr = ipaddress.ip_address(ip.strip())
    except ValueError: raise ApiError(422, "ip must be a valid IPv4 or IPv6 address")
    out = {"ip": str(addr), "version": addr.version, "is_private": addr.is_private, "is_global": addr.is_global,
           "is_multicast": addr.is_multicast, "is_loopback": addr.is_loopback}
    if not addr.is_global:
        return {**out, "country": None, "asn": None, "attribution": ATTR}
    c = db("country").get(str(addr)) or {}
    s = db("asn").get(str(addr)) or {}
    out.update({"country_code": (c.get("country") or {}).get("iso_code"), "country": ((c.get("country") or {}).get("names") or {}).get("en"),
                "continent_code": (c.get("continent") or {}).get("code"), "continent": ((c.get("continent") or {}).get("names") or {}).get("en"),
                "is_eu": bool((c.get("country") or {}).get("is_in_european_union")),
                "asn": s.get("autonomous_system_number"), "organization": s.get("autonomous_system_organization"), "attribution": ATTR})
    return out

def caller_ip(request):
    for h in ("X-Forwarded-For", "X-Real-IP"):
        v = request.headers.get(h)
        if v: return v.split(",")[0].strip()
    return request.remote_addr

def dispatch(request, path):
    path, a = path.rstrip("/") or "/", request.args
    try:
        if path in ("/", "/health"): return jsonify(status="ok")
        if PROXY_SECRET and request.headers.get("X-RapidAPI-Proxy-Secret") != PROXY_SECRET:
            raise ApiError(403, "Use this API through RapidAPI.")
        if path == "/lookup":
            ip = a.get("ip")
            if not ip: raise ApiError(422, "ip query parameter is required")
            return jsonify(lookup(ip))
        if path == "/me": return jsonify(lookup(caller_ip(request)))
        if path == "/bulk":
            body = request.get_json(silent=True) or {}
            ips = body.get("ips") if isinstance(body, dict) else None
            if not isinstance(ips, list) or not ips: raise ApiError(422, 'POST JSON {"ips": ["8.8.8.8", ...]}')
            if len(ips) > 100: raise ApiError(413, "max 100 IPs per request")
            res = []
            for ip in ips:
                try: res.append(lookup(str(ip)))
                except ApiError as e: res.append({"ip": ip, "error": e.msg})
            return jsonify(results=res)
        raise ApiError(404, "Not found. Endpoints: /lookup, /me, /bulk (POST)")
    except ApiError as e:
        return jsonify(error=e.msg), e.code
