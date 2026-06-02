"""
Build tract-level and block-group-level Population & Housing-Unit change
GeoJSONs for the webmap, covering Dallas County + 6 adjacent counties.

Counties: Dallas, Collin, Denton, Tarrant, Ellis, Kaufman, Rockwall.

Methodology — block-level crosswalk
-----------------------------------
Because BG boundaries can shift meaningfully between 2010 and 2020, an
area-weighted crosswalk at the BG level dumps a lot of population across
the wrong side of a redrawn boundary (it assumes uniform population
density within each 2010 BG, which is usually false near edges).

To avoid that artifact, 2010 data is pulled at the BLOCK level (P001001 /
H001001), then crosswalked to 2020 blocks via the Census Bureau's
TAB2010_TAB2020 block-level relationship file, then aggregated up to 2020
BGs and tracts. Blocks are small enough (~50–100 people typically) that
the within-block uniform-density assumption introduces minimal error,
and the vast majority of 2010 blocks fall entirely inside a single 2020
block (weight = 1.0).

Sources
-------
- 2010 Decennial SF1   https://api.census.gov/data/2010/dec/sf1   (block level)
- 2020 Decennial DHC   https://api.census.gov/data/2020/dec/dhc   (BG level)
- TAB2010_TAB2020 block relationship (state 48)
    TAB2010_TAB2020_ST48.zip in project root

Outputs
-------
  data/block_groups.geojson
  data/tracts.geojson

Schema (same as before):
  geoid, land_sq_mi, pop_2010, pop_2020, pop_change, hu_2010, hu_2020,
  hu_change, density_2010, density_2020, low_density, geometry
"""

import io
import os
import time
import zipfile
import numpy as np
import pandas as pd
import requests
import geopandas as gpd

WEBMAP_DIR  = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(WEBMAP_DIR)

API_KEY = os.environ.get("CENSUS_API_KEY", "")

STATE_FIPS    = "48"
COUNTY_FIPS   = ["113", "085", "121", "439", "139", "257", "397"]  # 7 counties

TRACT_ZIP   = os.path.join(PROJECT_DIR, "tl_2020_48_tract.zip")
BG_ZIP      = os.path.join(PROJECT_DIR, "tl_2020_48_bg.zip")
BLOCK_XW_ZIP = os.path.join(PROJECT_DIR, "TAB2010_TAB2020_ST48.zip")

LOW_DENSITY_PSM = 1000

t0 = time.time()
def log(msg): print(f"[{time.time()-t0:.0f}s] {msg}", flush=True)


# ---------------------------------------------------------------------------
# Helper: Census API fetch with retry
# ---------------------------------------------------------------------------
def census_get(url):
    last_err = None
    for attempt in range(3):
        try:
            r = requests.get(url, timeout=120)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last_err = e
            time.sleep(2 ** attempt)
    raise last_err


# ---------------------------------------------------------------------------
# 1. Pull 2020 DHC pop/HU at BG level for 7 counties
# ---------------------------------------------------------------------------
log("Pulling 2020 DHC BG pop/HU for 7 counties ...")
key_q = f"&key={API_KEY}" if API_KEY else ""
frames = []
for cfips in COUNTY_FIPS:
    url = (f"https://api.census.gov/data/2020/dec/dhc?get=P1_001N,H1_001N"
           f"&for=block%20group:*&in=state:{STATE_FIPS}+county:{cfips}{key_q}")
    j = census_get(url)
    df = pd.DataFrame(j[1:], columns=j[0])
    df["GEOID_BG_20"] = df["state"] + df["county"] + df["tract"] + df["block group"]
    df = df.rename(columns={"P1_001N": "pop_2020", "H1_001N": "hu_2020"})
    df[["pop_2020", "hu_2020"]] = df[["pop_2020", "hu_2020"]].astype(int)
    frames.append(df[["GEOID_BG_20", "pop_2020", "hu_2020"]])
