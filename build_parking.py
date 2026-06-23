"""
OSM surface parking lots for the City of Dallas -> data/parking_dallas.geojson.

amenity=parking polygons, kept where `parking` is `surface` or untagged (the
untagged lots are overwhelmingly surface). Excludes structured parking
(multi-storey / underground / rooftop / carports / garage) and on-street forms
(street_side / lane). Clipped to the city by centroid; one `area_acres` per lot.
Companion to build_buildings.py / build_alleys.py.
"""
import os

import geopandas as gpd
import osmnx as ox
import shapely

WEB = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(WEB)
DATA = os.path.join(WEB, "data")
OUT = os.path.join(DATA, "parking_dallas.geojson")

ox.settings.use_cache = True
ox.settings.cache_folder = os.path.join(PROJECT, "osm_cache", "overpass")
ox.settings.requests_timeout = 600

city = gpd.read_file(os.path.join(DATA, "city_boundary.geojson")).to_crs(4326)
cgeom = city.geometry.union_all()
city3857 = city.to_crs(3857).geometry.union_all()

print("pulling OSM amenity=parking ...", flush=True)
p = ox.features_from_polygon(cgeom, tags={"amenity": "parking"})
p = p[p.geometry.type.isin(["Polygon", "MultiPolygon"])].copy()
if "parking" in p.columns:
    pk = p["parking"]
    p = p[pk.isna() | (pk == "surface")].copy()  # surface + untagged only
print(f"  surface(+untagged) parking polygons: {len(p):,}", flush=True)

# keep only lots whose centroid is IN the City of Dallas
p = p.reset_index(drop=True)
inside = p.geometry.to_crs(3857).centroid.within(city3857)
p = p[inside.values].reset_index(drop=True)

# area (acres) from an equal-area-ish projection, before simplifying
p["area_acres"] = (p.geometry.to_crs(2276).area / 43560.0).round(2).values

# simplify + drop slivers (< 150 m^2 ~ a few stalls)
g = p.to_crs(3857)
g["geometry"] = shapely.simplify(shapely.make_valid(g.geometry.values), 4)
g = g[shapely.area(g.geometry.values) >= 150].copy()
out = g.to_crs(4326)
out = out[~out.geometry.is_empty & out.geometry.notna()].copy()
out = out[["area_acres", "geometry"]]
out.to_file(OUT, driver="GeoJSON", coordinate_precision=5)
print(f"wrote {OUT}  {len(out):,} lots  {os.path.getsize(OUT) / 1e6:.2f} MB  "
      f"({out['area_acres'].sum():,.0f} acres total)", flush=True)
