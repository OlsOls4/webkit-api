"""TextKit API: language detection, sentiment, readability, keywords, profanity, summary, slug and stats."""
import math, os, re, unicodedata
from collections import Counter
import functions_framework
from flask import jsonify
from langdetect import DetectorFactory, detect_langs
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

DetectorFactory.seed = 0
PROXY_SECRET = os.getenv("RAPIDAPI_PROXY_SECRET", "")
MAX_CHARS = 50_000
VADER = SentimentIntensityAnalyzer()
STOP = set("""a about above after again against all am an and any are as at be because been before being below between both but by can
could did do does doing down during each few for from further had has have having he her here hers herself him himself his how i if in into
is it its itself just me more most my myself no nor not now of off on once only or other our ours ourselves out over own same she should so
some such than that the their theirs them themselves then there these they this those through to too under until up very was we were what
when where which while who whom why will with would you your yours yourself yourselves also may might must shall us one two get got like
make made many much new said says use used using way well even back still yet""".split())
PROFANE = set("""arse arsehole ass asshole bastard bitch bollocks bullshit cock crap cunt damn dick dickhead douche fag fuck fucked fucker fucking
goddamn motherfucker nigger piss prick pussy shit shitty slut twat wanker whore""".split())
WORD = re.compile(r"[A-Za-z\u00C0-\u024F']+")
SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'])")

class ApiError(Exception):
    def __init__(self, code, msg): self.code, self.msg = code, msg

def get_text(request):
    body = request.get_json(silent=True) or {}
    t = body.get("text") if isinstance(body, dict) else None
    t = t or request.form.get("text") or request.args.get("text")
    if not t or not t.strip(): raise ApiError(422, "Provide text as a query parameter, form field, or JSON body {\"text\": ...}")
    if len(t) > MAX_CHARS: raise ApiError(413, f"text max {MAX_CHARS} characters")
    return t

def p(request, name, default=None):
    body = request.get_json(silent=True) or {}
    if isinstance(body, dict) and name in body: return body[name]
    return request.args.get(name, request.form.get(name, default))

def language(t):
    try: langs = detect_langs(t)
    except Exception: raise ApiError(422, "Could not detect language (text too short or no letters)")
    return {"language": langs[0].lang, "confidence": round(langs[0].prob, 4), "candidates": [{"language": l.lang, "confidence": round(l.prob, 4)} for l in langs[:5]]}

def sentiment(t):
    s = VADER.polarity_scores(t)
    label = "positive" if s["compound"] >= 0.05 else "negative" if s["compound"] <= -0.05 else "neutral"
    sents = [x for x in SENT.split(t.strip()) if x][:50]
    return {"label": label, "compound": s["compound"], "positive": s["pos"], "neutral": s["neu"], "negative": s["neg"],
            "sentences": [{"text": x[:300], "compound": VADER.polarity_scores(x)["compound"]} for x in sents] if len(sents) > 1 else None}

def _syl(w):
    w = w.lower().strip("'")
    if len(w) <= 3: return 1
    w = re.sub(r"(?:[^laeiouy]es|ed|[^laeiouy]e)$", "", w); w = re.sub(r"^y", "", w)
    return max(1, len(re.findall(r"[aeiouy]{1,2}", w)))

def readability(t):
    words = WORD.findall(t); sents = max(1, len([s for s in SENT.split(t.strip()) if s.strip()]))
    if not words: raise ApiError(422, "text has no words")
    nw = len(words); syl = sum(_syl(w) for w in words); poly = sum(1 for w in words if _syl(w) >= 3)
    letters = sum(len(w) for w in words)
    fre = 206.835 - 1.015 * nw / sents - 84.6 * syl / nw
    fk = 0.39 * nw / sents + 11.8 * syl / nw - 15.59
    fog = 0.4 * (nw / sents + 100 * poly / nw)
    smog = 1.043 * math.sqrt(poly * 30 / sents) + 3.1291
    cli = 0.0588 * (letters / nw * 100) - 0.296 * (sents / nw * 100) - 15.8
    ari = 4.71 * letters / nw + 0.5 * nw / sents - 21.43
    grade = sorted([fk, fog, smog, cli, ari])[2]
    level = ("very easy" if fre >= 90 else "easy" if fre >= 80 else "fairly easy" if fre >= 70 else "standard" if fre >= 60
             else "fairly difficult" if fre >= 50 else "difficult" if fre >= 30 else "very difficult")
    r = lambda x: round(x, 2)
    return {"flesch_reading_ease": r(fre), "level": level, "flesch_kincaid_grade": r(fk), "gunning_fog": r(fog), "smog_index": r(smog),
            "coleman_liau_index": r(cli), "automated_readability_index": r(ari), "consensus_grade": r(grade),
            "syllables": syl, "complex_words": poly, "reading_time_seconds": round(nw / 238 * 60)}

