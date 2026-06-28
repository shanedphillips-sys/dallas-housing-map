"""
OSM water bodies (natural=water) for the City of Dallas -> data/water_dallas.geojson.

Used as a mask on the webmap to remove water from the zoning / land-use / FAR /
decade fill layers (those layers color parcels/zoning polygons that cover lakes &
the river, which shouldn't read as a zoning or land-use category).
"""
import os

import geopandas as gpd
import osmnx as ox
import shapely

WEB = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(WEB)
DATA = os.path.join(WEB, "data")
OUT = os.path.join(DATA, "water_dallas.geojson")

ox.settings.use_cache = True
ox.settings.cache_folder = os.path.join(PROJECT, "osm_cache", "overpass")
ox.settings.requests_timeout = 600

city = gpd.read_file(os.path.join(DATA, "city_boundary.geojson")).to_crs(4326)
cgeom = city.geometry.union_all()
print("pulling OSM natural=water for City of Dallas ...", flush=True)
w = ox.features_from_polygon(cgeom, tags={"natural": "water"})
w = w[w.geometry.type.isin(["Polygon", "MultiPolygon"])].copy()
print(f"  {len(w):,} water polygons (raw)", flush=True)

w = w.to_crs(3857)
w["geometry"] = shapely.simplify(shapely.make_valid(w.geometry.values), 4)
city3857 = shapely.make_valid(city.to_crs(3857).geometry.union_all())
w = gpd.clip(w, city3857)
w = w[shapely.area(w.geometry.values) >= 2000].copy()   # drop tiny ponds (<~0.5 acre)
out = w.to_crs(4326)
out = out[~out.geometry.is_empty & out.geometry.notna()][["geometry"]]
out.to_file(OUT, driver="GeoJSON", coordinate_precision=5)
print(f"wrote {OUT}  ({len(out)} water bodies, {os.path.getsize(OUT) / 1e6:.2f} MB, "
      f"{w.geometry.area.sum() / 2_589_988:,.1f} sq mi water)", flush=True)
