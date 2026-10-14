"""DomainKit API: DNS, SSL certificate, WHOIS/RDAP, HTTP headers and tech detection."""
import datetime as dt, ipaddress, os, re, socket, ssl
import dns.resolver, httpx, functions_framework
from flask import jsonify

PROXY_SECRET = os.getenv("RAPIDAPI_PROXY_SECRET", "")
DOMAIN_RE = re.compile(r"^(?=.{1,253}$)(?!-)([a-z0-9-]{1,63}(?<!-)\.)+[a-z]{2,63}$")
UA = "Mozilla/5.0 (compatible; DomainKitAPI/1.0; +https://rapidapi.com/Olly-1VN9JTXKG; ollymcbride4@gmail.com)"

class ApiError(Exception):
    def __init__(self, code, msg): self.code, self.msg = code, msg

def clean_domain(raw):
    d = (raw or "").strip().lower()
    d = re.sub(r"^[a-z]+://", "", d).split("/")[0].split(":")[0].rstrip(".")
    if d.startswith("www.") and d.count(".") > 1: pass
    if not DOMAIN_RE.match(d): raise ApiError(422, "domain query parameter must be a valid domain, e.g. example.com")
    return d

def public_ip_check(host):
    try: infos = socket.getaddrinfo(host, None)
    except socket.gaierror: raise ApiError(422, "Domain does not resolve")
    if any(not ipaddress.ip_address(i[4][0]).is_global for i in infos): raise ApiError(400, "Private or reserved addresses are not allowed")

def dns_lookup(domain, types):
    out = {}
    r = dns.resolver.Resolver(); r.lifetime = 4
    for t in types:
        try:
            ans = r.resolve(domain, t)
            if t == "MX": out[t] = sorted([{"priority": a.preference, "host": str(a.exchange).rstrip(".")} for a in ans], key=lambda x: x["priority"])
            elif t == "TXT": out[t] = [b"".join(a.strings).decode("utf-8", "replace") for a in ans]
            elif t == "SOA":
                a = ans[0]; out[t] = {"mname": str(a.mname).rstrip("."), "rname": str(a.rname).rstrip("."), "serial": a.serial}
            else: out[t] = [a.to_text().rstrip(".") for a in ans]
        except Exception: out[t] = []
    spf = next((t for t in out.get("TXT", []) if t.lower().startswith("v=spf1")), None)
    try: dmarc = next((b"".join(a.strings).decode() for a in r.resolve("_dmarc." + domain, "TXT")), None)
    except Exception: dmarc = None
    return {"domain": domain, "records": out, "email_security": {"spf": spf, "dmarc": dmarc, "has_mx": bool(out.get("MX"))}}

def ssl_info(domain, port=443):
    public_ip_check(domain)
    ctx = ssl.create_default_context()
    valid, err = True, None
    try:
        with socket.create_connection((domain, port), timeout=6) as s, ctx.wrap_socket(s, server_hostname=domain) as ss:
            cert, proto, cipher = ss.getpeercert(), ss.version(), ss.cipher()[0]
    except ssl.SSLCertVerificationError as e:
        valid, err = False, e.verify_message
        ctx2 = ssl._create_unverified_context()
        try:
            with socket.create_connection((domain, port), timeout=6) as s, ctx2.wrap_socket(s, server_hostname=domain) as ss:
                proto, cipher = ss.version(), ss.cipher()[0]
        except Exception: proto = cipher = None
        return {"domain": domain, "valid": False, "error": err, "protocol": proto, "cipher": cipher}
    except (OSError, socket.timeout) as e:
        raise ApiError(502, f"Could not connect on port {port}: {type(e).__name__}")
    nb = dt.datetime.strptime(cert["notBefore"], "%b %d %H:%M:%S %Y %Z").replace(tzinfo=dt.timezone.utc)
    na = dt.datetime.strptime(cert["notAfter"], "%b %d %H:%M:%S %Y %Z").replace(tzinfo=dt.timezone.utc)
    flat = lambda seq: {k: v for t in seq for k, v in t}
    return {"domain": domain, "valid": valid, "issuer": flat(cert.get("issuer", ())), "subject": flat(cert.get("subject", ())),
            "san": [v for k, v in cert.get("subjectAltName", ()) if k == "DNS"][:50],
            "valid_from": nb.isoformat(), "valid_to": na.isoformat(),
            "days_remaining": (na - dt.datetime.now(dt.timezone.utc)).days, "protocol": proto, "cipher": cipher,
            "serial_number": cert.get("serialNumber")}

