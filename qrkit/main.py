"""QRKit API: QR codes and barcodes as PNG, SVG or base64 JSON."""
import base64, io, os
import functions_framework, segno, barcode
from barcode.writer import ImageWriter, SVGWriter
from flask import Response, jsonify

PROXY_SECRET = os.getenv("RAPIDAPI_PROXY_SECRET", "")
BARCODES = {"code128": "code128", "code39": "code39", "ean13": "ean13", "ean8": "ean8", "upca": "upca", "isbn13": "isbn13", "issn": "issn", "itf": "itf", "pzn": "pzn"}

class ApiError(Exception):
    def __init__(self, code, msg): self.code, self.msg = code, msg

def color(v, default):
    v = (v or default).strip().lstrip("#")
    if v.lower() == "transparent": return None
    if len(v) not in (3, 6) or any(c not in "0123456789abcdefABCDEF" for c in v): raise ApiError(422, "Colors must be hex like 000000 or ff8800")
    return "#" + v

def out(data, fmt, mime):
    if fmt == "base64": return jsonify(format=mime.split("/")[1].split("+")[0], mime=mime, data_uri=f"data:{mime};base64," + base64.b64encode(data).decode())
    return Response(data, mimetype=mime, headers={"Cache-Control": "public, max-age=86400"})

def qr(a):
    text = a.get("text") or a.get("data")
    if not text: raise ApiError(422, "text query parameter is required")
    if len(text) > 2000: raise ApiError(422, "text max 2000 characters")
    fmt = a.get("format", "png").lower()
    if fmt not in ("png", "svg", "base64"): raise ApiError(422, "format must be png, svg or base64")
    try: size = max(64, min(int(a.get("size", 300)), 2000)); border = max(0, min(int(a.get("margin", 4)), 20))
    except ValueError: raise ApiError(422, "size and margin must be integers")
    ecc = a.get("ecc", "M").upper()
    if ecc not in ("L", "M", "Q", "H"): raise ApiError(422, "ecc must be L, M, Q or H")
    dark, light = color(a.get("color"), "000000"), color(a.get("bg"), "ffffff")
    q = segno.make(text, error=ecc.lower(), boost_error=False)
    modules = q.symbol_size(border=border)[0]
    scale = max(1, size // modules)
    buf = io.BytesIO()
    if fmt == "svg" or (fmt == "base64" and a.get("image", "png") == "svg"):
        q.save(buf, kind="svg", scale=scale, border=border, dark=dark, light=light, xmldecl=False)
        return out(buf.getvalue(), fmt, "image/svg+xml")
    q.save(buf, kind="png", scale=scale, border=border, dark=dark, light=light)
    return out(buf.getvalue(), fmt, "image/png")

def qr_wifi(a):
    ssid = a.get("ssid")
    if not ssid: raise ApiError(422, "ssid is required")
    sec = a.get("security", "WPA").upper()
    if sec not in ("WPA", "WEP", "NOPASS"): raise ApiError(422, "security must be WPA, WEP or nopass")
    esc = lambda s: "".join("\\" + c if c in '\\;,:"' else c for c in s)
    text = f"WIFI:T:{'nopass' if sec == 'NOPASS' else sec};S:{esc(ssid)};" + (f"P:{esc(a.get('password',''))};" if sec != "NOPASS" else "") + ("H:true;" if a.get("hidden") == "true" else "") + ";"
    args = dict(a); args["text"] = text
    return qr(args)

def qr_vcard(a):
    name = a.get("name")
    if not name: raise ApiError(422, "name is required")
    lines = ["BEGIN:VCARD", "VERSION:3.0", f"FN:{name}", f"N:{name}"]
    for key, tag in (("phone", "TEL"), ("email", "EMAIL"), ("org", "ORG"), ("title", "TITLE"), ("url", "URL"), ("address", "ADR")):
        if a.get(key): lines.append(f"{tag}:{a[key]}")
    lines.append("END:VCARD")
    args = dict(a); args["text"] = "\n".join(lines)
    return qr(args)

def bar(a):
    kind = a.get("type", "code128").lower()
    if kind not in BARCODES: raise ApiError(422, "type must be one of " + ", ".join(BARCODES))
    text = a.get("text") or a.get("data")
    if not text or len(text) > 80: raise ApiError(422, "text is required (max 80 characters)")
    fmt = a.get("format", "png").lower()
    if fmt not in ("png", "svg", "base64"): raise ApiError(422, "format must be png, svg or base64")
    show = a.get("show_text", "true") != "false"
    svg = fmt == "svg" or (fmt == "base64" and a.get("image", "png") == "svg")
    try:
        code = barcode.get(BARCODES[kind], text, writer=SVGWriter() if svg else ImageWriter())
    except Exception as e:
        raise ApiError(422, f"Invalid data for {kind}: {e}")
    buf = io.BytesIO()
    code.write(buf, options={"write_text": show, "module_height": 15.0, "quiet_zone": 4.0})
    return out(buf.getvalue(), fmt, "image/svg+xml" if svg else "image/png")

@functions_framework.http
def handler(request):
    path, a = request.path.rstrip("/") or "/", request.args.to_dict()
    try:
        if path in ("/", "/health"): return jsonify(status="ok")
        if PROXY_SECRET and request.headers.get("X-RapidAPI-Proxy-Secret") != PROXY_SECRET:
            raise ApiError(403, "Use this API through RapidAPI.")
        routes = {"/qr": qr, "/qr/wifi": qr_wifi, "/qr/vcard": qr_vcard, "/barcode": bar}
        if path in routes: return routes[path](a)
        raise ApiError(404, "Not found. Endpoints: /qr, /qr/wifi, /qr/vcard, /barcode")
    except ApiError as e:
        return jsonify(error=e.msg), e.code
