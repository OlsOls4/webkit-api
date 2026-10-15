"""VATKit: live EU VAT number checks against the European Commission's VIES service, offline VAT number format
validation (EU + UK), EU VAT rates and VIES availability."""
import re
import httpx
from flask import jsonify
from stdnum.eu import vat as euvat
from stdnum.gb import vat as gbvat
from stdnum.exceptions import ValidationError, InvalidLength, InvalidChecksum, InvalidFormat, InvalidComponent

class ApiError(Exception):
    def __init__(self, code, msg, extra=None): self.code, self.msg, self.extra = code, msg, extra or {}

VIES = "https://ec.europa.eu/taxation_customs/vies/rest-api"
UA = {"User-Agent": "VATKit/1.0 (+https://rapidapi.com/Olly-1VN9JTXKG)", "Accept": "application/json"}
VIES_SOURCE = "European Commission VIES (VAT Information Exchange System), https://ec.europa.eu/taxation_customs/vies/"
COUNTRIES = {"AT": "Austria", "BE": "Belgium", "BG": "Bulgaria", "CY": "Cyprus", "CZ": "Czechia", "DE": "Germany", "DK": "Denmark",
             "EE": "Estonia", "EL": "Greece", "ES": "Spain", "FI": "Finland", "FR": "France", "HR": "Croatia", "HU": "Hungary",
             "IE": "Ireland", "IT": "Italy", "LT": "Lithuania", "LU": "Luxembourg", "LV": "Latvia", "MT": "Malta", "NL": "Netherlands",
             "PL": "Poland", "PT": "Portugal", "RO": "Romania", "SE": "Sweden", "SI": "Slovenia", "SK": "Slovakia",
             "XI": "Northern Ireland (UK, EU VAT rules for goods)"}
# EU VAT rates (%). Source: European Commission, Your Europe "VAT rules and rates" table (last checked by the Commission 13 Jul 2026).
# Maintained by hand: update RATES_AS_OF whenever a member state changes a rate.
RATES_AS_OF = "2026-07-13"
RATES_SOURCE = "European Commission, Your Europe: VAT rates applied in EU member countries (https://europa.eu/youreurope/business/taxation/vat/vat-rules-rates/index_en.htm). Regional rates (e.g. Canary Islands, Azores, Madeira) are not included; see the EC Taxes in Europe database for detail."
RATES = {  # code: (standard, [reduced], super_reduced, parking, has_zero_rate)
    "AT": (20, [10, 13], None, 13, False), "BE": (21, [6, 12], None, 12, False), "BG": (20, [9], None, None, False),
    "CY": (19, [5, 9], 3, None, False), "CZ": (21, [12], None, None, True), "DE": (19, [7], None, None, False),
    "DK": (25, [], None, None, True), "EE": (24, [9], None, None, False), "EL": (24, [6, 13, 17], 4, None, False),
    "ES": (21, [10], 4, None, False), "FI": (25.5, [10, 13.5], None, None, False), "FR": (20, [5.5, 10], 2.1, None, False),
    "HR": (25, [5, 13], None, None, False), "HU": (27, [5, 18], None, None, False), "IE": (23, [9, 13.5], None, None, False),
    "IT": (22, [5, 10], 4, None, False), "LT": (21, [5, 12], None, None, False), "LU": (17, [8], 3, 14, False),
    "LV": (21, [5, 12], None, None, False), "MT": (18, [5, 7], None, 12, False), "NL": (21, [9], None, None, False),
    "PL": (23, [5, 8], None, None, False), "PT": (23, [6, 13], None, 13, False), "RO": (21, [11], None, None, False),
    "SE": (25, [6, 12], None, None, False), "SI": (22, [5, 9.5], None, None, False), "SK": (23, [5, 19], None, None, False)}
CURRENCY = {"BG": "BGN", "CZ": "CZK", "DK": "DKK", "HU": "HUF", "PL": "PLN", "RO": "RON", "SE": "SEK"}
TRANSIENT = {"MS_UNAVAILABLE": "The member state's VAT database is temporarily unavailable",
             "MS_MAX_CONCURRENT_REQ": "Too many concurrent requests to this member state's VAT database",
             "GLOBAL_MAX_CONCURRENT_REQ": "VIES is handling too many requests",
             "SERVICE_UNAVAILABLE": "VIES is temporarily unavailable", "TIMEOUT": "The member state's VAT database did not answer in time",
             "SERVER_BUSY": "VIES is busy", "IP_BLOCKED": "VIES is temporarily refusing requests"}


