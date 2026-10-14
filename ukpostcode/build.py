"""Build ukpostcode/postcodes.sqlite from OS Code-Point Open (OGL v3). Run at deploy time."""
import csv, glob, io, os, sqlite3, sys, zipfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from osgb import to_wgs84
import openpyxl
src, out = sys.argv[1], sys.argv[2]
z = zipfile.ZipFile(src)
wb = openpyxl.load_workbook(io.BytesIO(z.read(next(n for n in z.namelist() if n.endswith("Codelist.xlsx")))), read_only=True)
names = {}
for ws in wb.worksheets:
    if ws.title in ("Sheet1", "AREA_CODES"): continue
    for r in ws.iter_rows(values_only=True):
        if r and len(r) >= 2 and r[1]: names[str(r[1])] = str(r[0])
COUNTRY = {"E92000001": "England", "W92000004": "Wales", "S92000003": "Scotland", "N92000002": "Northern Ireland"}
if os.path.exists(out): os.remove(out)
db = sqlite3.connect(out)
db.execute("CREATE TABLE n(id INTEGER PRIMARY KEY, code TEXT, name TEXT)")
db.execute("CREATE TABLE p(pc TEXT PRIMARY KEY, lat REAL, lng REAL, q INTEGER, country INTEGER, county INTEGER, district INTEGER, ward INTEGER) WITHOUT ROWID")
ids = {}
def nid(code):
    if not code: return None
    if code not in ids:
        ids[code] = len(ids) + 1
        db.execute("INSERT INTO n VALUES(?,?,?)", (ids[code], code, COUNTRY.get(code) or names.get(code)))
    return ids[code]
rows = []
for n in z.namelist():
    if not (n.startswith("Data/CSV/") and n.endswith(".csv")): continue
    for r in csv.reader(io.TextIOWrapper(z.open(n), "utf-8")):
        pc, q, e, no, cy, rh, lh, cc, dc, wc = r[:10]
        e, no = int(e), int(no)
        lat, lng = to_wgs84(e, no) if e and no else (None, None)
        rows.append((pc.replace(" ", "").upper(), lat, lng, int(q), nid(cy), nid(cc), nid(dc), nid(wc)))
    db.executemany("INSERT OR REPLACE INTO p VALUES(?,?,?,?,?,?,?,?)", rows); rows = []
db.execute("CREATE INDEX p_lat ON p(lat)"); db.commit(); db.execute("VACUUM"); db.close()
print("built", out, os.path.getsize(out))
