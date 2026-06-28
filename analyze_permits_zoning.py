"""
Share of dwelling units permitted 2015-2024 by base-zoning category and project size.

Permit points (data/permits.geojson, units>=1, 2015-2024) are spatially joined to
base zoning (data/zoning.geojson); each permit's zoning category is collapsed to
PD / Single-family / Multifamily-Mixed-use / Commercial, and its units are binned by
project size (1, 2-9, 10-49, 50+). Cells = sum of dwelling units.

Category collapse (from the zoning `category` field):
  PD                    = Planned Development
  Single-family         = Single-Family + Townhouse/Cluster + Conservation District
  Multifamily/Mixed-use = Multifamily + Mixed-Use + Community Area
  Other (catch-all)     = Commercial + Industrial + Other + any unmatched (everything else)

Zoning is CURRENT base zoning (not zoning at permit time). Writes
data/permits_zoning_share_units.csv and ..._pct.csv; prints the tables.
"""
import os

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

WEB = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(WEB, "data")

CAT_MAP = {
    "Planned Development": "PD",
    "Single-Family": "Single-family",
    "Townhouse / Cluster": "Single-family",
    "Conservation District": "Single-family",
    "Multifamily": "Multifamily/Mixed-use",
    "Mixed-Use": "Multifamily/Mixed-use",
    "Community Area": "Multifamily/Mixed-use",
    "Commercial": "Other",
    "Industrial": "Other",
    "Other": "Other",
}
CAT_ORDER = ["PD", "Single-family", "Multifamily/Mixed-use", "Other"]
SIZE_LABELS = ["1", "2-9", "10-49", "50+"]
SIZE_BINS = [0.5, 1.5, 9.5, 49.5, np.inf]

zoning = gpd.read_file(os.path.join(DATA, "zoning.geojson"))[["category", "geometry"]].to_crs("EPSG:3857")
zoning["geometry"] = shapely.make_valid(zoning.geometry.values)
zoning["zcat"] = zoning["category"].map(CAT_MAP).fillna("Commercial")

p = gpd.read_file(os.path.join(DATA, "permits.geojson")).to_crs("EPSG:3857")
p = p[p["year"].between(2015, 2024) & (p["units"] >= 1)].copy()
n_permits = len(p)
j = gpd.sjoin(p, zoning[["zcat", "geometry"]], predicate="within", how="left")
j = j[~j.index.duplicated(keep="first")]
unmatched = int(j["zcat"].isna().sum())
j["zcat"] = j["zcat"].fillna("Other")   # catch-all also absorbs any unmatched permits
j["size"] = pd.cut(j["units"], bins=SIZE_BINS, labels=SIZE_LABELS)

rows = [c for c in CAT_ORDER if c in set(j["zcat"])]
units = (j.pivot_table(index="zcat", columns="size", values="units", aggfunc="sum",
                       fill_value=0, observed=False)
         .reindex(index=rows, columns=SIZE_LABELS, fill_value=0))
units["Total"] = units.sum(axis=1)
units.loc["Total"] = units.sum(axis=0)
grand = units.loc["Total", "Total"]
share = (units / grand * 100).round(2)

pd.set_option("display.width", 200)
print(f"Dwelling units permitted 2015-2024 (units>=1): {int(grand):,} units / {n_permits:,} permits"
      f"  ({unmatched} permits unmatched to a zoning polygon)\n")
print("=== UNITS by zoning category x project size ===")
print(units.astype(int).to_string())
print("\n=== SHARE of all permitted units, % ===")
print(share.to_string())
units.astype(int).to_csv(os.path.join(DATA, "permits_zoning_share_units.csv"))
share.to_csv(os.path.join(DATA, "permits_zoning_share_pct.csv"))
print("\nWrote data/permits_zoning_share_units.csv and ..._pct.csv")