_BOOT = {}
def _rdap_base(domain):
    if not _BOOT:
        try:
            for tlds, urls in httpx.get("https://data.iana.org/rdap/dns.json", timeout=10).json()["services"]:
                u = next((x for x in urls if x.startswith("https")), urls[0])
                for t in tlds: _BOOT[t.lower()] = u if u.endswith("/") else u + "/"
        except Exception: pass
    parts = domain.lower().split(".")
    for i in range(len(parts)):
        b = _BOOT.get(".".join(parts[i:]))
        if b: return b
    return "https://rdap.org/"

def whois(domain):
    base = _rdap_base(domain)
    import time
    for attempt in range(3):
        try:
            r = httpx.get(f"{base}domain/{domain}", timeout=10, follow_redirects=True, headers={"User-Agent": UA, "Accept": "application/rdap+json"})
        except httpx.HTTPError as e: raise ApiError(502, f"RDAP lookup failed: {type(e).__name__}")
        if r.status_code not in (429, 503) or attempt == 2: break
        time.sleep(1.5 * (attempt + 1))
    if r.status_code in (429, 503): raise ApiError(503, "Registry RDAP server is rate limiting; retry in a few seconds")
    if r.status_code == 404: raise ApiError(404, "Domain not found in RDAP (unregistered or TLD without RDAP)")
    if r.status_code != 200: raise ApiError(502, f"RDAP returned {r.status_code}")
    d = r.json()
    ev = {e.get("eventAction"): e.get("eventDate") for e in d.get("events", [])}
    registrar = None
    for ent in d.get("entities", []):
        if "registrar" in ent.get("roles", []):
            for item in (ent.get("vcardArray") or [None, []])[1]:
                if item[0] == "fn": registrar = item[3]
    created = ev.get("registration"); age = None
    if created:
        try: age = (dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(created.replace("Z", "+00:00"))).days
        except ValueError: pass
    return {"domain": domain, "registered": True, "registrar": registrar, "created": created, "updated": ev.get("last changed"),
            "expires": ev.get("expiration"), "domain_age_days": age, "status": d.get("status", []),
            "nameservers": [n.get("ldhName", "").lower() for n in d.get("nameservers", [])], "dnssec": (d.get("secureDNS") or {}).get("delegationSigned")}

TECH = [("WordPress", "body", r"wp-content|wp-includes"), ("Shopify", "body", r"cdn\.shopify\.com"), ("Wix", "body", r"static\.wixstatic\.com"),
        ("Squarespace", "body", r"squarespace"), ("Webflow", "body", r"webflow"), ("Next.js", "body", r"__NEXT_DATA__|/_next/"),
        ("Nuxt", "body", r"__NUXT__"), ("React", "body", r"data-reactroot|react-dom"), ("Vue", "body", r"data-v-[0-9a-f]{6}"),
        ("Angular", "body", r"ng-version"), ("Gatsby", "body", r"___gatsby"), ("Drupal", "body", r"Drupal\.settings|/sites/default/files"),
        ("Joomla", "body", r"/media/jui/|Joomla!"), ("Ghost", "body", r"ghost-(?:url|api)"), ("Bootstrap", "body", r"bootstrap(?:\.min)?\.css"),
        ("Tailwind CSS", "body", r"tailwind"), ("jQuery", "body", r"jquery(?:\.min)?\.js"), ("Google Analytics", "body", r"googletagmanager\.com/gtag|google-analytics\.com"),
        ("Google Tag Manager", "body", r"googletagmanager\.com/gtm"), ("Meta Pixel", "body", r"connect\.facebook\.net"), ("Hotjar", "body", r"hotjar"),
        ("Stripe", "body", r"js\.stripe\.com"), ("Intercom", "body", r"widget\.intercom\.io"), ("HubSpot", "body", r"js\.hs-scripts\.com"),
        ("Cloudflare", "header", r"cloudflare"), ("Vercel", "header", r"vercel"), ("Netlify", "header", r"netlify"), ("nginx", "header", r"nginx"),
        ("Apache", "header", r"apache"), ("Amazon CloudFront", "header", r"cloudfront"), ("Fastly", "header", r"fastly"), ("PHP", "header", r"php"),
        ("Express", "header", r"express"), ("ASP.NET", "header", r"asp\.net")]
