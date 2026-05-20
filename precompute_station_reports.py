"""
Pre-compute TOD Opportunity Area report stats for each rail station.

For each rail station, computes — at both ¼-mile and ½-mile buffers:
  - % of land in each base zoning category
  - % of land in each land use category (vacant types grouped)
  - % of land in each FAR bin
  - Sum of dwelling units
  - Sum of land area (acres)

Plus per station:
  - Tract GEOID containing the station
  - Tract 2024 ACS median household income
  - Tract 2024 ACS median family income

Output: webmap/data/station_reports.json
"""

import io
import json
import os
import re
import time
import requests
import numpy as np
import pandas as pd
import geopandas as gpd
from shapely.validation import make_valid
import warnings
warnings.filterwarnings("ignore")

t0 = time.time()
def log(msg): print(f"[{time.time()-t0:.0f}s] {msg}", flush=True)

API_KEY = os.environ.get("CENSUS_API_KEY", "")
PROJECT = r"C:\Users\shane\OneDrive\Documents\Domain Consulting\Projects\GDPC - Dallas Housing Report"
OUT_PATH = os.path.join(PROJECT, "webmap", "data", "station_reports.json")
PROJ_FT = "EPSG:2276"   # Texas State Plane North Central, US ft
QUARTER_MI = 1320       # ft
HALF_MI = 2640          # ft

LAND_USE_VACANT = {"Vacant - Single Family", "Vacant - Commercial", "Vacant - Industrial"}

FAR_BINS = ["No Building", "< 0.25", "0.25 - 0.49", "0.5 - 0.99", "1.0 - 1.49",
            "1.5 - 2.0", "2.0 - 2.9", "3.0 - 4.9", "5.0 - 9.9", "10+"]


def normalize_zone(z):
    if pd.isna(z): return z
    return re.sub(r"(\([^)]*\))+$", "", z.strip())

def categorize_zone(z):
    if pd.isna(z): return "Other"
    if z == "PD": return "Planned Development"
    if z == "CD": return "Conservation District"
    if z.startswith("R-") or z in {"A","MH","D"}:           return "Single-Family"
    if z.startswith("TH-") or z == "CH":                    return "Townhouse / Cluster"
    if z.startswith("MF-"):                                 return "Multifamily"
    if z.startswith("MU-") or z.startswith("WMU-") or z.startswith("UC-"): return "Mixed-Use"
    if z.startswith("CA-"):                                 return "Community Area"
    if z in {"IR","IM","LI"}:                               return "Industrial"
    if z in {"CR","RR","CS","NS","GR"}:                     return "Commercial"
    if z.startswith("LO-") or z.startswith("MO-") or z in {"GO","NO","O-2"}: return "Commercial"
    if z.startswith("MC-"):                                 return "Commercial"
    return "Other"

def far_category(far):
    if pd.isna(far) or far <= 0: return "No Building"
    if far < 0.25:    return "< 0.25"
    if far < 0.5:     return "0.25 - 0.49"
    if far < 1.0:     return "0.5 - 0.99"
    if far < 1.5:     return "1.0 - 1.49"
    if far <= 2.0:    return "1.5 - 2.0"
    if far < 3.0:     return "2.0 - 2.9"
    if far < 5.0:     return "3.0 - 4.9"
    if far < 10.0:    return "5.0 - 9.9"
    return "10+"

LAND_USE_MAP = {
    "SINGLE FAMILY RESIDENCES":               "Single Family",
    "SFR - TOWNHOUSES":                       "Townhouses",
    "MFR - DUPLEXES":                         "Duplexes",
    "MFR - 3-4 UNITS":                        "MF 3-4 Units",
    "MFR - 5-19 UNITS":                       "MF 5-19 Units",
    "MFR - 20-49 UNITS":                      "MF 20-49 Units",
    "MFR - 50+ UNITS":                        "MF 50+ Units",
    "MFR - APARTMENTS":                       "MF Apartments (Unclassified)",
    "SFR - VACANT LOTS/TRACTS":               "Vacant - Single Family",
    "COMMERCIAL - VACANT PLOTTED LOTS/TRACTS":"Vacant - Commercial",
    "INDUSTRIAL - VACANT PLOTTED LOTS/TRACTS":"Vacant - Industrial",
    "COMMERCIAL IMPROVEMENTS":                "Commercial",
    "INDUSTRIAL IMPROVEMENTS":                "Industrial",
    "QUALIFIED OPEN SPACE LAND":              "Open Space",
    "MOBILE HOME ON OWNERS LAND":             "Mobile Home",
    "SFR - CONDOMINIUMS":                     "SFR Condominiums",
}


