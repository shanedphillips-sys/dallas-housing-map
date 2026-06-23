"""
Tract-level analysis (City of Dallas): median household income vs. the
single-family share of land zoned to allow housing.

Agricultural (zone_norm 'A') is EXCLUDED entirely (it is parked in the
"Single-Family" category but is fringe holding-zone land, not neighborhood
housing, and it badly inflated SF share in low-density edge tracts).

Denominator = land zoned to allow housing. Two versions are computed:
  core  = Single-Family + Multifamily + Townhouse/Cluster + Mixed-Use + Central
          Area (CA). These are the districts whose purpose includes housing.
  broad = core + Commercial. Dallas permits multifamily by right in its retail
          and office districts (CR, RR, CS, NO, LO, GO, MO, NS), so this counts
          all land where housing is allowed. Reported as a sensitivity.

sf_share   = Single-Family / core            (the chart's y-axis)
mf_share   = Multifamily / core
mf_allow   = (Multifamily + Mixed-Use + CA) / core   ("allows apartments")
Dallas tracts = centroid inside the city boundary, with >5 core housing acres.
Income = ACS 2024 5-year B19013_001E (median household income).

Writes data/income_zoning.json and prints the correlations.
"""
import json
import os
import statistics as st

import geopandas as gpd
import requests

WEB = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(WEB, "data")
KEY = os.environ.get("CENSUS_API_KEY", "86cf199069aa31e1593fc7012564f38af501b568")
COUNTIES = ["113", "085", "121", "439", "139", "257", "397"]

CORE_CATS = ["Single-Family", "Multifamily", "Townhouse / Cluster",
             "Mixed-Use", "Community Area"]   # Community Area == Central Area (CA-1/2)
KEEP = CORE_CATS + ["Commercial"]             # Commercial only feeds the broad denominator

# ---- 1. Geometry: city tracts + housing-zoning area per tract --------------
tracts = gpd.read_file(os.path.join(DATA, "tracts.geojson"))[["geoid", "geometry"]].to_crs(3857)
city = gpd.read_file(os.path.join(DATA, "city_boundary.geojson")).to_crs(3857)
city_poly = city.geometry.union_all()
tracts["incity"] = tracts.geometry.centroid.within(city_poly)
city_tracts = tracts[tracts["incity"]][["geoid", "geometry"]].copy()
print(f"city tracts (centroid in boundary): {len(city_tracts)}")

zoning = gpd.read_file(os.path.join(DATA, "zoning.geojson"))[["category", "zone_norm", "geometry"]].to_crs(3857)
ag = zoning[zoning["zone_norm"] == "A"]
print(f"excluding Agricultural (zone_norm 'A'): {len(ag)} polys, "
      f"{(ag.to_crs(3857).geometry.area.sum()/4046.86):,.0f} ac citywide")
z = zoning[(zoning["zone_norm"] != "A") & (zoning["category"].isin(KEEP))].copy()

ov = gpd.overlay(z[["category", "geometry"]], city_tracts, how="intersection")
ov["acres"] = ov.geometry.area / 4046.86
piv = ov.groupby(["geoid", "category"])["acres"].sum().unstack(fill_value=0.0)
for c in KEEP:
    if c not in piv:
        piv[c] = 0.0

piv["core"] = piv[CORE_CATS].sum(axis=1)
piv["broad"] = piv["core"] + piv["Commercial"]
piv = piv[piv["core"] > 5].copy()
piv["sf_share"] = piv["Single-Family"] / piv["core"]
piv["sf_share_broad"] = piv["Single-Family"] / piv["broad"]
piv["mf_share"] = piv["Multifamily"] / piv["core"]
piv["mf_allow_share"] = (piv["Multifamily"] + piv["Mixed-Use"] + piv["Community Area"]) / piv["core"]
print(f"tracts with >5 core housing acres: {len(piv)}")

# ---- 2. ACS median household income (2024 5-yr) ----------------------------
mhi = {}
for c in COUNTIES:
    url = (f"https://api.census.gov/data/2024/acs/acs5?get=B19013_001E"
           f"&for=tract:*&in=state:48&in=county:{c}&key={KEY}")
    j = requests.get(url, timeout=120).json()
    for row in j[1:]:
        try:
            v = float(row[0])
        except (TypeError, ValueError):
            v = None
        mhi[row[1] + row[2] + row[3]] = v if (v is not None and v > 0) else None

# ---- 3. Join, write, summarize --------------------------------------------
rows = []
for geoid, r in piv.iterrows():
    inc = mhi.get(geoid)
    if inc is None:
        continue
    rows.append({"geoid": geoid, "mhi": int(inc),
                 "sf_share": round(float(r["sf_share"]), 4),
                 "sf_share_broad": round(float(r["sf_share_broad"]), 4),
                 "mf_share": round(float(r["mf_share"]), 4),
                 "mf_allow_share": round(float(r["mf_allow_share"]), 4),
                 "res_acres": round(float(r["core"]), 1)})

with open(os.path.join(DATA, "income_zoning.json"), "w") as f:
    json.dump(rows, f)


def pearson(xs, ys):
    mx, my = st.mean(xs), st.mean(ys)
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sx = sum((x - mx) ** 2 for x in xs) ** 0.5
    sy = sum((y - my) ** 2 for y in ys) ** 0.5
    return cov / (sx * sy) if sx and sy else float("nan")


inc = [r["mhi"] for r in rows]
print(f"\nn = {len(rows)} Dallas tracts with income + housing zoning")
print(f"  median household income: ${st.median(inc):,.0f}  (range ${min(inc):,}-${max(inc):,})")
print(f"  SF share (core):  median {st.median(r['sf_share'] for r in rows):.2f}")
print(f"  SF share (broad): median {st.median(r['sf_share_broad'] for r in rows):.2f}")
print(f"  corr(income, SF share, core)  = {pearson(inc, [r['sf_share'] for r in rows]):+.3f}")
print(f"  corr(income, SF share, broad) = {pearson(inc, [r['sf_share_broad'] for r in rows]):+.3f}")
print(f"  corr(income, MF share, core)  = {pearson(inc, [r['mf_share'] for r in rows]):+.3f}")
print("Wrote data/income_zoning.json")
