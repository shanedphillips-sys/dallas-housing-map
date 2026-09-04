"""
All PFC/HFC apartment projects in the City of Dallas as map points (parallel to the
LIHTC layer data/subsidized_housing.geojson). ALL years — not just new construction.
Covers the Dallas-County (DCAD) and Collin-County (Collin CAD) portions of the city.

  Dallas: DCAD ACCOUNT_INFO -> PFC/HFC-owned Dallas accounts (owner-name match) + name/
          address/deed year; COM_DETAIL -> apartment/loft units + earliest year built
  Collin: Collin CAD CSV -> PFC/HFC-owned Dallas apartment parcels (owner-name match,
          situsCity == DALLAS, propCategoryCode B*, imprvUnits > 0)
  Denton: data/denton_pfc_hfc.json (cached once by build_denton_pfc.py from the 19 GB
          protax export) -> PFC/HFC-owned Dallas apartment parcels
  parcels_{q}.geojson -> parcel geometry -> representative point (DCAD account_num,
          COL-<propID> for Collin, DEN-<pID> for Denton; Denton parcels the webmap lacks
          fall back to the cached protax lon/lat)
  -> data/pfc_hfc_projects.geojson : Point features
     props: name, address, owner, total_units, year_built, acquired, lihtc, units_est

The Denton protax records some large complexes as "1 unit"; where that happens the unit
count is estimated from living building area (slim imprvMainArea / ~950 sqft) and flagged
`units_est` so the popup can mark it. `lihtc` flags projects whose CAD name carries a
"TDHCA#" (also tax-credit). Read-only over the CAD sources.
"""
import csv
import json
import os
import re
from collections import defaultdict

import pyogrio

WEB = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(WEB, "data")
D = (r"C:/Users/shane/OneDrive/Documents/Domain Consulting/Projects/"
     r"GDPC - Dallas Housing Report/GDPC Claude Stuff/DCAD2025_CERTIFIED")
COLLIN_CANDIDATES = [
    os.path.join(os.path.dirname(WEB), "Collin_CAD_Appraisal_Data_-_2025_20260520.csv"),
    (r"C:/Users/shane/OneDrive/Documents/Domain Consulting/Projects/"
     r"GDPC - Dallas Housing Report/Collin_CAD_Appraisal_Data_-_2025_20260520.csv"),
]

PFC_RE = ("HOUSING FINANCE", "PUBLIC FACILIT")


def titlecase(s):
    return " ".join(w.capitalize() if not w.isdigit() else w for w in (s or "").split())


def clean_name(s):
    s = titlecase((s or "").strip(" %"))
    return re.sub(r"\s*-?\s*Tdhca#?\s*\d+", "", s, flags=re.I).strip(" -%")


# ============================================================================
# Dallas County (DCAD)
# ============================================================================
acct = {}
with open(os.path.join(D, "ACCOUNT_INFO.CSV"), encoding="latin-1", newline="") as f:
    for r in csv.DictReader(f):
        nm = ((r["OWNER_NAME1"] or "") + " " + (r["OWNER_NAME2"] or "")).upper()
        if not any(k in nm for k in PFC_RE):
            continue
        if (r["PROPERTY_CITY"] or "").strip().upper() != "DALLAS":
            continue
        a = r["ACCOUNT_NUM"].strip()
        addr = " ".join(x for x in [(r["STREET_NUM"] or "").strip() + (r["STREET_HALF_NUM"] or "").strip(),
                                    titlecase(r["FULL_STREET_NAME"])] if x).strip()
        deed = (r["DEED_TXFR_DATE"] or "").strip()[:4]
        acct[a] = {
            "name": clean_name(r["BIZ_NAME"]) or addr or titlecase(r["OWNER_NAME1"]),
            "address": addr,
            "owner": titlecase(r["OWNER_NAME1"]),
            "acquired": int(deed) if deed.isdigit() and int(deed) > 1900 else None,
            "lihtc": "TDHCA" in ((r["BIZ_NAME"] or "") + " " + (r["LEGAL1"] or "")).upper(),
        }