bg_2020 = pd.concat(frames, ignore_index=True)
log(f"  2020 BGs: {len(bg_2020):,}")


# ---------------------------------------------------------------------------
# 2. Pull 2010 SF1 pop/HU at BLOCK level for 7 counties
#    The Census API supports `&for=block:*&in=state:48+county:XXX` and
#    returns everything in one call. ~10-50k rows per county.
# ---------------------------------------------------------------------------
log("Pulling 2010 SF1 BLOCK pop/HU for 7 counties ...")
frames = []
for cfips in COUNTY_FIPS:
    url = (f"https://api.census.gov/data/2010/dec/sf1?get=P001001,H001001"
           f"&for=block:*&in=state:{STATE_FIPS}+county:{cfips}{key_q}")
    j = census_get(url)
    df = pd.DataFrame(j[1:], columns=j[0])
    # GEOID_BLOCK_10 = state+county+tract+block
    df["GEOID_BLOCK_10"] = df["state"] + df["county"] + df["tract"] + df["block"]
    df = df.rename(columns={"P001001": "pop_2010", "H001001": "hu_2010"})
    df[["pop_2010", "hu_2010"]] = df[["pop_2010", "hu_2010"]].astype(int)
    frames.append(df[["GEOID_BLOCK_10", "pop_2010", "hu_2010"]])
    log(f"  county {cfips}: {len(df):,} blocks")
blk_2010 = pd.concat(frames, ignore_index=True)
log(f"  2010 blocks (total): {len(blk_2010):,}, sum pop: {blk_2010['pop_2010'].sum():,}")


# ---------------------------------------------------------------------------
# 3. Block-level 2010<->2020 crosswalk
# ---------------------------------------------------------------------------
log(f"Loading block crosswalk: {os.path.basename(BLOCK_XW_ZIP)}")
with zipfile.ZipFile(BLOCK_XW_ZIP) as z:
    member = [n for n in z.namelist() if n.endswith(".txt")][0]
    with z.open(member) as f:
        xw = pd.read_csv(f, sep="|", dtype=str, encoding="utf-8-sig")
log(f"  total rows: {len(xw):,}")

# Filter to relationships where the 2010 block was in our 7-county TX area
xw = xw[(xw["STATE_2010"] == STATE_FIPS) &
        (xw["COUNTY_2010"].isin(COUNTY_FIPS))].copy()
log(f"  rows with 2010 block in our 7 counties: {len(xw):,}")

# Build full 2010 block GEOID (state + county + tract + 4-digit block)
xw["GEOID_BLOCK_10"] = (
    xw["STATE_2010"] + xw["COUNTY_2010"] + xw["TRACT_2010"] + xw["BLK_2010"]
)
# Full 2020 BG GEOID = state + county + tract + first digit of block number
xw["GEOID_BG_20"] = (
    xw["STATE_2020"] + xw["COUNTY_2020"] + xw["TRACT_2020"] + xw["BLK_2020"].str[0]
)

# Area-weight = AREALAND_INT / AREALAND_2010
xw["AREALAND_INT"]  = pd.to_numeric(xw["AREALAND_INT"], errors="coerce").fillna(0)
xw["AREALAND_2010"] = pd.to_numeric(xw["AREALAND_2010"], errors="coerce").fillna(0)
xw["w"] = np.where(xw["AREALAND_2010"] > 0,
                   xw["AREALAND_INT"] / xw["AREALAND_2010"], 0)

# Sanity: weights for each 2010 block should sum to ~1.0
ww = xw.groupby("GEOID_BLOCK_10")["w"].sum()
log(f"  weight-sum quantiles (should ~= 1): min={ww.min():.3f} median={ww.median():.3f} max={ww.max():.3f}")


