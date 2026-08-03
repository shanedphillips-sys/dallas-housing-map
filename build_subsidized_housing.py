"""
Subsidized (LIHTC) housing points for the webmap, from the TDHCA Housing Tax Credit
Property Inventory (OneDrive xlsx). City of Dallas properties with valid coords;
deduped by location (keeping the max-unit award record). Points carry total units,
LIHTC (income-restricted) units, award year, population served, program type.

Note: this is LIHTC only (the TDHCA inventory) — not public housing, HUD project-
based, or vouchers. Older awards (compliance is ~30 yrs) may be exiting affordability.
Output: data/subsidized_housing.geojson
"""
import json
import os

import geopandas as gpd
import pandas as pd

WEB = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(WEB, "data")
HTC = (r"C:\Users\shane\OneDrive\Documents\Domain Consulting\Projects"
       r"\GDPC - Dallas Housing Report\GDPC Claude Stuff\HTC Property Inventory as of May 29 2026.xlsx")


def clean(v):
    return None if pd.isna(v) else str(v).strip()


def ival(v):
    n = pd.to_numeric(v, errors="coerce")
    return None if pd.isna(n) else int(n)


h = pd.read_excel(HTC, sheet_name="PropInventory")
h["lat"] = pd.to_numeric(h["Latitude11"], errors="coerce")
h["lon"] = pd.to_numeric(h["Longitude11"], errors="coerce")
h = h.dropna(subset=["lat", "lon"])
h["_tot"] = pd.to_numeric(h["Total Units"], errors="coerce").fillna(0)
h = h.sort_values("_tot", ascending=False).drop_duplicates(subset=["lat", "lon"])   # one point per site

g = gpd.GeoDataFrame(h, geometry=gpd.points_from_xy(h.lon, h.lat), crs=4326)
city = gpd.read_file(os.path.join(DATA, "city_boundary.geojson")).to_crs(4326).geometry.union_all()
g = g[g.within(city)].copy()

feats = []
for _, r in g.iterrows():
    feats.append({"type": "Feature",
                  "geometry": {"type": "Point", "coordinates": [round(r.lon, 5), round(r.lat, 5)]},
                  "properties": {
                      "name": clean(r.get("Development Name")),
                      "address": clean(r.get("Project Address ")),
                      "year": ival(r.get("Year")),
                      "total_units": ival(r.get("Total Units")),
                      "lihtc_units": ival(r.get("LIHTC Units")),
                      "pop_served": clean(r.get("Population Served")),
                      "program": clean(r.get("Program Type")),
                  }})
op = os.path.join(DATA, "subsidized_housing.geojson")
json.dump({"type": "FeatureCollection", "features": feats}, open(op, "w"), allow_nan=False)
tot = sum(f["properties"]["total_units"] or 0 for f in feats)
li = sum(f["properties"]["lihtc_units"] or 0 for f in feats)
print(f"wrote {op}: {len(feats)} LIHTC properties, {tot:,} total units, {li:,} income-restricted units")