SEC_HEADERS = ["strict-transport-security", "content-security-policy", "x-frame-options", "x-content-type-options", "referrer-policy", "permissions-policy"]

def site_scan(domain):
    url = f"https://{domain}"
    public_ip_check(domain)
    try:
        with httpx.Client(follow_redirects=False, timeout=10, headers={"User-Agent": UA}) as c:
            chain = []
            for _ in range(5):
                r = c.get(url); chain.append({"url": url, "status": r.status_code})
                if r.is_redirect:
                    url = str(httpx.URL(url).join(r.headers.get("location", "")))
                    public_ip_check(httpx.URL(url).host); continue
                break
    except httpx.HTTPError as e: raise ApiError(502, f"Fetch failed: {type(e).__name__}")
    hdrs = {k.lower(): v for k, v in r.headers.items()}
    hblob = " ".join(f"{k}: {v}" for k, v in hdrs.items()).lower()
    body = r.text[:500_000]
    tech = sorted({n for n, where, pat in TECH if re.search(pat, body if where == "body" else hblob, re.I)})
    gen = re.search(r'<meta[^>]+name=["\']generator["\'][^>]+content=["\']([^"\']+)', body, re.I)
    sec = {h: (h in hdrs) for h in SEC_HEADERS}
    return {"domain": domain, "final_url": url, "status_code": r.status_code, "redirect_chain": chain,
            "server": hdrs.get("server"), "powered_by": hdrs.get("x-powered-by"), "generator": gen.group(1) if gen else None,
            "technologies": tech, "security_headers": sec, "security_score": round(100 * sum(sec.values()) / len(sec)),
            "headers": dict(list(hdrs.items())[:60])}

@functions_framework.http
def handler(request):
    return dispatch(request, request.path)

def dispatch(request, path):
    path, a = path.rstrip("/") or "/", request.args
    try:
        if path in ("/", "/health"): return jsonify(status="ok")
        if PROXY_SECRET and request.headers.get("X-RapidAPI-Proxy-Secret") != PROXY_SECRET:
            raise ApiError(403, "Use this API through RapidAPI.")
        if path == "/dns":
            types = [t.strip().upper() for t in a.get("types", "A,AAAA,MX,NS,TXT,CNAME,SOA").split(",") if t.strip()]
            bad = [t for t in types if t not in ("A", "AAAA", "MX", "NS", "TXT", "CNAME", "SOA", "CAA")]
            if bad: raise ApiError(422, f"Unsupported record types: {','.join(bad)}")
            return jsonify(dns_lookup(clean_domain(a.get("domain")), types))
        if path == "/ssl": return jsonify(ssl_info(clean_domain(a.get("domain"))))
        if path == "/whois": return jsonify(whois(clean_domain(a.get("domain"))))
        if path == "/scan": return jsonify(site_scan(clean_domain(a.get("domain"))))
        raise ApiError(404, "Not found. Endpoints: /dns, /ssl, /whois, /scan")
    except ApiError as e:
        return jsonify(error=e.msg), e.code
