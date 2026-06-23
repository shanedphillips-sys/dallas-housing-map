"""
Add the City-of-Dallas parcels that exist in DCAD's PARCEL_GEOM.shp but are
missing from our extract (PARCEL_CORE_MERGED dropped ~2k downtown / condo / special
parcels -- e.g. 2100 Ross, a $110M tower). Geometry comes from PARCEL_GEOM (keyed
by Acct); attributes are derived from the same CAD files the build uses
(ACCOUNT_APPRL_YEAR, ACCOUNT_INFO, COM_DETAIL/RES_DETAIL, SPTD map).

Appends the new features to data/parcels_{nw,ne,sw,se}.geojson. Re-run
build_footprint_far.py afterward to refresh FAR / foot_far for everyone.
"""
import json
import os

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from shapely.ops import transform

F = r"C:\Users\shane\OneDrive\Documents\Domain Consulting\Projects\GDPC - Dallas Housing Report\GDPC Claude Stuff\DCAD2025_CERTIFIED"
PGEOM = r"C:\Users\shane\OneDrive\Documents\Domain Consulting\Projects\GDPC - Dallas Housing Report\GDPC Claude Stuff\PARCEL_GEOM\PARCEL_GEOM.shp"
YR = "2025"
LAT_SPLIT, LON_SPLIT = 32.81, -96.78
LAND_USE_MAP = {
    "SINGLE FAMILY RESIDENCES": "Single Family", "SFR - TOWNHOUSES": "Townhouses",
    "MFR - DUPLEXES": "Duplexes", "MFR - 3-4 UNITS": "MF 3-4 Units", "MFR - 5-19 UNITS": "MF 5-19 Units",
    "MFR - 20-49 UNITS": "MF 20-49 Units", "MFR - 50+ UNITS": "MF 50+ Units",
    "MFR - APARTMENTS": "MF Apartments (Unclassified)", "SFR - VACANT LOTS/TRACTS": "Vacant - Single Family",
    "COMMERCIAL - VACANT PLOTTED LOTS/TRACTS": "Vacant - Commercial",
    "INDUSTRIAL - VACANT PLOTTED LOTS/TRACTS": "Vacant - Industrial", "COMMERCIAL IMPROVEMENTS": "Commercial",
    "INDUSTRIAL IMPROVEMENTS": "Industrial", "QUALIFIED OPEN SPACE LAND": "Open Space",
    "MOBILE HOME ON OWNERS LAND": "Mobile Home", "SFR - CONDOMINIUMS": "SFR Condominiums",
}


def far_cat(far):
    if pd.isna(far) or far <= 0: return "No Building"
    for hi, lab in [(0.25, "< 0.25"), (0.5, "0.25 - 0.49"), (1.0, "0.5 - 0.99"), (1.5, "1.0 - 1.49"),
                    (2.0001, "1.5 - 2.0"), (3.0, "2.0 - 2.9"), (5.0, "3.0 - 4.9"), (10.0, "5.0 - 9.9")]:
        if far < hi: return lab
    return "10+"


def num(s):
    return pd.to_numeric(s, errors="coerce").fillna(0)


print("loading CAD tables ...", flush=True)
ap = pd.read_csv(f"{F}/ACCOUNT_APPRL_YEAR.CSV", dtype=str, encoding="latin-1",
                 usecols=["ACCOUNT_NUM", "APPRAISAL_YR", "GIS_PARCEL_ID", "IMPR_VAL", "LAND_VAL", "TOT_VAL", "SPTD_CODE", "DIVISION_CD", "CITY_JURIS_DESC"])
ap = ap[ap.APPRAISAL_YR == YR].copy()
for c in ["IMPR_VAL", "LAND_VAL", "TOT_VAL"]:
    ap[c] = num(ap[c])