# ---------------------------------------------------------------------------
# Load source data
# ---------------------------------------------------------------------------
log("Loading rail stops...")
stops = gpd.read_file(os.path.join(PROJECT, "GDPC Claude Stuff", "Rail_Stops.geojson")).to_crs("EPSG:4326")
log(f"  {len(stops)} stops")

log("Loading parcels (this is the slow load)...")
parcels = gpd.read_file(os.path.join(PROJECT, "GDPC Claude Stuff", "PARCEL_CORE_MERGED.gpkg"))
parcels["geometry"] = parcels["geometry"].apply(make_valid)
log(f"  {len(parcels):,} parcels")

# Apply MFR apartment subcategorization (consistent with rebuild_pipeline / build_parcels_geojson)
parcels["area_feet"] = pd.to_numeric(parcels["area_feet"], errors="coerce")
parcels["building_sf"] = parcels["RES_TOT_MAIN_SF"]
mask = parcels["building_sf"].isna() | (parcels["building_sf"] == 0)
parcels.loc[mask, "building_sf"] = parcels.loc[mask, "COM_GROSS_BLDG_AREA"]
parcels["building_sf"] = parcels["building_sf"].fillna(0)
parcels["total_units"] = parcels["RES_NUM_UNITS"].fillna(0) + parcels["COM_NUM_UNITS"].fillna(0)
parcels["floor_area_ratio"] = np.where(
    parcels["area_feet"] > 0, parcels["building_sf"] / parcels["area_feet"], np.nan
)
parcels["far_cat"] = parcels["floor_area_ratio"].apply(far_category)

# Year built: prefer RES, fallback COM. Then filter implausible values
# (bottom-coded 0s and pre-1850 data-entry errors) so they don't pull the
# mean down. About 17K parcels have year_built == 0; another handful have
# values before 1850.
parcels["year_built"] = parcels["RES_YR_BUILT"]
m = parcels["year_built"].isna() | (parcels["year_built"] == 0)
parcels.loc[m, "year_built"] = parcels.loc[m, "COM_YEAR_BUILT"]
parcels["year_built_clean"] = parcels["year_built"].where(parcels["year_built"] >= 1850)

# Decade-built categories (must match the webmap's DECADE_BINS)
def decade_cat(yr):
    if pd.isna(yr) or yr < 1850: return "No data"
    if yr < 1940: return "Pre-1940"
    if yr < 2010: return f"{int(yr // 10 * 10)}s"
    return "2010 or later"
parcels["decade_cat"] = parcels["year_built_clean"].apply(decade_cat)

apt = parcels["LAND_SPTD_DESC"] == "MFR - APARTMENTS"
u = parcels.loc[apt, "total_units"]
parcels.loc[apt & (u >= 3) & (u <= 4),  "LAND_SPTD_DESC"] = "MFR - 3-4 UNITS"
parcels.loc[apt & (u >= 5) & (u <= 19), "LAND_SPTD_DESC"] = "MFR - 5-19 UNITS"
parcels.loc[apt & (u >= 20)& (u <= 49), "LAND_SPTD_DESC"] = "MFR - 20-49 UNITS"
parcels.loc[apt & (u >= 50),            "LAND_SPTD_DESC"] = "MFR - 50+ UNITS"
parcels["land_use_cat"] = parcels["LAND_SPTD_DESC"].map(LAND_USE_MAP).fillna("Other")

log("Loading zoning...")
zoning = gpd.read_file(os.path.join(PROJECT, "Base_Zoning.geojson")).to_crs("EPSG:4326")
zoning["geometry"] = zoning["geometry"].apply(make_valid)
zoning["zone_norm"] = zoning["ZONE_DIST"].apply(normalize_zone)
zoning["category"] = zoning["zone_norm"].apply(categorize_zone)