apt = defaultdict(lambda: {"units": 0, "yb": None})
with open(os.path.join(D, "COM_DETAIL.CSV"), encoding="latin-1", newline="") as f:
    for r in csv.DictReader(f):
        a = r["ACCOUNT_NUM"].strip()
        if a not in acct:
            continue
        cls = (r["BLDG_CLASS_DESC"] or "").upper()
        if "APARTMENT" not in cls and "LOFT" not in cls:
            continue
        u = r["NUM_UNITS"].strip()
        apt[a]["units"] += int(u) if u.isdigit() else 0
        yb = r["YEAR_BUILT"].strip()
        yb = int(yb) if yb.isdigit() and int(yb) > 1850 else None
        if yb and (apt[a]["yb"] is None or yb < apt[a]["yb"]):
            apt[a]["yb"] = yb

dcad_projects = {a: {**acct[a], "total_units": d["units"], "year_built": d["yb"]}
                 for a, d in apt.items() if d["units"] > 0}
print(f"Dallas (DCAD) PFC/HFC apartment accounts: {len(dcad_projects)}  "
      f"({sum(p['total_units'] for p in dcad_projects.values())} units)")


# ============================================================================
# Collin County (Collin CAD certified CSV) — keyed by propID (COL-<propID> parcels)
# ============================================================================
collin_csv = next((p for p in COLLIN_CANDIDATES if os.path.exists(p)), None)
collin_projects = {}
if not collin_csv:
    print("WARNING: Collin CAD CSV not found — skipping Collin County.")
else:
    with open(collin_csv, encoding="latin-1", newline="") as f:
        for r in csv.DictReader(f):
            if (r.get("situsCity") or "").strip().upper() != "DALLAS":
                continue
            nm = ((r.get("ownerName") or "") + " " + (r.get("ownerNameAddtl") or "")).upper()
            if not any(k in nm for k in PFC_RE):
                continue
            if not (r.get("propCategoryCode") or "").upper().startswith("B"):
                continue                                    # apartment/multifamily category
            u = (r.get("imprvUnits") or "").replace(",", "").strip()
            units = int(float(u)) if re.fullmatch(r"\d+(\.\d+)?", u) else 0
            if units <= 0:                                  # actual building, not a land/component parcel
                continue
            try:
                pid = int(str(r.get("propID")).strip())
            except (TypeError, ValueError):
                continue
            addr = " ".join(x for x in [(r.get("situsBldgNum") or "").strip(),
                                        (r.get("situsStreetPrefix") or "").strip(),
                                        titlecase(r.get("situsStreetName")),
                                        (r.get("situsStreetSuffix") or "").strip()] if x).strip()
            yb = (r.get("imprvYearBuilt") or "").strip()
            dyear = re.search(r"(19|20)\d\d", (r.get("deedEffDate") or r.get("deedFileDate") or ""))
            collin_projects[pid] = {
                "name": clean_name(r.get("dbaName")) or addr or titlecase(r.get("ownerName")),
                "address": addr,
                "owner": titlecase(r.get("ownerName")),
                "total_units": units,
                "year_built": int(yb) if yb.isdigit() and int(yb) > 1850 else None,
                "acquired": int(dyear.group()) if dyear else None,
                "lihtc": "TDHCA" in ((r.get("dbaName") or "") + " " + (r.get("legalDescription") or "")).upper(),
            }
    print(f"Collin (Collin CAD) PFC/HFC apartment parcels: {len(collin_projects)}  "
          f"({sum(p['total_units'] for p in collin_projects.values())} units)")


