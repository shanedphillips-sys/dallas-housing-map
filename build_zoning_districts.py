"""
Category -> zoning-district catalog for the webmap's Base-zoning picker menu.

Reads data/zoning.geojson, groups base districts (zone_norm — parentheticals like
(A)/(SAH) merged) by category with city-clipped area, orders categories
residential->special and districts by area desc. Writes data/zoning_districts.json
(small; drives the collapsible zone checkboxes; sqmi = base-district area).
"""
import json
import os
import re

import geopandas as gpd
import shapely

WEB = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(WEB, "data")
CAT_ORDER = ["Single-Family", "Townhouse / Cluster", "Multifamily", "Mixed-Use",
             "Commercial", "Industrial", "Community Area", "Planned Development",
             "Conservation District", "Other"]
# explicit, rational within-category order for the residential families; every other
# category falls back to natural name order (prefix, then number) — never by area.
ZONE_ORDER = {
    "Single-Family": ["R-5", "R-7.5", "R-10", "R-13", "R-16", "R-1/2ac", "R-1ac", "D", "MH", "A"],
    "Multifamily": ["MF-1", "MF-2", "MF-3", "MF-4"],
    "Townhouse / Cluster": ["TH-1", "TH-2", "TH-3", "CH"],
    "Mixed-Use": ["MU-1", "MU-2", "MU-3", "UC-2", "WMU-3", "WMU-5", "WMU-8"],
}


def natural_key(zd):
    m = re.match(r"([A-Za-z]+)-?([\d.]*)", zd)
    if not m:
        return (zd, 0.0)
    return (m.group(1), float(m.group(2)) if m.group(2) else 0.0)


def zone_sort_key(cat, zd):
    order = ZONE_ORDER.get(cat)
    if order and zd in order:
        return (0, order.index(zd), "", 0.0)
    pre, num = natural_key(zd)
    return (1, 0, pre, num)

z = gpd.read_file(os.path.join(DATA, "zoning.geojson"))[["zone_norm", "category", "geometry"]].to_crs(2276)
z["geometry"] = shapely.make_valid(z.geometry.values)
city = gpd.read_file(os.path.join(DATA, "city_boundary.geojson")).to_crs(2276)
z = gpd.clip(z, shapely.make_valid(city.geometry.union_all()))
z["zone_norm"] = z["zone_norm"].astype(str).str.strip()   # base district (parentheticals stripped)
z["category"] = z["category"].fillna("Other")
z["acres"] = z.geometry.area / 43560.0
agg = z.groupby(["category", "zone_norm"], as_index=False).acres.sum()
agg["sqmi"] = agg.acres / 640.0

ordered = CAT_ORDER + [c for c in agg.category.unique() if c not in CAT_ORDER]
out = []
for cat in ordered:
    rows = sorted(agg[agg.category == cat].itertuples(),
                  key=lambda r: zone_sort_key(cat, r.zone_norm))
    if not rows:
        continue
    out.append({"category": cat,
                "zones": [{"zd": r.zone_norm, "sqmi": round(r.sqmi, 3)} for r in rows]})

with open(os.path.join(DATA, "zoning_districts.json"), "w") as f:
    json.dump({"categories": out}, f, indent=0)
print(f"wrote data/zoning_districts.json: {len(out)} categories, "
      f"{sum(len(c['zones']) for c in out)} districts")
for c in out:
    print(f"  {c['category']}: {len(c['zones'])}")
