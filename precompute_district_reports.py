"""
Pre-compute Council District report stats. For each of the 14 City of
Dallas council districts, produces a JSON record with:

  At-a-glance: population, dwelling units, density, median HH/family income,
               median age, council member, district area
  Housing stock: DCAD dwelling units, ACS dwelling units, median year built,
                 avg household size, % overcrowded, % owner-occupied,
                 vacancy rate
  Housing costs: median home value, median rent, % cost-burdened /
                 severely cost-burdened (renters + owners w/ mortgage)
  People: % under 18, % 65+, race/ethnicity mix, % foreign-born,
          % bachelor's degree or higher (25+)
  Mobility: # rail stations in district, % within 1/2 mi of rail,
            % households with no vehicle, % non-auto commute
  Recent change: pop change 2010-2020, HU change 2010-2020
  Permitted housing 2010-2024: SF / MF / total units
  Built environment: zoning mix, land use mix, FAR mix, decade built mix

Output: webmap/data/district_reports.json
"""

import io
import json
import os
import re
import time

import numpy as np
import pandas as pd
import geopandas as gpd
import requests
from shapely.validation import make_valid
from shapely.ops import unary_union
import warnings
warnings.filterwarnings("ignore")

t0 = time.time()
def log(msg): print(f"[{time.time()-t0:.0f}s] {msg}", flush=True)

API_KEY = os.environ.get("CENSUS_API_KEY", "")
PROJECT = r"C:\Users\shane\OneDrive\Documents\Domain Consulting\Projects\GDPC - Dallas Housing Report"
OUT_PATH = os.path.join(PROJECT, "webmap", "data", "district_reports.json")
PROJ_FT = "EPSG:2276"
HALF_MI = 2640
LAND_USE_VACANT = {"Vacant - Single Family", "Vacant - Commercial", "Vacant - Industrial"}


# ---------------------------------------------------------------------------
# ACS 2024 5-year variable definitions (organized for readability)
# ---------------------------------------------------------------------------
ACS_VARS = {
    # Simple totals / medians
    "B01003_001E": "pop",
    "B01002_001E": "med_age",
    "B19013_001E": "mhi",
    "B19119_001E": "mfi",
    "B25001_001E": "hu_acs",
    "B25010_001E": "avg_hh_size",
    "B25035_001E": "med_yr_built",
    "B25077_001E": "med_home_value",
    "B25064_001E": "med_rent",
    "B09001_001E": "pop_under_18",
    "B25002_002E": "hu_occupied",
    "B25002_003E": "hu_vacant",
    "B25003_002E": "hh_owner",
    "B25003_003E": "hh_renter",
    "B05002_001E": "pob_total",
    "B05002_013E": "pob_foreign",
    # Race / Hispanic (B03002)
    "B03002_001E": "race_total",
    "B03002_003E": "race_nh_white",
    "B03002_004E": "race_nh_black",
    "B03002_006E": "race_nh_asian",
    "B03002_012E": "race_hispanic",
    # Education (B15003): 25+, bachelor's, master's, professional, doctorate
    "B15003_001E": "edu_total25",
    "B15003_022E": "edu_bach",
    "B15003_023E": "edu_mast",
    "B15003_024E": "edu_prof",
    "B15003_025E": "edu_doc",
    # Occupants per room (B25014): owner / renter at >1.0 per room
    "B25014_001E": "occ_total",
    "B25014_005E": "occ_own_1to1_5",
    "B25014_006E": "occ_own_1_5to2",
    "B25014_007E": "occ_own_2plus",
    "B25014_011E": "occ_rent_1to1_5",
    "B25014_012E": "occ_rent_1_5to2",
    "B25014_013E": "occ_rent_2plus",
    # Vehicles (B25044)
    "B25044_001E": "veh_total",
    "B25044_003E": "veh_own_none",
    "B25044_010E": "veh_rent_none",
    # Commute (B08301)
    "B08301_001E": "commute_total",
    "B08301_002E": "commute_auto",
    # Rent burden (B25070)
    "B25070_001E": "rb_total",
    "B25070_007E": "rb_30to35",
    "B25070_008E": "rb_35to40",
    "B25070_009E": "rb_40to50",
    "B25070_010E": "rb_50plus",
    # Owner burden, w/ mortgage (B25091)
    "B25091_001E": "ob_total",
    "B25091_008E": "ob_30to35",
    "B25091_009E": "ob_35to40",
    "B25091_010E": "ob_40to50",
    "B25091_011E": "ob_50plus",
    # B01001 65+ cohorts (12 variables)
    "B01001_020E": "age_m_65_66", "B01001_021E": "age_m_67_69",
    "B01001_022E": "age_m_70_74", "B01001_023E": "age_m_75_79",
    "B01001_024E": "age_m_80_84", "B01001_025E": "age_m_85p",
    "B01001_044E": "age_f_65_66", "B01001_045E": "age_f_67_69",
    "B01001_046E": "age_f_70_74", "B01001_047E": "age_f_75_79",
    "B01001_048E": "age_f_80_84", "B01001_049E": "age_f_85p",
}
COUNTIES = ["113", "085", "121"]  # Dallas, Collin, Denton (in TX = 48)


