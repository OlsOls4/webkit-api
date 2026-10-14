"""LLMKit: token counting, RAG chunking, truncation, HTML/URL to Markdown and JSON repair for LLM apps."""
import json, os, re, unicodedata
from flask import jsonify

HERE = os.path.dirname(os.path.abspath(__file__))
os.environ.setdefault("TIKTOKEN_CACHE_DIR", os.path.join(HERE, "tiktoken_cache"))
ENCODINGS = ("o200k_base", "cl100k_base", "p50k_base", "r50k_base")
MAX_CHARS = 2_000_000

class ApiError(Exception):
    def __init__(self, code, msg): self.code, self.msg = code, msg

_enc = {}
def enc(name):
    name = name or "o200k_base"
    if name not in ENCODINGS: raise ApiError(422, "encoding must be one of " + ", ".join(ENCODINGS))
    if name not in _enc:
        import tiktoken
        try: _enc[name] = tiktoken.get_encoding(name)
        except Exception: raise ApiError(503, "Tokenizer unavailable, retry shortly")
    return _enc[name]

def body(request):
    b = request.get_json(silent=True) if request.method == "POST" else None
    return b if isinstance(b, dict) else {}

def arg(request, k, default=None):
    b = body(request)
    return b.get(k, request.args.get(k, default))

def text_of(request):
    t = arg(request, "text")
    if t is None and request.method == "POST" and not body(request): t = request.get_data(as_text=True)
    if not t: raise ApiError(422, "text is required (query param, JSON body {\"text\": ...} or raw POST body)")
    if len(t) > MAX_CHARS: raise ApiError(413, "text max 2,000,000 characters")
    return t

def num(v, d, lo, hi):
    try: return max(lo, min(hi, int(v if v is not None else d)))
    except (TypeError, ValueError): raise ApiError(422, "numeric parameter must be an integer")

def tokens(t, e):
    ids = enc(e).encode(t, disallowed_special=())
    return {"encoding": e or "o200k_base", "tokens": len(ids), "characters": len(t), "words": len(t.split()),
            "chars_per_token": round(len(t) / len(ids), 2) if ids else None,
            "models": {"o200k_base": "GPT-4o, GPT-4.1, o-series", "cl100k_base": "GPT-4, GPT-3.5, text-embedding-3", "p50k_base": "Codex, text-davinci", "r50k_base": "GPT-3"}[e or "o200k_base"]}

def chunk(t, e, size, overlap, mode):
    E = enc(e)
    if mode == "tokens":
        ids = E.encode(t, disallowed_special=()); out, i = [], 0
        step = max(1, size - overlap)
        while i < len(ids):
            out.append(E.decode(ids[i:i + size]))
            if i + size >= len(ids): break
            i += step
        chunks = out
    else:
        units = [u for u in (re.split(r"\n\s*\n", t) if mode == "paragraphs" else re.split(r"(?<=[.!?])\s+", t)) if u.strip()]
        chunks, cur, cur_n = [], [], 0
        for u in units:
            n = len(E.encode(u, disallowed_special=()))
            if cur and cur_n + n > size:
                chunks.append(("\n\n" if mode == "paragraphs" else " ").join(cur))
                keep, k = [], 0
                for x in reversed(cur):
                    xn = len(E.encode(x, disallowed_special=()))
                    if k + xn > overlap: break
                    keep.insert(0, x); k += xn
                cur, cur_n = keep, k
            cur.append(u); cur_n += n
        if cur: chunks.append(("\n\n" if mode == "paragraphs" else " ").join(cur))
    return {"encoding": e or "o200k_base", "mode": mode, "chunk_size": size, "overlap": overlap, "count": len(chunks),
            "chunks": [{"index": i, "tokens": len(E.encode(c, disallowed_special=())), "characters": len(c), "text": c} for i, c in enumerate(chunks)]}

def truncate(t, e, n, keep):
    E = enc(e); ids = E.encode(t, disallowed_special=())
    cut = ids if len(ids) <= n else (ids[:n] if keep == "start" else ids[-n:])
    return {"encoding": e or "o200k_base", "original_tokens": len(ids), "tokens": len(cut), "truncated": len(ids) > n, "text": E.decode(cut)}

def clean(t):
    t = unicodedata.normalize("NFKC", t)
    t = re.sub(r"[\u200b-\u200f\u202a-\u202e\u2060\ufeff]", "", t)
    t = re.sub(r"[ \t]+", " ", t); t = re.sub(r" *\n *", "\n", t); t = re.sub(r"\n{3,}", "\n\n", t).strip()
    return {"text": t, "characters": len(t)}

def _single_to_double(x):
    out, i, n, ind = [], 0, len(x), False
    while i < n:
        ch = x[i]
        if ind:
            out.append(ch)
            if ch == "\\" and i + 1 < n: out.append(x[i + 1]); i += 2; continue
            if ch == '"': ind = False
            i += 1; continue
        if ch == '"': ind = True; out.append(ch); i += 1; continue
        if ch == "'":
            j, buf = i + 1, []
            while j < n and x[j] != "'":
                if x[j] == "\\" and j + 1 < n: buf.append(x[j:j + 2]); j += 2; continue
                buf.append('\\"' if x[j] == '"' else x[j]); j += 1
            out.append('"' + "".join(buf) + '"'); i = j + 1; continue
        out.append(ch); i += 1
    return "".join(out)

