"""
Cross-check: building PERMITS (units permitted) vs APPRAISAL-DISTRICT parcels
(dwellings by year built), by units-in-structure, City of Dallas.

Permits: new sf/mf (+ mixed-use-coded-com) permits 2010-2022, binned by units/permit.
CAD: residential parcels binned by units-in-structure, counted as dwellings, for
several year_built ranges (to bracket the permit->completion lag). Units per parcel:
  Single Family / Townhouses / SFR Condo / Mobile Home -> 1
  Duplexes -> 2  (DCAD records total_units=1 for duplexes, so we override)
  MF 3-4 / 5-19 / 20-49 / 50+ / Apartments -> total_units (skip if 0/unknown)
"""
import geopandas as gpd
import numpy as np
import pandas as pd

ORDER = ["1 (single-family)", "2", "3–4", "5–9", "10–19", "20–49", "50+"]


def binof(u):
    if u <= 1: return ORDER[0]
    if u == 2: return ORDER[1]
    if u <= 4: return ORDER[2]
    if u <= 9: return ORDER[3]
    if u <= 19: return ORDER[4]
    if u <= 49: return ORDER[5]
    return ORDER[6]


# ---------- PERMITS 2010-2022 (City of Dallas, same classification as charts) ----
perm = gpd.read_file("data/permits.geojson")
new = perm[(perm["act"] == "new") & (perm["year"].between(2010, 2022))].copy()
new["units"] = new["units"].fillna(0); new["value"] = new["value"].fillna(0); new["date"] = new["date"].fillna("")
vpu = np.where(new["units"] > 0, new["value"] / new["units"].where(new["units"] > 0, 1), 0)
mfkeys = set(zip(new.loc[new["type"] == "mf", "addr"], new.loc[new["type"] == "mf", "date"]))
not_ov = np.array([ad not in mfkeys for ad in zip(new["addr"], new["date"])])
is_mu = (new["type"] == "com") & (new["units"] >= 2) & (vpu >= 100000) & not_ov
new["res"] = np.where(new["type"].isin(["sf", "mf"]), new["type"], np.where(is_mu, "mu", None))
res = new[new["res"].notna()].copy().to_crs(3857)
tr = gpd.read_file("data/tracts.geojson")[["geoid", "geometry"]].to_crs(3857)
city = gpd.read_file("data/city_boundary.geojson").to_crs(3857).geometry.union_all()
tr["incity"] = tr.geometry.centroid.within(city)
ct = tr[tr["incity"]][["geoid", "geometry"]]
pres = gpd.sjoin(res[["units", "geometry"]], ct, predicate="within", how="inner")
pu = pres["units"].astype(int)
pu = pu[pu >= 1]
permits_col = pu.map(binof).value_counts().reindex(ORDER).fillna(0).astype(int)
# weight by units (dwellings permitted), not permit count:
perm_units = pd.Series(pu.values, index=pu.map(binof)).groupby(level=0).sum().reindex(ORDER).fillna(0).astype(int)

# ---------- CAD parcels ----------
ONE = {"Single Family", "Townhouses", "SFR Condominiums", "Mobile Home / Mfg Housing", "Mobile Home"}
TWO = {"Duplexes"}
MFC = {"MF 3-4 Units", "MF 5-19 Units", "MF 20-49 Units", "MF 50+ Units", "MF Apartments (Unclassified)"}
parts = []
for q in ["nw", "ne", "sw", "se"]:
    parts.append(gpd.read_file(f"data/parcels_{q}.geojson", ignore_geometry=True)[["land_use_cat", "total_units", "year_built"]])
cad = pd.concat(parts, ignore_index=True)
cad["yb"] = pd.to_numeric(cad["year_built"], errors="coerce")
cad["tu"] = pd.to_numeric(cad["total_units"], errors="coerce").fillna(0)
cad["u"] = np.nan
cad.loc[cad["land_use_cat"].isin(ONE), "u"] = 1
cad.loc[cad["land_use_cat"].isin(TWO), "u"] = 2
mf = cad["land_use_cat"].isin(MFC) & (cad["tu"] > 0)
cad.loc[mf, "u"] = cad.loc[mf, "tu"]
print("condo accounts (SFR Condominiums) citywide:", int((cad["land_use_cat"] == "SFR Condominiums").sum()))
print("MF parcels with unknown unit count (tu=0), built 2010-2024:",
      int((cad["land_use_cat"].isin(MFC) & (cad["tu"] == 0) & cad["yb"].between(2010, 2024)).sum()))

RANGES = [(2010, 2022), (2010, 2023), (2010, 2024), (2011, 2022), (2011, 2023), (2011, 2024)]
cols = {"Permits 2010-22": perm_units}
res_cad = cad.dropna(subset=["u"]).copy()
res_cad["bin"] = res_cad["u"].map(binof)
for a, b in RANGES:
    sub = res_cad[res_cad["yb"].between(a, b)]
    cols[f"CAD {a}-{str(b)[2:]}"] = sub.groupby("bin")["u"].sum().reindex(ORDER).fillna(0).astype(int)

tbl = pd.DataFrame(cols).reindex(ORDER)
tbl.loc["TOTAL"] = tbl.sum()
pd.set_option("display.width", 200)
print("\nDwellings by units in structure — City of Dallas\n")
print(tbl.to_string())