def fetch_acs(county_fips):
    """Pull all ACS_VARS for one county. Splits into chunks of 45 variables
    since the API caps at 50."""
    all_keys = list(ACS_VARS.keys())
    chunks = [all_keys[i:i+45] for i in range(0, len(all_keys), 45)]
    df = None
    for chunk in chunks:
        url = (
            "https://api.census.gov/data/2024/acs/acs5"
            f"?get={','.join(chunk)}&for=tract:*&in=state:48+county:{county_fips}"
        )
        if API_KEY: url += f"&key={API_KEY}"
        r = requests.get(url, timeout=120); r.raise_for_status()
        rows = r.json()
        sub = pd.DataFrame(rows[1:], columns=rows[0])
        sub["GEOID"] = sub["state"] + sub["county"] + sub["tract"]
        sub = sub.drop(columns=["state","county","tract"])
        for c in chunk:
            sub[c] = pd.to_numeric(sub[c], errors="coerce")
            sub.loc[sub[c] < 0, c] = np.nan  # Census negative = missing
        df = sub if df is None else df.merge(sub, on="GEOID", how="outer")
    return df


# ---------------------------------------------------------------------------
# Load all source data
# ---------------------------------------------------------------------------
log("Loading council districts...")
districts = gpd.read_file(os.path.join(PROJECT, "Council_Boundaries.geojson")).to_crs("EPSG:4326")
districts["geometry"] = districts["geometry"].apply(make_valid)
districts_ft = districts.to_crs(PROJ_FT)
districts_ft["_area_sqft"] = districts_ft.geometry.area
districts_ft["_area_sqmi"] = districts_ft["_area_sqft"] / 27_878_400

log("Loading tracts (TX)...")
tracts = gpd.read_file(os.path.join(PROJECT, "tl_2020_48_tract.zip")).to_crs("EPSG:4326")
tracts = tracts[tracts["COUNTYFP"].isin(COUNTIES)].copy()
tracts["geometry"] = tracts["geometry"].apply(make_valid)
tracts_ft = tracts.to_crs(PROJ_FT)
tracts_ft["_tract_area"] = tracts_ft.geometry.area

log("Pulling ACS 2024 5-year data...")
acs = pd.concat([fetch_acs(c) for c in COUNTIES], ignore_index=True)
acs = acs.rename(columns=ACS_VARS)
log(f"  ACS rows: {len(acs):,}")

# Derive aggregate 65+ pop
age65_cols = [c for c in acs.columns if c.startswith("age_m_") or c.startswith("age_f_")]
acs["pop_65p"] = acs[age65_cols].sum(axis=1, min_count=1)

log("Loading parcels (slow load)...")
parcels = gpd.read_file(os.path.join(PROJECT, "GDPC Claude Stuff", "PARCEL_CORE_MERGED.gpkg"))
parcels["geometry"] = parcels["geometry"].apply(make_valid)
parcels["area_feet"] = pd.to_numeric(parcels["area_feet"], errors="coerce")
parcels["building_sf"] = parcels["RES_TOT_MAIN_SF"]
m = parcels["building_sf"].isna() | (parcels["building_sf"] == 0)
parcels.loc[m, "building_sf"] = parcels.loc[m, "COM_GROSS_BLDG_AREA"]
parcels["building_sf"] = parcels["building_sf"].fillna(0)
parcels["total_units"] = parcels["RES_NUM_UNITS"].fillna(0) + parcels["COM_NUM_UNITS"].fillna(0)
parcels["floor_area_ratio"] = np.where(parcels["area_feet"] > 0, parcels["building_sf"] / parcels["area_feet"], np.nan)

