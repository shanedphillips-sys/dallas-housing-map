"""
Build ZIP-level (ZCTA) Zillow home-value (ZHVI) and rent (ZORI) change layers
for the webmap, covering the 7-county region (Dallas + Collin, Denton, Tarrant,
Ellis, Kaufman, Rockwall).

Inputs (raw Zillow monthly ZIP files, gitignored — too big / 122 MB to commit):
  data/Zip_zhvi_uc_sfrcondo_tier_0.33_0.67_sm_sa_month.csv   home value, 2000-01+
  data/Zip_zori_uc_sfrcondomfr_sm_month.csv                  rent (ZORI), 2015-01+

Geometry: cb_2020 generalized ZCTA boundaries (national), filtered to the ZIPs
Zillow assigns to our 7 counties.

Annualization: per ZIP, average all available months within a calendar year ->
one annual figure. Years 2010..2025 for ZHVI; 2015..2025 for ZORI (no earlier
data exists, which is why the webmap cross-hatches ZIPs lacking the chosen start
year). A year with no months for a ZIP is null.

Inflation: deflated to constant 2024$ via CPI-U annual averages
(data/cpi_annual.json): real_2024 = nominal_year * CPI[2024] / CPI[year].

Output: data/zillow_zip.geojson
  props per ZIP: zip, city, county, zhvi_2010..zhvi_2025, zori_2015..zori_2025
  (integers in constant 2024$, or null where Zillow has no value that year).
Only ZIPs with at least one non-null value (either metric) are included; ZIPs
Zillow never covers are simply absent (render as background, distinct from the
cross-hatch used for "covered, but not back to your start year").
"""

import json
import os
import time
import numpy as np
import pandas as pd
import geopandas as gpd
from shapely.geometry import mapping

WEBMAP_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(WEBMAP_DIR)
DATA_DIR = os.path.join(WEBMAP_DIR, "data")

ZHVI_CSV = os.path.join(DATA_DIR, "Zip_zhvi_uc_sfrcondo_tier_0.33_0.67_sm_sa_month.csv")
ZORI_CSV = os.path.join(DATA_DIR, "Zip_zori_uc_sfrcondomfr_sm_month.csv")
CPI_JSON = os.path.join(DATA_DIR, "cpi_annual.json")
ZCTA_ZIP = os.path.join(PROJECT_DIR, "cb_2020_us_zcta520_500k.zip")
OUT_PATH = os.path.join(DATA_DIR, "zillow_zip.geojson")

COUNTY_NAMES = {"Dallas County", "Collin County", "Denton County",
                "Tarrant County", "Ellis County", "Kaufman County",
                "Rockwall County"}

ZHVI_YEARS = list(range(2010, 2026))   # 2010..2025
ZORI_YEARS = list(range(2015, 2026))   # 2015..2025

t0 = time.time()
def log(msg): print(f"[{time.time()-t0:.0f}s] {msg}", flush=True)

def clean(x):
    """NaN/NaT -> None (pandas yields NaN for blank City/CountyName; a bare
    NaN token is invalid JSON for the browser even though Python tolerates it)."""
    return None if pd.isna(x) else x

with open(CPI_JSON) as f:
    cpi = {int(k): float(v) for k, v in json.load(f).items()}
base = cpi[2024]


