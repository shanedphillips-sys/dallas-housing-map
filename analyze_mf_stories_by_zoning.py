"""
DCAD multifamily building STORIES by multifamily / mixed-use zoning district,
UNIT-WEIGHTED (each building's stories weighted by its unit count, so big apartment
projects aren't outvoted by the many small MF buildings).

DCAD only (Dallas County). Stories per account = the TALLEST building from
COM_DETAIL.NUM_STORIES (commercial, numeric, capped at 80 to drop bad entries) and
RES_DETAIL.NUM_STORIES_DESC (residential, text -> numeric). Multifamily buildings =
parcels with an MF land-use category (Duplexes + MF 3-4/5-19/20-49/50+/Apartments).
Zoning district = parcel centroid in the base district (zone_norm), category
Multifamily or Mixed-Use.

Per district: unit-weighted p10/25/50/75/90 of stories, plus total MF parcels,
total MF units, total MF land (acres), and how many parcels carry a stories value.
Writes data/mf_stories_by_zoning.csv.
"""
import os

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

WEB = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(WEB, "data")
DCAD = (r"C:\Users\shane\OneDrive\Documents\Domain Consulting\Projects"
        r"\GDPC - Dallas Housing Report\GDPC Claude Stuff\DCAD2025_CERTIFIED")
YR = "2025"
MF_CATS = {"Duplexes", "MF 3-4 Units", "MF 5-19 Units", "MF 20-49 Units",
           "MF 50+ Units", "MF Apartments (Unclassified)"}
STORY_TEXT = {"ONE STORY": 1, "ONE AND ONE HALF STORIES": 1.5, "TWO STORIES": 2,
              "TWO AND ONE HALF STORIES": 2.5, "THREE STORIES": 3,
              "THREE AND ONE HALF STORIES": 3.5, "FOUR STORIES": 4}
STORY_CAP = 80
YEAR_MIN = 2010   # only projects built this year or later; set to None for all years


def num(s):
    return pd.to_numeric(s, errors="coerce")


def wpct(stories, units, q):
    """Unit-weighted percentile of stories (each building weighted by its units)."""
    m = (~np.isnan(stories)) & (units > 0)
    v, w = stories[m], units[m]
    if len(v) == 0:
        return np.nan
    o = np.argsort(v, kind="stable")
    v, w = v[o], w[o]
    cw = np.cumsum(w)
    idx = int(np.searchsorted(cw, q / 100.0 * cw[-1], side="left"))
    return float(v[min(idx, len(v) - 1)])


# ---- stories per DCAD account (tallest building) ----------------------------
com = pd.read_csv(f"{DCAD}/COM_DETAIL.CSV", dtype=str, encoding="latin-1",
                  usecols=["ACCOUNT_NUM", "APPRAISAL_YR", "NUM_STORIES"])
com = com[com.APPRAISAL_YR == YR].copy()
com["st"] = num(com.NUM_STORIES)
com.loc[(com.st <= 0) | (com.st > STORY_CAP), "st"] = np.nan
res = pd.read_csv(f"{DCAD}/RES_DETAIL.CSV", dtype=str, encoding="latin-1",
                  usecols=["ACCOUNT_NUM", "APPRAISAL_YR", "NUM_STORIES_DESC"])
res = res[res.APPRAISAL_YR == YR].copy()
res["st"] = res.NUM_STORIES_DESC.str.strip().str.upper().map(STORY_TEXT)
stories = (pd.concat([com[["ACCOUNT_NUM", "st"]], res[["ACCOUNT_NUM", "st"]]])
           .dropna(subset=["st"]).groupby("ACCOUNT_NUM")["st"].max())

dcad_accts = set(pd.read_csv(f"{DCAD}/ACCOUNT_APPRL_YEAR.CSV", dtype=str, encoding="latin-1",
                             usecols=["ACCOUNT_NUM", "APPRAISAL_YR"])
                 .query("APPRAISAL_YR == @YR").ACCOUNT_NUM)

# ---- multifamily parcels (DCAD only) ----------------------------------------
p = pd.concat([gpd.read_file(f"{DATA}/parcels_{q}.geojson")
               [["account_num", "land_use_cat", "total_units", "area_feet", "year_built", "geometry"]]
               for q in ["nw", "ne", "sw", "se"]], ignore_index=True)
p = gpd.GeoDataFrame(p, crs="EPSG:4326")
p = p[p.land_use_cat.isin(MF_CATS) & p.account_num.isin(dcad_accts)].copy()
p["total_units"] = num(p.total_units).fillna(0)
p["area_feet"] = num(p.area_feet).fillna(0)
p["year_built"] = num(p.year_built)
if YEAR_MIN:
    p = p[p.year_built >= YEAR_MIN].copy()
p["stories"] = p.account_num.map(stories)

# ---- spatial join to MF/MU zoning districts (base zone_norm) ----------------
z = gpd.read_file(f"{DATA}/zoning.geojson")[["zone_norm", "category", "geometry"]].to_crs(3857)
z["geometry"] = shapely.make_valid(z.geometry.values)
z = z[z.category.isin(["Multifamily", "Mixed-Use"])]
pc = p.to_crs(3857)
pc["geometry"] = shapely.centroid(shapely.make_valid(pc.geometry.values))
j = gpd.sjoin(pc, z[["zone_norm", "geometry"]], predicate="within", how="inner")

# ---- per-district unit-weighted percentiles + totals ------------------------
rows = []
for zn, g in j.groupby("zone_norm"):
    st = g.stories.values.astype(float)
    u = g.total_units.values.astype(float)
    rows.append({"zoning_district": zn, "parcels": len(g), "units": int(u.sum()),
                 "land_acres": round(g.area_feet.sum() / 43560.0, 1),
                 "parcels_w_stories": int((~np.isnan(st)).sum()),
                 "p10": wpct(st, u, 10), "p25": wpct(st, u, 25), "p50": wpct(st, u, 50),
                 "p75": wpct(st, u, 75), "p90": wpct(st, u, 90)})
out = pd.DataFrame(rows).sort_values("units", ascending=False).reset_index(drop=True)
suffix = f"_{YEAR_MIN}plus" if YEAR_MIN else ""
out.to_csv(f"{DATA}/mf_stories_by_zoning{suffix}.csv", index=False)
pd.set_option("display.width", 220)
yr_note = f", year built >= {YEAR_MIN}" if YEAR_MIN else ""
print(f"Unit-weighted MF building stories by MF/MU zoning district (DCAD only{yr_note})\n")
print(out.to_string(index=False))
