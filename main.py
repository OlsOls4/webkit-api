"""WebKit API as a Cloud Run function (entry point: handler)."""
import ipaddress, os, re, socket
from urllib.parse import urljoin, urlparse
import dns.resolver, httpx, functions_framework
from bs4 import BeautifulSoup
from flask import jsonify

PROXY_SECRET = os.getenv("RAPIDAPI_PROXY_SECRET", "")
MAX_BYTES = 3_000_000
UA = "Mozilla/5.0 (compatible; WebKitAPI/1.0; +https://rapidapi.com/Olly-1VN9JTXKG; ollymcbride4@gmail.com)"

class ApiError(Exception):
    def __init__(self, code, msg): self.code, self.msg = code, msg

DISPOSABLE = set("""10minutemail.com 20minutemail.com 33mail.com anonbox.net dispostable.com dropmail.me
emailondeck.com fakeinbox.com getairmail.com getnada.com guerrillamail.com guerrillamail.net guerrillamail.org
guerrillamailblock.com harakirimail.com inboxkitten.com maildrop.cc mailinator.com mailinator.net mailnesia.com
mailpoof.com mintemail.com moakt.com mohmal.com mytemp.email nada.email sharklasers.com spamgourmet.com
temp-mail.io temp-mail.org tempail.com tempmail.dev tempmail.net tempmailo.com tempr.email throwawaymail.com
trashmail.com trashmail.de yopmail.com yopmail.fr yopmail.net emailfake.com burnermail.io tmail.ws tmpmail.org
mail.tm 1secmail.com 1secmail.net mailcatch.com spambox.us discard.email""".split())
ROLE = set("admin administrator billing contact help hello info marketing noreply no-reply office postmaster sales support team webmaster abuse careers jobs hr".split())
FREE = set("gmail.com googlemail.com yahoo.com yahoo.co.uk outlook.com hotmail.com hotmail.co.uk live.com msn.com icloud.com me.com aol.com proton.me protonmail.com gmx.com gmx.de mail.com yandex.com zoho.com btinternet.com".split())
TYPOS = {"gmial.com": "gmail.com", "gmai.com": "gmail.com", "gamil.com": "gmail.com", "gmail.co": "gmail.com",
         "hotmial.com": "hotmail.com", "hotmal.com": "hotmail.com", "yaho.com": "yahoo.com", "yahooo.com": "yahoo.com",
         "outlok.com": "outlook.com", "outllook.com": "outlook.com", "iclud.com": "icloud.com"}
