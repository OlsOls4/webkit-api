"""ValidKit: IBAN, VAT, card number, ISBN, BIC, EAN and postcode validation for checkout and KYC forms."""
import os, re
from stdnum import bic, ean, iban, isbn, luhn
from stdnum.eu import vat
from flask import jsonify

PROXY_SECRET = os.getenv("RAPIDAPI_PROXY_SECRET", "")

class ApiError(Exception):
    def __init__(self, code, msg): self.code, self.msg = code, msg

CARDS = [("amex", r"^3[47]\d{13}$"), ("visa", r"^4\d{12}(\d{3}){0,2}$"), ("mastercard", r"^(5[1-5]\d{14}|2(2[2-9]\d|[3-6]\d\d|7[01]\d|720)\d{12})$"),
         ("discover", r"^6(011|5\d\d|4[4-9]\d)\d{12,15}$"), ("diners", r"^3(0[0-5]|[68]\d)\d{11,16}$"), ("jcb", r"^35(2[89]|[3-8]\d)\d{12,15}$"),
         ("unionpay", r"^62\d{14,17}$"), ("maestro", r"^(5[06-9]|6\d)\d{10,17}$")]
POSTCODES = {"GB": r"^[A-Z]{1,2}\d[A-Z\d]? ?\d[A-Z]{2}$", "US": r"^\d{5}(-\d{4})?$", "CA": r"^[A-Z]\d[A-Z] ?\d[A-Z]\d$", "DE": r"^\d{5}$",
             "FR": r"^\d{5}$", "ES": r"^\d{5}$", "IT": r"^\d{5}$", "NL": r"^\d{4} ?[A-Z]{2}$", "AU": r"^\d{4}$", "IE": r"^[A-Z]\d[\dW] ?[A-Z\d]{4}$",
             "IN": r"^\d{6}$", "BR": r"^\d{5}-?\d{3}$", "JP": r"^\d{3}-?\d{4}$", "SE": r"^\d{3} ?\d{2}$", "PL": r"^\d{2}-\d{3}$", "PT": r"^\d{4}-\d{3}$",
             "BE": r"^\d{4}$", "CH": r"^\d{4}$", "AT": r"^\d{4}$", "DK": r"^\d{4}$", "NO": r"^\d{4}$", "NZ": r"^\d{4}$", "MX": r"^\d{5}$", "ZA": r"^\d{4}$"}

def check(mod, value, **extra):
    try:
        v = mod.validate(value)
        return {"input": value, "valid": True, "normalized": v, **{k: f(v) for k, f in extra.items()}}
    except Exception as e:
        return {"input": value, "valid": False, "reason": type(e).__name__.replace("Invalid", "invalid ").strip().lower() or "invalid"}

def card(v):
    d = re.sub(r"[\s-]", "", v)
    brand = next((b for b, p in CARDS if re.match(p, d)), None)
    ok = d.isdigit() and 12 <= len(d) <= 19 and luhn.is_valid(d)
    return {"valid": bool(ok and brand), "luhn_valid": bool(d.isdigit() and luhn.is_valid(d)) if d.isdigit() else False, "brand": brand,
            "length": len(d), "masked": (d[:6] + "*" * max(0, len(d) - 10) + d[-4:]) if len(d) >= 12 else None}

def dispatch(request, path):
    path, a = path.rstrip("/") or "/", request.args
    try:
        if path in ("/", "/health"): return jsonify(status="ok")
        if PROXY_SECRET and request.headers.get("X-RapidAPI-Proxy-Secret") != PROXY_SECRET:
            raise ApiError(403, "Use this API through RapidAPI.")
        val = (a.get("value") or "").strip()[:64]
        if path not in ("/iban", "/vat", "/card", "/isbn", "/bic", "/ean", "/postcode"):
            raise ApiError(404, "Not found. Endpoints: /iban, /vat, /card, /isbn, /bic, /ean, /postcode")
        if not val: raise ApiError(422, "value query parameter is required")
        if path == "/iban": return jsonify(check(iban, val, formatted=iban.format, country=lambda v: v[:2], bank_code_hint=lambda v: v[4:8]))
        if path == "/vat":
            r = check(vat, val, formatted=lambda v: v, country=lambda v: v[:2].replace("EL", "GR"))
            r["note"] = "Checksum/format validation; not a live VIES registration lookup."
            return jsonify(r)
        if path == "/card": return jsonify(card(val))
        if path == "/isbn": return jsonify(check(isbn, val, isbn13=isbn.to_isbn13, formatted=lambda v: isbn.format(v)))
        if path == "/bic": return jsonify(check(bic, val, bank=lambda v: v[:4], country=lambda v: v[4:6]))
        if path == "/ean": return jsonify(check(ean, val))
        c = (a.get("country") or "").upper()
        if c not in POSTCODES: raise ApiError(422, "country must be one of " + ", ".join(sorted(POSTCODES)))
        norm = val.upper()
        ok = bool(re.match(POSTCODES[c], norm))
        if ok and c == "GB": norm = re.sub(r"^(.+?)\s?(\d[A-Z]{2})$", r"\1 \2", norm)
        return jsonify(input=val, country=c, valid=ok, normalized=norm if ok else None)
    except ApiError as e:
        return jsonify(error=e.msg), e.code
