"""FraudKit: one risk score for a signup or order from email, IP, phone, user-agent and billing country."""
from flask import jsonify

class ApiError(Exception):
    def __init__(self, code, msg): self.code, self.msg = code, msg

HOSTING = ("amazon", "google", "microsoft", "digitalocean", "ovh", "hetzner", "linode", "akamai", "vultr", "oracle", "alibaba",
           "tencent", "choopa", "contabo", "leaseweb", "m247", "datacamp", "cloudflare", "fastly", "scaleway", "hostinger", "ionos",
           "godaddy", "psychz", "quadranet", "colocrossing", "zenlayer", "packet", "constant", "servers", "hosting", "datacenter", "cdn77")
VPNISH = ("vpn", "proxy", "tor ", "mullvad", "nordvpn", "expressvpn", "surfshark", "private internet", "privado", "windscribe", "proton")

SAME = {"GG": "GB", "JE": "GB", "IM": "GB"}
def same(a, b): return SAME.get(a, a) == SAME.get(b, b)

def parse_ua(ua):
    from ua_parser import parse
    r = parse(ua or "")
    ua_s, os_s, dev = r.user_agent, r.os, r.device
    low = (ua or "").lower()
    bot = any(k in low for k in ("bot", "crawl", "spider", "slurp", "headless", "phantomjs", "selenium", "puppeteer", "playwright",
                                  "python-requests", "curl/", "wget/", "httpclient", "okhttp", "go-http-client", "java/", "scrapy", "axios/", "node-fetch"))
    family = ua_s.family if ua_s else "Other"
    return {"user_agent": ua, "browser": family, "browser_version": ".".join(x for x in (ua_s.major, ua_s.minor) if x) if ua_s else None,
            "os": os_s.family if os_s else None, "os_version": ".".join(x for x in (os_s.major, os_s.minor) if x) if os_s else None,
            "device": dev.family if dev else None, "device_brand": dev.brand if dev else None,
            "is_mobile": bool(dev and dev.family not in (None, "Other", "Spider")) or "mobile" in low,
            "is_bot": bot or (dev is not None and dev.family == "Spider")}

def score(email=None, ip=None, phone=None, user_agent=None, country=None):
    signals, reasons, risk = {}, [], 0
    country = (country or "").upper() or None
    if email:
        import main as root
        e = root.validate_email(email[:254]); signals["email"] = e
        v = e.get("verdict")
        if v == "invalid": risk += 35; reasons.append("email is invalid or has no mail server")
        elif v == "disposable": risk += 40; reasons.append("disposable email domain")
        elif v == "risky": risk += 15; reasons.append("email looks risky" + (" (possible typo)" if e.get("did_you_mean") else ""))
        if e.get("checks", {}).get("role_account"): risk += 5; reasons.append("role account (info@, admin@)")
    ipc = None
    if ip:
        from geoip.main import lookup, ApiError as GE
        try: g = lookup(ip)
        except GE as x: raise ApiError(x.code, x.msg)
        signals["ip"] = g; ipc = g.get("country_code")
        org = (g.get("organization") or "").lower()
        if not g.get("is_global"): risk += 10; reasons.append("private or reserved IP")
        if any(k in org for k in VPNISH): risk += 30; reasons.append("IP belongs to a VPN/proxy provider")
        elif any(k in org for k in HOSTING): risk += 25; reasons.append("IP is in a hosting/datacenter network")
        if country and ipc and not same(ipc, country): risk += 15; reasons.append(f"IP country {ipc} differs from billing country {country}")
    if phone:
        from phonekit.main import info
        p = info(phone[:40], country or ipc); signals["phone"] = p
        if not p.get("valid"): risk += 25; reasons.append("phone number is invalid")
        else:
            if p.get("line_type") in ("voip", "premium_rate", "shared_cost", "personal_number"): risk += 15; reasons.append(f"phone line type is {p.get('line_type')}")
            pr = p.get("region")
            if country and pr and not same(pr, country): risk += 10; reasons.append(f"phone country {pr} differs from billing country {country}")
            elif ipc and pr and not same(pr, ipc): risk += 5; reasons.append(f"phone country {pr} differs from IP country {ipc}")
    if user_agent:
        u = parse_ua(user_agent[:1000]); signals["user_agent"] = u
        if u["is_bot"]: risk += 30; reasons.append("user-agent is a bot or automation tool")
        elif u["browser"] == "Other": risk += 10; reasons.append("unrecognised browser")
    if not signals: raise ApiError(422, "Provide at least one of: email, ip, phone, user_agent")
    risk = min(100, risk)
    level = "high" if risk >= 60 else "medium" if risk >= 30 else "low"
    return {"risk_score": risk, "risk_level": level, "recommendation": {"low": "allow", "medium": "review", "high": "block or challenge"}[level],
            "reasons": reasons, "signals": signals}

def dispatch(request, path):
    path, a = path.rstrip("/") or "/", request.args
    try:
        if path in ("/", "/health"): return jsonify(status="ok")
        if path == "/score":
            b = request.get_json(silent=True) if request.method == "POST" else None
            src = b if isinstance(b, dict) else a
            return jsonify(score(src.get("email"), src.get("ip"), src.get("phone"), src.get("user_agent") or src.get("ua"), src.get("country")))
        if path == "/user-agent":
            ua = a.get("ua") or a.get("user_agent") or request.headers.get("User-Agent")
            if not ua: raise ApiError(422, "ua query parameter is required")
            return jsonify(parse_ua(ua[:1000]))
        if path == "/disposable":
            d = (a.get("email") or a.get("domain") or "").lower().rpartition("@")[2].strip()
            if not d: raise ApiError(422, "domain or email query parameter is required")
            import main as root
            return jsonify(domain=d, disposable=d in root.DISPOSABLE)
        raise ApiError(404, "Not found. Endpoints: /score, /user-agent, /disposable")
    except ApiError as e:
        return jsonify(error=e.msg), e.code
