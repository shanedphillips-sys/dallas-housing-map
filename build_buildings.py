"""
3D building footprints for the City of Dallas -> data/buildings_dallas.geojson
(Polygon, property `height_m`).

Hybrid of two sources, because neither alone is good enough:

* GEOMETRY + most heights: Microsoft GlobalMLBuildingFootprints (`meanHeight`),
  pulled from the Planetary Computer Delta table. Quadkey 23112330 (zoom 9) covers
  the whole City of Dallas. ~1M footprints in the tile; ~350k fall in the city.
  Strength: ML footprints are complete and uniform, and 25% carry a height
  (vs OSM's ~1%), which gives residential neighborhoods real texture.

* TALL-building heights: Microsoft's `meanHeight` is low-rise only -- max ~39 m
  across the whole tile, and EVERY downtown/uptown tower is -1 (unknown). MS-only
  would render a flat downtown. So we overlay OSM `height` / `building:levels`
  (which carry the real skyline, 200-280 m) onto MS footprints whose centroid
  falls inside a height-tagged OSM building.

height_m = MS meanHeight if > 0,
           else OSM tagged height (height m, feet auto-converted; or levels x 3.2 m)
           else 6 m default (~2 stories).
Clipped 2.5-600 m. Simplified ~5 m, footprints < 30 m^2 dropped.
"""
import io
import os
import re

import geopandas as gpd
import numpy as np
import osmnx as ox
import pandas as pd
import planetary_computer as pc
import pyarrow as pa
import pyarrow.parquet as pq
import pystac_client
import requests
import shapely
from deltalake import DeltaTable

WEB = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(WEB)
DATA = os.path.join(WEB, "data")
OUT = os.path.join(DATA, "buildings_dallas.geojson")
QUADKEY = "23112330"  # zoom-9 Bing quadkey covering the City of Dallas

ox.settings.use_cache = True
ox.settings.cache_folder = os.path.join(PROJECT, "osm_cache", "overpass")
ox.settings.requests_timeout = 600


def parse_height(h):
    if not isinstance(h, str):
        return np.nan
    s = h.lower()
    ft = ("'" in s) or ("ft" in s) or ("feet" in s)
    m = re.search(r"[\d.]+", s)
    if not m:
        return np.nan
    v = float(m.group())
    return v * 0.3048 if ft else v


# ---- City of Dallas boundary ------------------------------------------------
city = gpd.read_file(os.path.join(DATA, "city_boundary.geojson")).to_crs(4326)
cgeom = city.geometry.union_all()
minx, miny, maxx, maxy = city.total_bounds

# ---- Microsoft footprints (Planetary Computer Delta table) ------------------
print("opening ms-buildings Delta table ...", flush=True)
cat = pystac_client.Client.open("https://planetarycomputer.microsoft.com/api/stac/v1")
asset = cat.get_collection("ms-buildings").assets["delta"]
acct = asset.extra_fields["table:storage_options"]["account_name"]
tok = pc.sas.get_token(acct, "footprints").token.lstrip("?")
dt = DeltaTable(asset.href, storage_options={"account_name": acct, "sas_token": tok})
uris = [u for u in dt.file_uris()
        if "RegionName=UnitedStates" in u and f"quadkey={QUADKEY}" in u]
print(f"  Dallas-quadkey parquet parts: {len(uris)}", flush=True)


def load_part(u):
    blob = u.split("az://footprints/")[1]
    url = f"https://{acct}.blob.core.windows.net/footprints/{blob}?{tok}"
    buf = io.BytesIO()
    with requests.get(url, stream=True, timeout=300) as r:
        r.raise_for_status()
        for chunk in r.iter_content(8 << 20):
            buf.write(chunk)
    buf.seek(0)
    return pq.read_table(buf, columns=["geometry", "meanHeight"])


