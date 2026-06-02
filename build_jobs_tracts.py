"""
Build a tract-level Jobs GeoJSON for the webmap.

Coverage: Dallas County + adjacent counties (Collin, Denton, Tarrant, Ellis,
Kaufman, Rockwall) — 7 counties total.

Data source: LEHD LODES8 WAC (Workplace Area Characteristics), 2022, TX,
segment S000 (all workers), job type JT00 (all jobs).
    https://lehd.ces.census.gov/data/lodes/LODES8/tx/wac/

Output fields per tract:
    geoid                — 11-digit tract GEOID
    county_fips          — first 5 chars of GEOID
    land_sq_mi           — land area (from TIGER ALAND10)
    jobs_total           — C000 = total workplace jobs
    jobs_per_acre        — density, jobs / (land_sq_mi * 640)
    jobs_share_pct       — tract jobs / sum of jobs across 7-county area, ×100
    jobs_low             — CE01: jobs paying <= $1,250/month (~$15k/yr)
    jobs_mid             — CE02: $1,251-$3,333/month ($15k-$40k/yr)
    jobs_high            — CE03: > $3,333/month (>$40k/yr)
    sec_<NAICS>          — CNS01..CNS20 sector breakdowns
    wages_midpoint       — estimated total annual payroll, midpoint method
    wages_sector         — estimated total annual payroll, BLS sector-weighted method
    wages_midpoint_per_acre, wages_sector_per_acre

Two wage estimation methods are computed side-by-side for comparison:

  Midpoint method (simple): assume each wage bucket's average annual wage:
    CE01 (low):  $10,000/yr
    CE02 (mid):  $27,500/yr   (true midpoint of $15-40k)
    CE03 (high): $80,000/yr   (rough Dallas MSA average above $40k)

  Sector-weighted method (BLS-based): sum across CNS01..CNS20 the count of
  jobs times the published BLS QCEW 2022 Dallas-Fort Worth-Arlington MSA
  average annual wage for that NAICS sector. Values below are from BLS
  QCEW MSA 31080 (Dallas-Fort Worth-Arlington), 2022 annual averages,
  rounded to the nearest $1,000. These are private + government combined.
"""

import os
import io
import time
import numpy as np
import pandas as pd
import geopandas as gpd

WEBMAP_DIR  = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(WEBMAP_DIR)
OUT_PATH    = os.path.join(WEBMAP_DIR, "data", "jobs_tracts.geojson")

LODES_GZ    = os.path.join(PROJECT_DIR, "lodes_tx_wac_2022.csv.gz")
TRACT_ZIP   = os.path.join(PROJECT_DIR, "tl_2020_48_tract.zip")

# 7-county target (Dallas + adjacent)
COUNTY_FIPS = {
    "113": "Dallas",
    "085": "Collin",
    "121": "Denton",
    "439": "Tarrant",
    "139": "Ellis",
    "257": "Kaufman",
    "397": "Rockwall",
}
STATE_FIPS = "48"
FULL_COUNTY_FIPS = [STATE_FIPS + c for c in COUNTY_FIPS]   # ["48113", ...]

t0 = time.time()
def log(msg): print(f"[{time.time()-t0:.0f}s] {msg}", flush=True)


# ---------------------------------------------------------------------------
# Wage assumptions (documented above)
# ---------------------------------------------------------------------------
MIDPOINT_WAGES = {"CE01": 10000.0, "CE02": 27500.0, "CE03": 80000.0}

