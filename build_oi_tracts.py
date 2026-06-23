"""
Opportunity Insights upward-mobility layer for the map: predicted adult household
income at age 35 for children who grew up in 25th-percentile-income families
(the Opportunity Atlas absolute-mobility measure), by census tract, 7 counties.

The OI estimates are on 2010 tracts; the map uses 2020 tracts, so each 2020 tract
takes its value directly (same GEOID) else from its dominant (largest land-area
overlap) 2010 parent -- the same crosswalk as the ACS / zoning / permit OI work
(Census tab20_tract20_tract10 relationship file).

Implausibly high estimates (> $100k -- tiny-sample Atlas noise; the regional p90
is ~$46k, and the raw file has a lone $1.06M tract) are dropped to null.

Writes data/oi_tracts.geojson  (per tract: {geoid, oi}; oi null = no estimate).
"""
import json
import os

import geopandas as gpd
import pandas as pd
from shapely.geometry import mapping

WEB = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(WEB)
DATA = os.path.join(WEB, "data")
OI = r"C:\Users\shane\OneDrive\Documents\Domain Consulting\Projects\GDPC - Dallas Housing Report\GDPC Claude Stuff\opportunity_insights_tract_kfr_rP_gP_p25.csv"
REL = os.path.join(PROJECT, "tab20_tract20_tract10_natl.txt")
PREF = {"48113", "48085", "48121", "48439", "48139", "48257", "48397"}
CAP = 100_000

# ---- OI value by 2010 tract (drop <=0 and >CAP noise) ----------------------
oi = pd.read_csv(OI, dtype={"tract": str})
oi["tract"] = oi["tract"].str.zfill(11)
oi["v"] = pd.to_numeric(oi["Household_Income_at_Age_35_rP_gP_p25"], errors="coerce")
oimap = {t: v for t, v in zip(oi["tract"], oi["v"]) if pd.notna(v) and 0 < v <= CAP}
dropped = sorted(v for t, v in zip(oi["tract"], oi["v"])
                 if pd.notna(v) and v > CAP and t[:5] in PREF)
print(f"OI 2010 tracts kept: {len(oimap):,}  (dropped {len(dropped)} 7-county >${CAP:,}: {[int(d) for d in dropped]})")

# ---- dominant 2010 parent per 2020 tract -----------------------------------
best = {}
with open(REL, encoding="utf-8-sig") as f:
    h = f.readline().rstrip("\n").split("|")
    i20, i10, ia = h.index("GEOID_TRACT_20"), h.index("GEOID_TRACT_10"), h.index("AREALAND_PART")
    for line in f:
        p = line.rstrip("\n").split("|")
        if p[i20][:5] not in PREF:
            continue
        try:
            a = float(p[ia])
        except ValueError:
            a = 0.0
        if p[i20] not in best or a > best[p[i20]][0]:
            best[p[i20]] = (a, p[i10])
parent = {g: v[1] for g, v in best.items()}


def oi_for(g20):
    if g20 in oimap:
        return oimap[g20], "direct"
    par = parent.get(g20)
    if par and par in oimap:
        return oimap[par], "xwalk"
    return None, "none"


# ---- assign to each 2020 tract, write GeoJSON ------------------------------
tr = gpd.read_file(os.path.join(DATA, "tracts.geojson"))[["geoid", "geometry"]]
feats, n = [], {"direct": 0, "xwalk": 0, "none": 0}
vals = []
for geoid, geom in zip(tr["geoid"], tr.geometry):
    v, how = oi_for(geoid)
    n[how] += 1
    if v is not None:
        vals.append(v)
    feats.append({"type": "Feature",
                  "properties": {"geoid": geoid, "oi": int(round(v)) if v is not None else None},
                  "geometry": mapping(geom)})

OUT = os.path.join(DATA, "oi_tracts.geojson")
json.dump({"type": "FeatureCollection", "name": "oi_tracts", "features": feats},
          open(OUT, "w"), allow_nan=False)

s = pd.Series(vals)
print(f"2020 tracts: {len(tr)}  ({n['direct']} direct, {n['xwalk']} via 2010 parent, {n['none']} no estimate)")
print(f"OI assigned: min ${s.min():,.0f}  p10 ${s.quantile(.1):,.0f}  median ${s.median():,.0f}  "
      f"p90 ${s.quantile(.9):,.0f}  max ${s.max():,.0f}")
for lo, hi in [(0, 25000), (25000, 30000), (30000, 35000), (35000, 42000), (42000, 50000), (50000, 9e9)]:
    print(f"   ${lo:,}-{hi:,}: {((s >= lo) & (s < hi)).sum()} tracts")
print(f"Wrote {OUT}  ({os.path.getsize(OUT)/1e6:.1f} MB)")
