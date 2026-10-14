import json, os
here=os.path.dirname(os.path.abspath(__file__)); slugs=json.load(open(f"{here}/slugs.json"))
for kit, slug in slugs.items():
    p=f"{here}/{kit}/server.json"
    if not slug or not os.path.exists(p): continue
    d=json.load(open(p)); host=f"{slug}.p.rapidapi.com"
    d["title"]=d["title"].replace(" MCP","")
    d["websiteUrl"]=f"https://rapidapi.com/Olly-1VN9JTXKG/api/{slug}"
    d["remotes"]=[{"type":"streamable-http","url":f"https://{host}/mcp","headers":[
        {"name":"X-RapidAPI-Key","description":f"Your RapidAPI key (subscribe to {d['title']} on RapidAPI; free plan available)","isRequired":True,"isSecret":True},
        {"name":"X-RapidAPI-Host","description":"RapidAPI host for this API","isRequired":True,"default":host,"choices":[host]}]}]
    json.dump(d,open(p,"w"),indent=2); print(kit, host)
