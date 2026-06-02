"""
Build a simplified Dallas parcels GeoJSON for the web map.

Source: PARCEL_CORE_MERGED.gpkg (in GDPC Claude Stuff/)
Output: webmap/data/parcels.geojson

What we do:
  1. Filter to City of Dallas (city == "DALLAS")
  2. Compute derived columns the pipeline already documents:
       building_sf  (RES_TOT_MAIN_SF preferred, fallback COM_GROSS_BLDG_AREA)
       year_built   (RES_YR_BUILT preferred, fallback COM_YEAR_BUILT)
       total_units  (RES_NUM_UNITS + COM_NUM_UNITS)
       floor_area_ratio (building_sf / area_feet)
       far_cat      (categorical FAR bin for styling)
       land_use_cat (collapsed LAND_SPTD_DESC to display categories)
       address      (assembled from st_num/dir/name/type/unit)
  3. Drop heavy attributes; keep minimal popup-relevant set
  4. Simplify geometries to ~2 m
  5. Save as GeoJSON
"""

import os
import time
import numpy as np
import pandas as pd
import geopandas as gpd
from shapely.validation import make_valid
import warnings
warnings.filterwarnings("ignore")

t0 = time.time()
def log(msg): print(f"[{time.time()-t0:.0f}s] {msg}", flush=True)

PROJECT_DIR = r"C:\Users\shane\OneDrive\Documents\Domain Consulting\Projects\GDPC - Dallas Housing Report"
SRC = os.path.join(PROJECT_DIR, "GDPC Claude Stuff", "PARCEL_CORE_MERGED.gpkg")
OUT = os.path.join(PROJECT_DIR, "webmap", "data", "parcels.geojson")

# ---------------------------------------------------------------------------
# 1. Load
# ---------------------------------------------------------------------------
log(f"Loading {SRC}...")
gdf = gpd.read_file(SRC)
log(f"  {len(gdf):,} parcels loaded")

# ---------------------------------------------------------------------------
# 2. Filter to Dallas (defensive — pipeline already does this, but verify)
# ---------------------------------------------------------------------------
gdf = gdf[gdf["city"].astype(str).str.upper() == "DALLAS"].copy()
log(f"  {len(gdf):,} Dallas parcels")

# Drop rows with no geometry
gdf = gdf[~gdf.geometry.is_empty & gdf.geometry.notna()].copy()
gdf["geometry"] = gdf["geometry"].apply(make_valid)
log(f"  {len(gdf):,} with valid geometry")

# ---------------------------------------------------------------------------
# 3. Compute derived attributes
# ---------------------------------------------------------------------------
gdf["area_feet"] = pd.to_numeric(gdf["area_feet"], errors="coerce")
gdf["building_sf"] = gdf["RES_TOT_MAIN_SF"]
mask = gdf["building_sf"].isna() | (gdf["building_sf"] == 0)
gdf.loc[mask, "building_sf"] = gdf.loc[mask, "COM_GROSS_BLDG_AREA"]
gdf["building_sf"] = gdf["building_sf"].fillna(0)

gdf["year_built"] = gdf["RES_YR_BUILT"]
mask = gdf["year_built"].isna() | (gdf["year_built"] == 0)
gdf.loc[mask, "year_built"] = gdf.loc[mask, "COM_YEAR_BUILT"]

gdf["total_units"] = gdf["RES_NUM_UNITS"].fillna(0) + gdf["COM_NUM_UNITS"].fillna(0)

gdf["floor_area_ratio"] = np.where(
    gdf["area_feet"] > 0,
    gdf["building_sf"] / gdf["area_feet"],
    np.nan,
)

# FAR category (matches the static FAR map from station_area_analysis.py)
def far_category(far):
    if pd.isna(far) or far <= 0:
        return "No Building"
    elif far < 0.25:
        return "< 0.25"
    elif far < 0.5:
        return "0.25 - 0.49"
    elif far < 1.0:
        return "0.5 - 0.99"
    elif far < 1.5:
        return "1.0 - 1.49"
    elif far <= 2.0:
        return "1.5 - 2.0"
    elif far < 3.0:
        return "2.0 - 2.9"
    elif far < 5.0:
        return "3.0 - 4.9"
    elif far < 10.0:
        return "5.0 - 9.9"
    else:
        return "10+"

