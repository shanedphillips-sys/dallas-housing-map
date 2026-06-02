"""
Merge Collin Central Appraisal District (Collin CAD) data into the parcel
GeoJSON files for COL-prefixed parcels.

Background
----------
The base parcel GeoJSON files (built by build_parcels_geojson.py) include
parcel geometries for the Collin County and Denton County portions of the
City of Dallas — but the value, year-built, building-area, and land-use
fields come only from DCAD, which covers Dallas County. As a result, the
~9,000 Collin County parcels (mostly in Council District 12) render as
"no data" on the value-per-acre, FAR, decade-built, and land-use maps.

This script fills those gaps by joining the Collin CAD certified appraisal
CSV (matched on propID) onto the COL- parcels in each quadrant GeoJSON.

Source
------
C:\\Users\\shane\\OneDrive\\Documents\\Domain Consulting\\Projects\\
  GDPC - Dallas Housing Report\\Collin_CAD_Appraisal_Data_-_2025_20260520.csv

Run after build_parcels_geojson.py. Idempotent: re-running just refreshes
the Collin-derived fields without touching DCAD parcels.
"""

import os
import json
import numpy as np
import pandas as pd
import geopandas as gpd

WEBMAP_DIR  = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(WEBMAP_DIR)
DATA_DIR    = os.path.join(WEBMAP_DIR, "data")
CAD_CSV     = os.path.join(
    PROJECT_DIR,
    "Collin_CAD_Appraisal_Data_-_2025_20260520.csv",
)

QUADRANTS = ["nw", "ne", "sw", "se"]


def log(msg):
    print(msg, flush=True)


# ---------------------------------------------------------------------------
# Load and clean Collin CAD
# ---------------------------------------------------------------------------
log(f"Reading Collin CAD: {CAD_CSV}")
cad = pd.read_csv(
    CAD_CSV,
    low_memory=False,
    usecols=[
        "propID", "propType", "situsCity",
        "situsBldgNum", "situsStreetPrefix", "situsStreetName",
        "situsStreetSuffix", "situsUnit",
        "currValMarket", "currValImprv", "currValLand",
        "imprvYearBuilt", "imprvMainArea", "imprvUnits",
        "imprvClassCd",
        "propCategoryCode",
        "landSizeAcres",
    ],
)
log(f"  Rows: {len(cad):,}")

# Filter to Real property (drop personal-property L* etc. that don't have
# parcel geometry of their own)
cad = cad[cad["propType"].astype(str).str.lower() == "real"].copy()
log(f"  Real property rows: {len(cad):,}")

# Value fields come in as strings with thousand-separator commas
for c in ["currValMarket", "currValImprv", "currValLand",
          "imprvMainArea", "imprvUnits", "landSizeAcres"]:
    if cad[c].dtype == object:
        cad[c] = cad[c].astype(str).str.replace(",", "", regex=False)
    cad[c] = pd.to_numeric(cad[c], errors="coerce")

cad["imprvYearBuilt"] = pd.to_numeric(cad["imprvYearBuilt"], errors="coerce")

# Build address string in the same style as DCAD: "<num> <dir> <name> <suffix>"
def _addr_part(s):
    s = "" if pd.isna(s) else str(s).strip()
    return "" if s.lower() in ("nan", "none") else s

def build_address(row):
    parts = [
        _addr_part(row.get("situsBldgNum")),
        _addr_part(row.get("situsStreetPrefix")),
        _addr_part(row.get("situsStreetName")),
        _addr_part(row.get("situsStreetSuffix")),
    ]
    addr = " ".join([p for p in parts if p])
    unit = _addr_part(row.get("situsUnit"))
    if unit:
        addr = f"{addr} {unit}".strip()
    return addr

cad["address"] = cad.apply(build_address, axis=1)

# propCategoryCode → land_use_cat (Texas PTAD category codes)
# Keep values consistent with existing DCAD-derived categories.
PTAD_TO_LAND_USE = {
    "A":  "Single Family",
    "B":  "MF Apartments (Unclassified)",  # subdivided below if imprvUnits present
    "C":  "Vacant - Single Family",
    "C1": "Vacant - Single Family",
    "C2": "Vacant - Commercial",
    "D":  "Open Space",
    "D1": "Open Space",
    "D2": "Open Space",
    "E":  "Other",
    "F":  "Commercial",
    "F1": "Commercial",
    "F2": "Industrial",
    "G":  "Other",
    "H":  "Other",
    "J":  "Other",
    "J1": "Other", "J2": "Other", "J3": "Other", "J4": "Other",
    "J5": "Other", "J6": "Other", "J7": "Other", "J8": "Other", "J9": "Other",
    "L":  "Commercial",
    "L1": "Commercial",
    "L2": "Industrial",
    "M":  "Mobile Home",
    "M1": "Mobile Home",
    "N":  "Other",
    "O":  "Single Family",   # residential inventory (builder spec)
    "S":  "Other",
    "X":  "Other",
}
cad["land_use_cat"] = cad["propCategoryCode"].astype(str).map(PTAD_TO_LAND_USE).fillna("Other")

# Subdivide multifamily by unit count where available
units = cad["imprvUnits"].fillna(0)
mf_mask = cad["propCategoryCode"].astype(str).str.startswith("B")
cad.loc[mf_mask & (units >= 3) & (units <= 4),   "land_use_cat"] = "MF 3-4 Units"
cad.loc[mf_mask & (units >= 5) & (units <= 19),  "land_use_cat"] = "MF 5-19 Units"
cad.loc[mf_mask & (units >= 20) & (units <= 49), "land_use_cat"] = "MF 20-49 Units"
cad.loc[mf_mask & (units >= 50),                 "land_use_cat"] = "MF 50+ Units"

