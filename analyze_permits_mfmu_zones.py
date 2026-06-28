"""
Units permitted 2015-2024 in Multifamily/Mixed-use + Townhouse/Cluster zoning, broken
out by individual zoning district (zone_dist) x project size (1, 2-9, 10-49, 50+), with
the land area (sq mi) each district covers in the city.

Districts = zoning `category` in {Multifamily, Mixed-Use, Community Area,
Townhouse/Cluster (= TH-1(A), TH-2(A), TH-3(A), CH)}.
Shares are % of ALL permitted units citywide. sq_mi = district land area in the city
(clipped to the boundary), shown for every district even if it had zero permits
2015-2024.

Writes data/permits_mfmu_zones_units.csv and ..._pct.csv; prints both tables.
"""
import os

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

WEB = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(WEB, "data")
CRS = "EPSG:2276"            # US ft -> correct areas
SQMI = 27_878_400.0         # sq ft per sq mile
MFMU_CATS = {"Multifamily", "Mixed-Use", "Community Area", "Townhouse / Cluster"}
SIZE_LABELS = ["1", "2-9", "10-49", "50+"]
SIZE_BINS = [0.5, 1.5, 9.5, 49.5, np.inf]

zoning = gpd.read_file(os.path.join(DATA, "zoning.geojson"))[["zone_dist", "category", "geometry"]].to_crs(CRS)
zoning["geometry"] = shapely.make_valid(zoning.geometry.values)
zoning["zone_dist"] = zoning["zone_dist"].astype(str).str.strip()
city = gpd.read_file(os.path.join(DATA, "city_boundary.geojson")).to_crs(CRS)
cgeom = shapely.make_valid(city.geometry.union_all())

# land area (sq mi) per MF/MU district, clipped to the city
zclip = gpd.clip(zoning, cgeom)
zclip["sqmi"] = zclip.geometry.area / SQMI
mf_area = zclip[zclip["category"].isin(MFMU_CATS)].groupby("zone_dist")["sqmi"].sum()

# permits -> zone_dist; grand total = ALL permitted units citywide (share denominator)
p = gpd.read_file(os.path.join(DATA, "permits.geojson")).to_crs(CRS)
p = p[p["year"].between(2015, 2024) & (p["units"] >= 1)].copy()
j = gpd.sjoin(p, zoning, predicate="within", how="left")
j = j[~j.index.duplicated(keep="first")]
grand = float(j["units"].sum())

mf = j[j["category"].isin(MFMU_CATS)].copy()
mf["size"] = pd.cut(mf["units"], bins=SIZE_BINS, labels=SIZE_LABELS)
pivot = mf.pivot_table(index="zone_dist", columns="size", values="units",
                       aggfunc="sum", fill_value=0, observed=False)

all_mfmu = sorted(set(mf_area.index) | set(mf["zone_dist"].dropna()))
units = pivot.reindex(index=all_mfmu, columns=SIZE_LABELS, fill_value=0).astype(int)
units["Total"] = units.sum(axis=1)
units.insert(0, "sq_mi", mf_area.reindex(all_mfmu).fillna(0.0).values)  # unrounded for the ratio
units = units.sort_values("Total", ascending=False)
units.loc["Total"] = units.sum()
# units permitted per sq mi of district land (column after Total)
upm = (units["Total"] / units["sq_mi"]).replace([np.inf, -np.inf], np.nan)
units["units_per_sqmi"] = upm.round(0).fillna(0).astype(int)
for c in SIZE_LABELS + ["Total"]:
    units[c] = units[c].round().astype(int)
units["sq_mi"] = units["sq_mi"].round(2)

share = units.copy().astype(float)
for c in SIZE_LABELS + ["Total"]:
    share[c] = (units[c] / grand * 100).round(2)
share["sq_mi"] = units["sq_mi"]                     # land area, not a share
share["units_per_sqmi"] = units["units_per_sqmi"]  # density, not a share

pd.set_option("display.width", 200)
print(f"All permitted units citywide 2015-2024 (units>=1): {int(grand):,}")
print(f"MF/MU + Townhouse/Cluster zones: {units.loc['Total','Total']:,} units across "
      f"{units.loc['Total','sq_mi']:.2f} sq mi\n")
print("=== UNITS by MF/MU + Townhouse/Cluster district x project size ===")
print(units.to_string())
print("\n=== SHARE of all permitted units citywide, % (sq_mi = land area) ===")
print(share.to_string())
units.to_csv(os.path.join(DATA, "permits_mfmu_zones_units.csv"))
share.to_csv(os.path.join(DATA, "permits_mfmu_zones_pct.csv"))
print("\nWrote data/permits_mfmu_zones_units.csv and ..._pct.csv")
