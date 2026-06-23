"""
Tract-level analysis (City of Dallas): median household income vs. new dwelling
units permitted 2015-2024.

Units counted = NEW construction (act == 'new'), years 2015-2024:
  - all 'sf' and 'mf' permits (units field = dwelling units), PLUS
  - 'com' permits that are really housing miscoded as commercial: units >= 2 and
    construction cost >= $100k/unit (the median real mf permit), and NOT sharing
    an address+date with an mf permit (double-count guard). The cheap 'com'
    "units" ($0-$40k/unit) are commercial suite-counts, not dwellings, and are
    excluded. This recovers ~1,176 mixed-use units (~2.3%).

Audit (build_permits review): zero duplicate rows (exact or coord-ignoring);
multi-row same-address mf permits are genuine separate buildings (distinct unit
counts) and are correctly summed.

Every City-of-Dallas tract (centroid in boundary) with an income value is kept;
no-permit tracts count as 0. Income = ACS 2024 5-year B19013_001E.
Writes data/permits_income.json {geoid, mhi, units, sf_units, mf_units, mu_units}.
"""
import json
import os
import statistics as st

import geopandas as gpd
import numpy as np
import requests

WEB = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(WEB, "data")
KEY = os.environ.get("CENSUS_API_KEY", "86cf199069aa31e1593fc7012564f38af501b568")
COUNTIES = ["113", "085", "121", "439", "139", "257", "397"]
COM_RES_VPU = 100_000   # $/unit floor for treating a 'com' permit as housing

# ---- 1. City-of-Dallas tracts (same universe as the income chart) ----------
tracts = gpd.read_file(os.path.join(DATA, "tracts.geojson"))[["geoid", "geometry"]].to_crs(3857)
city = gpd.read_file(os.path.join(DATA, "city_boundary.geojson")).to_crs(3857)
city_poly = city.geometry.union_all()
tracts["incity"] = tracts.geometry.centroid.within(city_poly)
city_tracts = tracts[tracts["incity"]][["geoid", "geometry"]].copy()
print(f"city tracts (centroid in boundary): {len(city_tracts)}")

# ---- 2. Classify new 2015-2024 permits as residential, sum units per tract -
perm = gpd.read_file(os.path.join(DATA, "permits.geojson"))
new = perm[(perm["act"] == "new") & (perm["year"].between(2015, 2024))].copy()
new["units"] = new["units"].fillna(0)
new["value"] = new["value"].fillna(0)
new["date"] = new["date"].fillna("")
vpu = np.where(new["units"] > 0, new["value"] / new["units"].where(new["units"] > 0, 1), 0)

mfkeys = set(zip(new.loc[new["type"] == "mf", "addr"], new.loc[new["type"] == "mf", "date"]))
not_mf_overlap = np.array([ad not in mfkeys for ad in zip(new["addr"], new["date"])])
is_mu = (new["type"] == "com") & (new["units"] >= 2) & (vpu >= COM_RES_VPU) & not_mf_overlap
new["res"] = np.where(new["type"].isin(["sf", "mf"]), new["type"],
                      np.where(is_mu, "mu", None))
res = new[new["res"].notna()].copy().to_crs(3857)
print(f"residential permits 2015-2024: {len(res):,}  "
      f"(sf {(res.res=='sf').sum():,}, mf {(res.res=='mf').sum():,}, "
      f"com-as-housing {(res.res=='mu').sum():,})  {int(res['units'].sum()):,} units")

j = gpd.sjoin(res[["units", "res", "geometry"]], city_tracts, predicate="within", how="inner")
for t in ("sf", "mf", "mu"):
    j[f"u_{t}"] = j["units"].where(j["res"] == t, 0)
agg = j.groupby("geoid")[["units", "u_sf", "u_mf", "u_mu"]].sum()
ct = city_tracts[["geoid"]].merge(agg, on="geoid", how="left").fillna(0.0)

# ---- 3. ACS median household income (2024 5-yr) ----------------------------
mhi = {}
for c in COUNTIES:
    url = (f"https://api.census.gov/data/2024/acs/acs5?get=B19013_001E"
           f"&for=tract:*&in=state:48&in=county:{c}&key={KEY}")
    jr = requests.get(url, timeout=120).json()
    for row in jr[1:]:
        try:
            v = float(row[0])
        except (TypeError, ValueError):
            v = None
        mhi[row[1] + row[2] + row[3]] = v if (v is not None and v > 0) else None

# ---- 4. Join, write, summarize --------------------------------------------
rows = []
for _, r in ct.iterrows():
    inc = mhi.get(r["geoid"])
    if inc is None:
        continue
    rows.append({"geoid": r["geoid"], "mhi": int(inc), "units": int(r["units"]),
                 "sf_units": int(r["u_sf"]), "mf_units": int(r["u_mf"]),
                 "mu_units": int(r["u_mu"])})

with open(os.path.join(DATA, "permits_income.json"), "w") as f:
    json.dump(rows, f)


def pearson(xs, ys):
    mx, my = st.mean(xs), st.mean(ys)
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sx = sum((x - mx) ** 2 for x in xs) ** 0.5
    sy = sum((y - my) ** 2 for y in ys) ** 0.5
    return cov / (sx * sy) if sx and sy else float("nan")


inc = [r["mhi"] for r in rows]
u = [r["units"] for r in rows]
print(f"\nn = {len(rows)} Dallas tracts  ({sum(1 for r in rows if r['units']>0)} with >0 units)")
print(f"  units: total {sum(u):,}  (sf {sum(r['sf_units'] for r in rows):,}, "
      f"mf {sum(r['mf_units'] for r in rows):,}, com-as-housing {sum(r['mu_units'] for r in rows):,})")
print(f"  median {st.median(u):.0f}  max {max(u):,}")
print(f"  corr(income, units) = {pearson(inc, u):+.3f}")
print("Wrote data/permits_income.json")