a2g = dict(zip(ap.ACCOUNT_NUM, ap.GIS_PARCEL_ID))
a2sptd = dict(zip(ap.ACCOUNT_NUM, ap.SPTD_CODE))
gimp = ap.groupby("GIS_PARCEL_ID")[["IMPR_VAL", "LAND_VAL", "TOT_VAL"]].sum()
gacct = ap.groupby("GIS_PARCEL_ID")["ACCOUNT_NUM"].apply(list)
grep = ap.sort_values("IMPR_VAL").groupby("GIS_PARCEL_ID")["ACCOUNT_NUM"].last()  # rep = max-impr account
# city real-property GIS parcels (have a RES/COM account in City of Dallas)
rp = ap[(ap.DIVISION_CD.isin(["RES", "COM"])) & (ap.CITY_JURIS_DESC == "DALLAS")]
city_rp_gis = set(rp.GIS_PARCEL_ID)
del ap

info = pd.read_csv(f"{F}/ACCOUNT_INFO.CSV", dtype=str, encoding="latin-1",
                   usecols=["ACCOUNT_NUM", "APPRAISAL_YR", "STREET_NUM", "FULL_STREET_NAME", "UNIT_ID", "BIZ_NAME"])
info = info[info.APPRAISAL_YR == YR]
a2addr = {}
for r in info.itertuples():
    s = f"{str(r.STREET_NUM or '').strip()} {str(r.FULL_STREET_NAME or '').strip()}".strip()
    u = str(r.UNIT_ID or "").strip()
    a2addr[r.ACCOUNT_NUM] = (s + (f" #{u}" if u and u.lower() != "nan" else "")).strip() or None
a2biz = dict(zip(info.ACCOUNT_NUM, info.BIZ_NAME))
del info

com = pd.read_csv(f"{F}/COM_DETAIL.CSV", dtype=str, encoding="latin-1", usecols=["ACCOUNT_NUM", "APPRAISAL_YR", "GROSS_BLDG_AREA", "YEAR_BUILT", "NUM_UNITS", "PROPERTY_NAME"])
com = com[com.APPRAISAL_YR == YR]
res = pd.read_csv(f"{F}/RES_DETAIL.CSV", dtype=str, encoding="latin-1", usecols=["ACCOUNT_NUM", "APPRAISAL_YR", "TOT_MAIN_SF", "YR_BUILT", "NUM_UNITS"])
res = res[res.APPRAISAL_YR == YR]
sf = pd.concat([com.assign(a=num(com.GROSS_BLDG_AREA)).groupby("ACCOUNT_NUM")["a"].sum(),
                res.assign(a=num(res.TOT_MAIN_SF)).groupby("ACCOUNT_NUM")["a"].sum()]).groupby(level=0).sum().to_dict()
yb = pd.concat([res.groupby("ACCOUNT_NUM")["YR_BUILT"].first(), com.groupby("ACCOUNT_NUM")["YEAR_BUILT"].first()]).groupby(level=0).last().to_dict()
un = pd.concat([com.assign(u=num(com.NUM_UNITS)).groupby("ACCOUNT_NUM")["u"].sum(),
                res.assign(u=num(res.NUM_UNITS)).groupby("ACCOUNT_NUM")["u"].sum()]).groupby(level=0).sum().to_dict()
cpn = com.groupby("ACCOUNT_NUM")["PROPERTY_NAME"].first().to_dict()
try:
    exempt = set(pd.read_csv(f"{F}/TOTAL_EXEMPTION.CSV", dtype=str, encoding="latin-1", usecols=["ACCOUNT_NUM"]).ACCOUNT_NUM)
except Exception:
    exempt = set()
del com, res

# SPTD_CODE -> land_sptd_desc, learned from the shipped parcels
parts = [gpd.read_file(f"data/parcels_{q}.geojson", ignore_geometry=True)[["account_num", "land_sptd_desc"]] for q in ["nw", "ne", "sw", "se"]]
g0 = pd.concat(parts, ignore_index=True)
g0["sptd"] = g0["account_num"].map(a2sptd)
sptd_desc = g0.dropna(subset=["sptd", "land_sptd_desc"]).groupby("sptd")["land_sptd_desc"].agg(lambda s: s.value_counts().idxmax()).to_dict()
geo_acct = set(g0["account_num"])
geo_gis = {a2g.get(a) for a in geo_acct}
missing_gis = (city_rp_gis - geo_gis) - {None}
print(f"missing City-of-Dallas real-property GIS parcels: {len(missing_gis):,}", flush=True)