gdf["far_cat"] = gdf["floor_area_ratio"].apply(far_category)

# Subcategorize MFR apartments by total units (matches the pipeline)
apt_mask = gdf["LAND_SPTD_DESC"] == "MFR - APARTMENTS"
units = gdf.loc[apt_mask, "total_units"]
gdf.loc[apt_mask & (units >= 3) & (units <= 4), "LAND_SPTD_DESC"] = "MFR - 3-4 UNITS"
gdf.loc[apt_mask & (units >= 5) & (units <= 19), "LAND_SPTD_DESC"] = "MFR - 5-19 UNITS"
gdf.loc[apt_mask & (units >= 20) & (units <= 49), "LAND_SPTD_DESC"] = "MFR - 20-49 UNITS"
gdf.loc[apt_mask & (units >= 50), "LAND_SPTD_DESC"] = "MFR - 50+ UNITS"

# Collapse LAND_SPTD_DESC to display categories (consistent with parcel map)
LAND_USE_MAP = {
    "SINGLE FAMILY RESIDENCES": "Single Family",
    "SFR - TOWNHOUSES": "Townhouses",
    "MFR - DUPLEXES": "Duplexes",
    "MFR - 3-4 UNITS": "MF 3-4 Units",
    "MFR - 5-19 UNITS": "MF 5-19 Units",
    "MFR - 20-49 UNITS": "MF 20-49 Units",
    "MFR - 50+ UNITS": "MF 50+ Units",
    "MFR - APARTMENTS": "MF Apartments (Unclassified)",
    "SFR - VACANT LOTS/TRACTS": "Vacant - Single Family",
    "COMMERCIAL - VACANT PLOTTED LOTS/TRACTS": "Vacant - Commercial",
    "INDUSTRIAL - VACANT PLOTTED LOTS/TRACTS": "Vacant - Industrial",
    "COMMERCIAL IMPROVEMENTS": "Commercial",
    "INDUSTRIAL IMPROVEMENTS": "Industrial",
    "QUALIFIED OPEN SPACE LAND": "Open Space",
    "MOBILE HOME ON OWNERS LAND": "Mobile Home",
    "SFR - CONDOMINIUMS": "SFR Condominiums",
}
gdf["land_use_cat"] = gdf["LAND_SPTD_DESC"].map(LAND_USE_MAP).fillna("Other")

# Promote totally-exempt commercial / industrial / other parcels to
# "Institutional" so schools, churches, government buildings, hospitals,
# etc. don't show up as Commercial on the land-use map. Residential exempt
# parcels (Land Bank homes, public housing) are intentionally left in
# their housing categories so housing analysis stays consistent.
_inst_mask = (gdf["totexempt"] == "X") & gdf["land_use_cat"].isin(
    ["Commercial", "Industrial", "Other"]
)
gdf.loc[_inst_mask, "land_use_cat"] = "Institutional"
log(f"  Reclassified {int(_inst_mask.sum()):,} totally-exempt parcels as Institutional")

# ---------------------------------------------------------------------------
# 3b. Merge DCAD appraisal values (TOT_VAL / IMPR_VAL / LAND_VAL)
#     from ACCOUNT_APPRL_YEAR.CSV in the DCAD2025_CERTIFIED folder.
#     (The 2026 "current" zip is pre-certification — all values are 0.)
# ---------------------------------------------------------------------------
log("Merging in DCAD 2025 certified appraisal values from ACCOUNT_APPRL_YEAR.CSV...")
appr_path = os.path.join(PROJECT_DIR, "GDPC Claude Stuff", "DCAD2025_CERTIFIED", "ACCOUNT_APPRL_YEAR.CSV")
appr = pd.read_csv(
    appr_path,
    usecols=["ACCOUNT_NUM", "APPRAISAL_YR", "TOT_VAL", "IMPR_VAL", "LAND_VAL"],
    low_memory=False,
)
appr["ACCOUNT_NUM"] = appr["ACCOUNT_NUM"].astype(str)
# Keep only the most recent appraisal year (file may include multiple)
appr = appr.sort_values("APPRAISAL_YR").drop_duplicates(subset="ACCOUNT_NUM", keep="last")
log(f"  Appraisal rows: {len(appr):,} (year range {appr['APPRAISAL_YR'].min()}–{appr['APPRAISAL_YR'].max()})")

