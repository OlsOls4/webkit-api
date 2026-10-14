"""PhoneKit: phone number validation, formatting, carrier, region, type and time zones."""
import os
import phonenumbers as pn
from phonenumbers import carrier, geocoder, timezone as pntz
from flask import jsonify

PROXY_SECRET = os.getenv("RAPIDAPI_PROXY_SECRET", "")
TYPES = {v: k.lower() for k, v in vars(pn.PhoneNumberType).items() if isinstance(v, int)}

class ApiError(Exception):
    def __init__(self, code, msg): self.code, self.msg = code, msg

def info(raw, country):
    if raw[:1] == " " and raw.strip()[:1].isdigit(): raw = "+" + raw.strip()
    try: n = pn.parse(raw, (country or "").upper() or None)
    except pn.NumberParseException as e:
        return {"input": raw, "valid": False, "possible": False, "error": str(e).split(") ", 1)[-1]}
    valid = pn.is_valid_number(n)
    region = pn.region_code_for_number(n)
    return {"input": raw, "valid": valid, "possible": pn.is_possible_number(n),
            "e164": pn.format_number(n, pn.PhoneNumberFormat.E164),
            "international": pn.format_number(n, pn.PhoneNumberFormat.INTERNATIONAL),
            "national": pn.format_number(n, pn.PhoneNumberFormat.NATIONAL),
            "rfc3966": pn.format_number(n, pn.PhoneNumberFormat.RFC3966),
            "country_code": n.country_code, "national_number": str(n.national_number), "region": region,
            "location": geocoder.description_for_number(n, "en") or None,
            "carrier": carrier.name_for_number(n, "en") or None,
            "line_type": TYPES.get(pn.number_type(n), "unknown"),
            "timezones": [t for t in pntz.time_zones_for_number(n) if t != "Etc/Unknown"]}

def dispatch(request, path):
    path, a = path.rstrip("/") or "/", request.args
    try:
        if path in ("/", "/health"): return jsonify(status="ok")
        if PROXY_SECRET and request.headers.get("X-RapidAPI-Proxy-Secret") != PROXY_SECRET:
            raise ApiError(403, "Use this API through RapidAPI.")
        if path == "/validate":
            num = a.get("number") or a.get("phone")
            if not num: raise ApiError(422, "number query parameter is required")
            return jsonify(info(num[:40], a.get("country")))
        if path == "/bulk":
            body = request.get_json(silent=True) or {}
            nums = body.get("numbers") if isinstance(body, dict) else None
            if not isinstance(nums, list) or not nums: raise ApiError(422, 'POST JSON {"numbers": [...], "country": "GB"}')
            if len(nums) > 100: raise ApiError(413, "max 100 numbers per request")
            return jsonify(results=[info(str(x)[:40], body.get("country")) for x in nums])
        if path == "/example":
            c = (a.get("country") or "").upper()
            ex = pn.example_number(c) if c else None
            if not ex: raise ApiError(422, "country must be an ISO 3166 alpha-2 code like GB")
            return jsonify(info(pn.format_number(ex, pn.PhoneNumberFormat.E164), c))
        raise ApiError(404, "Not found. Endpoints: /validate, /bulk (POST), /example")
    except ApiError as e:
        return jsonify(error=e.msg), e.code
