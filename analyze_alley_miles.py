"""Total miles of alley in the City of Dallas (OSM service=alley, clipped to city;
data/alleys_dallas.geojson). Length measured in EPSG:2276 (Texas N Central, ftUS)."""
import os

import geopandas as gpd

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

a = gpd.read_file(os.path.join(DATA, "alleys_dallas.geojson")).to_crs(2276)
miles = a.geometry.length.sum() / 5280.0
print(f"alley segments: {len(a):,}")
print(f"total alley length: {miles:,.1f} miles")
