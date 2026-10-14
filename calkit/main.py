"""CalKit: public holidays, business-day maths, timezone lookup and conversion."""
import datetime as dt
from zoneinfo import ZoneInfo, available_timezones
from flask import jsonify
import holidays as hol

class ApiError(Exception):
    def __init__(self, code, msg): self.code, self.msg = code, msg

def pdate(v, name):
    if not v: raise ApiError(422, f"{name} is required (YYYY-MM-DD)")
    try: return dt.date.fromisoformat(v[:10])
    except ValueError: raise ApiError(422, f"{name} must be YYYY-MM-DD")

def cal(country, subdiv, years):
    c = (country or "").upper()
    if c not in hol.list_supported_countries(): raise ApiError(422, "Unsupported country. See /countries")
    try: return hol.country_holidays(c, subdiv=(subdiv or None), years=years)
    except NotImplementedError: raise ApiError(422, "Unsupported subdivision for this country. See /countries")

def weekend_days(a):
    w = (a.get("weekend") or "sat,sun").lower().split(",")
    m = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
    try: return {m[x.strip()[:3]] for x in w if x.strip()}
    except KeyError: raise ApiError(422, "weekend must be day names like sat,sun or fri,sat")

def is_bd(d, H, wk): return d.weekday() not in wk and d not in H

def dispatch(request, path):
    path, a = path.rstrip("/") or "/", request.args
    try:
        if path in ("/", "/health"): return jsonify(status="ok")
        if path == "/countries":
            sup = hol.list_supported_countries()
            return jsonify(count=len(sup), countries={k: sorted(v) for k, v in sorted(sup.items())})
        if path == "/holidays":
            try: y = int(a.get("year") or dt.date.today().year)
            except ValueError: raise ApiError(422, "year must be an integer")
            if not 1950 <= y <= 2100: raise ApiError(422, "year must be between 1950 and 2100")
            H = cal(a.get("country"), a.get("subdiv"), y)
            return jsonify(country=a.get("country", "").upper(), subdiv=a.get("subdiv"), year=y, count=len(H),
                           holidays=[{"date": d.isoformat(), "name": n, "weekday": d.strftime("%A")} for d, n in sorted(H.items())])
        if path == "/is-holiday":
            d = pdate(a.get("date"), "date"); H = cal(a.get("country"), a.get("subdiv"), d.year); wk = weekend_days(a)
            return jsonify(date=d.isoformat(), weekday=d.strftime("%A"), is_holiday=d in H, holiday_name=H.get(d), is_weekend=d.weekday() in wk,
                           is_business_day=is_bd(d, H, wk))
        if path == "/next-holiday":
            d = pdate(a.get("date") or dt.date.today().isoformat(), "date"); H = cal(a.get("country"), a.get("subdiv"), [d.year, d.year + 1])
            nxt = sorted(x for x in H if x >= d)[:num(a.get("count"), 1, 1, 20)]
            return jsonify(from_date=d.isoformat(), holidays=[{"date": x.isoformat(), "name": H[x], "days_away": (x - d).days} for x in nxt])
        if path == "/business-days/add":
            d = pdate(a.get("date"), "date"); n = num(a.get("days"), None, -3650, 3650); wk = weekend_days(a)
            H = cal(a.get("country"), a.get("subdiv"), list(range(d.year - 11, d.year + 12)))
            step = 1 if n >= 0 else -1; cur, left, skipped = d, abs(n), []
            while left:
                cur += dt.timedelta(days=step)
                if is_bd(cur, H, wk): left -= 1
                elif cur in H: skipped.append({"date": cur.isoformat(), "name": H[cur]})
            return jsonify(start=d.isoformat(), business_days=n, result=cur.isoformat(), weekday=cur.strftime("%A"), holidays_skipped=skipped)
        if path == "/business-days/between":
            s, e = pdate(a.get("start"), "start"), pdate(a.get("end"), "end"); wk = weekend_days(a)
            if abs((e - s).days) > 36500: raise ApiError(422, "range max 100 years")
            lo, hi = min(s, e), max(s, e); H = cal(a.get("country"), a.get("subdiv"), list(range(lo.year, hi.year + 1)))
            days = [lo + dt.timedelta(days=i) for i in range((hi - lo).days + 1)]
            bd = sum(1 for x in days if is_bd(x, H, wk))
            return jsonify(start=s.isoformat(), end=e.isoformat(), calendar_days=len(days), business_days=bd,
                           weekend_days=sum(1 for x in days if x.weekday() in wk), holidays=[{"date": x.isoformat(), "name": H[x]} for x in days if x in H and x.weekday() not in wk],
                           note="Both start and end dates are included")
        if path == "/timezone":
            try: lat, lng = float(a.get("lat")), float(a.get("lng"))
            except (TypeError, ValueError): raise ApiError(422, "lat and lng are required numbers")
            if not (-90 <= lat <= 90 and -180 <= lng <= 180): raise ApiError(422, "lat/lng out of range")
            import tzfpy
            tz = tzfpy.get_tz(lng, lat)
            if not tz: raise ApiError(404, "No timezone found")
            now = dt.datetime.now(ZoneInfo(tz))
            return jsonify(lat=lat, lng=lng, timezone=tz, local_time=now.isoformat(timespec="seconds"), utc_offset=now.strftime("%z"),
                           abbreviation=now.tzname(), is_dst=bool(now.dst()))
        if path == "/convert":
            t, f, to = a.get("time"), a.get("from"), a.get("to")
            zones = available_timezones()
            if f not in zones or to not in zones: raise ApiError(422, "from and to must be IANA timezones like Europe/London, America/New_York")
            try: x = dt.datetime.fromisoformat(t) if t else dt.datetime.now()
            except ValueError: raise ApiError(422, "time must be ISO 8601 like 2026-10-14T09:30")
            x = x.replace(tzinfo=ZoneInfo(f)) if x.tzinfo is None else x
            y = x.astimezone(ZoneInfo(to))
            return jsonify(input=x.isoformat(timespec="seconds"), output=y.isoformat(timespec="seconds"), from_zone=f, to_zone=to,
                           from_offset=x.strftime("%z"), to_offset=y.strftime("%z"), to_abbreviation=y.tzname())
        raise ApiError(404, "Not found. Endpoints: /holidays, /is-holiday, /next-holiday, /business-days/add, /business-days/between, /timezone, /convert, /countries")
    except ApiError as e:
        return jsonify(error=e.msg), e.code

def num(v, d, lo, hi):
    if v in (None, ""):
        if d is None: raise ApiError(422, "days is required")
        return d
    try: return max(lo, min(hi, int(v)))
    except ValueError: raise ApiError(422, "must be an integer")