# ============================================================================
# Denton County — cached PFC/HFC extract from build_denton_pfc.py (DEN-<pID>)
# ============================================================================
denton_projects = {}
denton_cache = os.path.join(DATA, "denton_pfc_hfc.json")
DENTON_SQFT_PER_UNIT = 950   # to estimate units where Denton CAD records the count as <=1
if os.path.exists(denton_cache):
    # slim building areas, to estimate units where the CAD unit count is missing (the Denton
    # protax records some large complexes as "1 unit"; sizing a dot by that would hide them)
    slim_area = {}
    slim_path = os.path.join(DATA, "denton_dallas_slim.json")
    if os.path.exists(slim_path):
        for r in json.load(open(slim_path, encoding="utf-8")):
            try:
                slim_area[int(r.get("pID"))] = float(r.get("imprvMainArea") or 0)
            except (TypeError, ValueError):
                pass
    for pid, h in json.load(open(denton_cache)).items():
        state = (h.get("stateCd") or "").upper()
        use = (h.get("useCd") or "").upper()
        if not (state.startswith("B1") or use.startswith("MF")):   # apartment / multifamily only
            continue
        try:
            key = int(pid)
        except (TypeError, ValueError):
            continue
        units = h.get("total_units") or 0
        units_est = False
        if units <= 1:                             # CAD count missing -> estimate from living area
            area = slim_area.get(key, 0)
            if area >= 20000:                      # a real apartment building, not a stub record
                units = round(area / DENTON_SQFT_PER_UNIT)
                units_est = True
        denton_projects[key] = {
            "name": h.get("name") or h.get("address") or h.get("owner"),
            "address": h.get("address"), "owner": h.get("owner"),
            "total_units": units, "units_est": units_est,
            "year_built": h.get("year_built"), "acquired": h.get("acquired"),
            "lihtc": bool(h.get("lihtc")),
            "lon": h.get("lon"), "lat": h.get("lat"),
        }
    n_est = sum(1 for p in denton_projects.values() if p["units_est"])
    print(f"Denton (protax cache) PFC/HFC apartment parcels: {len(denton_projects)}  "
          f"({sum(p['total_units'] for p in denton_projects.values())} units; {n_est} unit-count estimated)")
else:
    print("Denton cache (data/denton_pfc_hfc.json) not found — run build_denton_pfc.py; skipping Denton.")


# ============================================================================
# Locate every project via parcel geometry -> representative point
# ============================================================================
def resolve(account_num):
    if account_num in dcad_projects:
        return dcad_projects[account_num]
    if account_num.startswith("COL-"):
        s = account_num[4:]
        if s.isdigit():
            return collin_projects.get(int(s))
    if account_num.startswith("DEN-"):
        s = account_num[4:]
        if s.isdigit():
            return denton_projects.get(int(s))
    return None


def make_feat(pr, lon, lat):
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [round(lon, 6), round(lat, 6)]},
        "properties": {
            "name": pr["name"], "address": pr["address"], "owner": pr["owner"],
            "total_units": pr["total_units"], "year_built": pr["year_built"],
            "acquired": pr["acquired"], "lihtc": pr["lihtc"],
            "units_est": pr.get("units_est", False),
        },
    }


feats = []
seen = set()
denton_located = set()
for q in ["nw", "ne", "sw", "se"]:
    p = os.path.join(DATA, f"parcels_{q}.geojson")
    if not os.path.exists(p):
        continue
    g = pyogrio.read_dataframe(p, columns=["account_num"])
    g["account_num"] = g["account_num"].astype(str).str.strip()
    g = g[g["account_num"].map(lambda a: resolve(a) is not None)]
    if not len(g):
        continue
    g = g.to_crs(4326)
    for _, row in g.iterrows():
        a = row["account_num"]
        if a in seen or row.geometry is None:
            continue
        seen.add(a)
        if a.startswith("DEN-") and a[4:].isdigit():
            denton_located.add(int(a[4:]))
        pr = resolve(a)
        pt = row.geometry.representative_point()
        feats.append(make_feat(pr, pt.x, pt.y))

# Denton parcels the webmap doesn't carry (e.g. a 2023 split) -> cached protax point
for pid, pr in denton_projects.items():
    if pid in denton_located:
        continue
    if pr.get("lon") is None or pr.get("lat") is None:
        print(f"  WARNING: Denton pID {pid} not in webmap parcels and no cached point — dropped")
        continue
    feats.append(make_feat(pr, pr["lon"], pr["lat"]))

n_projects = len(dcad_projects) + len(collin_projects) + len(denton_projects)
out = os.path.join(DATA, "pfc_hfc_projects.geojson")
json.dump({"type": "FeatureCollection", "features": feats}, open(out, "w"), allow_nan=False)
print(f"located {len(feats)} / {n_projects}  ->  {out}")
print(f"  mapped units: {sum(f['properties']['total_units'] for f in feats)}  "
      f"| also-LIHTC projects: {sum(1 for f in feats if f['properties']['lihtc'])}")
