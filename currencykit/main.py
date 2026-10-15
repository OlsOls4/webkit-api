"""CurrencyKit: ECB euro foreign exchange reference rates (latest, historical, time series) and currency conversion.
Source: European Central Bank euro foreign exchange reference rates (free reuse with attribution)."""
import datetime as dt, os, re, threading, time
import httpx
from flask import jsonify

class ApiError(Exception):
    def __init__(self, code, msg): self.code, self.msg = code, msg

ECB = "https://www.ecb.europa.eu/stats/eurofxref/"
FEEDS = {"daily": ("eurofxref-daily.xml", 1800), "90d": ("eurofxref-hist-90d.xml", 3600), "hist": ("eurofxref-hist.xml", 6 * 3600)}
SOURCE = "European Central Bank euro foreign exchange reference rates (https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/index.en.html)"
NOTE = "ECB reference rates are published for information purposes only, around 16:00 CET on TARGET business days. Not for transaction use."
FIRST = dt.date(1999, 1, 4)
MAX_SPAN = 366
NAMES = {
    "EUR": "Euro", "USD": "US dollar", "JPY": "Japanese yen", "BGN": "Bulgarian lev", "CZK": "Czech koruna", "DKK": "Danish krone",
    "GBP": "Pound sterling", "HUF": "Hungarian forint", "PLN": "Polish zloty", "RON": "Romanian leu", "SEK": "Swedish krona",
    "CHF": "Swiss franc", "ISK": "Icelandic krona", "NOK": "Norwegian krone", "TRY": "Turkish lira", "AUD": "Australian dollar",
    "BRL": "Brazilian real", "CAD": "Canadian dollar", "CNY": "Chinese yuan renminbi", "HKD": "Hong Kong dollar",
    "IDR": "Indonesian rupiah", "ILS": "Israeli shekel", "INR": "Indian rupee", "KRW": "South Korean won", "MXN": "Mexican peso",
    "MYR": "Malaysian ringgit", "NZD": "New Zealand dollar", "PHP": "Philippine peso", "SGD": "Singapore dollar", "THB": "Thai baht",
    "ZAR": "South African rand", "HRK": "Croatian kuna", "RUB": "Russian rouble", "CYP": "Cypriot pound", "EEK": "Estonian kroon",
    "LTL": "Lithuanian litas", "LVL": "Latvian lats", "MTL": "Maltese lira", "SIT": "Slovenian tolar", "SKK": "Slovak koruna",
    "ROL": "Romanian leu (old)", "TRL": "Turkish lira (old)"}

_cache, _lock = {}, threading.Lock()
DAY_RE = re.compile(r"<Cube\s+time=['\"](\d{4}-\d{2}-\d{2})['\"]\s*>(.*?)</Cube>", re.S)
RATE_RE = re.compile(r"currency=['\"]([A-Z]{3})['\"]\s+rate=['\"]([0-9.]+)['\"]")


def _parse(xml):
    out = {}
    for d, body in DAY_RE.findall(xml):
        out[d] = {c: float(r) for c, r in RATE_RE.findall(body)}
    return out


def feed(name):
    """Parsed feed {YYYY-MM-DD: {CUR: rate per EUR}}, cached in memory (and /tmp) with a TTL."""
    fname, ttl = FEEDS[name]
    now = time.time()
    hit = _cache.get(name)
    if hit and now - hit[0] < ttl: return hit[1]
    with _lock:
        hit = _cache.get(name)
        if hit and now - hit[0] < ttl: return hit[1]
        tmp = f"/tmp/ecb-{fname}"
        try:
            r = httpx.get(ECB + fname, timeout=25, headers={"User-Agent": "CurrencyKit/1.0 (+https://rapidapi.com/Olly-1VN9JTXKG)"})
            r.raise_for_status()
            data = _parse(r.text)
            if not data: raise ValueError("empty feed")
            try: open(tmp, "w").write(r.text)
            except OSError: pass
        except Exception:
            if hit: _cache[name] = (now - ttl + 300, hit[1]); return hit[1]  # serve stale, retry in 5 min
            try:
                data = _parse(open(tmp).read())
                if not data: raise ValueError
            except Exception:
                raise ApiError(503, "ECB reference rates are temporarily unavailable, retry shortly")
        _cache[name] = (now, data)
        return data


def cur(v, name, allowed):
    c = (v or "").strip().upper()
    if not re.fullmatch(r"[A-Z]{3}", c): raise ApiError(422, f"{name} must be a 3-letter ISO 4217 currency code, e.g. USD")
    if c not in allowed: raise ApiError(422, f"{name} {c} is not available for this date. See /currencies")
    return c


def pdate(v, name):
    if not v: raise ApiError(422, f"{name} is required (YYYY-MM-DD)")
    try: d = dt.date.fromisoformat(v.strip()[:10])
    except ValueError: raise ApiError(422, f"{name} must be YYYY-MM-DD")
    if d < FIRST: raise ApiError(422, f"{name} must be on or after 1999-01-04 (first ECB reference rate)")
    if d > dt.date.today() + dt.timedelta(days=1): raise ApiError(422, f"{name} cannot be in the future")
    return d


def sig(x, n=8):
    return float(f"{x:.{n}g}")