# ---- geometry from PARCEL_GEOM, dissolved to one polygon per missing GIS parcel
print("loading PARCEL_GEOM ...", flush=True)
pg = gpd.read_file(PGEOM)[["Acct", "geometry"]]
pg["gis"] = pg["Acct"].map(a2g)
pg = pg[pg["gis"].isin(missing_gis)].copy()
pg["geometry"] = shapely.make_valid(pg.geometry.values)
diss = pg.dissolve(by="gis")
print(f"  missing parcels with geometry in PARCEL_GEOM: {len(diss):,}", flush=True)
diss = diss.to_crs(2276)
diss["area_feet"] = diss.geometry.area
diss["geometry"] = diss.geometry.simplify(8.0, preserve_topology=True)
diss = diss.to_crs(4326)


def round_coords(geom, p=5):
    return transform(lambda x, y, z=None: (round(x, p), round(y, p)), geom)


def categorize(rep, units):
    desc = sptd_desc.get(a2sptd.get(rep, ""), None)
    if desc == "MFR - APARTMENTS" and units:
        desc = ("MFR - 3-4 UNITS" if units <= 4 else "MFR - 5-19 UNITS" if units <= 19
                else "MFR - 20-49 UNITS" if units <= 49 else "MFR - 50+ UNITS")
    cat = LAND_USE_MAP.get(desc, "Other")
    if rep in exempt and cat in ("Commercial", "Industrial", "Other"):
        cat = "Institutional"
    return cat


# ---- build features, bucket by quadrant ------------------------------------
buckets = {"nw": [], "ne": [], "sw": [], "se": []}
for gid, row in diss.iterrows():
    geom = round_coords(row.geometry)
    if geom.is_empty:
        continue
    rep = grep.get(gid)
    accts = gacct.get(gid, [rep])
    bsf = float(sum(sf.get(a, 0) or 0 for a in accts))
    units = int(sum(un.get(a, 0) or 0 for a in accts))
    area = float(row.area_feet)
    impr, land, tot = float(gimp.loc[gid, "IMPR_VAL"]), float(gimp.loc[gid, "LAND_VAL"]), float(gimp.loc[gid, "TOT_VAL"])
    far = bsf / area if area > 0 else None
    acres = area / 43560.0 if area > 0 else None
    yv = yb.get(rep)
    try:
        yi = int(float(yv)) if yv and str(yv).lower() != "nan" else 0
    except ValueError:
        yi = 0
    props = {"account_num": rep, "address": a2addr.get(rep), "land_use_cat": categorize(rep, units),
             "area_feet": round(area), "building_sf": round(bsf), "total_units": units, "year_built": yi,
             "floor_area_ratio": round(far, 2) if far else None, "far_cat": far_cat(far),
             "tot_val": round(tot), "impr_val": round(impr), "land_val": round(land),
             "value_per_acre": int(round(tot / acres)) if acres else 0,
             "impr_per_acre": int(round(impr / acres)) if acres else 0,
             "land_per_acre": int(round(land / acres)) if acres else 0,
             "property_name": (cpn.get(rep) if isinstance(cpn.get(rep), str) else a2biz.get(rep)),
             "added_parcel": True}
    props = {k: v for k, v in props.items() if v is not None and not (isinstance(v, float) and pd.isna(v))}
    c = geom.centroid
    q = ("nw" if c.y >= LAT_SPLIT and c.x < LON_SPLIT else "ne" if c.y >= LAT_SPLIT else "sw" if c.x < LON_SPLIT else "se")
    buckets[q].append({"type": "Feature", "geometry": shapely.geometry.mapping(geom), "properties": props})

for q in ["nw", "ne", "sw", "se"]:
    path = f"data/parcels_{q}.geojson"
    data = json.load(open(path))
    data["features"].extend(buckets[q])
    json.dump(data, open(path, "w"), separators=(",", ":"))
    print(f"  {path}: +{len(buckets[q]):,} parcels  (now {len(data['features']):,})", flush=True)
print(f"TOTAL added: {sum(len(v) for v in buckets.values()):,}", flush=True)
