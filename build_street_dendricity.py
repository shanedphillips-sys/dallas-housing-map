"""
Per-tract street-network DENDRICITY for the 7-county region, from OpenStreetMap
via OSMnx — a measure of how "tree-like" (cul-de-sac / suburban) vs. "looped"
(grid / connected) the local street network is.

Method (after Barrington-Leigh & Millard-Ball's Street-Network Disconnectedness
Index): classify every street edge as a network BRIDGE (an edge whose removal
disconnects the network — this includes dead-ends/culs-de-sac) or part of a
CYCLE (a loop). Dendricity = length-weighted share of bridge street length.
  0.0 = fully looped mesh / grid      1.0 = pure tree (everything a dead-end)

Bridges are a GLOBAL property, so we pull the drive network for all 7 counties,
compose into ONE graph (shared OSM node IDs stitch county boundaries), and
classify bridges on the whole network — THEN assign each edge to a tract by its
midpoint and aggregate. (Computing bridges on a per-tract subgraph would be wrong:
a through-street clipped at the tract edge would look like a dead-end.)

Output: data/street_dendricity_tracts.geojson
  props per tract: geoid, dendricity, street_mi, n_intersections,
  intersection_density (per sq mi), pct_deadend (dead-ends / (dead-ends+intersections)).

Env: ONLY_COUNTIES=397,257  limits to those county FIPS (for a quick test run).
Per-county graphs are cached as graphml under ../osm_cache so reruns are cheap.
"""
import json
import os
import time

import networkx as nx
import osmnx as ox
import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

WEBMAP_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(WEBMAP_DIR)
DATA = os.path.join(WEBMAP_DIR, "data")
TRACTS = os.path.join(DATA, "tracts.geojson")
OUT = os.path.join(DATA, "street_dendricity_tracts.geojson")
CACHE = os.path.join(PROJECT_DIR, "osm_cache")
os.makedirs(CACHE, exist_ok=True)

ox.settings.use_cache = True
ox.settings.cache_folder = os.path.join(CACHE, "overpass")
ox.settings.requests_timeout = 300

COUNTY_FIPS = {"48113": "Dallas", "48085": "Collin", "48121": "Denton",
               "48439": "Tarrant", "48139": "Ellis", "48257": "Kaufman",
               "48397": "Rockwall"}
ONLY = set(f.strip() for f in os.environ.get("ONLY_COUNTIES", "").split(",") if f.strip())

t0 = time.time()
def log(m): print(f"[{time.time()-t0:.0f}s] {m}", flush=True)


# ---------------------------------------------------------------------------
# 1. Tract geometry (2020) + per-county dissolve for the OSM pull
# ---------------------------------------------------------------------------
log("Loading tracts ...")
tracts = gpd.read_file(TRACTS)[["geoid", "land_sq_mi", "geometry"]]
tracts["cfips"] = tracts["geoid"].str[:5]
counties = tracts.dissolve("cfips").reset_index()
# smallest-area county first so a test run / early failure surfaces fast
counties["_a"] = counties.geometry.area
counties = counties.sort_values("_a")


# ---------------------------------------------------------------------------
# 2. Pull each county's drive network (cached), compose into one graph
# ---------------------------------------------------------------------------
graphs = []
for _, c in counties.iterrows():
    fips = c["cfips"]
    if ONLY and fips not in ONLY:
        continue
    gml = os.path.join(CACHE, f"drive_{fips}.graphml")
    if os.path.exists(gml):
        log(f"{COUNTY_FIPS[fips]} ({fips}): loading cached graph ...")
        G = ox.load_graphml(gml)
    else:
        log(f"{COUNTY_FIPS[fips]} ({fips}): downloading OSM drive network ...")
        G = ox.graph_from_polygon(c.geometry, network_type="drive", truncate_by_edge=True)
        ox.save_graphml(G, gml)
    log(f"  {COUNTY_FIPS[fips]}: {G.number_of_nodes():,} nodes, {G.number_of_edges():,} edges")
    graphs.append(G)

log("Composing counties into one graph ...")
G = nx.compose_all(graphs) if len(graphs) > 1 else graphs[0]
log(f"  composed: {G.number_of_nodes():,} nodes, {G.number_of_edges():,} edges")


# ---------------------------------------------------------------------------
# 3. Classify bridges (tree-like) vs. cycle edges on the whole network
# ---------------------------------------------------------------------------
log("Building undirected/simple graphs ...")
U = ox.convert.to_undirected(G)          # MultiGraph (keeps parallel edges)
S = nx.Graph(U)                          # simple graph for bridge finding
parallel = {frozenset((u, v)) for u, v in U.edges() if U.number_of_edges(u, v) > 1}
log("Finding bridges ...")
bridges = {frozenset(e) for e in nx.bridges(S)}   # tree-like simple edges (incl. dead-ends)
log(f"  {len(bridges):,} bridge edges of {S.number_of_edges():,} simple edges")

