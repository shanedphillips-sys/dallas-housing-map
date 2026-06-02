"""
Add an 'Institutional' land-use category to existing parcel GeoJSONs.

DCAD flags totally-exempt parcels with totexempt == 'X'. These are schools,
city/county/state government, religious organizations, hospitals, etc. —
but the appraisal record's LAND_SPTD_DESC still classifies them under
broad codes like 'COMMERCIAL IMPROVEMENTS', so they currently show up as
'Commercial' on the land-use map.

This script pulls totexempt from the source PARCEL_CORE_MERGED.gpkg, joins
by ACCOUNT_NUM, and reclassifies DCAD parcels where:
    totexempt == 'X'  AND  current land_use_cat in {Commercial, Industrial, Other}
        --> land_use_cat = 'Institutional'

Exempt residential parcels (Land Bank, public housing, etc.) are NOT
remapped — they remain in their housing categories for housing analysis.
"""

import os
import numpy as np
import pandas as pd
import geopandas as gpd

PROJECT_DIR = r"C:\Users\shane\OneDrive\Documents\Domain Consulting\Projects\GDPC - Dallas Housing Report"
WEBMAP_DIR  = os.path.join(PROJECT_DIR, "webmap")
DATA_DIR    = os.path.join(WEBMAP_DIR, "data")
SRC_GPKG    = os.path.join(PROJECT_DIR, "GDPC Claude Stuff", "PARCEL_CORE_MERGED.gpkg")

QUADRANTS = ["nw", "ne", "sw", "se"]

# Categories that should be promoted to "Institutional" when totexempt=='X'.
PROMOTE_FROM = {"Commercial", "Industrial", "Other"}


def log(msg): print(msg, flush=True)


# ---------------------------------------------------------------------------
# Pull just the exempt-flag table from the source gpkg
# ---------------------------------------------------------------------------
log(f"Loading totexempt flags from {SRC_GPKG} ...")
src = gpd.read_file(SRC_GPKG, columns=["ACCOUNT_NUM", "totexempt", "city"])
src = src[src["city"].astype(str).str.upper() == "DALLAS"]
src["ACCOUNT_NUM"] = src["ACCOUNT_NUM"].astype(str)

exempt_lookup = (
    src[src["totexempt"] == "X"]
    .drop_duplicates(subset="ACCOUNT_NUM")
    .set_index("ACCOUNT_NUM")
)
log(f"  Dallas parcels flagged totexempt='X': {len(exempt_lookup):,}")


# ---------------------------------------------------------------------------
# Patch each quadrant
# ---------------------------------------------------------------------------
total_changed = 0

for q in QUADRANTS:
    path = os.path.join(DATA_DIR, f"parcels_{q}.geojson")
    log(f"\nProcessing {os.path.basename(path)} ...")
    gdf = gpd.read_file(path)

    # Only DCAD parcels (skip COL- and DEN-)
    is_dcad = ~gdf["account_num"].astype(str).str.startswith(("COL-", "DEN-"))
    is_exempt = gdf["account_num"].astype(str).isin(exempt_lookup.index)
    promotable = gdf["land_use_cat"].isin(PROMOTE_FROM)

    mask = is_dcad & is_exempt & promotable
    n_change = int(mask.sum())
    total_changed += n_change

    # Counts by source category, for the log
    before = gdf.loc[mask, "land_use_cat"].value_counts().to_dict() if n_change else {}

    gdf.loc[mask, "land_use_cat"] = "Institutional"
    log(f"  reclassified {n_change:,} parcels to Institutional")
    for k, v in sorted(before.items(), key=lambda x: -x[1]):
        log(f"    from {k}: {v:,}")

    if n_change:
        gdf.to_file(path, driver="GeoJSON")
        log(f"  wrote {len(gdf):,} features")
    else:
        log("  no changes — skipped write")

log(f"\n=== Done. Total reclassified: {total_changed:,} ===")