EMAIL_RE = re.compile(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]{1,64}@([A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}$")


def _mx(domain):
    try:
        return sorted((r.preference, str(r.exchange).rstrip(".")) for r in dns.resolver.resolve(domain, "MX", lifetime=4))
    except Exception:
        try:
            dns.resolver.resolve(domain, "A", lifetime=3); return [(0, domain)]
        except Exception:
            return []

def validate_email(email):
    email = email.strip()
    syntax = bool(EMAIL_RE.match(email)) and ".." not in email
    local, _, domain = email.rpartition("@"); domain = domain.lower()
    mx = _mx(domain) if syntax else []
    disposable, role = domain in DISPOSABLE, local.lower() in ROLE
    score = (40 if syntax else 0) + (40 if mx else 0) + (0 if disposable else 10) + (0 if role else 10)
    if not syntax or not mx: verdict = "invalid"
    elif disposable: verdict = "disposable"
    elif domain in TYPOS: verdict = "risky"; score -= 30
    elif score >= 90: verdict = "deliverable"
    else: verdict = "risky"
    return {"email": email, "verdict": verdict, "score": score if syntax else 0,
            "checks": {"syntax": syntax, "mx_found": bool(mx), "disposable": disposable,
                       "role_account": role, "free_provider": domain in FREE},
            "domain": domain, "mx_records": [h for _, h in mx][:5],
            "did_you_mean": f"{local}@{TYPOS[domain]}" if domain in TYPOS else None}

def _safe(url):
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.hostname: raise ApiError(400, "URL must start with http:// or https://")
    try: infos = socket.getaddrinfo(p.hostname, None)
    except socket.gaierror: raise ApiError(422, "Host could not be resolved")
    if any(not ipaddress.ip_address(i[4][0]).is_global for i in infos): raise ApiError(400, "Private or reserved addresses are not allowed")

def _fetch(url):
    _safe(url)
    try:
        with httpx.Client(follow_redirects=False, timeout=10, headers={"User-Agent": UA}) as c:
            for _ in range(5):
                r = c.get(url)
                if r.is_redirect: url = urljoin(url, r.headers.get("location", "")); _safe(url); continue
                break
    except httpx.HTTPError as e: raise ApiError(502, f"Fetch failed: {type(e).__name__}")
    if r.status_code >= 400: raise ApiError(502, f"Target site returned HTTP {r.status_code}")
    if "html" not in r.headers.get("content-type", "html"): raise ApiError(415, "URL is not an HTML page")
    return str(r.url), r.status_code, r.content[:MAX_BYTES].decode(r.encoding or "utf-8", "replace")

def _meta(s, *names):
    for n in names:
        t = s.find("meta", attrs={"property": n}) or s.find("meta", attrs={"name": n})
        if t and t.get("content"): return t["content"].strip()
    return None

def preview(url):
    final, status, html = _fetch(url); s = BeautifulSoup(html, "html.parser")
    icon = s.find("link", rel=lambda v: v and "icon" in " ".join(v).lower())
    img = _meta(s, "og:image", "twitter:image"); can = s.find("link", rel="canonical")
    return {"url": final, "status_code": status,
            "title": _meta(s, "og:title", "twitter:title") or (s.title.string.strip() if s.title and s.title.string else None),
            "description": _meta(s, "og:description", "twitter:description", "description"),
            "image": urljoin(final, img) if img else None, "site_name": _meta(s, "og:site_name"), "type": _meta(s, "og:type"),
            "favicon": urljoin(final, icon["href"]) if icon and icon.get("href") else urljoin(final, "/favicon.ico"),
            "language": s.html.get("lang") if s.html else None, "canonical": can.get("href") if can else None}

def extract(url, max_chars):
    final, status, html = _fetch(url); s = BeautifulSoup(html, "html.parser")
    title = s.title.string.strip() if s.title and s.title.string else None
    author, published = _meta(s, "author", "article:author"), _meta(s, "article:published_time", "date")
    for t in s(["script", "style", "noscript", "nav", "footer", "header", "aside", "form", "svg", "iframe", "table", "figure", "sup"]): t.decompose()
    root = max(s.find_all(["article", "main"]) or [s.body or s], key=lambda e: len(e.get_text(" ", strip=True)))
    md, plain = [], []
    for el in root.find_all(["h1", "h2", "h3", "h4", "p", "li", "blockquote", "pre"]):
        txt = el.get_text(" ", strip=True)
        if len(txt) < 2: continue
        plain.append(txt); n = el.name
        md.append(("#" * int(n[1]) + " " + txt) if n[0] == "h" else ("- " + txt) if n == "li" else ("> " + txt) if n == "blockquote" else txt)
    text = "\n\n".join(plain)[:max_chars]
    return {"url": final, "status_code": status, "title": title, "author": author, "published": published,
            "word_count": len(text.split()), "text": text, "markdown": "\n\n".join(md)[:max_chars]}

@functions_framework.http
def handler(request):
    path, a = request.path.rstrip("/") or "/", request.args
    for prefix, mod in (("/domain", "domainkit"), ("/qrkit", "qrkit"), ("/text", "textkit"), ("/phone", "phonekit"), ("/valid", "validkit"), ("/geo", "geoip"), ("/doc", "dockit")):
        if path == prefix or path.startswith(prefix + "/"):
            import importlib
            return importlib.import_module(mod + ".main").dispatch(request, path[len(prefix):] or "/")
    try:
        if path in ("/", "/health"): return jsonify(status="ok")
        if PROXY_SECRET and request.headers.get("X-RapidAPI-Proxy-Secret") != PROXY_SECRET:
            raise ApiError(403, "Use this API through RapidAPI.")
        if path == "/email/validate":
            e = a.get("email", "")
            if not e or len(e) > 254: raise ApiError(422, "email query parameter is required (max 254 chars)")
            return jsonify(validate_email(e))
        if path in ("/url/preview", "/url/extract"):
            u = a.get("url", "")
            if not u or len(u) > 2048: raise ApiError(422, "url query parameter is required (max 2048 chars)")
            if path == "/url/preview": return jsonify(preview(u))
            try: mc = int(a.get("max_chars", 20000))
            except ValueError: raise ApiError(422, "max_chars must be an integer")
            return jsonify(extract(u, max(500, min(mc, 100000))))
        raise ApiError(404, "Not found. Endpoints: /email/validate, /url/preview, /url/extract")
    except ApiError as e:
        return jsonify(error=e.msg), e.code
