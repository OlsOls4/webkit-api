"""DocKit: PDF text/metadata extraction, page count, and Markdown/text to PDF generation."""
import base64, io, os
import httpx, markdown as md
from fpdf import FPDF
from pypdf import PdfReader
from flask import Response, jsonify

PROXY_SECRET = os.getenv("RAPIDAPI_PROXY_SECRET", "")
MAX_BYTES = 10 * 1024 * 1024

class ApiError(Exception):
    def __init__(self, code, msg): self.code, self.msg = code, msg

def get_pdf(request):
    f = request.files.get("file")
    if f: data = f.read(MAX_BYTES + 1)
    elif request.args.get("url"):
        import main as root
        url = request.args["url"]
        try: root._safe(url)
        except Exception as e: raise ApiError(400, getattr(e, "msg", "Invalid or disallowed url"))
        try:
            with httpx.stream("GET", url, timeout=15, follow_redirects=False, headers={"User-Agent": "DocKitAPI/1.0"}) as r:
                if r.status_code != 200: raise ApiError(502, f"Fetching url returned {r.status_code}")
                data = b""
                for chunk in r.iter_bytes():
                    data += chunk
                    if len(data) > MAX_BYTES: break
        except httpx.HTTPError as e: raise ApiError(502, f"Fetch failed: {type(e).__name__}")
    elif request.data: data = request.data[:MAX_BYTES + 1]
    else: raise ApiError(422, "Send a PDF as multipart 'file', raw body, or ?url=")
    if len(data) > MAX_BYTES: raise ApiError(413, "PDF max 10 MB")
    if not data.startswith(b"%PDF"): raise ApiError(422, "Not a PDF file")
    try: return PdfReader(io.BytesIO(data))
    except Exception: raise ApiError(422, "Could not read PDF")

def meta(r):
    m = r.metadata or {}
    g = lambda k: str(m.get(k)) if m.get(k) else None
    return {"pages": len(r.pages), "encrypted": r.is_encrypted, "title": g("/Title"), "author": g("/Author"), "subject": g("/Subject"),
            "creator": g("/Creator"), "producer": g("/Producer"), "created": g("/CreationDate"), "modified": g("/ModDate")}

def to_pdf(text, is_md, title):
    pdf = FPDF(); pdf.set_auto_page_break(True, 15); pdf.add_page(); pdf.set_font("Helvetica", size=11)
    if title: pdf.set_title(title)
    safe = lambda s: s.encode("latin-1", "replace").decode("latin-1")
    if is_md:
        pdf.write_html(safe(md.markdown(text, extensions=["tables", "fenced_code"])))
    else:
        pdf.multi_cell(0, 6, safe(text))
    return bytes(pdf.output())

def dispatch(request, path):
    path = path.rstrip("/") or "/"
    try:
        if path in ("/", "/health"): return jsonify(status="ok")
        if PROXY_SECRET and request.headers.get("X-RapidAPI-Proxy-Secret") != PROXY_SECRET:
            raise ApiError(403, "Use this API through RapidAPI.")
        if path == "/pdf/info": return jsonify(meta(get_pdf(request)))
        if path == "/pdf/text":
            r = get_pdf(request)
            if r.is_encrypted: raise ApiError(422, "PDF is encrypted")
            try: limit = max(1, min(int(request.args.get("max_pages", 50)), 200))
            except ValueError: raise ApiError(422, "max_pages must be an integer")
            pages = [(p.extract_text() or "") for p in r.pages[:limit]]
            full = "\n\n".join(pages)
            return jsonify(**meta(r), pages_extracted=len(pages), words=len(full.split()), text=full, page_texts=pages)
        if path in ("/markdown-to-pdf", "/text-to-pdf"):
            body = request.get_json(silent=True) or {}
            text = (body.get("text") if isinstance(body, dict) else None) or request.form.get("text") or request.args.get("text")
            if not text: raise ApiError(422, 'Provide text (JSON {"text": ...}, form or query)')
            if len(text) > 200_000: raise ApiError(413, "text max 200,000 characters")
            title = (body.get("title") if isinstance(body, dict) else None) or request.args.get("title")
            try: data = to_pdf(text, path == "/markdown-to-pdf", title)
            except Exception as e: raise ApiError(422, f"Could not render: {type(e).__name__}")
            if request.args.get("format") == "base64":
                return jsonify(mime="application/pdf", size=len(data), data_uri="data:application/pdf;base64," + base64.b64encode(data).decode())
            return Response(data, mimetype="application/pdf", headers={"Content-Disposition": 'inline; filename="document.pdf"'})
        raise ApiError(404, "Not found. Endpoints: /pdf/info, /pdf/text, /markdown-to-pdf, /text-to-pdf")
    except ApiError as e:
        return jsonify(error=e.msg), e.code
