"""
Merge Denton CAD data into the parcel GeoJSON files for DEN-prefixed parcels.

Source slim file: data/denton_dallas_slim.json (produced by extract_denton_dallas.py).
Join key: pID  <-->  numeric portion of DEN-XXXXXXXXXXXXXX in account_num.

Parallel to merge_collin_cad.py.
"""

import os, json
import numpy as np
import pandas as pd
import geopandas as gpd

WEBMAP_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR   = os.path.join(WEBMAP_DIR, "data")
SLIM_PATH  = os.path.join(DATA_DIR, "denton_dallas_slim.json")
QUADRANTS  = ["nw", "ne", "sw", "se"]


def log(msg): print(msg, flush=True)


# ---------------------------------------------------------------------------
# Load slim Denton Dallas-city records
# ---------------------------------------------------------------------------
log(f"Reading {SLIM_PATH}")
with open(SLIM_PATH, "r", encoding="utf-8") as f:
    den = pd.DataFrame(json.load(f))
log(f"  Rows: {len(den):,}")

# Numeric coercion
for c in ["valMarket", "valLand", "valStructure", "valImprHS", "valImprNHS",
          "imprvActualYearBuilt", "imprvMainArea", "imprvUnits",
          "landSizeAcres", "landSizeSqft"]:
    den[c] = pd.to_numeric(den[c], errors="coerce")

# Address builder
def _addr_part(s):
    s = "" if pd.isna(s) else str(s).strip()
    return "" if s.lower() in ("nan", "none") else s

def build_address(row):
    parts = [
        _addr_part(row.get("streetNum")),
        _addr_part(row.get("streetPrefix")),
        _addr_part(row.get("streetName")),
        _addr_part(row.get("streetSuffix")),
    ]
    return " ".join(p for p in parts if p)

den["address"] = den.apply(build_address, axis=1)


# stateCd -> land_use_cat. Texas PTAD codes.
def land_use_from_state_cd(code, units):
    code = (code or "").upper().strip()
    if not code: return "Other"
    if code in ("A1", "A2", "A3", "A4", "A5", "O", "A"):
        return "Single Family"
    if code == "B1":   # multifamily 3+ units
        if units >= 50:  return "MF 50+ Units"
        if units >= 20:  return "MF 20-49 Units"
        if units >= 5:   return "MF 5-19 Units"
        if units >= 3:   return "MF 3-4 Units"
        return "MF Apartments (Unclassified)"
    if code == "B2":   return "Duplexes"
    if code.startswith("B"): return "MF Apartments (Unclassified)"
    if code == "C1":   return "Vacant - Single Family"
    if code in ("C2", "C3"): return "Vacant - Commercial"
    if code.startswith("C"): return "Vacant - Single Family"
    if code.startswith("D"): return "Open Space"
    if code.startswith("E"): return "Other"
    if code == "F1":   return "Commercial"
    if code == "F2":   return "Industrial"
    if code.startswith("F"): return "Commercial"
    if code.startswith("J"): return "Other"
    if code in ("L1",):      return "Commercial"
    if code in ("L2",):      return "Industrial"
    if code.startswith("M"): return "Mobile Home"
    return "Other"

den["land_use_cat"] = den.apply(
    lambda r: land_use_from_state_cd(r["stateCd"], r["imprvUnits"] or 0),
    axis=1,
)

den_lookup = den.set_index("pID")
log(f"  Distinct pIDs in slim: {len(den_lookup):,}")


# ---------------------------------------------------------------------------
# FAR binning (must match build_parcels_geojson.py)
# ---------------------------------------------------------------------------
def far_category(far):
    if pd.isna(far) or far <= 0:        return "No Building"
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

    is_den = gdf["account_num"].astype(str).str.startswith("DEN-")
    n_den = int(is_den.sum())
    if n_den == 0:
        log("  No Denton parcels in this quadrant - skipping.")
        continue

    pid = gdf.loc[is_den, "account_num"].str[4:]
    pid = pd.to_numeric(pid, errors="coerce").astype("Int64")

    matched_mask = pid.isin(den_lookup.index)
    n_matched = int(matched_mask.sum())
    n_unmatched = n_den - n_matched
    TOTAL_PATCHED += n_matched
    TOTAL_UNMATCHED += n_unmatched
    log(f"  DEN- parcels: {n_den:,}  matched: {n_matched:,}  unmatched: {n_unmatched:,}")

    pid_for_lookup = pid.where(matched_mask)
    den_rows = den_lookup.reindex(pid_for_lookup.values)

    idx = gdf.index[is_den]

    gdf.loc[idx, "address"]        = den_rows["address"].values
    gdf.loc[idx, "land_use_cat"]   = den_rows["land_use_cat"].fillna("Other").values
    gdf.loc[idx, "land_sptd_desc"] = den_rows["land_use_cat"].fillna("Other").values
    gdf.loc[idx, "bldg_class"]     = den_rows["imprvClass"].fillna("").values

    building_sf = pd.to_numeric(den_rows["imprvMainArea"], errors="coerce").fillna(0).values
    total_units = pd.to_numeric(den_rows["imprvUnits"], errors="coerce").fillna(0).values
    year_built  = pd.to_numeric(den_rows["imprvActualYearBuilt"], errors="coerce").values

    gdf.loc[idx, "building_sf"] = building_sf
    gdf.loc[idx, "total_units"] = total_units
    gdf.loc[idx, "year_built"]  = year_built

    area_feet = pd.to_numeric(gdf.loc[idx, "area_feet"], errors="coerce").fillna(0).values
    with np.errstate(divide="ignore", invalid="ignore"):
        far = np.where(area_feet > 0, building_sf / area_feet, np.nan)
    gdf.loc[idx, "floor_area_ratio"] = np.round(far, 2)
    gdf.loc[idx, "far_cat"] = [far_category(f) for f in far]

    tot_val  = pd.to_numeric(den_rows["valMarket"],    errors="coerce").fillna(0).values
    impr_val = pd.to_numeric(den_rows["valStructure"], errors="coerce").fillna(0).values
    land_val = pd.to_numeric(den_rows["valLand"],      errors="coerce").fillna(0).values

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

    log(f"  Writing {path} ...")
    gdf.to_file(path, driver="GeoJSON")
    log(f"  wrote {len(gdf):,} features")


log("\n=== Summary ===")
log(f"Total DEN- parcels patched:   {TOTAL_PATCHED:,}")
log(f"Total DEN- parcels unmatched: {TOTAL_UNMATCHED:,}")
log("Done.")