def latest():
    data = feed("daily")
    d = max(data)
    return d, data[d]


def series_for(start):
    """Smallest feed that covers dates from `start`."""
    if (dt.date.today() - start).days <= 85:
        data = feed("90d")
        if data and min(data) <= start.isoformat(): return data
    return feed("hist")


def on_or_before(d):
    """Rates for the requested date, or the closest earlier ECB business day."""
    ld, lr = latest()
    if d.isoformat() >= ld: return ld, lr
    data = series_for(d - dt.timedelta(days=7))
    keys = [k for k in data if k <= d.isoformat()]
    if not keys: raise ApiError(404, "No ECB reference rate on or before that date")
    k = max(keys)
    return k, data[k]


def rebase(rates, base, symbols):
    r = dict(rates); r["EUR"] = 1.0
    b = r[base]
    keys = symbols or sorted(k for k in r if k != base)
    return {k: sig(r[k] / b) for k in keys}


def symbols_arg(v, allowed):
    if not v: return None
    out = []
    for s in v.split(","):
        s = s.strip()
        if s: out.append(cur(s, "symbols", allowed))
    if not out: return None
    if len(out) > 50: raise ApiError(422, "symbols accepts at most 50 codes")
    return list(dict.fromkeys(out))


def dispatch(request, path):
    path, a = path.rstrip("/") or "/", request.args
    try:
        if path in ("/", "/health"): return jsonify(status="ok")
        if path == "/latest":
            d, rates = latest(); allowed = set(rates) | {"EUR"}
            base = cur(a.get("base") or "EUR", "base", allowed)
            syms = symbols_arg(a.get("symbols"), allowed)
            return jsonify(base=base, date=d, rates=rebase(rates, base, syms), source=SOURCE, note=NOTE)
        if path == "/historical":
            req = pdate(a.get("date"), "date"); d, rates = on_or_before(req); allowed = set(rates) | {"EUR"}
            base = cur(a.get("base") or "EUR", "base", allowed)
            syms = symbols_arg(a.get("symbols"), allowed)
            return jsonify(base=base, requested_date=req.isoformat(), date=d, rates=rebase(rates, base, syms), source=SOURCE,
                           note="If the requested date was a weekend or TARGET holiday, the closest earlier ECB business day is used.")
        if path == "/convert":
            try: amount = float(a.get("amount", "1") or "1")
            except ValueError: raise ApiError(422, "amount must be a number")
            if not (-1e15 < amount < 1e15) or amount != amount: raise ApiError(422, "amount out of range")
            if a.get("date"):
                req = pdate(a.get("date"), "date"); d, rates = on_or_before(req)
            else:
                req = None; d, rates = latest()
            allowed = set(rates) | {"EUR"}
            if not a.get("from") or not a.get("to"): raise ApiError(422, "from and to are required currency codes, e.g. from=USD&to=GBP")
            f, t = cur(a.get("from"), "from", allowed), cur(a.get("to"), "to", allowed)
            r = dict(rates); r["EUR"] = 1.0
            rate = r[t] / r[f]
            return jsonify(**{"from": f, "to": t, "amount": amount, "rate": sig(rate, 8), "result": round(amount * rate, 6),
                              "date": d, "requested_date": req.isoformat() if req else None, "inverse_rate": sig(1 / rate, 8), "source": SOURCE})
        if path == "/timeseries":
            s, e = pdate(a.get("start"), "start"), pdate(a.get("end"), "end")
            if e < s: raise ApiError(422, "end must be on or after start")
            if (e - s).days > MAX_SPAN: raise ApiError(422, f"range max {MAX_SPAN} days; split longer ranges into several calls")
            data = series_for(s)
            days = sorted(k for k in data if s.isoformat() <= k <= e.isoformat())
            ld, lr = latest()
            if s.isoformat() <= ld <= e.isoformat() and ld not in days: days.append(ld); data = {**data, ld: lr}
            allowed = (set().union(*(data[k] for k in days)) if days else set(lr)) | {"EUR"}
            base = cur(a.get("base") or "EUR", "base", allowed)
            syms = symbols_arg(a.get("symbols"), allowed)
            out = {}
            for k in days:
                day = data[k]
                if base != "EUR" and base not in day: continue
                keys = [x for x in (syms or sorted(set(day) | {"EUR"})) if x != base and (x == "EUR" or x in day)]
                out[k] = rebase(day, base, keys)
            return jsonify(base=base, start=s.isoformat(), end=e.isoformat(), days=len(out), rates=out, source=SOURCE)
        if path == "/currencies":
            d, rates = latest()
            cs = sorted(set(rates) | {"EUR"})
            return jsonify(date=d, count=len(cs), currencies=[{"code": c, "name": NAMES.get(c, c)} for c in cs],
                           historical_only={c: n for c, n in sorted(NAMES.items()) if c not in cs},
                           note="historical_only lists currencies that appear only in older ECB data (e.g. pre-euro national currencies); /historical and /timeseries accept them for dates when they were quoted.",
                           source=SOURCE)
        raise ApiError(404, "Not found. Endpoints: /latest, /convert, /historical, /timeseries, /currencies")
    except ApiError as e:
        return jsonify(error=e.msg), e.code
