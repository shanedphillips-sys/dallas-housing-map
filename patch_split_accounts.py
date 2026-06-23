"""
Fix A: parcels that show vacant / no-building only because the building lives on a
separate "improvement-only" account on the SAME GIS parcel (no polygon of its own).

For each land-only polygon (impr_val==0) whose GIS_PARCEL_ID carries an improved
account, pull that account's building from the DCAD detail files and attach it:
  building_sf  <- sum TOT_MAIN_SF (RES) + GROSS_BLDG_AREA (COM) over the GIS parcel
  impr_val     <- sum IMPR_VAL over the GIS parcel's accounts; tot = land + impr
  land_use_cat <- improved account's SPTD_CODE -> desc -> display category
  year_built / total_units / far / far_cat / per-acre values recomputed
Patches data/parcels_{nw,ne,sw,se}.geojson in place. Only DCAD (Dallas Co.) parcels.
"""
import json
import os

import geopandas as gpd
import numpy as np
import pandas as pd

F = r"C:\Users\shane\OneDrive\Documents\Domain Consulting\Projects\GDPC - Dallas Housing Report\GDPC Claude Stuff\DCAD2025_CERTIFIED"
YR = "2025"

LAND_USE_MAP = {
    "SINGLE FAMILY RESIDENCES": "Single Family", "SFR - TOWNHOUSES": "Townhouses",
    "MFR - DUPLEXES": "Duplexes", "MFR - 3-4 UNITS": "MF 3-4 Units",
    "MFR - 5-19 UNITS": "MF 5-19 Units", "MFR - 20-49 UNITS": "MF 20-49 Units",
    "MFR - 50+ UNITS": "MF 50+ Units", "MFR - APARTMENTS": "MF Apartments (Unclassified)",
    "SFR - VACANT LOTS/TRACTS": "Vacant - Single Family",
    "COMMERCIAL - VACANT PLOTTED LOTS/TRACTS": "Vacant - Commercial",
    "INDUSTRIAL - VACANT PLOTTED LOTS/TRACTS": "Vacant - Industrial",
    "COMMERCIAL IMPROVEMENTS": "Commercial", "INDUSTRIAL IMPROVEMENTS": "Industrial",
    "QUALIFIED OPEN SPACE LAND": "Open Space", "MOBILE HOME ON OWNERS LAND": "Mobile Home",
    "SFR - CONDOMINIUMS": "SFR Condominiums",
}


def far_cat(far):
    if pd.isna(far) or far <= 0: return "No Building"
    for hi, lab in [(0.25, "< 0.25"), (0.5, "0.25 - 0.49"), (1.0, "0.5 - 0.99"),
                    (1.5, "1.0 - 1.49"), (2.0001, "1.5 - 2.0"), (3.0, "2.0 - 2.9"),
                    (5.0, "3.0 - 4.9"), (10.0, "5.0 - 9.9")]:
        if far < hi: return lab
    return "10+"


# ---- source tables (2025) --------------------------------------------------
ap = pd.read_csv(f"{F}/ACCOUNT_APPRL_YEAR.CSV", dtype=str, encoding="latin-1",
                 usecols=["ACCOUNT_NUM", "APPRAISAL_YR", "GIS_PARCEL_ID", "IMPR_VAL", "LAND_VAL", "TOT_VAL", "SPTD_CODE"])
ap = ap[ap["APPRAISAL_YR"] == YR].copy()
for c in ["IMPR_VAL", "LAND_VAL", "TOT_VAL"]:
    ap[c] = pd.to_numeric(ap[c], errors="coerce").fillna(0)
acct_gis = dict(zip(ap["ACCOUNT_NUM"], ap["GIS_PARCEL_ID"]))
acct_sptd = dict(zip(ap["ACCOUNT_NUM"], ap["SPTD_CODE"]))
gis_impr = ap.groupby("GIS_PARCEL_ID")["IMPR_VAL"].sum()
gis_accts = ap.groupby("GIS_PARCEL_ID")["ACCOUNT_NUM"].apply(list)
gis_top_impr = ap[ap["IMPR_VAL"] > 0].sort_values("IMPR_VAL").groupby("GIS_PARCEL_ID")["ACCOUNT_NUM"].last()

res = pd.read_csv(f"{F}/RES_DETAIL.CSV", dtype=str, encoding="latin-1",
                  usecols=["ACCOUNT_NUM", "APPRAISAL_YR", "TOT_MAIN_SF", "YR_BUILT", "NUM_UNITS"])
res = res[res["APPRAISAL_YR"] == YR]
com = pd.read_csv(f"{F}/COM_DETAIL.CSV", dtype=str, encoding="latin-1",
                  usecols=["ACCOUNT_NUM", "APPRAISAL_YR", "GROSS_BLDG_AREA", "YEAR_BUILT", "NUM_UNITS", "PROPERTY_NAME"])