log("Loading 2020 TIGER tracts (TX)...")
tracts = gpd.read_file(os.path.join(PROJECT, "tl_2020_48_tract.zip")).to_crs("EPSG:4326")
tracts["geometry"] = tracts["geometry"].apply(make_valid)
tracts = tracts[["GEOID", "geometry"]]


# ---------------------------------------------------------------------------
# Project everything to feet for buffer math
# ---------------------------------------------------------------------------
stops_ft   = stops.to_crs(PROJ_FT)
parcels_ft = parcels.to_crs(PROJ_FT)
zoning_ft  = zoning.to_crs(PROJ_FT)


# ---------------------------------------------------------------------------
# Spatial-index helpers (sjoin) for speed
# ---------------------------------------------------------------------------
# Precompute parcel "original" area so we can apportion units when a parcel
# straddles a buffer edge.
parcels_ft = parcels_ft.copy()
parcels_ft["_orig_area"] = parcels_ft.geometry.area

# Touch the spatial indexes once so subsequent intersects() are fast
_ = parcels_ft.sindex
_ = zoning_ft.sindex


def stats_for_buffer(buf_geom):
    """Compute zoning %, land use %, FAR %, units, acres for a single buffer geom."""
    # --- Zoning (area-weighted by category) ---
    z_idx = list(zoning_ft.sindex.intersection(buf_geom.bounds))
    z_cand = zoning_ft.iloc[z_idx]
    z_clipped = z_cand.geometry.intersection(buf_geom)
    z_areas = z_clipped.area
    zoning_df = pd.DataFrame({
        "category": z_cand["category"].values,
        "a": z_areas.values,
    })
    z_total = zoning_df["a"].sum()
    zoning_pct = (
        (zoning_df.groupby("category")["a"].sum() / z_total * 100).round(1).to_dict()
        if z_total > 0 else {}
    )

    # --- Parcels (land use + FAR + units + bldg sf + year built) ---
    p_idx = list(parcels_ft.sindex.intersection(buf_geom.bounds))
    p_cand = parcels_ft.iloc[p_idx]
    p_clipped = p_cand.geometry.intersection(buf_geom)
    clip_area = p_clipped.area
    parcel_df = pd.DataFrame({
        "land_use_cat": p_cand["land_use_cat"].values,
        "far_cat": p_cand["far_cat"].values,
        "decade_cat": p_cand["decade_cat"].values,
        "total_units": p_cand["total_units"].values,
        "building_sf": p_cand["building_sf"].values,
        "year_built": p_cand["year_built_clean"].values,
        "orig_area": p_cand["_orig_area"].values,
        "clip_area": clip_area.values,
    })
    parcel_df["frac"] = parcel_df["clip_area"] / parcel_df["orig_area"].replace(0, np.nan)
    parcel_df["frac"] = parcel_df["frac"].fillna(0).clip(upper=1.0)

    p_total = parcel_df["clip_area"].sum()

    # Group vacant types
    parcel_df["land_use_grp"] = np.where(
        parcel_df["land_use_cat"].isin(LAND_USE_VACANT),
        "Vacant", parcel_df["land_use_cat"],
    )

    landuse_pct = (
        (parcel_df.groupby("land_use_grp")["clip_area"].sum() / p_total * 100).round(1).to_dict()
        if p_total > 0 else {}
    )
    far_pct = (
        (parcel_df.groupby("far_cat")["clip_area"].sum() / p_total * 100).round(1).to_dict()
        if p_total > 0 else {}
    )
    decade_pct = (
        (parcel_df.groupby("decade_cat")["clip_area"].sum() / p_total * 100).round(1).to_dict()
        if p_total > 0 else {}
    )

    # Apportion dwelling units and building sq ft by overlap fraction
    units = float((parcel_df["total_units"].fillna(0) * parcel_df["frac"]).sum())
    bldg_sf = float((parcel_df["building_sf"].fillna(0) * parcel_df["frac"]).sum())

    # Average year built — parcels weighted by building sq ft so big
    # buildings don't get drowned out by small ones, and only real values
    # are used (year_built_clean drops 0s and pre-1850 errors).
    yb_mask = parcel_df["year_built"].notna() & (parcel_df["building_sf"] > 0)
    if yb_mask.any():
        w = parcel_df.loc[yb_mask, "building_sf"] * parcel_df.loc[yb_mask, "frac"]
        avg_yb = float((parcel_df.loc[yb_mask, "year_built"] * w).sum() / w.sum())
        avg_yb = int(round(avg_yb))
    else:
        avg_yb = None

    return {
        "land_acres": round(p_total / 43560, 1),
        "dwelling_units": int(round(units)),
        "total_building_sf": int(round(bldg_sf)),
        "avg_year_built": avg_yb,
        "zoning_pct": zoning_pct,
        "land_use_pct": landuse_pct,
        "far_pct": far_pct,
        "decade_pct": decade_pct,
    }


