"""
Rank half-mile rail-station areas (City of Dallas, >=50%-in-city set) by the
amount of VACANT + SURFACE-PARKING land inside the station area -- i.e. the
near-transit redevelopment opportunity.

Vacant         : DCAD/CCAD/Denton parcels coded vacant (land_use_cat starts
                 "Vacant", or state-property-type description contains VACANT).
                 DCAD has no separate surface-parking code, so unimproved lots
                 used for parking already fall here.
Surface parking: OpenStreetMap amenity=parking polygons, excluding structured
                 (multi-storey/underground/garage/rooftop) and on-street
                 (street_side/lane). This catches IMPROVED/striped lots that
                 DCAD records as commercial.
Combined       : geometric UNION of the two per station (so a parking lot that
                 also reads as a vacant parcel is not double-counted). This is
                 the ranking metric.

Outputs: console table, data/station_vacant_parking.csv, JSON summary, and
chart_station_vacant_parking.png (stacked horizontal bars).
"""
import json
import os
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8")      # Windows console is cp1252 by default
except Exception:
    pass

import geopandas as gpd
import numpy as np
import pandas as pd
import osmnx as ox
from shapely.ops import unary_union

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

t0 = time.time()
WEB = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(WEB, "data")
CRS_FT = 2276
HALF_MILE_FT = 2640.0
SQFT_AC = 43560.0
PARK_EXCLUDE = {"multi-storey", "underground", "garage", "rooftop", "street_side", "lane"}
pd.set_option("display.max_rows", 200)
pd.set_option("display.width", 170)


def log(m):
    print(f"[{time.time()-t0:5.1f}s] {m}", flush=True)


# ---- 1. Passing station circles -------------------------------------------
city = gpd.read_file(os.path.join(DATA, "city_boundary.geojson")).to_crs(CRS_FT)
city_poly = city.geometry.union_all()
stops = gpd.read_file(os.path.join(DATA, "rail_stops.geojson")).to_crs(CRS_FT)
stops["circle"] = stops.geometry.buffer(HALF_MILE_FT)
stops["frac"] = stops["circle"].apply(lambda g: g.intersection(city_poly).area / g.area)
st = stops[stops["frac"] >= 0.50].copy().reset_index(drop=True)
circles = st["circle"].tolist()
union = unary_union(circles)
log(f"{len(st)} station areas (>=50% in city)")

# ---- 2. DCAD vacant parcels -----------------------------------------------
mask4326 = gpd.GeoSeries([union], crs=CRS_FT).to_crs(4326).iloc[0]
parts = []
for q in ["nw", "ne", "sw", "se"]:
    g = gpd.read_file(os.path.join(DATA, f"parcels_{q}.geojson"),
                      mask=mask4326, columns=["land_use_cat", "land_sptd_desc"])
    parts.append(g.to_crs(CRS_FT))
parc = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), crs=CRS_FT)
is_vac = (parc["land_use_cat"].fillna("").str.startswith("Vacant")
          | parc["land_sptd_desc"].fillna("").str.upper().str.contains("VACANT"))
vac = parc[is_vac].copy()
vac["geometry"] = vac.geometry.buffer(0)
vac = vac[~vac.geometry.is_empty]
log(f"vacant parcels in footprint: {len(vac)}")

# ---- 3. OSM surface parking ------------------------------------------------
osm = ox.features_from_polygon(mask4326, tags={"amenity": "parking"})
osm = osm[osm.geometry.geom_type.isin(["Polygon", "MultiPolygon"])].copy()
ptag = osm["parking"] if "parking" in osm.columns else pd.Series(np.nan, index=osm.index)
park = osm[~ptag.isin(PARK_EXCLUDE)].to_crs(CRS_FT).copy()
park["geometry"] = park.geometry.buffer(0)
park = park[~park.geometry.is_empty]
log(f"OSM surface-parking polygons: {len(park)} (of {len(osm)} parking polys)")

# ---- 4. Per-station areas (vacant, parking, deduped combined) --------------
vsi, psi = vac.sindex, park.sindex
vgeom, pgeom = vac.geometry.values, park.geometry.values
rows = []
for _, r in st.iterrows():
    c = r["circle"]
    vg = [vgeom[i].intersection(c) for i in vsi.query(c, predicate="intersects")]
    pg = [pgeom[i].intersection(c) for i in psi.query(c, predicate="intersects")]
    vg = [g for g in vg if not g.is_empty]
    pg = [g for g in pg if not g.is_empty]
    vac_ac = sum(g.area for g in vg) / SQFT_AC
    park_ac = sum(g.area for g in pg) / SQFT_AC
    comb_ac = (unary_union(vg + pg).area / SQFT_AC) if (vg or pg) else 0.0
    rows.append({
        "station": r["stop_name"],
        "vacant_ac": round(vac_ac, 1),
        "parking_ac": round(park_ac, 1),
        "combined_ac": round(comb_ac, 1),
        "pct_of_area": round(100 * comb_ac / (c.area / SQFT_AC), 1),
    })

df = pd.DataFrame(rows).sort_values("combined_ac", ascending=False).reset_index(drop=True)
df.insert(0, "rank", df.index + 1)
df["parking_net_ac"] = (df["combined_ac"] - df["vacant_ac"]).round(1)   # parking beyond vacant

log(f"½-mile station area = {circles[0].area / SQFT_AC:.0f} ac (π·2640²)")
print("\n========  Vacant + surface parking within ½-mile of station  ========")
print(df[["rank", "station", "vacant_ac", "parking_ac", "combined_ac", "pct_of_area"]].to_string(index=False))

df.to_csv(os.path.join(DATA, "station_vacant_parking.csv"), index=False)
json.dump({
    "metric": "vacant + surface parking acres within half-mile (geometric union, deduped)",
    "vacant_source": "DCAD/CCAD/Denton parcels coded vacant",
    "parking_source": "OSM amenity=parking, surface only",
    "half_mile_area_ac": round(circles[0].area / SQFT_AC, 1),
    "n_stations": len(df),
    "ranking": df.to_dict(orient="records"),
}, open(os.path.join(DATA, "station_vacant_parking.json"), "w"), indent=2)

# ---- 5. Stacked bar chart --------------------------------------------------
d = df.iloc[::-1]                      # highest at top
y = np.arange(len(d))
fig, ax = plt.subplots(figsize=(11, 15))
ax.barh(y, d["vacant_ac"], color="#8B9E4F", label="Vacant land")
ax.barh(y, d["parking_net_ac"], left=d["vacant_ac"], color="#4A6FA5",
        label="Surface parking (beyond vacant)")
ax.set_yticks(y)
ax.set_yticklabels(d["station"], fontsize=7.5)
ax.set_xlabel("Acres within ½-mile of station", fontsize=11)
ax.set_title("Dallas rail-station areas ranked by vacant + surface-parking land",
             fontsize=13, loc="left", pad=10)
for yi, tot in zip(y, d["combined_ac"]):
    ax.text(tot + 2, yi, f"{tot:.0f}", va="center", fontsize=7, color="#333333")
ax.legend(loc="lower right", fontsize=10, frameon=True, edgecolor="#BBBBBB")
ax.margins(y=0.005)
ax.grid(axis="x", color="#dddddd", linewidth=0.6)
ax.set_axisbelow(True)
for s in ("top", "right"):
    ax.spines[s].set_visible(False)
fig.tight_layout()
fig.savefig(os.path.join(WEB, "chart_station_vacant_parking.png"), dpi=200, facecolor="white")
plt.close(fig)
log("wrote chart_station_vacant_parking.png + CSV + JSON")
log("DONE")
