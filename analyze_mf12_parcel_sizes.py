"""
Parcel-size distribution (sq ft) for land in the MF-1 and MF-2 zoning districts.

Every parcel is assigned to the base district (zone_norm) its centroid falls in;
parcel size = geometric polygon area in EPSG:2276 (Texas N Central, ftUS). ALL
parcels in the district (any land use), unweighted — each parcel is one
observation. Writes data/mf12_parcel_sizes.csv.
"""
import os

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

WEB = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(WEB, "data")
DISTRICTS = ["MF-1", "MF-2"]

z = gpd.read_file(os.path.join(DATA, "zoning.geojson"))[["zone_norm", "geometry"]].to_crs(2276)
z["geometry"] = shapely.make_valid(z.geometry.values)
z = z[z.zone_norm.isin(DISTRICTS)]

p = pd.concat([gpd.read_file(os.path.join(DATA, f"parcels_{q}.geojson"))[["geometry"]]
               for q in ["nw", "ne", "sw", "se"]], ignore_index=True)
p = gpd.GeoDataFrame(p, crs="EPSG:4326").to_crs(2276)
p["geometry"] = shapely.make_valid(p.geometry.values)
p["sqft"] = shapely.area(p.geometry.values)
p = p[p.sqft > 0].copy()
p["geometry"] = shapely.centroid(p.geometry.values)
j = gpd.sjoin(p[["sqft", "geometry"]], z, predicate="within", how="inner")

rows = []
for d in DISTRICTS + ["MF-1 & MF-2"]:
    a = (j if d == "MF-1 & MF-2" else j[j.zone_norm == d]).sqft.values
    rows.append({"district": d, "parcels": len(a),
                 "total_acres": round(a.sum() / 43560.0, 1),
                 "mean_sqft": int(a.mean()),
                 "p10": int(np.percentile(a, 10)), "p25": int(np.percentile(a, 25)),
                 "p50": int(np.percentile(a, 50)), "p75": int(np.percentile(a, 75)),
                 "p90": int(np.percentile(a, 90))})
out = pd.DataFrame(rows)
out.to_csv(os.path.join(DATA, "mf12_parcel_sizes.csv"), index=False)
pd.set_option("display.width", 200)
print("Parcel size (sq ft) for land in MF-1 / MF-2 districts — unweighted\n")
print(out.to_string(index=False))
print(f"\nsmallest parcel: {int(j.sqft.min()):,} sqft | largest: {int(j.sqft.max()):,} sqft")
