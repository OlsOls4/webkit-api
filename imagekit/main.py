"""ImageKit: resize, convert, compress, crop, thumbnail, EXIF strip/read, and info for images."""
import base64, io
import httpx
from flask import jsonify, Response
from PIL import Image, ImageOps, ExifTags

MAX_BYTES = 15_000_000
MAX_PIXELS = 40_000_000
Image.MAX_IMAGE_PIXELS = MAX_PIXELS
FORMATS = {"jpeg": "image/jpeg", "jpg": "image/jpeg", "png": "image/png", "webp": "image/webp", "gif": "image/gif", "bmp": "image/bmp", "tiff": "image/tiff", "ico": "image/x-icon"}

class ApiError(Exception):
    def __init__(self, code, msg): self.code, self.msg = code, msg

def load(request):
    f = request.files.get("file") if request.files else None
    if f: data = f.read(MAX_BYTES + 1)
    elif request.args.get("url"):
        import main as root
        url = request.args["url"]
        try: root._safe(url)
        except Exception as e: raise ApiError(400, getattr(e, "msg", "Invalid or disallowed url"))
        try:
            with httpx.stream("GET", url, timeout=15, follow_redirects=False, headers={"User-Agent": root.UA}) as r:
                if r.status_code != 200: raise ApiError(502, f"Fetching url returned {r.status_code}")
                data = b""
                for c in r.iter_bytes():
                    data += c
                    if len(data) > MAX_BYTES: break
        except httpx.HTTPError as e: raise ApiError(502, f"Fetch failed: {type(e).__name__}")
    else:
        b = request.get_json(silent=True)
        if isinstance(b, dict) and b.get("base64"):
            s = b["base64"].split(",", 1)[-1]
            try: data = base64.b64decode(s, validate=False)
            except Exception: raise ApiError(422, "base64 is not valid")
        elif request.data: data = request.data
        else: raise ApiError(422, "Send an image as ?url=, multipart 'file', raw body, or JSON {\"base64\": ...}")
    if len(data) > MAX_BYTES: raise ApiError(413, "Image max 15 MB")
    try:
        im = Image.open(io.BytesIO(data)); im.load()
    except Image.DecompressionBombError: raise ApiError(413, "Image too large (max 40 megapixels)")
    except Exception: raise ApiError(422, "Could not read image (supported: JPEG, PNG, WebP, GIF, BMP, TIFF, ICO)")
    return im, len(data)

def num(a, k, d, lo, hi):
    v = a.get(k)
    if v in (None, ""): return d
    try: return max(lo, min(hi, int(v)))
    except ValueError: raise ApiError(422, f"{k} must be an integer")

def encode(im, fmt, quality, request, extra=None):
    fmt = (fmt or (im.format or "png")).lower()
    if fmt not in FORMATS: raise ApiError(422, "format must be one of jpeg, png, webp, gif, bmp, tiff, ico")
    pil = "JPEG" if fmt in ("jpg", "jpeg") else fmt.upper()
    if pil == "JPEG" and im.mode not in ("RGB", "L"):
        bg = Image.new("RGB", im.size, (255, 255, 255))
        if im.mode in ("RGBA", "LA", "P"):
            im2 = im.convert("RGBA"); bg.paste(im2, mask=im2.split()[-1])
        else: bg.paste(im.convert("RGB"))
        im = bg
    buf = io.BytesIO(); kw = {}
    if pil in ("JPEG", "WEBP"): kw.update(quality=quality, optimize=True)
    if pil == "PNG": kw.update(optimize=True)
    if pil == "JPEG": kw["progressive"] = True
    if pil == "ICO": kw["sizes"] = [(min(im.width, 256), min(im.height, 256))]
    im.save(buf, pil, **kw); data = buf.getvalue(); mime = FORMATS[fmt]
    if request.args.get("output") == "base64":
        return jsonify(format=fmt, mime=mime, width=im.width, height=im.height, bytes=len(data), **(extra or {}),
                       data_uri=f"data:{mime};base64," + base64.b64encode(data).decode())
    return Response(data, mimetype=mime, headers={"X-Image-Width": str(im.width), "X-Image-Height": str(im.height), "X-Image-Bytes": str(len(data))})