com = com[com["APPRAISAL_YR"] == YR]
sf = (pd.concat([res.assign(sf=pd.to_numeric(res["TOT_MAIN_SF"], errors="coerce")).groupby("ACCOUNT_NUM")["sf"].sum(),
                 com.assign(sf=pd.to_numeric(com["GROSS_BLDG_AREA"], errors="coerce")).groupby("ACCOUNT_NUM")["sf"].sum()])
      .groupby(level=0).sum())
yb = pd.concat([res.groupby("ACCOUNT_NUM")["YR_BUILT"].first(), com.groupby("ACCOUNT_NUM")["YEAR_BUILT"].first()]).groupby(level=0).last()
units = (pd.concat([res.assign(u=pd.to_numeric(res["NUM_UNITS"], errors="coerce")).groupby("ACCOUNT_NUM")["u"].sum(),
                    com.assign(u=pd.to_numeric(com["NUM_UNITS"], errors="coerce")).groupby("ACCOUNT_NUM")["u"].sum()])
         .groupby(level=0).sum())
pname = com.groupby("ACCOUNT_NUM")["PROPERTY_NAME"].first()
try:
    te = pd.read_csv(f"{F}/TOTAL_EXEMPTION.CSV", dtype=str, encoding="latin-1", usecols=["ACCOUNT_NUM"])
    exempt = set(te["ACCOUNT_NUM"])
except Exception:
    exempt = set()

# SPTD_CODE -> land_sptd_desc, learned from the shipped parcels
parts = [gpd.read_file(f"data/parcels_{q}.geojson", ignore_geometry=True)[["account_num", "land_sptd_desc"]] for q in ["nw", "ne", "sw", "se"]]
g0 = pd.concat(parts, ignore_index=True)
g0["sptd"] = g0["account_num"].map(acct_sptd)
sptd_desc = g0.dropna(subset=["sptd", "land_sptd_desc"]).groupby("sptd")["land_sptd_desc"].agg(lambda s: s.value_counts().idxmax()).to_dict()


def categorize(impr_acct, units_val):
    desc = sptd_desc.get(acct_sptd.get(impr_acct, ""), None)
    if desc == "MFR - APARTMENTS" and units_val:
        if 3 <= units_val <= 4: desc = "MFR - 3-4 UNITS"
        elif 5 <= units_val <= 19: desc = "MFR - 5-19 UNITS"
        elif 20 <= units_val <= 49: desc = "MFR - 20-49 UNITS"
        elif units_val >= 50: desc = "MFR - 50+ UNITS"
    cat = LAND_USE_MAP.get(desc, "Other")
    if impr_acct in exempt and cat in ("Commercial", "Industrial", "Other"):
        cat = "Institutional"
    return cat, desc


# ---- patch each quadrant ---------------------------------------------------
patched = 0
for q in ["nw", "ne", "sw", "se"]:
    path = f"data/parcels_{q}.geojson"
    data = json.load(open(path))
    n = 0
    for feat in data["features"]:
        p = feat["properties"]
        acct = p.get("account_num")
        gid = acct_gis.get(acct)
        if gid is None or float(p.get("impr_val", 0) or 0) > 0:
            continue
        if gis_impr.get(gid, 0) <= 0:
            continue
        top = gis_top_impr.get(gid)
        bsf = float(sum(sf.get(a, 0) or 0 for a in gis_accts.get(gid, [])))
        if bsf <= 0:
            continue                              # no building area recoverable -> skip
        area = float(p.get("area_feet", 0) or 0)
        uval = float(units.get(top, 0) or 0)
        cat, _ = categorize(top, uval)
        impr = float(gis_impr.get(gid, 0))
        land = float(p.get("land_val", 0) or 0)
        tot = land + impr
        acres = area / 43560.0 if area > 0 else None
        far = (bsf / area) if area > 0 else None
        p["building_sf"] = round(bsf)
        p["land_use_cat"] = cat
        p["impr_val"] = round(impr); p["tot_val"] = round(tot); p["land_val"] = round(land)
        p["floor_area_ratio"] = round(far, 2) if far else None
        p["far_cat"] = far_cat(far)
        if acres:
            p["value_per_acre"] = int(round(tot / acres)); p["impr_per_acre"] = int(round(impr / acres)); p["land_per_acre"] = int(round(land / acres))
        yv = yb.get(top)
        if pd.notna(yv):
            try: p["year_built"] = int(float(yv))
            except ValueError: pass
        if uval > 0: p["total_units"] = int(uval)
        if isinstance(pname.get(top), str) and pname.get(top).strip(): p["property_name"] = pname.get(top).strip()
        p["split_account_fixed"] = True
        n += 1
    json.dump(data, open(path, "w"), separators=(",", ":"))
    patched += n
    print(f"{path}: patched {n}")
print(f"TOTAL parcels patched: {patched}")