# ---------------------------------------------------------------------------
# 4. Apply weights: 2010 block pop/HU -> 2020 BG
# ---------------------------------------------------------------------------
log("Crosswalking 2010 block pop/HU to 2020 BGs ...")
merged = xw.merge(blk_2010, on="GEOID_BLOCK_10", how="left")
merged["pop_2010"] = merged["pop_2010"].fillna(0) * merged["w"]
merged["hu_2010"]  = merged["hu_2010"].fillna(0)  * merged["w"]

bg_2010_xw = (
    merged.groupby("GEOID_BG_20")[["pop_2010", "hu_2010"]]
          .sum().reset_index()
)
bg_2010_xw[["pop_2010", "hu_2010"]] = bg_2010_xw[["pop_2010", "hu_2010"]].round(0).astype(int)
log(f"  2010 BGs after crosswalk: {len(bg_2010_xw):,}, sum pop: {bg_2010_xw['pop_2010'].sum():,}")


# ---------------------------------------------------------------------------
# 5. Combine + aggregate to tract
# ---------------------------------------------------------------------------
bg = bg_2020.merge(bg_2010_xw, on="GEOID_BG_20", how="left").fillna(0)
bg["pop_change"] = bg["pop_2020"] - bg["pop_2010"]
bg["hu_change"]  = bg["hu_2020"]  - bg["hu_2010"]
bg["geoid"]      = bg["GEOID_BG_20"]
bg = bg.drop(columns=["GEOID_BG_20"])

bg["GEOID_TRACT"] = bg["geoid"].str[:11]
tract = (bg.groupby("GEOID_TRACT")[["pop_2010", "pop_2020", "hu_2010", "hu_2020"]]
           .sum().reset_index())
tract["pop_change"] = tract["pop_2020"] - tract["pop_2010"]
tract["hu_change"]  = tract["hu_2020"]  - tract["hu_2010"]
tract = tract.rename(columns={"GEOID_TRACT": "geoid"})
log(f"  Tracts: {len(tract):,}  BGs: {len(bg):,}")


# ---------------------------------------------------------------------------
# 6. Load geometry & merge
# ---------------------------------------------------------------------------
def load_geom(zip_path, level_label):
    log(f"Loading {os.path.basename(zip_path)} ...")
    g = gpd.read_file(f"zip://{zip_path}")
    g = g[g["COUNTYFP"].isin(COUNTY_FIPS)].copy()
    g["geoid"] = g["GEOID"].astype(str)
    land_col = "ALAND" if "ALAND" in g.columns else "ALAND10"
    g["land_sq_mi"] = (g[land_col].astype(float) / 2589988.110336).round(4)
    log(f"  {level_label}: {len(g):,}")
    return g[["geoid", "land_sq_mi", "geometry"]]

tract_geom = load_geom(TRACT_ZIP, "Tracts")
bg_geom    = load_geom(BG_ZIP,    "BGs")


def finalize(df_data, df_geom, out_path):
    m = df_geom.merge(df_data, on="geoid", how="left").fillna(0)
    for c in ["pop_2010","pop_2020","hu_2010","hu_2020","pop_change","hu_change"]:
        m[c] = m[c].astype(int)
    m["density_2010"] = np.where(m["land_sq_mi"]>0, m["pop_2010"] / m["land_sq_mi"], 0).round(1)
    m["density_2020"] = np.where(m["land_sq_mi"]>0, m["pop_2020"] / m["land_sq_mi"], 0).round(1)
    m["low_density"] = (m["density_2010"] < LOW_DENSITY_PSM) & (m["density_2020"] < LOW_DENSITY_PSM)
    m["geometry"] = m["geometry"].simplify(0.0001, preserve_topology=True)
    out = m.to_crs(4326)
    log(f"Writing {out_path} ...")
    out.to_file(out_path, driver="GeoJSON")
    log(f"  wrote {len(out):,} features")

finalize(tract, tract_geom, os.path.join(WEBMAP_DIR, "data", "tracts.geojson"))
finalize(bg,    bg_geom,    os.path.join(WEBMAP_DIR, "data", "block_groups.geojson"))

log("Done.")
