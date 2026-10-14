"""UK PostcodeKit: postcode lookup, nearest postcodes, autocomplete and distance from OS Code-Point Open (OGL v3)."""
import math, os, re, sqlite3, threading
from flask import jsonify

HERE = os.path.dirname(os.path.abspath(__file__))
ATTR = "Contains OS data © Crown copyright and database right 2026. Contains Royal Mail data © Royal Mail copyright and database right 2026. Licensed under the Open Government Licence v3.0."
RE = re.compile(r"^[A-Z]{1,2}\d[A-Z\d]?\d[A-Z]{2}$")
_local = threading.local()

class ApiError(Exception):
    def __init__(self, code, msg): self.code, self.msg = code, msg

def db():
    if not getattr(_local, "c", None):
        p = os.path.join(HERE, "postcodes.sqlite")
        if not os.path.exists(p): raise ApiError(503, "Postcode database unavailable")
        _local.c = sqlite3.connect(f"file:{p}?mode=ro&immutable=1", uri=True, check_same_thread=False)
    return _local.c

def norm(pc): return re.sub(r"\s+", "", (pc or "").upper())
def fmt(pc): return pc[:-3] + " " + pc[-3:]
def tidy(n):
    if not n: return None
    n = re.sub(r"\s*\((B)\)$", "", n); n = n.replace(" London Boro", " London Borough")
    return re.sub(r" (Ward|ED|District|County)$", "", n)

Q = "SELECT p.pc,p.lat,p.lng,p.q,(SELECT name FROM n WHERE id=p.country),(SELECT name FROM n WHERE id=p.county),(SELECT name FROM n WHERE id=p.district),(SELECT name FROM n WHERE id=p.ward),(SELECT code FROM n WHERE id=p.district),(SELECT code FROM n WHERE id=p.ward) FROM p "
def row(r, extra=None):
    pc = r[0]; m = re.match(r"^([A-Z]{1,2})(\d[A-Z\d]?)", pc[:-3])
    return {"postcode": fmt(pc), "outcode": pc[:-3], "incode": pc[-3:], "area": m.group(1) if m else None, "latitude": r[1], "longitude": r[2],
            "positional_quality": r[3], "country": r[4], "county": tidy(r[5]), "district": tidy(r[6]), "ward": tidy(r[7]),
            "district_code": r[8], "ward_code": r[9], **(extra or {})}

def get(pc):
    p = norm(pc)
    if not RE.match(p): raise ApiError(422, "Not a valid UK postcode format")
    r = db().execute(Q + "WHERE p.pc=?", (p,)).fetchone()
    if not r: raise ApiError(404, "Postcode not found (it may be terminated, or a Northern Ireland/Channel Islands postcode not covered)")
    return r

def hav(a, b, c, d):
    R = 6371.0088; p1, p2 = math.radians(a), math.radians(c); dl, dp = math.radians(d - b), math.radians(c - a)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))

def nearest(lat, lng, radius_m, limit):
    dlat = radius_m / 111320; dlng = radius_m / (111320 * max(0.2, math.cos(math.radians(lat))))
    rs = db().execute(Q + "WHERE p.lat BETWEEN ? AND ? AND p.lng BETWEEN ? AND ?", (lat - dlat, lat + dlat, lng - dlng, lng + dlng)).fetchall()
    out = sorted(((hav(lat, lng, r[1], r[2]) * 1000, r) for r in rs if r[1] is not None), key=lambda x: x[0])
    return [row(r, {"distance_m": round(d)}) for d, r in out if d <= radius_m][:limit]

def dispatch(request, path):
    path, a = path.rstrip("/") or "/", request.args
    try:
        if path in ("/", "/health"): return jsonify(status="ok")
        if path == "/lookup": return jsonify(row(get(a.get("postcode")), {"attribution": ATTR}))
        if path == "/validate":
            p = norm(a.get("postcode")); fmt_ok = bool(RE.match(p))
            exists = bool(fmt_ok and db().execute("SELECT 1 FROM p WHERE pc=?", (p,)).fetchone())
            return jsonify(input=a.get("postcode"), valid_format=fmt_ok, exists=exists, normalized=fmt(p) if fmt_ok else None)
        if path == "/nearest":
            if a.get("postcode"): r = get(a["postcode"]); lat, lng = r[1], r[2]
            else:
                try: lat, lng = float(a.get("lat")), float(a.get("lng"))
                except (TypeError, ValueError): raise ApiError(422, "postcode, or lat and lng, is required")
            try: rad = max(10, min(5000, int(a.get("radius", 500)))); lim = max(1, min(100, int(a.get("limit", 10))))
            except ValueError: raise ApiError(422, "radius and limit must be integers")
            return jsonify(latitude=lat, longitude=lng, radius_m=rad, results=nearest(lat, lng, rad, lim), attribution=ATTR)
        if path == "/autocomplete":
            p = norm(a.get("q") or a.get("postcode"))
            if len(p) < 2 or not re.match(r"^[A-Z0-9]+$", p): raise ApiError(422, "q must be at least 2 characters of a postcode")
            lim = max(1, min(50, int(a.get("limit", 10)) if (a.get("limit") or "10").isdigit() else 10))
            rs = db().execute("SELECT pc FROM p WHERE pc >= ? AND pc < ? ORDER BY pc LIMIT ?", (p, p + "~", lim)).fetchall()
            return jsonify(query=a.get("q") or a.get("postcode"), results=[fmt(r[0]) for r in rs])
        if path == "/distance":
            x, y = get(a.get("from")), get(a.get("to"))
            km = hav(x[1], x[2], y[1], y[2])
            return jsonify(**{"from": fmt(x[0]), "to": fmt(y[0]), "distance_km": round(km, 3), "distance_miles": round(km / 1.609344, 3), "note": "Straight-line (great-circle) distance"})
        if path == "/outcode":
            o = norm(a.get("outcode"))
            if not re.match(r"^[A-Z]{1,2}\d[A-Z\d]?$", o): raise ApiError(422, "outcode must look like BS3 or SW1A")
            rs = db().execute("SELECT lat,lng,(SELECT name FROM n WHERE id=district) FROM p WHERE pc >= ? AND pc < ? AND length(pc)=?", (o, o + "~", len(o) + 3)).fetchall()
            rs = [r for r in rs if r[0] is not None]
            if not rs: raise ApiError(404, "Outcode not found")
            return jsonify(outcode=o, postcodes=len(rs), latitude=round(sum(r[0] for r in rs) / len(rs), 6), longitude=round(sum(r[1] for r in rs) / len(rs), 6),
                           districts=sorted({tidy(r[2]) for r in rs if r[2]}), attribution=ATTR)
        raise ApiError(404, "Not found. Endpoints: /lookup, /validate, /nearest, /autocomplete, /distance, /outcode")
    except ApiError as e:
        return jsonify(error=e.msg), e.code
    except Exception as e:
        return jsonify(error=f"Internal error: {type(e).__name__}: {str(e)[:200]}"), 500