# Year built
parcels["year_built"] = parcels["RES_YR_BUILT"]
m = parcels["year_built"].isna() | (parcels["year_built"] == 0)
parcels.loc[m, "year_built"] = parcels.loc[m, "COM_YEAR_BUILT"]
parcels["year_built_clean"] = parcels["year_built"].where(parcels["year_built"] >= 1850)

# FAR categories
def far_category(far):
    if pd.isna(far) or far <= 0: return "No Building"
    if far < 0.25: return "< 0.25"
    if far < 0.5:  return "0.25 - 0.49"
    if far < 1.0:  return "0.5 - 0.99"
    if far < 1.5:  return "1.0 - 1.49"
    if far <= 2.0: return "1.5 - 2.0"
    if far < 3.0:  return "2.0 - 2.9"
    if far < 5.0:  return "3.0 - 4.9"
    if far < 10.0: return "5.0 - 9.9"
    return "10+"
parcels["far_cat"] = parcels["floor_area_ratio"].apply(far_category)

# Decade-built categories (match the map's bins)
def decade_cat(yr):
    if pd.isna(yr) or yr < 1850: return "No data"
    if yr < 1940: return "Pre-1940"
    if yr < 2010: return f"{int(yr // 10 * 10)}s"
    return "2010 or later"
parcels["decade_cat"] = parcels["year_built_clean"].apply(decade_cat)

# MFR apartment subcategorization
apt = parcels["LAND_SPTD_DESC"] == "MFR - APARTMENTS"
u = parcels.loc[apt, "total_units"]
parcels.loc[apt & (u >= 3) & (u <= 4),  "LAND_SPTD_DESC"] = "MFR - 3-4 UNITS"
parcels.loc[apt & (u >= 5) & (u <= 19), "LAND_SPTD_DESC"] = "MFR - 5-19 UNITS"
parcels.loc[apt & (u >= 20)& (u <= 49), "LAND_SPTD_DESC"] = "MFR - 20-49 UNITS"
parcels.loc[apt & (u >= 50),            "LAND_SPTD_DESC"] = "MFR - 50+ UNITS"

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
parcels["land_use_cat"] = parcels["LAND_SPTD_DESC"].map(LAND_USE_MAP).fillna("Other")
parcels_ft = parcels.to_crs(PROJ_FT)
parcels_ft["_orig_area"] = parcels_ft.geometry.area
_ = parcels_ft.sindex

log("Loading zoning...")
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

zoning = gpd.read_file(os.path.join(PROJECT, "Base_Zoning.geojson")).to_crs("EPSG:4326")
zoning["geometry"] = zoning["geometry"].apply(make_valid)
zoning["zone_norm"] = zoning["ZONE_DIST"].apply(normalize_zone)
zoning["category"] = zoning["zone_norm"].apply(categorize_zone)
zoning_ft = zoning.to_crs(PROJ_FT)
_ = zoning_ft.sindex

log("Loading rail stops + station areas...")
rail_stops = gpd.read_file(os.path.join(PROJECT, "GDPC Claude Stuff", "Rail_Stops.geojson")).to_crs("EPSG:4326")
station_areas = gpd.read_file(os.path.join(PROJECT, "webmap", "data", "station_areas.geojson")).to_crs("EPSG:4326")
rail_stops_ft = rail_stops.to_crs(PROJ_FT)
station_areas_ft = station_areas.to_crs(PROJ_FT)
station_areas_union = unary_union(station_areas_ft.geometry)

log("Loading permits (Building, UNITS>=1, 2010+, Complete/Issued, deduped)...")
permits_all = gpd.read_file(os.path.join(PROJECT, "NewPermit_1971_2024.geojson"))
m = (
    permits_all["PERMIT_TYPE"].fillna("").str.startswith("Building")
    & (permits_all["UNITS"].fillna(0) >= 1)
    & (permits_all["Issue_Year"].fillna(0) >= 2010)
    & (permits_all["Status"].isin(["Complete", "Issued"]))
)
permits = permits_all[m].copy()
ACTIVITY_PRIORITY = {"(A) New Construction":0,"(B) Reconstruction":1,"(G) Addition":2,
                     "(B) Finish Out":3,"(B) Renovation":4,"(B) Alteration":5}
