"""
Lot dimensions (width/frontage vs depth) for MF-1 / MF-2 parcels, profiled within
size-percentile bands (p25-p50, and p45-p55 = tight around the median).

Method: per parcel, take the minimum rotated (oriented) bounding rectangle; its two
side lengths are the lot's width (shorter side ~ street frontage) and depth (longer
side). "Rectangularity" = polygon area / rectangle area gauges how rectangular the
lot is (≈1 = clean rectangle, so width x depth is trustworthy). EPSG:2276 (ftUS).
Unweighted (each parcel one observation). Writes data/mf12_lot_dims.csv.

Caveat: width=shorter-side is a frontage *proxy* — it's true for typical lots
(deeper than wide) but not for corner/flag/assembled lots. The aspect-ratio and
rectangularity distributions below show how often that assumption holds.
"""
import math
import os

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

WEB = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(WEB, "data")
DISTRICTS = ["MF-1", "MF-2"]
BANDS = [(20, 30), (25, 50), (45, 55)]   # size-percentile bands to profile


def rect_dims(geom):
    """(width, depth, rect_area) from the oriented bounding rectangle."""
    pts = list(shapely.minimum_rotated_rectangle(geom).exterior.coords)
    s1 = math.dist(pts[0], pts[1])
    s2 = math.dist(pts[1], pts[2])
    return min(s1, s2), max(s1, s2), s1 * s2


z = gpd.read_file(os.path.join(DATA, "zoning.geojson"))[["zone_norm", "geometry"]].to_crs(2276)
z["geometry"] = shapely.make_valid(z.geometry.values)
z = z[z.zone_norm.isin(DISTRICTS)]

p = pd.concat([gpd.read_file(os.path.join(DATA, f"parcels_{q}.geojson"))[["geometry"]]
               for q in ["nw", "ne", "sw", "se"]], ignore_index=True)
p = gpd.GeoDataFrame(p, crs="EPSG:4326").to_crs(2276)
p["geometry"] = shapely.make_valid(p.geometry.values)
p["sqft"] = shapely.area(p.geometry.values)
p = p[p.sqft > 0].reset_index(drop=True)

cent = gpd.GeoDataFrame({"pid": p.index}, geometry=shapely.centroid(p.geometry.values), crs=2276)
j = (gpd.sjoin(cent, z, predicate="within", how="inner")[["pid", "zone_norm"]]
     .drop_duplicates("pid"))
df = p.merge(j, left_index=True, right_on="pid")

rows = []
for d in DISTRICTS:
    sub = df[df.zone_norm == d]
    for lo_p, hi_p in BANDS:
        lo, hi = np.percentile(sub.sqft, [lo_p, hi_p])
        band = sub[(sub.sqft >= lo) & (sub.sqft <= hi)]
        dims = np.array([rect_dims(g) for g in band.geometry.values])
        w, dep, rarea = dims[:, 0], dims[:, 1], dims[:, 2]
        aspect = dep / w
        rect = band.sqft.values / rarea
        wq = np.percentile(w, [25, 50, 75])
        dq = np.percentile(dep, [25, 50, 75])
        rows.append({"district": d, "band": f"p{lo_p}-p{hi_p}",
                     "size_lo": int(lo), "size_hi": int(hi), "n": len(band),
                     "width_p25": round(wq[0], 1), "width_p50": round(wq[1], 1), "width_p75": round(wq[2], 1),
                     "depth_p25": round(dq[0], 1), "depth_p50": round(dq[1], 1), "depth_p75": round(dq[2], 1),
                     "aspect_p50": round(np.median(aspect), 2), "rect_p50": round(np.median(rect), 2)})

out = pd.DataFrame(rows)
out.to_csv(os.path.join(DATA, "mf12_lot_dims.csv"), index=False)
pd.set_option("display.width", 240)
print("MF-1 / MF-2 lot dimensions by size band (oriented-rectangle method, ft)\n")
print(out.to_string(index=False))
for r in rows:
    print(f"\n{r['district']} {r['band']}: typical lot {r['size_lo']:,}-{r['size_hi']:,} sqft "
          f"~ {r['width_p50']:.0f} ft wide x {r['depth_p50']:.0f} ft deep "
          f"(depth/width {r['aspect_p50']}, rectangularity {r['rect_p50']})")