def info(im, size):
    exif = {}
    try:
        for k, v in (im.getexif() or {}).items():
            name = ExifTags.TAGS.get(k, str(k))
            if isinstance(v, bytes): continue
            exif[name] = v if isinstance(v, (int, float)) else str(v)[:200]
    except Exception: pass
    return {"format": (im.format or "").lower() or None, "mode": im.mode, "width": im.width, "height": im.height, "bytes": size,
            "megapixels": round(im.width * im.height / 1e6, 2), "aspect_ratio": round(im.width / im.height, 4) if im.height else None,
            "has_alpha": im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info),
            "animated": bool(getattr(im, "is_animated", False)), "frames": getattr(im, "n_frames", 1), "exif": exif}

def dispatch(request, path):
    path, a = path.rstrip("/") or "/", request.args
    try:
        if path in ("/", "/health"): return jsonify(status="ok")
        if path not in ("/info", "/resize", "/convert", "/compress", "/thumbnail", "/crop", "/rotate", "/strip-exif", "/grayscale"):
            raise ApiError(404, "Not found. Endpoints: /info, /resize, /convert, /compress, /thumbnail, /crop, /rotate, /strip-exif, /grayscale")
        im, size = load(request)
        if path == "/info": return jsonify(info(im, size))
        src_fmt = im.format
        im = ImageOps.exif_transpose(im)
        if im.format is None: im.format = src_fmt
        q = num(a, "quality", 82, 1, 100); fmt = a.get("format")
        if path == "/resize":
            w, h = num(a, "width", 0, 0, 8000), num(a, "height", 0, 0, 8000)
            if not w and not h: raise ApiError(422, "width and/or height is required")
            fit = a.get("fit", "contain")
            if fit not in ("contain", "cover", "fill"): raise ApiError(422, "fit must be contain, cover or fill")
            if not w: w = round(im.width * h / im.height)
            if not h: h = round(im.height * w / im.width)
            if fit == "fill": im = im.resize((w, h), Image.LANCZOS)
            elif fit == "cover": im = ImageOps.fit(im, (w, h), Image.LANCZOS)
            else: im = im.copy(); im.thumbnail((w, h), Image.LANCZOS)
            return encode(im, fmt or im.format, q, request)
        if path == "/thumbnail":
            s = num(a, "size", 256, 16, 2000); im = ImageOps.fit(im, (s, s), Image.LANCZOS) if a.get("square", "true") != "false" else im.copy()
            if a.get("square") == "false": im.thumbnail((s, s), Image.LANCZOS)
            return encode(im, fmt or "webp", q, request)
        if path == "/convert":
            if not fmt: raise ApiError(422, "format is required (jpeg, png, webp, gif, bmp, tiff, ico)")
            return encode(im, fmt, q, request)
        if path == "/compress":
            mw = num(a, "max_width", 0, 0, 8000)
            if mw and im.width > mw: im = im.copy(); im.thumbnail((mw, 100000), Image.LANCZOS)
            target = (fmt or ("webp" if a.get("modern", "true") != "false" else ("png" if im.mode in ("RGBA", "LA", "P") else "jpeg"))).lower()
            return encode(im, target, num(a, "quality", 70, 1, 100), request, {"original_bytes": size})
        if path == "/crop":
            x, y = num(a, "x", 0, 0, 100000), num(a, "y", 0, 0, 100000)
            w, h = num(a, "width", 0, 1, 100000), num(a, "height", 0, 1, 100000)
            if x + w > im.width or y + h > im.height: raise ApiError(422, f"crop box exceeds image size {im.width}x{im.height}")
            return encode(im.crop((x, y, x + w, y + h)), fmt or im.format, q, request)
        if path == "/rotate":
            deg = num(a, "degrees", 90, -360, 360)
            im = im.rotate(-deg, expand=True, resample=Image.BICUBIC)
            if a.get("flip") == "horizontal": im = ImageOps.mirror(im)
            elif a.get("flip") == "vertical": im = ImageOps.flip(im)
            return encode(im, fmt or im.format or "png", q, request)
        if path == "/grayscale": return encode(ImageOps.grayscale(im), fmt or im.format, q, request)
        fmt0 = src_fmt; clean = im.copy(); clean.info = {k: v for k, v in im.info.items() if k in ("transparency",)}
        return encode(clean, fmt or fmt0, q, request)
    except ApiError as e:
        return jsonify(error=e.msg), e.code
