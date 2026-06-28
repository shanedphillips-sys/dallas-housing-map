"""
Share of City-of-Dallas land in each base zoning district.

Area per `zone_dist` (the as-coded zoning district) from data/zoning.geojson,
clipped to the city boundary. Share = district area / total zoned area in the city
(zoning tiles the city, so total zoned area ~ city land area). Planned Development
(PD) and Conservation District (CD) are each ONE class here — the individual PD/CD
numbers live in pd_num/cd_num, not in zone_dist.

Writes data/zoning_share.csv and prints the full table.
"""
import os

import geopandas as gpd
import pandas as pd
import shapely

WEB = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(WEB, "data")
SQ_FT_PER_ACRE = 43560.0

z = gpd.read_file(os.path.join(DATA, "zoning.geojson")).to_crs("EPSG:2276")
z["geometry"] = shapely.make_valid(z.geometry.values)
city = gpd.read_file(os.path.join(DATA, "city_boundary.geojson")).to_crs("EPSG:2276")
city_geom = shapely.make_valid(city.geometry.union_all())
z = gpd.clip(z, city_geom)

z["zone_dist"] = z["zone_dist"].astype(str).str.strip()
z["acres"] = z.geometry.area / SQ_FT_PER_ACRE

cat = z.groupby("zone_dist")["category"].agg(lambda s: s.value_counts().idxmax())
g = z.groupby("zone_dist").agg(polygons=("zone_dist", "size"), acres=("acres", "sum"))
g["category"] = cat
total = g["acres"].sum()
g["sq_mi"] = g["acres"] / 640.0
g["pct"] = g["acres"] / total * 100.0
g = (g.sort_values("acres", ascending=False).reset_index()
     [["zone_dist", "category", "polygons", "acres", "sq_mi", "pct"]])
g[["acres", "sq_mi", "pct"]] = g[["acres", "sq_mi", "pct"]].round({"acres": 1, "sq_mi": 2, "pct": 2})

g.to_csv(os.path.join(DATA, "zoning_share.csv"), index=False)
pd.set_option("display.max_rows", None, "display.width", 200)
print(f"City of Dallas — total zoned land {total:,.0f} acres "
      f"({total / 640:,.1f} sq mi); {len(g)} distinct zoning districts\n")
print(g.to_string(index=False))
print(f"\n(sum of % column = {g['pct'].sum():.1f})")
