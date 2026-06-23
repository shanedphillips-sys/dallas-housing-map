"""
Fix the parcel building data and build the footprint-adjusted FAR, in one pass.

(1) Re-derive building_sf from the CAD detail files (COM_DETAIL.GROSS_BLDG_AREA +
    RES_DETAIL.TOT_MAIN_SF) -- recovers ~600 buildings the source GPKG left blank
    (e.g. the Dallas Museum of Art). Uses max(detail, existing) so nothing shrinks.
(3) Pro-rate that account-level floor area across the account's polygons by land
    area -- the build pro-rated *values* but not building_sf, so tiny slivers of a
    multi-polygon account claimed the whole building and produced FAR-1117 artifacts.
Then redistribute each parcel's corrected floor area across the building footprints
overlapping it (foot_far), capped at 50 as a sliver safety net.

Recomputes building_sf / floor_area_ratio / far_cat AND foot_far / foot_sf and
writes them back into data/parcels_{nw,ne,sw,se}.geojson. (land_use_cat unchanged.)
"""
import json

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

QUADS = ["nw", "ne", "sw", "se"]
DATA = "data"
F = r"C:\Users\shane\OneDrive\Documents\Domain Consulting\Projects\GDPC - Dallas Housing Report\GDPC Claude Stuff\DCAD2025_CERTIFIED"
FAR_CAP = 50.0


def log(m): print(m, flush=True)


def far_cat(far):
    if pd.isna(far) or far <= 0: return "No Building"
    for hi, lab in [(0.25, "< 0.25"), (0.5, "0.25 - 0.49"), (1.0, "0.5 - 0.99"),
                    (1.5, "1.0 - 1.49"), (2.0001, "1.5 - 2.0"), (3.0, "2.0 - 2.9"),
                    (5.0, "3.0 - 4.9"), (10.0, "5.0 - 9.9")]:
        if far < hi: return lab
    return "10+"


# ---- CAD detail floor area per account (2025) ------------------------------
com = pd.read_csv(f"{F}/COM_DETAIL.CSV", usecols=["ACCOUNT_NUM", "APPRAISAL_YR", "GROSS_BLDG_AREA"], dtype=str, encoding="latin-1")
com = com[com.APPRAISAL_YR == "2025"]; com["a"] = pd.to_numeric(com.GROSS_BLDG_AREA, errors="coerce").fillna(0)
res = pd.read_csv(f"{F}/RES_DETAIL.CSV", usecols=["ACCOUNT_NUM", "APPRAISAL_YR", "TOT_MAIN_SF"], dtype=str, encoding="latin-1")
res = res[res.APPRAISAL_YR == "2025"]; res["a"] = pd.to_numeric(res.TOT_MAIN_SF, errors="coerce").fillna(0)
detail = pd.concat([com.groupby("ACCOUNT_NUM")["a"].sum(), res.groupby("ACCOUNT_NUM")["a"].sum()]).groupby(level=0).sum()
log(f"detail floor-area accounts: {len(detail):,}")

# ---- parcels ----------------------------------------------------------------
gdfs = []
for q in QUADS:
    g = gpd.read_file(f"{DATA}/parcels_{q}.geojson")[["account_num", "building_sf", "area_feet", "geometry"]]
    g["q"] = q; g["li"] = np.arange(len(g)); gdfs.append(g)
P = gpd.GeoDataFrame(pd.concat(gdfs, ignore_index=True), crs=gdfs[0].crs).to_crs(2276)
P["geometry"] = shapely.make_valid(P.geometry.values)
P["bsf_old"] = pd.to_numeric(P["building_sf"], errors="coerce").fillna(0.0)
P["pa"] = pd.to_numeric(P["area_feet"], errors="coerce").fillna(0.0)
P["pid"] = np.arange(len(P))
log(f"parcels: {len(P):,}")

