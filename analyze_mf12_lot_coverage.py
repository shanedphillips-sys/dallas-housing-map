"""
Lot coverage (building footprint area / parcel area) for MF-1 and MF-2 zoned
parcels, by lot-area decile, each district separately.

Footprints from data/buildings_dallas.geojson (Microsoft ML footprints + a few OSM
tower additions). Per parcel: union the intersecting footprints, clip to the parcel,
area -> coverage = that / lot area (0..1). Deciles computed within each district and
each subset (decile 1 = smallest lots).

Two tables:
  - ALL parcels in the district (any land use)
  - parcels with MULTIFAMILY HOUSING (MF land-use categories)
EPSG:2276 (ftUS). Writes data/mf12_lot_coverage_all.csv + _mf.csv.
"""
import os

import geopandas as gpd
import pandas as pd
import shapely

WEB = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(WEB, "data")
DISTRICTS = ["MF-1", "MF-2"]
MF_CATS = {"Duplexes", "MF 3-4 Units", "MF 5-19 Units", "MF 20-49 Units",
           "MF 50+ Units", "MF Apartments (Unclassified)"}

# ---- MF-1/MF-2 parcels with district + lot area ----------------------------
z = gpd.read_file(os.path.join(DATA, "zoning.geojson"))[["zone_norm", "geometry"]].to_crs(2276)
z["geometry"] = shapely.make_valid(z.geometry.values)
z = z[z.zone_norm.isin(DISTRICTS)]

p = pd.concat([gpd.read_file(os.path.join(DATA, f"parcels_{q}.geojson"))[["land_use_cat", "geometry"]]
               for q in ["nw", "ne", "sw", "se"]], ignore_index=True)
p = gpd.GeoDataFrame(p, crs="EPSG:4326").to_crs(2276)
p["geometry"] = shapely.make_valid(p.geometry.values)
p["lot_sqft"] = shapely.area(p.geometry.values)
p = p[p.lot_sqft > 0].reset_index(drop=True)
p["pid"] = p.index

cent = gpd.GeoDataFrame({"pid": p.pid}, geometry=shapely.centroid(p.geometry.values), crs=2276)
jz = gpd.sjoin(cent, z, predicate="within", how="inner")[["pid", "zone_norm"]].drop_duplicates("pid")
p = p.merge(jz, on="pid")
print(f"MF-1/MF-2 parcels: {len(p)}", flush=True)

# ---- footprint area per parcel (union of footprints clipped to the lot) ------
print("loading building footprints ...", flush=True)
b = gpd.read_file(os.path.join(DATA, "buildings_dallas.geojson"))[["geometry"]].to_crs(2276)
b["geometry"] = shapely.make_valid(b.geometry.values)
bp = gpd.sjoin(b, p[["pid", "geometry"]], predicate="intersects", how="inner")
print(f"building-parcel pairs: {len(bp)}", flush=True)
pgeom = p.set_index("pid").geometry
bp["clip"] = shapely.intersection(bp.geometry.values, pgeom.loc[bp.pid].values)
foot = bp.groupby("pid")["clip"].apply(lambda s: shapely.area(shapely.union_all(s.values)))
p["foot_sqft"] = p.pid.map(foot).fillna(0.0)
p["coverage"] = (p.foot_sqft / p.lot_sqft).clip(0, 1)


def decile_table(df):
    df = df.copy()
    df["decile"] = pd.qcut(df.lot_sqft, 10, labels=False, duplicates="drop") + 1
    rows = []
    for d, g in df.groupby("decile"):
        rows.append({"decile": int(d), "n": len(g),
                     "lot_lo": int(g.lot_sqft.min()), "lot_md": int(g.lot_sqft.median()),
                     "lot_hi": int(g.lot_sqft.max()),
                     "cov_md_pct": round(g.coverage.median() * 100, 1),
                     "cov_mean_pct": round(g.coverage.mean() * 100, 1)})
    return pd.DataFrame(rows)


def build(subsetter, title, path):
    parts = []
    for dist in DISTRICTS:
        sub = subsetter(p[p.zone_norm == dist])
        t = decile_table(sub)
        t.insert(0, "district", dist)
        parts.append(t)
    out = pd.concat(parts, ignore_index=True)
    out.to_csv(path, index=False)
    print(f"\n=== {title} ===")
    print(out.to_string(index=False))
    return out


pd.set_option("display.width", 200)
build(lambda d: d, "ALL parcels in MF-1 / MF-2 — lot coverage % by lot-area decile",
      os.path.join(DATA, "mf12_lot_coverage_all.csv"))
build(lambda d: d[d.land_use_cat.isin(MF_CATS)],
      "MF-HOUSING parcels in MF-1 / MF-2 — lot coverage % by lot-area decile",
      os.path.join(DATA, "mf12_lot_coverage_mf.csv"))
