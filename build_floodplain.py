"""
FEMA National Flood Hazard Layer flood zones for the City of Dallas, from the FEMA
public NFHL ArcGIS service (layer 28, S_FLD_HAZ_AR). Two categories:
  100yr  = 1% annual-chance Special Flood Hazard Area (zones A/AE/AH/AO/AR/A99/V/VE)
  500yr  = 0.2% annual-chance flood hazard (Zone X shaded)

The service caps pagination at ~10k records, so the city bbox is tiled into a grid;
each cell is paged independently and features deduped by OBJECTID. Clipped to the
city boundary and lightly simplified. Output: data/floodplain.geojson
"""
import os
import time

import geopandas as gpd
import requests
import shapely
from shapely.geometry import shape

WEB = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(WEB, "data")
URL = "https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28/query"
WHERE = ("FLD_ZONE IN ('A','AE','AH','AO','AR','A99','V','VE') "
         "OR ZONE_SUBTY = '0.2 PCT ANNUAL CHANCE FLOOD HAZARD'")
SFHA = {"A", "AE", "AH", "AO", "AR", "A99", "V", "VE"}
LON, LAT, NX, NY = (-97.05, -96.44), (32.60, 33.06), 4, 4


def fetch_cell(xmin, ymin, xmax, ymax):
    out, offset, page_size = [], 0, None
    while True:
        for attempt in range(3):
            try:
                r = requests.get(URL, params={
                    "where": WHERE, "geometry": f"{xmin},{ymin},{xmax},{ymax}",
                    "geometryType": "esriGeometryEnvelope", "inSR": "4326", "outSR": "4326",
                    "outFields": "OBJECTID,FLD_ZONE,ZONE_SUBTY", "returnGeometry": "true",
                    "f": "geojson", "resultRecordCount": 2000, "resultOffset": offset}, timeout=180)
                r.raise_for_status()
                break
            except requests.HTTPError:
                if attempt == 2:
                    raise
                time.sleep(2)
        fs = [f for f in r.json().get("features", []) if f.get("geometry")]
        out.extend(fs)
        if page_size is None:
            page_size = len(fs)
        offset += len(fs)
        if len(fs) == 0 or len(fs) < page_size:
            return out
        time.sleep(0.2)


xs = [LON[0] + (LON[1] - LON[0]) * i / NX for i in range(NX + 1)]
ys = [LAT[0] + (LAT[1] - LAT[0]) * j / NY for j in range(NY + 1)]
allf = {}
for i in range(NX):
    for j in range(NY):
        fs = fetch_cell(xs[i], ys[j], xs[i + 1], ys[j + 1])
        for f in fs:
            allf[f.get("id") or f["properties"].get("OBJECTID")] = f
        print(f"  cell {i},{j}: {len(fs)} (unique total {len(allf)})", flush=True)
feats = list(allf.values())

geoms = [shape(f["geometry"]) for f in feats]
cats = ["100yr" if f["properties"].get("FLD_ZONE") in SFHA else "500yr" for f in feats]
g = gpd.GeoDataFrame({"category": cats}, geometry=geoms, crs=4326)
g["geometry"] = shapely.make_valid(g.geometry.values)
city = gpd.read_file(os.path.join(DATA, "city_boundary.geojson")).to_crs(4326)
g = gpd.clip(g, shapely.make_valid(city.geometry.union_all()))
g = g.to_crs(3857)
g["geometry"] = shapely.simplify(shapely.make_valid(g.geometry.values), 8)
g = g.to_crs(4326)
g = g[~g.geometry.is_empty & g.geometry.notna()].copy()

op = os.path.join(DATA, "floodplain.geojson")
g.to_file(op, driver="GeoJSON", coordinate_precision=5)
print(f"wrote {op}: {len(g)} polys "
      f"({int((g.category == '100yr').sum())} 100yr, {int((g.category == '500yr').sum())} 500yr), "
      f"{os.path.getsize(op) / 1e6:.1f} MB")