def extract_json(t):
    s = t.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", s, re.S)
    if m: s = m.group(1).strip()
    start = min([i for i in (s.find("{"), s.find("[")) if i >= 0] or [-1])
    if start < 0: raise ApiError(422, "No JSON object or array found in text")
    s = s[start:]
    def attempt(x):
        try: return json.loads(x)
        except json.JSONDecodeError: return None
    v = attempt(s); repaired = False
    if v is None:
        x = s
        x = re.sub(r"//[^\n]*", "", x)
        x = re.sub(r",\s*([}\]])", r"\1", x)
        x = _single_to_double(x)
        x = re.sub(r"(?<=[{,])\s*([A-Za-z_][A-Za-z0-9_]*)\s*:", r'"\1":', x)
        x = re.sub(r"\bTrue\b", "true", x); x = re.sub(r"\bFalse\b", "false", x); x = re.sub(r"\bNone\b", "null", x)
        stack = []
        ins = esc = False; end = len(x)
        for i, ch in enumerate(x):
            if ins:
                if esc: esc = False
                elif ch == "\\": esc = True
                elif ch == '"': ins = False
                continue
            if ch == '"': ins = True
            elif ch in "{[": stack.append("}" if ch == "{" else "]")
            elif ch in "}]":
                if stack: stack.pop()
                if not stack: end = i + 1; break
        x = x[:end]
        if ins: x += '"'
        x = re.sub(r",\s*$", "", x) + "".join(reversed(stack))
        v = attempt(x); repaired = True
        if v is None: raise ApiError(422, "Found JSON-like text but could not repair it")
    return {"valid": True, "repaired": repaired, "json": v}

def to_markdown(request):
    import main as root
    url, html = arg(request, "url"), arg(request, "html")
    try: mc = num(arg(request, "max_chars"), 50000, 500, 200000)
    except ApiError as e: raise e
    if url:
        try: r = root.extract(url, mc)
        except root.ApiError as e: raise ApiError(e.code, e.msg)
        return {"url": r["url"], "title": r["title"], "markdown": r["markdown"], "tokens": len(enc("o200k_base").encode(r["markdown"], disallowed_special=()))}
    if html:
        from bs4 import BeautifulSoup
        s = BeautifulSoup(html[:MAX_CHARS], "html.parser")
        for t in s(["script", "style", "noscript", "iframe", "svg", "nav", "footer", "form"]): t.decompose()
        md = []
        for n in s.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "pre", "blockquote", "td"]):
            txt = " ".join(n.get_text(" ", strip=True).split())
            if not txt: continue
            if n.name[0] == "h" and n.name[1:].isdigit(): md.append("#" * int(n.name[1]) + " " + txt)
            elif n.name == "li": md.append("- " + txt)
            elif n.name == "pre": md.append("```\n" + n.get_text() + "\n```")
            elif n.name == "blockquote": md.append("> " + txt)
            else: md.append(txt)
        out = "\n\n".join(md)[:mc]
        return {"title": s.title.get_text(strip=True) if s.title else None, "markdown": out, "tokens": len(enc("o200k_base").encode(out, disallowed_special=()))}
    raise ApiError(422, "url or html is required")

def dispatch(request, path):
    path = path.rstrip("/") or "/"
    try:
        if path in ("/", "/health"): return jsonify(status="ok")
        e = arg(request, "encoding")
        if path == "/tokens": return jsonify(tokens(text_of(request), e))
        if path == "/chunk":
            size = num(arg(request, "chunk_size"), 500, 5, 8000); ov = num(arg(request, "overlap"), 50, 0, 2000)
            if ov >= size: raise ApiError(422, "overlap must be smaller than chunk_size")
            mode = arg(request, "mode", "tokens")
            if mode not in ("tokens", "sentences", "paragraphs"): raise ApiError(422, "mode must be tokens, sentences or paragraphs")
            return jsonify(chunk(text_of(request), e, size, ov, mode))
        if path == "/truncate":
            keep = arg(request, "keep", "start")
            if keep not in ("start", "end"): raise ApiError(422, "keep must be start or end")
            return jsonify(truncate(text_of(request), e, num(arg(request, "max_tokens"), 1000, 1, 1000000), keep))
        if path == "/clean": return jsonify(clean(text_of(request)))
        if path == "/extract-json": return jsonify(extract_json(text_of(request)))
        if path == "/to-markdown": return jsonify(to_markdown(request))
        raise ApiError(404, "Not found. Endpoints: /tokens, /chunk, /truncate, /clean, /extract-json, /to-markdown")
    except ApiError as x:
        return jsonify(error=x.msg), x.code