# BLS QCEW 2022 Dallas-Fort Worth-Arlington MSA average annual wages, by NAICS
# 2-digit sector. Values from BLS QCEW Table 5 (Industry: NAICS, Ownership:
# Total Covered, Area: 31080 Dallas-Fort Worth-Arlington MSA, Year: 2022).
# Rounded to the nearest $1,000.
SECTOR_WAGES = {
    "CNS01":  45000,  # 11 Agriculture, Forestry, Fishing
    "CNS02": 130000,  # 21 Mining (oil/gas in Texas)
    "CNS03": 130000,  # 22 Utilities
    "CNS04":  66000,  # 23 Construction
    "CNS05":  85000,  # 31-33 Manufacturing
    "CNS06":  93000,  # 42 Wholesale Trade
    "CNS07":  43000,  # 44-45 Retail Trade
    "CNS08":  59000,  # 48-49 Transportation & Warehousing
    "CNS09": 124000,  # 51 Information
    "CNS10": 135000,  # 52 Finance and Insurance
    "CNS11":  78000,  # 53 Real Estate, Rental, Leasing
    "CNS12": 115000,  # 54 Professional, Scientific, Technical Services
    "CNS13": 185000,  # 55 Management of Companies and Enterprises
    "CNS14":  52000,  # 56 Admin & Support, Waste Mgmt
    "CNS15":  52000,  # 61 Educational Services
    "CNS16":  66000,  # 62 Health Care and Social Assistance
    "CNS17":  43000,  # 71 Arts, Entertainment, Recreation
    "CNS18":  25000,  # 72 Accommodation & Food Services
    "CNS19":  40000,  # 81 Other Services
    "CNS20":  80000,  # 92 Public Administration
}

# Friendly names for the popup
SECTOR_LABELS = {
    "CNS01": "Agriculture & Forestry",
    "CNS02": "Mining / Oil & Gas",
    "CNS03": "Utilities",
    "CNS04": "Construction",
    "CNS05": "Manufacturing",
    "CNS06": "Wholesale Trade",
    "CNS07": "Retail Trade",
    "CNS08": "Transportation & Warehousing",
    "CNS09": "Information",
    "CNS10": "Finance & Insurance",
    "CNS11": "Real Estate",
    "CNS12": "Professional Services",
    "CNS13": "Mgmt of Companies",
    "CNS14": "Admin & Support",
    "CNS15": "Educational Services",
    "CNS16": "Health Care",
    "CNS17": "Arts & Entertainment",
    "CNS18": "Accommodation & Food",
    "CNS19": "Other Services",
    "CNS20": "Public Administration",
}

# ---------------------------------------------------------------------------
# 1. Load LODES, filter to 7 counties, aggregate to tract
# ---------------------------------------------------------------------------
log(f"Loading LODES: {LODES_GZ}")
wac_cols = ["w_geocode", "C000", "CE01", "CE02", "CE03"] + list(SECTOR_WAGES.keys())
wac = pd.read_csv(LODES_GZ, dtype={"w_geocode": str}, usecols=wac_cols)
log(f"  Statewide block rows: {len(wac):,}")

# County is chars 0-4 of the 15-digit block GEOID
wac["county_fips"] = wac["w_geocode"].str[:5]
wac = wac[wac["county_fips"].isin(FULL_COUNTY_FIPS)].copy()
log(f"  Rows in 7-county area: {len(wac):,}")

# Tract is chars 0-10 of block GEOID
wac["geoid"] = wac["w_geocode"].str[:11]

# Aggregate
sum_cols = ["C000", "CE01", "CE02", "CE03"] + list(SECTOR_WAGES.keys())
tract = wac.groupby("geoid")[sum_cols].sum().reset_index()
tract["county_fips"] = tract["geoid"].str[:5]
log(f"  Tracts with any jobs: {len(tract):,}")

# Rename core columns to friendlier names
tract = tract.rename(columns={
    "C000": "jobs_total",
    "CE01": "jobs_low",
    "CE02": "jobs_mid",
    "CE03": "jobs_high",
})

# Job share (% of 7-county total)
all_jobs_total = float(tract["jobs_total"].sum())
log(f"  Total jobs across 7 counties: {all_jobs_total:,.0f}")
tract["jobs_share_pct"] = (tract["jobs_total"] / all_jobs_total * 100).round(3)

# Wages — midpoint method
tract["wages_midpoint"] = (
    tract["jobs_low"]  * MIDPOINT_WAGES["CE01"] +
    tract["jobs_mid"]  * MIDPOINT_WAGES["CE02"] +
    tract["jobs_high"] * MIDPOINT_WAGES["CE03"]
).round(0).astype(np.int64)