permits["_rank"] = permits["ACTIVITY"].map(ACTIVITY_PRIORITY).fillna(99)
permits["ISSUE_DATE"] = pd.to_datetime(permits["ISSUE_DATE"], errors="coerce").dt.tz_localize(None)
permits = permits.sort_values("_rank").drop_duplicates(subset=["ISSUE_DATE","ADDRESS","UNITS"], keep="first")
permits["UNITS"] = permits["UNITS"].astype(int)
permits_ft = permits.to_crs(PROJ_FT)
log(f"  {len(permits_ft):,} permits after filtering+dedup")

log("Loading 2010-2020 BG change data...")
bg_change = pd.read_excel(
    os.path.join(PROJECT, "decennial_data_2010_2020.xlsx"),
    sheet_name="Block Group Level",
)
bg_change["GEOID"] = bg_change["GEOID"].astype(str).str.zfill(12)
bgs = gpd.read_file(os.path.join(PROJECT, "tl_2020_48_bg.zip")).to_crs("EPSG:4326")
bgs = bgs[bgs["COUNTYFP"].isin(COUNTIES)].copy()
bgs["geometry"] = bgs["geometry"].apply(make_valid)
bgs_ft = bgs.to_crs(PROJ_FT)
bgs_ft = bgs_ft.merge(bg_change, on="GEOID", how="inner")
bgs_ft["_bg_area"] = bgs_ft.geometry.area


# ---------------------------------------------------------------------------
# Per-district computation
# ---------------------------------------------------------------------------
def pct(a, b):
    if not b or b <= 0 or pd.isna(b): return None
    return round((a / b) * 100, 1)

def safeint(v):
    if v is None or pd.isna(v): return None
    return int(round(v))

def safe(v, decimals=None):
    if v is None or pd.isna(v): return None
    return round(float(v), decimals) if decimals is not None else float(v)


