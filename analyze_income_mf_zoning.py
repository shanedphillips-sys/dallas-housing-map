"""
Relationship between median household income and the share of land zoned
Multifamily, at two geographies: City of Dallas COUNCIL DISTRICTS and CENSUS TRACTS.

"MF-zoned share" = land in the base Multifamily zoning category (MF-1/2/3/4 etc.)
as a percent of all zoned land in the unit.

  IMPORTANT CAVEAT: this is the literal Multifamily zoning district only. Planned
  Development (PD), Mixed-Use (MU), and several Commercial districts also allow
  multifamily by right, and in Dallas most large MF is actually built on PD land
  (see analyze_mva_mf_permits.py) -- so this MF-district share UNDERSTATES where
  apartments are allowed. It matches the "Multifamily" zoning share reported in the
  council-district reports.

DISTRICTS: median income + Multifamily zoning % read from data/district_reports.json
  (precompute_district_reports.py: area-weighted ACS income; zoning % of zoned land).
TRACTS: Multifamily zoning % computed here by overlaying data/zoning.geojson on the
  City-of-Dallas census tracts; median income = ACS 2024 5-year B19013_001E.

Writes data/income_mf_zoning_districts.csv and data/income_mf_zoning_tracts.csv,
and prints the Pearson correlation at each level.
"""
import json
import os
import statistics as st

import geopandas as gpd
import pandas as pd
import requests
import shapely

WEB = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(WEB, "data")
KEY = os.environ.get("CENSUS_API_KEY", "86cf199069aa31e1593fc7012564f38af501b568")
COUNTIES = ["113", "085", "121"]  # Dallas, Collin, Denton (the city spans these)
SQM_PER_ACRE = 4046.86


def pearson(xs, ys):
    n = len(xs)
    mx, my = st.mean(xs), st.mean(ys)
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sx = sum((x - mx) ** 2 for x in xs) ** 0.5
    sy = sum((y - my) ** 2 for y in ys) ** 0.5
    return cov / (sx * sy) if sx and sy else float("nan")


# ---- 1. COUNCIL DISTRICTS (from the precomputed district reports) -----------
districts = json.load(open(os.path.join(DATA, "district_reports.json")))["districts"]
drows = []
for d in districts:
    mhi = d.get("mhi")
    mf = d.get("zoning_pct", {}).get("Multifamily", 0.0)
    if mhi:
        drows.append({"district": d["district"], "council_member": d.get("council_member", ""),
                      "mhi": int(mhi), "mf_zoned_pct": round(float(mf), 2)})
ddf = pd.DataFrame(drows).sort_values("mhi")
ddf.to_csv(os.path.join(DATA, "income_mf_zoning_districts.csv"), index=False)
r_d = pearson(ddf["mhi"].tolist(), ddf["mf_zoned_pct"].tolist())

# ---- 2. CENSUS TRACTS (compute MF-zoned share from the zoning layer) --------
tracts = gpd.read_file(os.path.join(DATA, "tracts.geojson"))[["geoid", "geometry"]].to_crs(3857)
city = gpd.read_file(os.path.join(DATA, "city_boundary.geojson")).to_crs(3857)
city_poly = shapely.make_valid(city.geometry.union_all())
tracts["geometry"] = shapely.make_valid(tracts.geometry.values)
ct = tracts[tracts.geometry.centroid.within(city_poly)][["geoid", "geometry"]].copy()

zoning = gpd.read_file(os.path.join(DATA, "zoning.geojson"))[["category", "geometry"]].to_crs(3857)
zoning["geometry"] = shapely.make_valid(zoning.geometry.values)
ov = gpd.overlay(zoning, ct, how="intersection")
ov["acres"] = ov.geometry.area / SQM_PER_ACRE
piv = ov.groupby(["geoid", "category"])["acres"].sum().unstack(fill_value=0.0)
piv["total"] = piv.sum(axis=1)
piv = piv[piv["total"] > 10].copy()  # drop tracts with negligible zoned land (water/airport)
piv["mf_zoned_pct"] = piv.get("Multifamily", 0.0) / piv["total"] * 100

mhi = {}
for c in COUNTIES:
    url = (f"https://api.census.gov/data/2024/acs/acs5?get=B19013_001E"
           f"&for=tract:*&in=state:48&in=county:{c}&key={KEY}")
    for row in requests.get(url, timeout=120).json()[1:]:
        try:
            v = float(row[0])
        except (TypeError, ValueError):
            v = None
        mhi[row[1] + row[2] + row[3]] = v if (v and v > 0) else None

trows = []
for geoid, row in piv.iterrows():
    inc = mhi.get(geoid)
    if inc:
        trows.append({"geoid": geoid, "mhi": int(inc),
                      "mf_zoned_pct": round(float(row["mf_zoned_pct"]), 2),
                      "zoned_acres": round(float(row["total"]), 1)})
tdf = pd.DataFrame(trows)
tdf.to_csv(os.path.join(DATA, "income_mf_zoning_tracts.csv"), index=False)
r_t = pearson(tdf["mhi"].tolist(), tdf["mf_zoned_pct"].tolist())

# ---- 3. Report -------------------------------------------------------------
print("Median household income vs. share of land zoned Multifamily (MF districts only)\n")
print(f"COUNCIL DISTRICTS (n={len(ddf)}): Pearson r = {r_d:+.3f}")
print(ddf[["district", "council_member", "mhi", "mf_zoned_pct"]].to_string(index=False))
print(f"\nCENSUS TRACTS (n={len(tdf)}): Pearson r = {r_t:+.3f}")
print(f"  MF-zoned %: median {tdf['mf_zoned_pct'].median():.1f}, mean {tdf['mf_zoned_pct'].mean():.1f}")
print(f"  income: median ${int(tdf['mhi'].median()):,}")
print("\nWrote data/income_mf_zoning_districts.csv and data/income_mf_zoning_tracts.csv")