def keywords(t, top):
    words = [w.lower().strip("'") for w in WORD.findall(t)]
    content = [w for w in words if w not in STOP and len(w) > 2]
    if not content: return {"keywords": [], "phrases": []}
    freq = Counter(content)
    phrases, cur = Counter(), []
    for w in words + ["."]:
        if w in STOP or len(w) <= 2:
            if 2 <= len(cur) <= 4: phrases[" ".join(cur)] += 1
            cur = []
        else: cur.append(w)
    n = len(content)
    kw = [{"keyword": w, "count": c, "score": round(c / n * (1 + math.log(len(w))), 4)} for w, c in freq.most_common(top * 3)]
    kw.sort(key=lambda x: -x["score"])
    return {"keywords": kw[:top], "phrases": [{"phrase": ph, "count": c} for ph, c in phrases.most_common(top) if c >= 1][:top]}

def profanity(t, mask):
    found = []
    def rep(m):
        w = m.group(0); base = w.lower().strip("'")
        hit = base in PROFANE or any(base.startswith(b) and len(base) - len(b) <= 3 for b in PROFANE if len(b) > 3)
        if hit: found.append(w); return mask * len(w)
        return w
    clean = WORD.sub(rep, t)
    return {"contains_profanity": bool(found), "count": len(found), "words": sorted(set(x.lower() for x in found)), "censored": clean}

def summarize(t, n):
    sents = [s.strip() for s in SENT.split(t.strip()) if len(s.strip()) > 20]
    if len(sents) <= n: return {"summary": " ".join(sents) or t.strip(), "sentences": len(sents)}
    freq = Counter(w.lower() for w in WORD.findall(t) if w.lower() not in STOP and len(w) > 2)
    top = max(freq.values()) if freq else 1
    scored = [(sum(freq.get(w.lower(), 0) / top for w in WORD.findall(s)) / (len(WORD.findall(s)) ** 0.5 or 1) + (0.3 if i == 0 else 0), i) for i, s in enumerate(sents)]
    keep = sorted(i for _, i in sorted(scored, reverse=True)[:n])
    return {"summary": " ".join(sents[i] for i in keep), "sentences": n, "original_sentences": len(sents)}

def slugify(t, sep):
    s = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().lower()
    return {"slug": re.sub(r"[^a-z0-9]+", sep, s).strip(sep)[:200]}

def stats(t):
    words = WORD.findall(t); sents = [s for s in SENT.split(t.strip()) if s.strip()]
    return {"characters": len(t), "characters_no_spaces": len(re.sub(r"\s", "", t)), "words": len(words), "unique_words": len(set(w.lower() for w in words)),
            "sentences": len(sents), "paragraphs": len([x for x in re.split(r"\n\s*\n", t) if x.strip()]),
            "avg_word_length": round(sum(map(len, words)) / len(words), 2) if words else 0,
            "avg_sentence_words": round(len(words) / len(sents), 2) if sents else 0, "reading_time_seconds": round(len(words) / 238 * 60),
            "speaking_time_seconds": round(len(words) / 150 * 60)}

def num(v, default, lo, hi):
    try: return max(lo, min(int(v if v is not None else default), hi))
    except (TypeError, ValueError): raise ApiError(422, "numeric parameter must be an integer")

@functions_framework.http
def handler(request):
    return dispatch(request, request.path)

def dispatch(request, path):
    path = path.rstrip("/") or "/"
    try:
        if path in ("/", "/health"): return jsonify(status="ok")
        if PROXY_SECRET and request.headers.get("X-RapidAPI-Proxy-Secret") != PROXY_SECRET:
            raise ApiError(403, "Use this API through RapidAPI.")
        if path not in ("/language", "/sentiment", "/readability", "/keywords", "/profanity", "/summarize", "/slugify", "/stats", "/analyze"):
            raise ApiError(404, "Not found. Endpoints: /language, /sentiment, /readability, /keywords, /profanity, /summarize, /slugify, /stats, /analyze")
        t = get_text(request)
        if path == "/language": return jsonify(language(t))
        if path == "/sentiment": return jsonify(sentiment(t))
        if path == "/readability": return jsonify(readability(t))
        if path == "/keywords": return jsonify(keywords(t, num(p(request, "top"), 10, 1, 50)))
        if path == "/profanity": return jsonify(profanity(t, (p(request, "mask") or "*")[:1]))
        if path == "/summarize": return jsonify(summarize(t, num(p(request, "sentences"), 3, 1, 20)))
        if path == "/slugify": return jsonify(slugify(t, "_" if p(request, "separator") == "_" else "-"))
        if path == "/stats": return jsonify(stats(t))
        out = {"stats": stats(t), "sentiment": sentiment(t), "keywords": keywords(t, 10)["keywords"]}
        try: out["language"] = language(t)
        except ApiError: out["language"] = None
        try: out["readability"] = readability(t)
        except Exception: out["readability"] = None
        out["sentiment"].pop("sentences", None)
        return jsonify(out)
    except ApiError as e:
        return jsonify(error=e.msg), e.code
