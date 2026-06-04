"""
Build county boundaries for the 7 counties covered by the jobs / pop-HU / ACS
layers, by dissolving the existing tract geometry (data/tracts.geojson) on the
county FIPS (first 5 chars of the 11-digit tract GEOID).

Dissolving the tracts we already ship keeps the county outlines aligned with the
tract/jobs/ACS layers and needs no separate TIGER download. But the shipped
tracts are simplified (~10 m), so adjacent tracts no longer share exact edges —
a naive dissolve leaves hundreds of sliver-holes (an unrenderable 600+-ring
polygon). We fix that with a morphological close in a metric CRS (buffer out,
buffer back in) to bridge the gaps, then drop interior holes (counties have no
genuine holes here), then simplify.

Output: data/counties.geojson  (one feature per county; props: fips, name)
"""

import os
import geopandas as gpd
from shapely.geometry import Polygon, MultiPolygon

WEBMAP_DIR = os.path.dirname(os.path.abspath(__file__))
TRACTS = os.path.join(WEBMAP_DIR, "data", "tracts.geojson")
OUT_PATH = os.path.join(WEBMAP_DIR, "data", "counties.geojson")

COUNTY_NAMES = {
    "48113": "Dallas",
    "48085": "Collin",
    "48121": "Denton",
    "48439": "Tarrant",
    "48139": "Ellis",
    "48257": "Kaufman",
    "48397": "Rockwall",
}


def drop_holes(geom):
    """Keep only exterior rings — counties have no genuine holes here, so any
    interior ring is a sliver artifact of the simplified-tract dissolve."""
    if geom.geom_type == "Polygon":
        return Polygon(geom.exterior)
    if geom.geom_type == "MultiPolygon":
        return MultiPolygon([Polygon(p.exterior) for p in geom.geoms])
    return geom


print(f"Reading {TRACTS} ...")
g = gpd.read_file(TRACTS)
g["fips"] = g["geoid"].astype(str).str[:5]

print("Dissolving tracts to counties ...")
counties = g.dissolve(by="fips").reset_index()[["fips", "geometry"]]

# Close gaps + remove sliver-holes in a metric CRS (Web Mercator, meters).
counties = counties.to_crs(3857)
counties["geometry"] = counties.geometry.buffer(150).buffer(-150)  # bridge sub-150 m gaps
counties["geometry"] = counties.geometry.apply(drop_holes)
counties["geometry"] = counties.geometry.simplify(60)
counties = counties.to_crs(4326)

counties["name"] = counties["fips"].map(COUNTY_NAMES)
counties = counties.sort_values("name").reset_index(drop=True)

# Diagnostics: parts + ring counts (should be ~1 part, 1 ring per county).
for _, r in counties.iterrows():
    geom = r.geometry
    if geom.geom_type == "Polygon":
        parts, rings = 1, len(geom.interiors) + 1
    else:
        parts = len(geom.geoms)
        rings = sum(len(p.interiors) + 1 for p in geom.geoms)
    print(f"  {r['name']:8s} fips={r['fips']}  parts={parts}  rings={rings}")

counties.to_file(OUT_PATH, driver="GeoJSON")
print(f"Wrote {OUT_PATH}  ({len(counties)} counties)")