def apportion_acs(district_geom):
    """Area-weighted apportionment of tract ACS data to a district polygon.
    Returns a dict of derived statistics."""
    # Tracts overlapping district, by area weight
    cand_idx = list(tracts_ft.sindex.intersection(district_geom.bounds))
    cand = tracts_ft.iloc[cand_idx]
    clip = cand.geometry.intersection(district_geom)
    area_in = clip.area
    weights = (area_in / cand["_tract_area"].values).clip(lower=0, upper=1)
    # Merge ACS
    df = cand[["GEOID"]].copy()
    df["w"] = weights.values
    df = df.merge(acs, on="GEOID", how="left")
    df = df[df["w"] > 0]

    if df.empty:
        return {}

    # Count-type variables — apportion by area weight
    count_vars = ["pop","pop_under_18","pop_65p","hu_acs","hu_occupied","hu_vacant",
                  "hh_owner","hh_renter","pob_total","pob_foreign",
                  "race_total","race_nh_white","race_nh_black","race_nh_asian","race_hispanic",
                  "edu_total25","edu_bach","edu_mast","edu_prof","edu_doc",
                  "occ_total","occ_own_1to1_5","occ_own_1_5to2","occ_own_2plus",
                  "occ_rent_1to1_5","occ_rent_1_5to2","occ_rent_2plus",
                  "veh_total","veh_own_none","veh_rent_none",
                  "commute_total","commute_auto",
                  "rb_total","rb_30to35","rb_35to40","rb_40to50","rb_50plus",
                  "ob_total","ob_30to35","ob_35to40","ob_40to50","ob_50plus"]
    counts = {v: float((df[v].fillna(0) * df["w"]).sum()) for v in count_vars if v in df.columns}

    # Median-type variables — population-weighted average across contributing tracts
    median_vars = ["med_age", "mhi", "mfi", "med_yr_built", "med_home_value", "med_rent",
                   "avg_hh_size"]
    medians = {}
    for v in median_vars:
        if v not in df.columns: continue
        mask = df[v].notna() & (df["w"] > 0)
        if not mask.any(): medians[v] = None; continue
        # Weight by apportioned population (or by area if pop missing)
        weight = (df.loc[mask, "pop"].fillna(0) * df.loc[mask, "w"]).values
        if weight.sum() <= 0:
            weight = df.loc[mask, "w"].values
        if weight.sum() <= 0:
            medians[v] = None
        else:
            medians[v] = float((df.loc[mask, v] * weight).sum() / weight.sum())

    # Compute the derived statistics we'll surface in the report
    return {
        # At-a-glance
        "pop": safeint(counts.get("pop")),
        "hu_acs": safeint(counts.get("hu_acs")),
        "med_age": safe(medians.get("med_age"), 1),
        "mhi": safeint(medians.get("mhi")),
        "mfi": safeint(medians.get("mfi")),
        # Housing stock
        "avg_hh_size": safe(medians.get("avg_hh_size"), 2),
        "med_yr_built": safeint(medians.get("med_yr_built")),
        "pct_owner": pct(counts.get("hh_owner", 0), counts.get("hh_owner", 0) + counts.get("hh_renter", 0)),
        "vacancy_rate": pct(counts.get("hu_vacant", 0), counts.get("hu_vacant", 0) + counts.get("hu_occupied", 0)),
        "pct_overcrowded": pct(
            sum(counts.get(k, 0) for k in ["occ_own_1to1_5","occ_own_1_5to2","occ_own_2plus",
                                            "occ_rent_1to1_5","occ_rent_1_5to2","occ_rent_2plus"]),
            counts.get("occ_total", 0),
        ),
        # Housing costs
        "med_home_value": safeint(medians.get("med_home_value")),
        "med_rent": safeint(medians.get("med_rent")),
        "pct_renter_cb": pct(
            sum(counts.get(k, 0) for k in ["rb_30to35","rb_35to40","rb_40to50","rb_50plus"]),
            counts.get("rb_total", 0),
        ),
        "pct_renter_scb": pct(counts.get("rb_50plus", 0), counts.get("rb_total", 0)),
        "pct_owner_cb": pct(
            sum(counts.get(k, 0) for k in ["ob_30to35","ob_35to40","ob_40to50","ob_50plus"]),
            counts.get("ob_total", 0),
        ),
        "pct_owner_scb": pct(counts.get("ob_50plus", 0), counts.get("ob_total", 0)),
        # People
        "pct_under_18": pct(counts.get("pop_under_18", 0), counts.get("pop", 0)),
        "pct_65plus": pct(counts.get("pop_65p", 0), counts.get("pop", 0)),
        "pct_hispanic": pct(counts.get("race_hispanic", 0), counts.get("race_total", 0)),
        "pct_nh_white": pct(counts.get("race_nh_white", 0), counts.get("race_total", 0)),
        "pct_nh_black": pct(counts.get("race_nh_black", 0), counts.get("race_total", 0)),
        "pct_nh_asian": pct(counts.get("race_nh_asian", 0), counts.get("race_total", 0)),
        "pct_other": pct(
            counts.get("race_total", 0) - counts.get("race_hispanic", 0)
            - counts.get("race_nh_white", 0) - counts.get("race_nh_black", 0)
            - counts.get("race_nh_asian", 0),
            counts.get("race_total", 0),
        ),
        "pct_foreign_born": pct(counts.get("pob_foreign", 0), counts.get("pob_total", 0)),
        "pct_bach_or_higher": pct(
            sum(counts.get(k, 0) for k in ["edu_bach","edu_mast","edu_prof","edu_doc"]),
            counts.get("edu_total25", 0),
        ),
        # Mobility
        "pct_no_vehicle": pct(
            counts.get("veh_own_none", 0) + counts.get("veh_rent_none", 0),
            counts.get("veh_total", 0),
        ),
        "pct_non_auto_commute": pct(
            counts.get("commute_total", 0) - counts.get("commute_auto", 0),
            counts.get("commute_total", 0),
        ),
    }


def parcel_intersection_stats(district_geom):
    p_idx = list(parcels_ft.sindex.intersection(district_geom.bounds))
    cand = parcels_ft.iloc[p_idx]
    clip = cand.geometry.intersection(district_geom)
    clip_area = clip.area
    df = pd.DataFrame({
        "land_use_cat": cand["land_use_cat"].values,
        "far_cat":      cand["far_cat"].values,
        "decade_cat":   cand["decade_cat"].values,
        "total_units":  cand["total_units"].values,
        "building_sf":  cand["building_sf"].values,
        "orig_area":    cand["_orig_area"].values,
        "clip_area":    clip_area.values,
    })
    df["frac"] = (df["clip_area"] / df["orig_area"].replace(0, np.nan)).fillna(0).clip(upper=1.0)
    p_total = df["clip_area"].sum()

    # Group vacant types for land use mix
    df["land_use_grp"] = np.where(df["land_use_cat"].isin(LAND_USE_VACANT), "Vacant", df["land_use_cat"])

    landuse_pct = (df.groupby("land_use_grp")["clip_area"].sum() / p_total * 100).round(1).to_dict() if p_total > 0 else {}
    far_pct     = (df.groupby("far_cat")["clip_area"].sum() / p_total * 100).round(1).to_dict() if p_total > 0 else {}
    decade_pct  = (df.groupby("decade_cat")["clip_area"].sum() / p_total * 100).round(1).to_dict() if p_total > 0 else {}

    units = int(round(float((df["total_units"].fillna(0) * df["frac"]).sum())))
    bldg_sf = int(round(float((df["building_sf"].fillna(0) * df["frac"]).sum())))
    return {
        "dcad_units": units,
        "dcad_bldg_sf": bldg_sf,
        "land_use_pct": landuse_pct,
        "far_pct": far_pct,
        "decade_pct": decade_pct,
    }