# ---- (1)+(3) corrected, pro-rated building_sf -------------------------------
acc = P.groupby("account_num").agg(ev=("bsf_old", "max"), ta=("pa", "sum"))
acc["det"] = acc.index.map(lambda a: float(detail.get(a, 0.0)))
acc["floor"] = np.maximum(acc["det"], acc["ev"])
P["afloor"] = P["account_num"].map(acc["floor"])
P["ata"] = P["account_num"].map(acc["ta"])
P["bsf"] = np.where(P["ata"] > 0, P["afloor"] * P["pa"] / P["ata"], P["bsf_old"])
log(f"buildings recovered (bsf_old<100 -> bsf>=1000): {int(((P['bsf_old']<100)&(P['bsf']>=1000)).sum()):,}")
log(f"multi-polygon parcels re-prorated: {int((P.groupby('account_num')['pid'].transform('size')>1).sum()):,}")

# ---- footprint redistribution (corrected floor area) ------------------------
B = gpd.read_file(f"{DATA}/buildings_dallas.geojson").to_crs(2276)
B["geometry"] = shapely.make_valid(B.geometry.values); B["fid"] = np.arange(len(B))
log(f"footprints: {len(B):,}; overlaying ...")
j = gpd.sjoin(B[["fid", "geometry"]], P[["pid", "geometry"]], predicate="intersects", how="inner")
bg = np.asarray(B.set_index("fid").geometry.loc[j["fid"].values].values, dtype=object)
pg = np.asarray(P.set_index("pid").geometry.loc[j["pid"].values].values, dtype=object)
j["s"] = shapely.area(shapely.intersection(bg, pg)); j = j[j["s"] > 1.0].copy()
bsf = P.set_index("pid")["bsf"]
fop = j.groupby("pid")["s"].sum(); j["w1"] = j["s"] / j["pid"].map(fop)
j["c"] = j["pid"].map(bsf) * j["w1"]; FA = j.groupby("fid")["c"].sum()
ft = j.groupby("fid")["s"].sum(); j["w2"] = j["s"] / j["fid"].map(ft)
j["a"] = j["fid"].map(FA) * j["w2"]; attr = j.groupby("pid")["a"].sum()
P["foot_sf"] = P["pid"].map(attr).fillna(0.0)
nofoot = ~P["pid"].isin(fop.index); P.loc[nofoot, "foot_sf"] = P.loc[nofoot, "bsf"]
P["foot_far"] = np.where(P["pa"] > 0, np.minimum(P["foot_sf"] / P["pa"], FAR_CAP).round(2), 0.0)
P["orig_far"] = np.where(P["pa"] > 0, P["bsf"] / P["pa"], np.nan)
log(f"conservation: corrected CAD {P['bsf'].sum():,.0f} sf -> redistributed {P['foot_sf'].sum():,.0f} sf")
log(f"max foot_far after cap: {P['foot_far'].max():.1f}")

# ---- write back -------------------------------------------------------------
for q in QUADS:
    path = f"{DATA}/parcels_{q}.geojson"; data = json.load(open(path)); sub = P[P.q == q]
    bsfm = dict(zip(sub.li, sub.bsf)); ofm = dict(zip(sub.li, sub.orig_far))
    ffm = dict(zip(sub.li, sub.foot_far)); fsm = dict(zip(sub.li, sub.foot_sf)); oldm = dict(zip(sub.li, sub.bsf_old))
    for i, feat in enumerate(data["features"]):
        p = feat["properties"]
        nb, ob = bsfm.get(i), oldm.get(i, 0)
        if nb is not None and abs(nb - ob) > 1:
            p["building_sf"] = int(round(nb))
            of = ofm.get(i)
            if of == of:  # not NaN
                p["floor_area_ratio"] = round(float(of), 2)
            else:
                p.pop("floor_area_ratio", None)
            p["far_cat"] = far_cat(of)
        ff = ffm.get(i, 0.0)
        if ff and ff > 0:
            p["foot_far"] = round(float(ff), 2); p["foot_sf"] = int(round(fsm.get(i, 0)))
        else:
            p.pop("foot_far", None); p.pop("foot_sf", None)
    json.dump(data, open(path, "w"), separators=(",", ":"))
    log(f"  wrote {path}")
log("Done.")