def split(raw, country=None):
    """Return (country_code, number) in VIES form (EL for Greece). Raises 422 on unusable input."""
    v = re.sub(r"[\s.\-/]", "", raw or "").upper()
    if country:
        cc = country.strip().upper()
        if v.startswith(cc) or (cc == "GR" and v.startswith("EL")) or (cc == "EL" and v.startswith("GR")): v = v[2:]
    else:
        if len(v) < 3 or not v[:2].isalpha(): raise ApiError(422, "vat must start with a 2-letter country prefix, e.g. IE6388047V (or pass country separately)")
        cc, v = v[:2], v[2:]
    cc = {"GR": "EL"}.get(cc, cc)
    if not v or len(v) > 14 or not v.isalnum(): raise ApiError(422, "VAT number must be 2-14 letters/digits after the country prefix")
    return cc, v


def fmt_check(cc, num):
    """Offline structural/checksum validation with python-stdnum."""
    try:
        if cc == "GB": gbvat.validate(num)
        else: euvat.validate(("GR" if cc == "EL" else cc) + num)
        return True, None
    except InvalidLength: return False, "invalid length"
    except InvalidChecksum: return False, "invalid checksum"
    except InvalidFormat: return False, "invalid format"
    except InvalidComponent: return False, "invalid component"
    except ValidationError: return False, "invalid"


def clean(s):
    s = (s or "").strip()
    return None if s in ("", "---") else s


def vies_check(cc, num, rcc=None, rnum=None):
    try:
        if rcc:
            r = httpx.post(f"{VIES}/check-vat-number", json={"countryCode": cc, "vatNumber": num, "requesterMemberStateCode": rcc, "requesterNumber": rnum},
                           headers=UA, timeout=20)
        else:
            r = httpx.get(f"{VIES}/ms/{cc}/vat/{num}", headers=UA, timeout=20)
    except httpx.HTTPError as e:
        raise ApiError(503, f"VIES could not be reached ({type(e).__name__}), retry shortly", {"error_code": "VIES_UNREACHABLE", "retryable": True})
    try: j = r.json()
    except ValueError: j = {}
    errs = [w.get("error") for w in (j.get("errorWrappers") or []) if isinstance(w, dict)]
    code = j.get("userError") or (errs[0] if errs else None)
    if code in TRANSIENT or (r.status_code >= 500 and code not in ("INVALID_INPUT", "INVALID_REQUESTER_INFO")):
        code = code or "SERVICE_UNAVAILABLE"
        raise ApiError(503, f"{TRANSIENT.get(code, 'VIES is temporarily unavailable')} ({code}). Retry in a few seconds or minutes.",
                       {"error_code": code, "country_code": cc, "retryable": True})
    if code == "INVALID_INPUT": raise ApiError(422, "VIES rejected the input: country code or VAT number is malformed", {"error_code": code})
    if code == "INVALID_REQUESTER_INFO": raise ApiError(422, "requester_vat is not a valid EU VAT number", {"error_code": code})
    if r.status_code >= 400 and code is None:
        raise ApiError(503, f"VIES returned HTTP {r.status_code}, retry shortly", {"error_code": "VIES_HTTP_ERROR", "retryable": True})
    valid = bool(j.get("valid", j.get("isValid", False)))
    addr = clean(j.get("address"))
    if addr: addr = re.sub(r"[ \t]{2,}", " ", addr)
    return {"valid": valid, "name": clean(j.get("name")) if valid else None,
            "address": re.sub(r"\s*\n\s*", ", ", addr) if valid and addr else None,
            "address_lines": [x.strip() for x in addr.split("\n") if x.strip()] if valid and addr else [],
            "request_date": j.get("requestDate"), "consultation_number": clean(j.get("requestIdentifier"))}