# Wages — sector-weighted (BLS)
wages_sector = np.zeros(len(tract), dtype=np.float64)
for sec, wage in SECTOR_WAGES.items():
    wages_sector += tract[sec].values * wage
tract["wages_sector"] = wages_sector.round(0).astype(np.int64)

# Sector-bucketed wage bins (3 bins). Each NAICS sector is assigned to one
# bin based on its Dallas-MSA BLS average wage. All jobs in that sector
# count toward that bin in every tract. This is a sector-level proxy for
# what fraction of workers earn within each band — it's not a per-job
# measurement (LODES doesn't ship that granularity above $40k).
SECTOR_BIN = {sec: ("under_50k" if w < 50000 else "50_to_100k" if w < 100000 else "over_100k")
              for sec, w in SECTOR_WAGES.items()}
tract["jobs_under_50k"]   = sum(tract[s] for s, b in SECTOR_BIN.items() if b == "under_50k")
tract["jobs_50_to_100k"]  = sum(tract[s] for s, b in SECTOR_BIN.items() if b == "50_to_100k")
tract["jobs_over_100k"]   = sum(tract[s] for s, b in SECTOR_BIN.items() if b == "over_100k")


# ---------------------------------------------------------------------------
# 2. Load tract geometry, compute land area & density
# ---------------------------------------------------------------------------
log(f"Loading TIGER tracts: {TRACT_ZIP}")
geom = gpd.read_file(f"zip://{TRACT_ZIP}")
geom = geom[geom["COUNTYFP"].isin(list(COUNTY_FIPS))].copy()
geom["geoid"] = geom["GEOID"].astype(str)
log(f"  Tracts in 7-county area: {len(geom):,}")

# ALAND10 / ALAND is in square meters; convert to sq miles
land_col = "ALAND" if "ALAND" in geom.columns else "ALAND10"
geom["land_sq_mi"] = (geom[land_col].astype(float) / 2589988.110336).round(4)

# Densities — jobs/acre, wages/acre. 1 sq mi = 640 acres.
def per_acre(numer, denom_sq_mi):
    acres = denom_sq_mi * 640.0
    out = np.where(acres > 0, numer / acres, 0)
    return np.nan_to_num(out, nan=0.0)


# ---------------------------------------------------------------------------
# 3. Merge data + geometry
# ---------------------------------------------------------------------------
merged = geom[["geoid", "land_sq_mi", "geometry"]].merge(tract, on="geoid", how="left")
# Fill no-jobs tracts (e.g., parks, airport runways) with zeros
fill_cols = ["jobs_total","jobs_low","jobs_mid","jobs_high","wages_midpoint","wages_sector"] + list(SECTOR_WAGES.keys())
fill_cols += ["jobs_under_50k", "jobs_50_to_100k", "jobs_over_100k"]
merged[fill_cols] = merged[fill_cols].fillna(0)
merged["jobs_share_pct"] = merged["jobs_share_pct"].fillna(0)
merged["county_fips"] = merged["geoid"].str[:5]

merged["jobs_per_acre"]           = per_acre(merged["jobs_total"], merged["land_sq_mi"]).round(2)
merged["wages_midpoint_per_acre"] = per_acre(merged["wages_midpoint"], merged["land_sq_mi"]).round(0).astype(np.int64)
merged["wages_sector_per_acre"]   = per_acre(merged["wages_sector"], merged["land_sq_mi"]).round(0).astype(np.int64)

# Tidy int casts
int_cols = ["jobs_total","jobs_low","jobs_mid","jobs_high",
            "jobs_under_50k","jobs_50_to_100k","jobs_over_100k"] + list(SECTOR_WAGES.keys())
for c in int_cols:
    merged[c] = merged[c].astype(np.int64)

# Simplify geometry to ~10m (in degrees, ~1e-4)
log("Simplifying geometry...")
merged["geometry"] = merged["geometry"].simplify(0.0001, preserve_topology=True)

log(f"Writing {OUT_PATH} ...")
merged_out = merged.to_crs(4326)
merged_out.to_file(OUT_PATH, driver="GeoJSON")
log(f"  wrote {len(merged_out):,} tracts")
log("Done.")
