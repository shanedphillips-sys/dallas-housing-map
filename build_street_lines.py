"""
Dallas STREET lines for the street-grid DISPLAY layer: the OSMnx "drive" network
only — no service roads or alleys. Alleys are now their own separate map layer
(see build_alleys.py / data/alleys_dallas.geojson), so streets can be viewed with
or without alleys. Each segment is classified GRID (part of a loop / cycle) vs.
STUB (a network bridge — dead-end / cul-de-sac), the same test as the dendricity
layer. We pull the City of Dallas buffered by 1.5 km (so boundary streets aren't
false dead-ends), classify bridges, then clip the output to the city.

(The tract dendricity CHOROPLETH stays on the stricter "drive" network — see
build_street_dendricity.py. This only feeds the street-grid display layer.)

Output: data/streets_dallas.geojson  (LineString, property kind = "grid" | "stub")
"""
import json
import os
import time

import networkx as nx
import osmnx as ox
import geopandas as gpd
from shapely import wkt
from shapely.geometry import LineString, Point
from shapely.prepared import prep

WEBMAP_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(WEBMAP_DIR)
DATA = os.path.join(WEBMAP_DIR, "data")
CITY = os.path.join(DATA, "city_boundary.geojson")
OUT = os.path.join(DATA, "streets_dallas.geojson")

ox.settings.use_cache = True
ox.settings.cache_folder = os.path.join(PROJECT_DIR, "osm_cache", "overpass")
ox.settings.requests_timeout = 300

SIMPLIFY_DEG = 0.00003   # ~3 m; invisible at display zoom, much smaller files
ROUND = 5                # ~1 m coordinate precision

DRIVE_HW = ("motorway|motorway_link|trunk|trunk_link|primary|primary_link|"
            "secondary|secondary_link|tertiary|tertiary_link|unclassified|"
            "residential|living_street|road")
FILTERS = f'["highway"~"^({DRIVE_HW})$"]'   # drive roads only (alleys = build_alleys.py)

t0 = time.time()
def log(m): print(f"[{time.time()-t0:.0f}s] {m}", flush=True)


# 1. City polygon + a 1.5 km pull buffer ------------------------------------
city = gpd.read_file(CITY).to_crs(4326).geometry.union_all()
pull_poly = gpd.GeoSeries([city], crs=4326).to_crs(3857).buffer(1500).to_crs(4326).iloc[0]
pcity = prep(city)

# 2. Pull drive + alleys TOGETHER (correct shared topology) -----------------
log("pulling drive + alleys for Dallas + 1.5 km ...")
G = ox.graph_from_polygon(pull_poly, custom_filter=FILTERS,
                          retain_all=True, truncate_by_edge=True)
log(f"  {G.number_of_nodes():,} nodes, {G.number_of_edges():,} edges")

# 3. Bridge / cycle classification ------------------------------------------
log("classifying bridges ...")
U = ox.convert.to_undirected(G)
S = nx.Graph(U)
parallel = {frozenset((u, v)) for u, v in U.edges() if U.number_of_edges(u, v) > 1}
bridges = {frozenset(e) for e in nx.bridges(S)}
def is_stub(u, v):
    fs = frozenset((u, v))
    return fs in bridges and fs not in parallel

# 4. Emit each in-city edge as a classified LineString ----------------------
log("building line features ...")
feats = []
n_seen = n_stub = 0
for u, v, d in U.edges(data=True):
    geom = d.get("geometry")
    if isinstance(geom, str):
        geom = wkt.loads(geom)
    if geom is None:
        geom = LineString([(G.nodes[u]["x"], G.nodes[u]["y"]),
                           (G.nodes[v]["x"], G.nodes[v]["y"])])
    geom = geom.simplify(SIMPLIFY_DEG, preserve_topology=False)
    coords = [[round(x, ROUND), round(y, ROUND)] for x, y in geom.coords]
    if len(coords) < 2:
        continue
    n_seen += 1
    mx, my = coords[len(coords) // 2]
    if not pcity.contains(Point(mx, my)):
        continue
    stub = is_stub(u, v)
    n_stub += stub
    nm = d.get("name")
    if isinstance(nm, list):
        nm = next((x for x in nm if x), None)
    props = {"kind": "stub" if stub else "grid"}
    if nm:
        props["name"] = str(nm)
    feats.append({"type": "Feature",
                  "properties": props,
                  "geometry": {"type": "LineString", "coordinates": coords}})
log(f"  {n_seen:,} segments scanned -> {len(feats):,} in Dallas ({n_stub:,} stub)")

with open(OUT, "w") as f:
    json.dump({"type": "FeatureCollection", "name": "streets_dallas", "features": feats}, f)
log(f"Wrote {OUT}  ({os.path.getsize(OUT) / 1e6:.1f} MB)")
log("Done.")