t = pa.concat_tables([load_part(u) for u in uris])
mh = t.column("meanHeight").to_numpy(zero_copy_only=False).astype("float64")
geoms = shapely.from_wkb(t.column("geometry").to_numpy(zero_copy_only=False))
ms = gpd.GeoDataFrame({"meanHeight": mh}, geometry=geoms, crs=4326)
print(f"  {len(ms):,} MS footprints in tile", flush=True)

# keep only buildings IN the City of Dallas, by CENTROID (a building belongs to
# whichever jurisdiction contains its center) -- excludes edge buildings that
# merely touch the city line but sit mostly in Irving/Garland/etc. Cheap bbox cut
# first, then the precise centroid-in-polygon test.
ms = ms.cx[minx:maxx, miny:maxy].reset_index(drop=True)
city3857 = city.to_crs(3857).geometry.union_all()
inside = ms.geometry.to_crs(3857).centroid.within(city3857)
ms = ms[inside.values].reset_index(drop=True)
print(f"  {len(ms):,} with centroid in City of Dallas | meanHeight>0: {(ms.meanHeight > 0).mean() * 100:.0f}%", flush=True)

# ---- OSM height-tagged buildings (the skyline MS is missing) ----------------
print("pulling OSM buildings for height tags (cached) ...", flush=True)
b = ox.features_from_polygon(cgeom, tags={"building": True})
b = b[b.geometry.type.isin(["Polygon", "MultiPolygon"])].copy()
lev = pd.to_numeric(b["building:levels"], errors="coerce") if "building:levels" in b.columns else pd.Series(np.nan, index=b.index)
hgt = b["height"].map(parse_height) if "height" in b.columns else pd.Series(np.nan, index=b.index)
osm_h = hgt.fillna(lev * 3.2)
osm = gpd.GeoDataFrame({"osm_h": osm_h.values}, geometry=b.geometry.values, crs=4326)
osm = osm[osm["osm_h"].notna()].reset_index(drop=True)
osm["geometry"] = shapely.make_valid(osm.geometry.values)
print(f"  {len(osm):,} OSM buildings carry a height/levels tag (incl. downtown towers)", flush=True)

# ---- assign OSM tower heights to MS footprints by centroid-in-polygon -------
ms3857 = ms.to_crs(3857)
osm3857 = osm.to_crs(3857)
pts = ms3857.copy()
pts["geometry"] = ms3857.geometry.centroid
j = gpd.sjoin(pts[["geometry"]], osm3857[["osm_h", "geometry"]], predicate="within", how="left")
osm_per_ms = j.groupby(level=0)["osm_h"].max()
ms3857["osm_h"] = osm_per_ms.reindex(ms3857.index)

# ---- final height + geometry cleanup ----------------------------------------
used_osm = (~(ms3857["meanHeight"].values > 0)) & ms3857["osm_h"].notna().values
h = np.where(ms3857["meanHeight"].values > 0, ms3857["meanHeight"].values, ms3857["osm_h"].values)
h = pd.Series(h, index=ms3857.index).fillna(6.0).clip(2.5, 600)
ms3857["height_m"] = h.round(1).values
# `src` = which dataset the footprint is attributed to: "osm" where we relied on an
# OSM building (the towers Microsoft leaves blank), else "ms" (Microsoft ML footprint).
ms3857["src"] = np.where(used_osm, "osm", "ms")
ms3857["geometry"] = shapely.simplify(ms3857.geometry.values, 5)
ms3857 = ms3857[shapely.area(ms3857.geometry.values) >= 30].copy()
out = ms3857.to_crs(4326)
out = out[~out.geometry.is_empty & out.geometry.notna()].copy()

n_osm = int((out["src"] == "osm").sum())
print(f"source: Microsoft {len(out) - n_osm:,} | OSM {n_osm:,}", flush=True)
print(f"  tallest building: {out['height_m'].max():.0f} m | >100 m: {(out['height_m'] > 100).sum()}", flush=True)
out[["height_m", "src", "geometry"]].to_file(OUT, driver="GeoJSON", coordinate_precision=5)
print(f"wrote {OUT}  {len(out):,} buildings  {os.path.getsize(OUT) / 1e6:.1f} MB", flush=True)