def rate_row(cc):
    s, red, sup, park, zero = RATES[cc]
    return {"country_code": cc, "iso_country_code": "GR" if cc == "EL" else cc, "country": COUNTRIES[cc], "currency": CURRENCY.get(cc, "EUR"),
            "standard_rate": s, "reduced_rates": red, "super_reduced_rate": sup, "parking_rate": park, "zero_rate": zero}


def dispatch(request, path):
    path, a = path.rstrip("/") or "/", request.args
    try:
        if path in ("/", "/health"): return jsonify(status="ok")
        if path == "/check":
            raw = a.get("vat") or a.get("number") or ""
            if not raw: raise ApiError(422, "vat is required, e.g. vat=IE6388047V (or country=IE&vat=6388047V)")
            if len(raw) > 30: raise ApiError(422, "vat is too long (max 30 characters)")
            cc, num = split(raw, a.get("country"))
            if cc == "GB": raise ApiError(422, "UK (GB) VAT numbers are not in VIES. Use /format for an offline GB check; Northern Ireland traders use the XI prefix")
            if cc not in COUNTRIES: raise ApiError(422, f"{cc} is not an EU VIES country code. Supported: " + ", ".join(COUNTRIES))
            rcc = rnum = None
            if a.get("requester_vat"):
                rcc, rnum = split(a.get("requester_vat"))
                if rcc not in COUNTRIES: raise ApiError(422, "requester_vat must be an EU VAT number with its country prefix")
            ok, why = fmt_check(cc, num)
            res = vies_check(cc, num, rcc, rnum)
            return jsonify(vat_number=cc + num, country_code=cc, country=COUNTRIES[cc], number=num, valid=res["valid"],
                           name=res["name"], address=res["address"], address_lines=res["address_lines"], request_date=res["request_date"],
                           consultation_number=res["consultation_number"], format_valid=ok, format_error=why,
                           note="Some member states (e.g. DE, ES) never return name or address through VIES; null then means 'not disclosed', not 'unknown company'.",
                           source=VIES_SOURCE)
        if path == "/format":
            raw = a.get("vat") or ""
            if not raw: raise ApiError(422, "vat is required, e.g. vat=FR40303265045")
            if len(raw) > 30: raise ApiError(422, "vat is too long (max 30 characters)")
            cc, num = split(raw, a.get("country"))
            if cc not in COUNTRIES and cc != "GB": raise ApiError(422, f"{cc} is not a supported country prefix. Supported: " + ", ".join(list(COUNTRIES) + ["GB"]))
            ok, why = fmt_check(cc, num)
            return jsonify(input=raw, vat_number=cc + num, country_code=cc, country=COUNTRIES.get(cc, "United Kingdom"), number=num,
                           format_valid=ok, error=why, checks_checksum=True,
                           note="Offline check of length, structure and check digits only. Use /check to confirm the number is actually registered.")
        if path == "/rates":
            c = (a.get("country") or "").strip().upper()
            meta = {"as_of": RATES_AS_OF, "source": RATES_SOURCE, "unit": "percent"}
            if c:
                c = {"GR": "EL"}.get(c, c)
                if c not in RATES: raise ApiError(422, "country must be an EU member state code, e.g. DE, FR, EL (or GR)")
                return jsonify(**rate_row(c), **meta)
            return jsonify(count=len(RATES), rates=[rate_row(k) for k in sorted(RATES)], **meta)
        if path == "/status":
            try:
                r = httpx.get(f"{VIES}/check-status", headers=UA, timeout=15); r.raise_for_status(); j = r.json()
            except (httpx.HTTPError, ValueError):
                raise ApiError(503, "VIES status could not be retrieved, retry shortly", {"error_code": "VIES_UNREACHABLE", "retryable": True})
            cs = [{"country_code": x.get("countryCode"), "country": COUNTRIES.get(x.get("countryCode")), "available": x.get("availability") == "Available",
                   "availability": x.get("availability")} for x in j.get("countries", [])]
            return jsonify(vies_available=bool((j.get("vow") or {}).get("available")), unavailable=[x["country_code"] for x in cs if not x["available"]],
                           countries=cs, source=VIES_SOURCE)
        raise ApiError(404, "Not found. Endpoints: /check, /format, /rates, /status")
    except ApiError as e:
        return jsonify(error=e.msg, **e.extra), e.code