def annualize(csv_path, prefix, years):
    """Read a Zillow monthly ZIP file, filter to our counties, return
    {zip: {f'{prefix}_{year}': real_2024_int_or_None}}, plus a city/county map."""
    log(f"Reading {os.path.basename(csv_path)} ...")
    df = pd.read_csv(csv_path, dtype={"RegionName": str})
    df = df[(df["State"] == "TX") & (df["CountyName"].isin(COUNTY_NAMES))].copy()
    df["zip"] = df["RegionName"].str.zfill(5)
    log(f"  {len(df)} ZIPs in 7-county area")

    date_cols = [c for c in df.columns if len(c) == 10 and c[4] == "-" and c[:4].isdigit()]
    by_year = {}
    for y in years:
        cols = [c for c in date_cols if c.startswith(f"{y}-")]
        if cols:
            by_year[y] = df[cols].mean(axis=1, skipna=True)   # NaN if all months NaN

    out = {}
    meta = {}
    for i, row in df.iterrows():
        z = row["zip"]
        meta[z] = {"city": clean(row.get("City")), "county": clean(row.get("CountyName"))}
        rec = {}
        for y in years:
            if y in by_year:
                v = by_year[y].loc[i]
                rec[f"{prefix}_{y}"] = int(round(v * base / cpi[y])) if pd.notna(v) else None
            else:
                rec[f"{prefix}_{y}"] = None
        out[z] = rec
    return out, meta


zhvi, meta1 = annualize(ZHVI_CSV, "zhvi", ZHVI_YEARS)
zori, meta2 = annualize(ZORI_CSV, "zori", ZORI_YEARS)

# Union of ZIPs and metadata (prefer ZHVI metadata, fall back to ZORI).
zips = sorted(set(zhvi) | set(zori))
meta = {**meta2, **meta1}
log(f"Total unique ZIPs with any Zillow data: {len(zips)}")

props = {}
for z in zips:
    p = {"zip": z, "city": meta.get(z, {}).get("city"),
         "county": meta.get(z, {}).get("county")}
    p.update(zhvi.get(z, {f"zhvi_{y}": None for y in ZHVI_YEARS}))
    p.update(zori.get(z, {f"zori_{y}": None for y in ZORI_YEARS}))
    # Per-metric coverage flags let the webmap tell apart three states:
    #   colored (computable for the chosen range), cross-hatched (covered but
    #   the series starts after the chosen start year), and no-data (this ZIP
    #   has no value for this metric in any year -> rendered as background).
    p["has_zhvi"] = any(p[f"zhvi_{y}"] is not None for y in ZHVI_YEARS)
    p["has_zori"] = any(p[f"zori_{y}"] is not None for y in ZORI_YEARS)
    props[z] = p


# ---------------------------------------------------------------------------
# Geometry: filter national ZCTAs to our ZIP set, simplify, write GeoJSON.
# ---------------------------------------------------------------------------
log("Loading ZCTA geometry ...")
g = gpd.read_file(f"zip://{ZCTA_ZIP}")
zcta_col = "ZCTA5CE20" if "ZCTA5CE20" in g.columns else "GEOID20"
g["zip"] = g[zcta_col].astype(str).str.zfill(5)
g = g[g["zip"].isin(set(zips))].copy()
g = g.to_crs(4326)
g["geometry"] = g["geometry"].simplify(0.0003, preserve_topology=True)
log(f"  matched {len(g)} ZCTA polygons (of {len(zips)} Zillow ZIPs)")

features = []
for _, row in g.iterrows():
    z = row["zip"]
    features.append({
        "type": "Feature",
        "properties": props[z],
        "geometry": mapping(row["geometry"]),
    })

out = {"type": "FeatureCollection", "name": "zillow_zip", "features": features}
with open(OUT_PATH, "w") as f:
    json.dump(out, f, allow_nan=False)   # raise on stray NaN rather than emit invalid JSON

size_mb = os.path.getsize(OUT_PATH) / 1e6
log(f"Wrote {OUT_PATH}  ({len(features)} ZIPs, {size_mb:.1f} MB)")

unmatched = sorted(set(zips) - set(g["zip"]))
if unmatched:
    log(f"  {len(unmatched)} Zillow ZIPs had no ZCTA match (dropped): {unmatched[:10]}...")

# Spot-checks
for z in [f for f in ["75201", "75204", "75080", "75024"] if f in props]:
    p = props[z]
    log(f"  e.g. {z} ({p['city']}): zhvi {p.get('zhvi_2010')}->{p.get('zhvi_2025')} (2024$), "
        f"zori {p.get('zori_2015')}->{p.get('zori_2025')} (2024$)")
log("Done.")