gdf["ACCOUNT_NUM"] = gdf["ACCOUNT_NUM"].astype(str)
gdf = gdf.merge(
    appr[["ACCOUNT_NUM", "TOT_VAL", "IMPR_VAL", "LAND_VAL"]],
    on="ACCOUNT_NUM", how="left",
)
for c in ["TOT_VAL", "IMPR_VAL", "LAND_VAL"]:
    gdf[c] = pd.to_numeric(gdf[c], errors="coerce").fillna(0)

# Pro-rate values across multi-polygon accounts.
# DCAD sometimes assigns one account number to several polygon slivers
# (e.g., DART right-of-way segments, fragmented platting, strictly-stratified
# condo unit polygons). The appraisal table carries the full TOT_VAL on the
# single account row — so a naive merge replicates the full value to every
# polygon and inflates per-acre numbers on the smaller slivers. We allocate
# each polygon a share equal to its land area / total land area of all
# polygons sharing the same account number.
gdf["area_feet"] = pd.to_numeric(gdf["area_feet"], errors="coerce").fillna(0)
account_areas = gdf.groupby("ACCOUNT_NUM")["area_feet"].transform("sum")
share = np.where(account_areas > 0, gdf["area_feet"] / account_areas, 0)
for c in ["TOT_VAL", "IMPR_VAL", "LAND_VAL"]:
    gdf[c] = (gdf[c] * share).round(0)

acct_counts = gdf["ACCOUNT_NUM"].value_counts()
multi_accts = (acct_counts > 1).sum()
multi_parcels = int(gdf["ACCOUNT_NUM"].isin(acct_counts[acct_counts > 1].index).sum())
log(f"  Pro-rated {multi_accts:,} accounts spanning multiple polygons ({multi_parcels:,} parcels affected)")

# Per-acre values (acres = area_feet / 43,560). Avoid div-by-zero.
gdf["acres_safe"] = gdf["area_feet"].replace(0, np.nan) / 43560.0
gdf["value_per_acre"] = (gdf["TOT_VAL"]  / gdf["acres_safe"]).round(0)
gdf["impr_per_acre"]  = (gdf["IMPR_VAL"] / gdf["acres_safe"]).round(0)
gdf["land_per_acre"]  = (gdf["LAND_VAL"] / gdf["acres_safe"]).round(0)
gdf[["value_per_acre", "impr_per_acre", "land_per_acre"]] = (
    gdf[["value_per_acre", "impr_per_acre", "land_per_acre"]].fillna(0).astype(np.int64)
)

# Build address
def build_address(row):
    parts = [
        str(row.get("st_num") or "").strip(),
        str(row.get("st_dir") or "").strip(),
        str(row.get("st_name") or "").strip(),
        str(row.get("st_type") or "").strip(),
    ]
    addr = " ".join(p for p in parts if p and p.lower() != "none")
    unit = str(row.get("unitid") or "").strip()
    if unit and unit.lower() != "none":
        addr = f"{addr} #{unit}"
    return addr.strip() or None

log("Building address strings...")
gdf["address"] = gdf.apply(build_address, axis=1)

# Round numeric columns for size
for col in ["area_feet", "building_sf", "floor_area_ratio",
            "LAND_TOTAL_VAL", "COM_MKT_VAL"]:
    if col in gdf.columns:
        gdf[col] = pd.to_numeric(gdf[col], errors="coerce")
        gdf[col] = gdf[col].round(0 if col != "floor_area_ratio" else 2)

# ---------------------------------------------------------------------------
# 4. Drop heavy attributes; keep minimal popup-essential set
# ---------------------------------------------------------------------------
KEEP = [
    "ACCOUNT_NUM", "address", "land_use_cat", "LAND_SPTD_DESC",
    "LAND_ZONING", "area_feet", "building_sf", "total_units",
    "year_built", "floor_area_ratio", "far_cat",
    "TOT_VAL", "IMPR_VAL", "LAND_VAL",
    "value_per_acre", "impr_per_acre", "land_per_acre",
    "COM_PROPERTY_NAME", "bldg_cl",
    "DART_STATION", "dacouncil",
    "geometry",
]
KEEP = [c for c in KEEP if c in gdf.columns]
gdf = gdf[KEEP].copy()