# ---------------------------------------------------------------------------
# Find the tract containing each station
# ---------------------------------------------------------------------------
log("Spatial-joining stations to tracts...")
stops_geo = stops.copy()
joined = gpd.sjoin(stops_geo, tracts, how="left", predicate="within")
station_to_tract = dict(zip(joined.index, joined["GEOID"]))


# ---------------------------------------------------------------------------
# Pull 2024 ACS for the unique tracts that contain stations
# ---------------------------------------------------------------------------
unique_tracts = sorted(set(t for t in station_to_tract.values() if isinstance(t, str)))
log(f"  {len(unique_tracts)} unique tracts contain stations")

# Pull at the state level (TX, FIPS 48) and filter — simpler than per-tract API calls.
unique_counties = sorted(set(t[2:5] for t in unique_tracts))
log(f"  Counties to pull from ACS 2024: {unique_counties}")

acs_data = {}
for cfips in unique_counties:
    url = (
        "https://api.census.gov/data/2024/acs/acs5"
        "?get=B19013_001E,B19119_001E"
        f"&for=tract:*&in=state:48+county:{cfips}"
    )
    if API_KEY:
        url += f"&key={API_KEY}"
    log(f"  Fetching ACS for county {cfips}...")
    r = requests.get(url, timeout=120)
    r.raise_for_status()
    rows = r.json()
    df = pd.DataFrame(rows[1:], columns=rows[0])
    df["GEOID"] = df["state"] + df["county"] + df["tract"]
    for col in ["B19013_001E", "B19119_001E"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df.loc[df["B19013_001E"] < 0, "B19013_001E"] = np.nan
    df.loc[df["B19119_001E"] < 0, "B19119_001E"] = np.nan
    for _, row in df.iterrows():
        acs_data[row["GEOID"]] = {
            "mhi_2024": None if pd.isna(row["B19013_001E"]) else int(row["B19013_001E"]),
            "mfi_2024": None if pd.isna(row["B19119_001E"]) else int(row["B19119_001E"]),
        }


# ---------------------------------------------------------------------------
# For each station, compute reports
# ---------------------------------------------------------------------------
reports = []
for idx, row in stops_ft.iterrows():
    pt = row.geometry
    name = row.get("stop_name") or "Unknown"
    log(f"Station {idx+1}/{len(stops_ft)}: {name}")

    quarter_buf = pt.buffer(QUARTER_MI)
    half_buf    = pt.buffer(HALF_MI)

    quarter_stats = stats_for_buffer(quarter_buf)
    half_stats    = stats_for_buffer(half_buf)

    tract_geoid = station_to_tract.get(idx)
    income = acs_data.get(tract_geoid, {}) if tract_geoid else {}

    reports.append({
        "stop_id": str(row.get("stop_id", "")),
        "stop_name": name,
        "tract_geoid": tract_geoid,
        "tract_mhi_2024": income.get("mhi_2024"),
        "tract_mfi_2024": income.get("mfi_2024"),
        "quarter_mile": quarter_stats,
        "half_mile":    half_stats,
    })

with open(OUT_PATH, "w") as f:
    json.dump({"stations": reports}, f, separators=(",", ":"))
log(f"Saved {OUT_PATH} ({os.path.getsize(OUT_PATH)/1024:.1f} KB)")
