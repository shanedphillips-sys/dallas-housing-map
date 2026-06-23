"""
Identify alleys (OSM highway=service + service=alley) in the City of Dallas and
measure alley concentration per census tract -- to flag alley-rich neighborhoods
(rear-access lots: ADUs / garage apartments / alley-loaded design-standard work).

Outputs:
  data/alleys_dallas.geojson  -- alley centerlines clipped to the city (optional map layer)
  data/alleys_tracts.geojson  -- per city tract: alley_mi, area_sqmi, alley_density (mi/sqmi)
"""
import json
import os

import geopandas as gpd
import osmnx as ox

WEB = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(WEB)
DATA = os.path.join(WEB, "data")
TXSP = 2276                      # NAD83 / Texas North Central (US survey foot) -- accurate lengths
SQFT_PER_SQMI = 5280.0 ** 2

ox.settings.use_cache = True
ox.settings.cache_folder = os.path.join(PROJECT, "osm_cache", "overpass")
ox.settings.requests_timeout = 300

city = gpd.read_file(os.path.join(DATA, "city_boundary.geojson")).to_crs(4326)
poly = city.geometry.union_all()

print("pulling OSM alleys (service=alley) for City of Dallas ...")
al = ox.features_from_polygon(poly, tags={"service": "alley"})
al = al[al.geometry.type.isin(["LineString", "MultiLineString"])].copy()
if "highway" in al.columns:
    al = al[al["highway"] == "service"]
al = al[["geometry"]].to_crs(TXSP)
print(f"  {len(al):,} alley ways, {al.geometry.length.sum()/5280:,.0f} mi (city bbox, pre-clip)")

tracts = gpd.read_file(os.path.join(DATA, "tracts.geojson"))[["geoid", "geometry"]].to_crs(TXSP)
city_sp = city.to_crs(TXSP).geometry.union_all()
tracts["incity"] = tracts.geometry.centroid.within(city_sp)
ct = tracts[tracts["incity"]][["geoid", "geometry"]].copy()

seg = gpd.overlay(al, ct, how="intersection", keep_geom_type=True)
seg["mi"] = seg.geometry.length / 5280.0
per = seg.groupby("geoid")["mi"].sum()
ct["area_sqmi"] = ct.geometry.area / SQFT_PER_SQMI
ct["alley_mi"] = ct["geoid"].map(per).fillna(0.0)
ct["alley_density"] = ct["alley_mi"] / ct["area_sqmi"]

print(f"\nCity of Dallas alleys (clipped): {ct['alley_mi'].sum():,.0f} mi across {(ct['alley_mi']>0).sum()} of {len(ct)} tracts")
q = ct["alley_density"]
print(f"alley density mi/sqmi: median {q.median():.1f}  p75 {q.quantile(.75):.1f}  p90 {q.quantile(.9):.1f}  max {q.max():.1f}")

cc = ct.to_crs(4326)
cc["cx"] = cc.geometry.centroid.x
cc["cy"] = cc.geometry.centroid.y
cxy = {r.geoid: (r.cy, r.cx) for r in cc.itertuples()}
print("\nTop 18 tracts by alley density (mi/sqmi):")
for r in ct.sort_values("alley_density", ascending=False).head(18).itertuples():
    cy, cx = cxy[r.geoid]
    print(f"  {r.geoid}  {r.alley_density:5.1f} mi/sqmi  ({r.alley_mi:4.1f} mi)  {cy:.4f},{cx:.4f}")

# ---- write outputs ---------------------------------------------------------
seg_wgs = seg[["geometry"]].to_crs(4326)
seg_wgs["geometry"] = seg_wgs.simplify(0.00002, preserve_topology=False)
seg_wgs.to_file(os.path.join(DATA, "alleys_dallas.geojson"), driver="GeoJSON")

cto = ct.to_crs(4326)[["geoid", "alley_mi", "alley_density", "area_sqmi", "geometry"]].copy()
for c in ("alley_mi", "alley_density", "area_sqmi"):
    cto[c] = cto[c].round(3)
gj = json.loads(cto.to_json())
json.dump(gj, open(os.path.join(DATA, "alleys_tracts.geojson"), "w"), allow_nan=False)
print(f"\nWrote data/alleys_dallas.geojson ({os.path.getsize(os.path.join(DATA,'alleys_dallas.geojson'))/1e6:.1f} MB) "
      f"and data/alleys_tracts.geojson")