# Build a propID-keyed lookup
cad_lookup = cad.set_index("propID")
log(f"  Distinct propIDs: {len(cad_lookup):,}")


# ---------------------------------------------------------------------------
# FAR binning (must match build_parcels_geojson.py)
# ---------------------------------------------------------------------------
def far_category(far):
    if pd.isna(far) or far <= 0:
        return "No Building"
    elif far < 0.25:    return "< 0.25"
    elif far < 0.5:     return "0.25 - 0.49"
    elif far < 1.0:     return "0.5 - 0.99"
    elif far < 1.5:     return "1.0 - 1.49"
    elif far <= 2.0:    return "1.5 - 2.0"
    elif far < 3.0:     return "2.0 - 2.9"
    elif far < 5.0:     return "3.0 - 4.9"
    elif far < 10.0:    return "5.0 - 9.9"
    else:               return "10+"


# ---------------------------------------------------------------------------
# Patch each quadrant GeoJSON
# ---------------------------------------------------------------------------
TOTAL_PATCHED = 0
TOTAL_UNMATCHED = 0

for q in QUADRANTS:
    path = os.path.join(DATA_DIR, f"parcels_{q}.geojson")
    log(f"\nProcessing {os.path.basename(path)} ...")
    gdf = gpd.read_file(path)

    is_col = gdf["account_num"].astype(str).str.startswith("COL-")
    n_col = int(is_col.sum())
    if n_col == 0:
        log("  No Collin parcels in this quadrant — skipping.")
        continue

    # Extract propID from "COL-0000001693830"
    pid = gdf.loc[is_col, "account_num"].str[4:]
    pid = pd.to_numeric(pid, errors="coerce").astype("Int64")

    matched_mask = pid.isin(cad_lookup.index)
    n_matched = int(matched_mask.sum())
    n_unmatched = n_col - n_matched
    TOTAL_PATCHED += n_matched
    TOTAL_UNMATCHED += n_unmatched
    log(f"  COL- parcels: {n_col:,}  matched in CAD: {n_matched:,}  unmatched: {n_unmatched:,}")

    # Look up CAD rows for matched parcels (in same order as gdf rows)
    pid_for_lookup = pid.where(matched_mask)
    cad_rows = cad_lookup.reindex(pid_for_lookup.values)

    # Assemble updates (one column at a time so we can keep DCAD parcels untouched)
    idx = gdf.index[is_col]

    gdf.loc[idx, "address"]      = cad_rows["address"].values
    gdf.loc[idx, "land_use_cat"] = cad_rows["land_use_cat"].fillna("Other").values
    # land_sptd_desc not present for Collin — reuse land_use_cat label so the
    # popup has something readable
    gdf.loc[idx, "land_sptd_desc"] = cad_rows["land_use_cat"].fillna("Other").values
    gdf.loc[idx, "bldg_class"]   = cad_rows["imprvClassCd"].fillna("").values

    # Building & year fields
    building_sf  = pd.to_numeric(cad_rows["imprvMainArea"], errors="coerce").fillna(0).values
    total_units  = pd.to_numeric(cad_rows["imprvUnits"], errors="coerce").fillna(0).values
    year_built   = pd.to_numeric(cad_rows["imprvYearBuilt"], errors="coerce").values

    gdf.loc[idx, "building_sf"] = building_sf
    gdf.loc[idx, "total_units"] = total_units
    gdf.loc[idx, "year_built"]  = year_built

    # FAR from existing area_feet (geometry-derived) ÷ Collin building sf
    area_feet = pd.to_numeric(gdf.loc[idx, "area_feet"], errors="coerce").fillna(0).values
    with np.errstate(divide="ignore", invalid="ignore"):
        far = np.where(area_feet > 0, building_sf / area_feet, np.nan)
    gdf.loc[idx, "floor_area_ratio"] = np.round(far, 2)
    gdf.loc[idx, "far_cat"] = [far_category(f) for f in far]

    # Value fields
    tot_val  = pd.to_numeric(cad_rows["currValMarket"], errors="coerce").fillna(0).values
    impr_val = pd.to_numeric(cad_rows["currValImprv"], errors="coerce").fillna(0).values
    land_val = pd.to_numeric(cad_rows["currValLand"], errors="coerce").fillna(0).values

    gdf.loc[idx, "tot_val"]  = tot_val
    gdf.loc[idx, "impr_val"] = impr_val
    gdf.loc[idx, "land_val"] = land_val

    with np.errstate(divide="ignore", invalid="ignore"):
        acres = np.where(area_feet > 0, area_feet / 43560.0, np.nan)
        vpa  = np.where(acres > 0, tot_val  / acres, 0)
        ipa  = np.where(acres > 0, impr_val / acres, 0)
        lpa  = np.where(acres > 0, land_val / acres, 0)

    gdf.loc[idx, "value_per_acre"] = np.nan_to_num(vpa, nan=0.0).round().astype(np.int64)
    gdf.loc[idx, "impr_per_acre"]  = np.nan_to_num(ipa, nan=0.0).round().astype(np.int64)
    gdf.loc[idx, "land_per_acre"]  = np.nan_to_num(lpa, nan=0.0).round().astype(np.int64)

    # ----- write back ------------------------------------------------------
    log(f"  Writing {path} ...")
    # GeoPandas to_file with driver=GeoJSON works but is slow for big files.
    # We can dump via the lower-level interface for speed parity with build script.
    gdf.to_file(path, driver="GeoJSON")
    log(f"  wrote {len(gdf):,} features")


log("\n=== Summary ===")
log(f"Total COL- parcels patched: {TOTAL_PATCHED:,}")
log(f"Total COL- parcels unmatched (no CAD record): {TOTAL_UNMATCHED:,}")
log("Done.")
