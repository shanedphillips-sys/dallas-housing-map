"""
Aggregate parcel value by land-use category for the "Value by Land Use"
analysis panel.

Reads all four parcel quadrant GeoJSONs and emits a tiny JSON file the
web map loads on demand.

Output schema (data/land_use_value_summary.json):
{
  "totals": {
    "parcels": <int>, "acres": <float>,
    "tot_val": <int>, "impr_val": <int>, "land_val": <int>
  },
  "by_land_use": [
    {
      "land_use": "Single Family",
      "parcels": ..., "acres": ...,
      "tot_val": ..., "impr_val": ..., "land_val": ...
    },
    ...
  ]
}

Categories appear in descending order of total value, so the most
important ones surface at the top of the panel.
"""

import json
import os
import pandas as pd
import geopandas as gpd

WEBMAP_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR   = os.path.join(WEBMAP_DIR, "data")
OUT_PATH   = os.path.join(DATA_DIR, "land_use_value_summary.json")

QUADRANTS = ["nw", "ne", "sw", "se"]
MIN_AREA_SQFT = 100   # match the webmap filter for placeholders / TIF rows


def log(msg): print(msg, flush=True)


log("Reading parcel quadrants...")
parts = []
for q in QUADRANTS:
    p = os.path.join(DATA_DIR, f"parcels_{q}.geojson")
    g = gpd.read_file(p)
    parts.append(g)
    log(f"  {q}: {len(g):,} parcels")

g = pd.concat(parts, ignore_index=True)
log(f"  combined: {len(g):,} parcels")

# Drop tiny placeholder / TIF parcels — these distort per-acre numbers and
# the webmap doesn't render them anyway.
before = len(g)
g = g[pd.to_numeric(g["area_feet"], errors="coerce").fillna(0) >= MIN_AREA_SQFT].copy()
log(f"  after area >= {MIN_AREA_SQFT} sq ft: {len(g):,} (dropped {before-len(g):,})")

# Coerce numerics
for c in ["area_feet", "tot_val", "impr_val", "land_val"]:
    g[c] = pd.to_numeric(g[c], errors="coerce").fillna(0)

g["acres"]    = g["area_feet"] / 43560.0
g["land_use"] = g["land_use_cat"].fillna("Other").astype(str)


# Totals across the whole city
totals = {
    "parcels":  int(len(g)),
    "acres":    round(float(g["acres"].sum()), 1),
    "tot_val":  int(round(g["tot_val"].sum())),
    "impr_val": int(round(g["impr_val"].sum())),
    "land_val": int(round(g["land_val"].sum())),
}
log(f"\nCitywide totals:")
log(f"  parcels:        {totals['parcels']:>14,}")
log(f"  acres:          {totals['acres']:>14,.1f}")
log(f"  total value:    ${totals['tot_val']:>14,}")
log(f"  improvement:    ${totals['impr_val']:>14,}")
log(f"  taxable land:   ${totals['land_val']:>14,}")

# Per-land-use breakdown
agg = (g.groupby("land_use")
        .agg(parcels=("land_use", "count"),
             acres=("acres", "sum"),
             tot_val=("tot_val", "sum"),
             impr_val=("impr_val", "sum"),
             land_val=("land_val", "sum"))
        .reset_index()
        .sort_values("tot_val", ascending=False))

by_land_use = []
for _, row in agg.iterrows():
    by_land_use.append({
        "land_use": row["land_use"],
        "parcels":  int(row["parcels"]),
        "acres":    round(float(row["acres"]), 1),
        "tot_val":  int(round(row["tot_val"])),
        "impr_val": int(round(row["impr_val"])),
        "land_val": int(round(row["land_val"])),
    })

log("\nBy land use (top 8 by total value):")
log(f"  {'category':<32} {'parcels':>10} {'acres':>10} {'tot_val':>16}")
for r in by_land_use[:8]:
    pct = 100 * r["tot_val"] / totals["tot_val"]
    log(f"  {r['land_use']:<32} {r['parcels']:>10,} {r['acres']:>10,.0f} ${r['tot_val']:>14,}  ({pct:>5.1f}%)")

with open(OUT_PATH, "w") as f:
    json.dump({"totals": totals, "by_land_use": by_land_use}, f, indent=2)
log(f"\nWrote {OUT_PATH}")