# Convert numeric NaN → None / proper integer where appropriate
for col in ["total_units", "year_built", "DART_STATION"]:
    if col in gdf.columns:
        gdf[col] = pd.to_numeric(gdf[col], errors="coerce").fillna(0).astype(int)

# Rename to lowercase / friendly names for the webmap
gdf = gdf.rename(columns={
    "ACCOUNT_NUM":     "account_num",
    "LAND_SPTD_DESC":  "land_sptd_desc",
    "LAND_ZONING":     "zoning_assessor",
    "TOT_VAL":         "tot_val",
    "IMPR_VAL":        "impr_val",
    "LAND_VAL":        "land_val",
    "COM_PROPERTY_NAME": "property_name",
    "bldg_cl":         "bldg_class",
    "DART_STATION":    "dart_station",
    "dacouncil":       "council_district",
})

# ---------------------------------------------------------------------------
# 5. Simplify geometry (~2 m in EPSG:2276 ≈ 0.00002° in 4326)
# ---------------------------------------------------------------------------
log("Simplifying geometries (this is the slow step)...")
proj = gdf.to_crs("EPSG:2276")
proj["geometry"] = proj["geometry"].simplify(8.0, preserve_topology=True)
gdf = proj.to_crs("EPSG:4326")

# Round coordinates to 5 decimal places (~1 m at this latitude). This shaves
# a large amount of file size from a GeoJSON dominated by coordinates.
from shapely.ops import transform
def _round_coords(geom, p=5):
    return transform(lambda x, y, z=None: (round(x, p), round(y, p)), geom)
log("Rounding coordinates to 5 decimal places...")
gdf["geometry"] = gdf["geometry"].apply(_round_coords)

# ---------------------------------------------------------------------------
# 6. Save in 4 quadrants so each file fits under GitHub's 100 MB single-file
#    limit and can be loaded in parallel.
#
#    Split point for Dallas:
#       lat: 32.81  (roughly downtown core)
#       lon: -96.78
# ---------------------------------------------------------------------------
import json
LAT_SPLIT = 32.81
LON_SPLIT = -96.78

# Determine quadrant from polygon centroid
log("Computing centroids for quadrant assignment...")
centroids = gdf.geometry.centroid
gdf["_lat"] = centroids.y
gdf["_lon"] = centroids.x

def quad(row):
    if row["_lat"] >= LAT_SPLIT and row["_lon"] < LON_SPLIT: return "nw"
    if row["_lat"] >= LAT_SPLIT and row["_lon"] >= LON_SPLIT: return "ne"
    if row["_lat"] <  LAT_SPLIT and row["_lon"] < LON_SPLIT: return "sw"
    return "se"
gdf["_quad"] = gdf.apply(quad, axis=1)
print(gdf["_quad"].value_counts().to_dict())

OUT_DIR = os.path.join(PROJECT_DIR, "webmap", "data")
for quad_key in ["nw", "ne", "sw", "se"]:
    sub = gdf[gdf["_quad"] == quad_key].drop(columns=["_lat", "_lon", "_quad"])
    out_path = os.path.join(OUT_DIR, f"parcels_{quad_key}.geojson")
    log(f"Writing {out_path} ({len(sub):,} parcels)...")
    features = []
    for _, row in sub.iterrows():
        props = row.drop("geometry").to_dict()
        props = {k: v for k, v in props.items()
                 if v is not None and (not isinstance(v, float) or not pd.isna(v))}
        features.append({
            "type": "Feature",
            "geometry": row.geometry.__geo_interface__,
            "properties": props,
        })
    geojson = {"type": "FeatureCollection", "features": features}
    with open(out_path, "w") as f:
        json.dump(geojson, f, separators=(",", ":"))
    sz = os.path.getsize(out_path) / 1024 / 1024
    log(f"  {sz:.1f} MB")
log("Done.")