def is_tree(u, v):
    fs = frozenset((u, v))
    return fs in bridges and fs not in parallel   # parallel edges form a 2-cycle


# ---------------------------------------------------------------------------
# 4. Edge midpoints + tree flag -> spatial join to tracts -> dendricity
# ---------------------------------------------------------------------------
log("Building edge midpoints ...")
recs = []
for u, v, d in U.edges(data=True):
    length = d.get("length")
    if not length:
        continue
    geom = d.get("geometry")
    if geom is not None:
        mp = geom.interpolate(0.5, normalized=True)
    else:
        mp = Point((G.nodes[u]["x"] + G.nodes[v]["x"]) / 2.0,
                   (G.nodes[u]["y"] + G.nodes[v]["y"]) / 2.0)
    recs.append((length, is_tree(u, v), mp))
edges = gpd.GeoDataFrame(
    {"len": [r[0] for r in recs], "tree": [r[1] for r in recs]},
    geometry=[r[2] for r in recs], crs=tracts.crs)
log(f"  {len(edges):,} edges; joining to tracts ...")
ejoin = gpd.sjoin(edges, tracts[["geoid", "geometry"]], how="inner", predicate="within")
eagg = ejoin.groupby("geoid").apply(
    lambda g: pd.Series({"total_len": g["len"].sum(),
                         "tree_len": g.loc[g["tree"], "len"].sum()}),
    include_groups=False)


# ---------------------------------------------------------------------------
# 5. Node degrees -> dead-ends / intersections per tract
# ---------------------------------------------------------------------------
log("Joining nodes to tracts ...")
deg = dict(S.degree())
nodes = gpd.GeoDataFrame(
    {"deg": [deg[n] for n in G.nodes()]},
    geometry=[Point(G.nodes[n]["x"], G.nodes[n]["y"]) for n in G.nodes()], crs=tracts.crs)
njoin = gpd.sjoin(nodes, tracts[["geoid", "geometry"]], how="inner", predicate="within")
nagg = njoin.groupby("geoid").apply(
    lambda g: pd.Series({"n_deadend": int((g["deg"] == 1).sum()),
                         "n_intersection": int((g["deg"] >= 3).sum())}),
    include_groups=False)


# ---------------------------------------------------------------------------
# 6. Assemble per-tract props, write GeoJSON (manual, for clean nulls)
# ---------------------------------------------------------------------------
log("Assembling output ...")
land = dict(zip(tracts["geoid"], tracts["land_sq_mi"]))
props = {}
for geoid in tracts["geoid"]:
    e = eagg.loc[geoid] if geoid in eagg.index else None
    n = nagg.loc[geoid] if geoid in nagg.index else None
    d = {"geoid": geoid}
    if e is not None and e["total_len"] > 0:
        d["dendricity"] = round(e["tree_len"] / e["total_len"], 3)
        d["street_mi"] = round(e["total_len"] / 1609.344, 2)
    else:
        d["dendricity"], d["street_mi"] = None, None
    if n is not None:
        ni, nd = int(n["n_intersection"]), int(n["n_deadend"])
        sqmi = land.get(geoid) or 0
        d["n_intersections"] = ni
        d["intersection_density"] = round(ni / sqmi, 1) if sqmi else None
        d["pct_deadend"] = round(nd / (nd + ni) * 100, 1) if (nd + ni) else None
    else:
        d["n_intersections"] = d["intersection_density"] = d["pct_deadend"] = None
    props[geoid] = d

with open(TRACTS) as f:
    geo = json.load(f)
feats, n_have = [], 0
for ft in geo["features"]:
    g = str(ft["properties"]["geoid"])
    p = props.get(g, {"geoid": g})
    if p.get("dendricity") is not None:
        n_have += 1
    feats.append({"type": "Feature", "properties": p, "geometry": ft["geometry"]})
out = {"type": "FeatureCollection", "name": "street_dendricity_tracts", "features": feats}
with open(OUT, "w") as f:
    json.dump(out, f, allow_nan=False)

mb = os.path.getsize(OUT) / 1e6
log(f"Wrote {OUT}  ({len(feats)} tracts, {n_have} with dendricity, {mb:.1f} MB)")

vals = sorted(p["dendricity"] for p in props.values() if p.get("dendricity") is not None)
if vals:
    import statistics as st
    log(f"  dendricity: min {vals[0]:.2f}  median {st.median(vals):.2f}  max {vals[-1]:.2f}")
    # most grid-like and most dendritic tracts
    by = sorted((p for p in props.values() if p.get("dendricity") is not None),
                key=lambda p: p["dendricity"])
    log(f"  most grid-like:  {by[0]['geoid']} dendricity={by[0]['dendricity']}")
    log(f"  most dendritic:  {by[-1]['geoid']} dendricity={by[-1]['dendricity']}")
log("Done.")