def zoning_intersection_stats(district_geom):
    z_idx = list(zoning_ft.sindex.intersection(district_geom.bounds))
    cand = zoning_ft.iloc[z_idx]
    clip = cand.geometry.intersection(district_geom)
    areas = clip.area
    df = pd.DataFrame({"category": cand["category"].values, "a": areas.values})
    total = df["a"].sum()
    return (df.groupby("category")["a"].sum() / total * 100).round(1).to_dict() if total > 0 else {}


def permits_stats(district_geom):
    # Spatial: keep permits whose point is inside the district
    p_idx = list(permits_ft.sindex.intersection(district_geom.bounds))
    cand = permits_ft.iloc[p_idx]
    inside = cand[cand.geometry.within(district_geom)]
    by_type = inside.groupby("Type")["UNITS"].sum()
    sf = int(by_type.get("Single Family", 0))
    mf = int(by_type.get("Multi Family", 0))
    com = int(by_type.get("Commercial", 0))
    return {"permit_units_sf": sf, "permit_units_mf": mf, "permit_units_com": com,
            "permit_units_total": sf + mf + com}


def transit_stats(district_geom):
    n_rail = int(rail_stops_ft.geometry.within(district_geom).sum())
    # % of district within 1/2 mile of a rail station
    overlap = district_geom.intersection(station_areas_union).area
    pct_in_buf = round(overlap / district_geom.area * 100, 1) if district_geom.area > 0 else 0
    return {"rail_stations": n_rail, "pct_within_half_mi_rail": pct_in_buf}


def change_2010_2020(district_geom):
    # Area-weighted sum from BGs whose centroid is in the district
    # (simpler than full intersection apportionment, and consistent with how
    # the spreadsheet was built).
    cand = bgs_ft[bgs_ft.geometry.centroid.within(district_geom)]
    if cand.empty:
        return {"pop_2010": None, "pop_2020": None, "pop_change": None,
                "hu_2010": None, "hu_2020": None, "hu_change": None}
    s = cand[["pop_2010","pop_2020","hu_2010","hu_2020"]].sum()
    return {
        "pop_2010": int(s["pop_2010"]),
        "pop_2020": int(s["pop_2020"]),
        "pop_change": int(s["pop_2020"] - s["pop_2010"]),
        "hu_2010": int(s["hu_2010"]),
        "hu_2020": int(s["hu_2020"]),
        "hu_change": int(s["hu_2020"] - s["hu_2010"]),
    }


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
reports = []
for idx, row in districts_ft.iterrows():
    g = row.geometry
    name = row.get("COUNCILPER", "")
    dist_num = row.get("DISTRICT", "")
    area_sqmi = row["_area_sqmi"]
    log(f"District {dist_num} ({name})  area={area_sqmi:.1f} sq mi")

    acs_stats = apportion_acs(g)
    parcel_stats = parcel_intersection_stats(g)
    zoning_pct   = zoning_intersection_stats(g)
    permit_stats = permits_stats(g)
    transit      = transit_stats(g)
    change       = change_2010_2020(g)

    pop = acs_stats.get("pop")
    density = round(pop / area_sqmi) if pop and area_sqmi > 0 else None

    reports.append({
        "district": str(dist_num),
        "council_member": name,
        "area_sqmi": round(area_sqmi, 2),
        "density": density,
        **acs_stats,
        **parcel_stats,
        "zoning_pct": zoning_pct,
        **permit_stats,
        **transit,
        **change,
    })

# Sort by district number (numeric)
reports.sort(key=lambda r: int(r["district"]))

with open(OUT_PATH, "w") as f:
    json.dump({"districts": reports}, f, separators=(",", ":"))
log(f"Saved {OUT_PATH} ({os.path.getsize(OUT_PATH)/1024:.1f} KB)")
