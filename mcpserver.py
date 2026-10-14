"""MCP (Model Context Protocol) server exposing every kit as tools, generated from openapi/*.json.
Streamable HTTP transport, stateless JSON responses. Discovery (initialize, tools/list) is open;
tools/call requires the RapidAPI gateway (subscribe to the 'APIKit MCP' listing on RapidAPI)."""
import base64, glob, json, os, re
from flask import jsonify, Response, current_app

HERE = os.path.dirname(os.path.abspath(__file__))
PROTO = "2025-06-18"
KIT_NAMES = {"webkit": "WebKit", "domainkit": "DomainKit", "qrkit": "QRKit", "textkit": "TextKit", "phonekit": "PhoneKit", "validkit": "ValidKit",
             "geoip": "GeoIP", "dockit": "DocKit", "fraudkit": "FraudKit", "llmkit": "LLMKit", "imagekit": "ImageKit", "calkit": "CalKit", "ukpostcode": "UK PostcodeKit"}
_TOOLS = None

def tools(kit=None):
    allt = _all()
    return {k: v for k, v in allt.items() if kit is None or v['kit'] == kit}

def _all():
    global _TOOLS
    if _TOOLS is not None: return _TOOLS
    out = {}
    for f in sorted(glob.glob(os.path.join(HERE, "openapi", "*.json"))):
        kit = os.path.basename(f)[:-5]; spec = json.load(open(f))
        prefix = spec["servers"][0]["url"].split(".run.app", 1)[-1]
        for path, ops in spec["paths"].items():
            for method, o in ops.items():
                if method not in ("get", "post"): continue
                name = (kit + "_" + re.sub(r"[^a-z0-9]+", "_", path.lower()).strip("_"))[:64]
                props, req = {}, []
                for p in o.get("parameters", []):
                    t = p.get("schema", {}).get("type", "string")
                    props[p["name"]] = {"type": t, "description": p.get("description", "")}
                    if p.get("required"): req.append(p["name"])
                bodykeys = []
                if "requestBody" in o:
                    ex = o["requestBody"]["content"]["application/json"]["schema"].get("example", {})
                    for k, v in ex.items():
                        props.setdefault(k, {"type": "array" if isinstance(v, list) else "number" if isinstance(v, (int, float)) and not isinstance(v, bool) else "string",
                                             "description": f"Request body field '{k}'"})
                        if isinstance(v, list): props[k]["items"] = {"type": "string"}
                        bodykeys.append(k)
                    req += [k for k in ("text", "ips", "numbers") if k in bodykeys and k not in req]
                desc = f"[{KIT_NAMES.get(kit, kit)}] {o.get('summary', '')}. {o.get('description', '')}".strip()
                out[name] = {"def": {"name": name, "description": desc[:1000], "inputSchema": {"type": "object", "properties": props, "required": req}},
                             "method": method.upper(), "path": prefix + path, "body": bodykeys, "kit": kit}
    _TOOLS = out
    return out

def call(name, args, kit=None):
    import main
    t = tools(kit).get(name)
    if not t: return {"isError": True, "content": [{"type": "text", "text": f"Unknown tool {name}"}]}
    args = dict(args or {})
    body = {k: args.pop(k) for k in list(args) if k in t["body"]} if t["body"] else None
    q = {k: (json.dumps(v) if isinstance(v, (dict, list)) else str(v).lower() if isinstance(v, bool) else str(v)) for k, v in args.items() if v is not None}
    with current_app.test_request_context(t["path"], method=t["method"], query_string=q, json=body if body else None):
        from flask import request as r
        resp = main.route(r)
    if isinstance(resp, tuple): resp, code = resp[0], resp[1]
    else: code = resp.status_code
    resp = current_app.make_response(resp)
    mime = (resp.mimetype or "")
    data = resp.get_data()
    if mime.startswith("image/") and mime != "image/svg+xml":
        return {"content": [{"type": "image", "data": base64.b64encode(data).decode(), "mimeType": mime}], "isError": code >= 400}
    if mime == "application/pdf":
        return {"content": [{"type": "resource", "resource": {"uri": "apikit://dockit/output.pdf", "mimeType": mime, "blob": base64.b64encode(data).decode()}}], "isError": code >= 400}
    text = data.decode("utf-8", "replace")
    res = {"content": [{"type": "text", "text": text[:200000]}], "isError": code >= 400}
    if mime == "application/json" and code < 400:
        try:
            v = json.loads(text)
            if isinstance(v, dict): res["structuredContent"] = v
        except ValueError: pass
    return res

def rpc(msg, request, kit=None):
    import main
    mid, m, p = msg.get("id"), msg.get("method"), msg.get("params") or {}
    ok = lambda r: {"jsonrpc": "2.0", "id": mid, "result": r}
    err = lambda c, s: {"jsonrpc": "2.0", "id": mid, "error": {"code": c, "message": s}}
    if m == "initialize":
        return ok({"protocolVersion": p.get("protocolVersion") if p.get("protocolVersion") in ("2025-06-18", "2025-03-26", "2024-11-05") else PROTO,
                   "capabilities": {"tools": {"listChanged": False}},
                   "serverInfo": {"name": "apikit" + (f"-{kit}" if kit else ""), "title": (KIT_NAMES.get(kit, kit) + " MCP") if kit else "APIKit: 13 developer APIs", "version": "1.1.0"},
                   "instructions": "Validation, enrichment, fraud scoring, LLM text utilities, images, QR codes, PDFs, holidays and UK postcodes. Tool calls are billed through RapidAPI: subscribe to 'APIKit MCP' at https://rapidapi.com/user/Olly-1VN9JTXKG and send your X-RapidAPI-Key header."})
    if m and m.startswith("notifications/"): return None
    if m == "ping": return ok({})
    if m == "tools/list": return ok({"tools": [t["def"] for t in tools(kit).values()]})
    if m == "tools/call":
        if not main.gate_ok(request):
            return ok({"isError": True, "content": [{"type": "text", "text": "Tool calls require a RapidAPI subscription. Subscribe to 'APIKit MCP' at https://rapidapi.com/user/Olly-1VN9JTXKG and connect via the RapidAPI URL with your X-RapidAPI-Key header."}]})
        try: return ok(call(p.get("name"), p.get("arguments"), kit))
        except Exception as e: return ok({"isError": True, "content": [{"type": "text", "text": f"Tool error: {type(e).__name__}: {str(e)[:200]}"}]})
    if m in ("resources/list",): return ok({"resources": []})
    if m in ("prompts/list",): return ok({"prompts": []})
    return err(-32601, f"Method not found: {m}")

def handle(request, kit=None):
    if kit and kit not in KIT_NAMES: return jsonify(error="Unknown kit. Use one of: " + ", ".join(KIT_NAMES)), 404
    if request.method == "GET":
        if "text/event-stream" in (request.headers.get("Accept") or ""): return Response("SSE stream not supported; use POST", status=405)
        return jsonify(name="apikit" + (f"-{kit}" if kit else ""), transport="streamable-http", tools=len(tools(kit)), kits=list(KIT_NAMES), docs="https://rapidapi.com/user/Olly-1VN9JTXKG")
    if request.method == "DELETE": return Response(status=204)
    if request.method != "POST": return Response(status=405)
    msg = request.get_json(silent=True)
    if msg is None: return jsonify({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}), 400
    if isinstance(msg, list):
        out = [r for r in (rpc(x, request, kit) for x in msg) if r is not None]
        return (jsonify(out), 200) if out else Response(status=202)
    r = rpc(msg, request, kit)
    if r is None: return Response(status=202)
    return jsonify(r)
