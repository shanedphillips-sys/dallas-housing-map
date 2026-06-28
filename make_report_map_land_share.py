"""
Report map: City of Dallas parcels colored by LAND's SHARE OF TOTAL ASSESSED VALUE
(land_val / tot_val). High share (red) = land is most of the value, i.e. little is
built on it (vacant / underused / teardown); low share (green) = improvements
dominate (well-developed). Excluded: parcels with zero reported land value, and
publicly-owned / tax-exempt parcels (DCAD totexempt flag — the Trinity floodway,
parks, government, schools, churches), which aren't private developable land.

Built from make_report_map_land_value.py, so the framing is identical:
  - north-up / true proportions (EPSG:2276), equal aspect, same clipped city boundary
  - light-gray (#E8E8E8) basemap interior with white roads (OSM motorway/trunk) and
    white water (data/water_dallas.geojson) where parcels aren't colored
  - 14x16" canvas at 600 DPI; legend/frame scaled ~1.94x; left-aligned legend
  - green->yellow->red ramp: green = low land share (~0.05-0.2), yellow ~0.5, red ~1.0

Output: report_map_land_share.png (repo) + a copy in the GDPC report-charts folder.
"""
import os
import shutil

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio
import shapely
import osmnx as ox
import matplotlib
matplotlib.use("Agg")
matplotlib.rcParams["text.parse_math"] = False
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

WEB = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(WEB, "data")
GDPC = (r"C:\Users\shane\OneDrive\Documents\Domain Consulting\Projects"
        r"\GDPC - Dallas Housing Report\GDPC Claude Stuff")
DCAD_GPKG = os.path.join(GDPC, "PARCEL_CORE_MERGED.gpkg")  # DCAD parcels w/ tax-exempt flag

PROJ = "EPSG:2276"
DPI = 600
FIG_W, FIG_H = 14, 16
OUTSIDE   = "#DDD5CA"      # surround (north_up style)
CITY_FILL = "#E8E8E8"      # light-gray basemap for unmapped areas; matches the PD/zoning maps
BOUNDARY  = "#000000"
BOUNDARY_LW = 0.5
FRAME_GRAY = "#BBBBBB"

# Land-share bins (land_val / tot_val), green -> yellow -> red. Green = low share
# (improvements dominate / well-developed); yellow ~ the 0.5 midpoint; red -> 1.0
# (land is nearly all the value -> vacant / underused). Boundaries put yellow on ~0.5.
SHARE_BINS = [
    (0.20, "#1A9850", "< 0.20"),
    (0.30, "#66BD63", "0.20 – 0.30"),
    (0.40, "#A6D96A", "0.30 – 0.40"),
    (0.55, "#FEE08B", "0.40 – 0.55"),
    (0.70, "#FDAE61", "0.55 – 0.70"),
    (0.85, "#F46D43", "0.70 – 0.85"),
    (float("inf"), "#D73027", "0.85 – 1.00"),
]
MIN_AREA = 100


def bin_color(v):
    for upper, color, _ in SHARE_BINS:
        if v < upper:
            return color
    return SHARE_BINS[-1][1]


# ---- City boundary: clip the eastern exclave + corridor stub (as in north_up) ----
city = gpd.read_file(os.path.join(DATA, "city_boundary.geojson")).to_crs(PROJ)
city_geom = shapely.make_valid(city.geometry.union_all())
b = city_geom.bounds
xs = np.linspace(b[0] + 20.5 * 5280, b[0] + 23.0 * 5280, 200)
vext = [city_geom.intersection(shapely.LineString([(x, b[1] - 1e3), (x, b[3] + 1e3)])).length
        for x in xs]
neck_x = xs[int(np.argmin(vext))]
city_geom = shapely.make_valid(city_geom.intersection(shapely.box(b[0], b[1], neck_x, b[3])))
stub = shapely.box(b[0] + 19.6 * 5280, b[1] + 15.5 * 5280, b[2], b[1] + 17.5 * 5280)
city_geom = shapely.make_valid(city_geom.difference(stub))
if city_geom.geom_type == "MultiPolygon":
    city_geom = max(city_geom.geoms, key=lambda p: p.area)
city = gpd.GeoDataFrame(geometry=[city_geom], crs=PROJ)

# ---- Parcels colored by land's share of total value, kept inside the trimmed city ----
gdfs = [pyogrio.read_dataframe(os.path.join(DATA, f"parcels_{q}.geojson"),
                               columns=["account_num", "land_val", "tot_val", "area_feet"])
        for q in ["nw", "ne", "sw", "se"]]
parcels = gpd.GeoDataFrame(pd.concat(gdfs, ignore_index=True), geometry="geometry", crs=gdfs[0].crs)

# Exclude publicly-owned / tax-exempt parcels (DCAD totexempt == "X"): the Trinity
# floodway, parks, government, schools, churches, etc. land_use_cat misses many of
# these (e.g. the 963-ac City floodway parcel is coded "Commercial"), so key off the
# appraisal-district exemption flag, joined by account number.
ex = pyogrio.read_dataframe(DCAD_GPKG, columns=["ACCOUNT_NUM", "totexempt"], read_geometry=False)
exempt = set(ex.loc[ex["totexempt"].astype(str).str.upper() == "X", "ACCOUNT_NUM"].astype(str))
n0 = len(parcels)
parcels = parcels[~parcels["account_num"].astype(str).isin(exempt)]
print(f"excluded {n0 - len(parcels):,} tax-exempt parcels")

parcels["lv"] = pd.to_numeric(parcels["land_val"], errors="coerce")
parcels["tv"] = pd.to_numeric(parcels["tot_val"], errors="coerce")
parcels["area"] = pd.to_numeric(parcels["area_feet"], errors="coerce").fillna(0)
# exclude parcels with zero (or missing) reported land value; guard the denominator
parcels = parcels[(parcels["lv"] > 0) & (parcels["tv"] > 0) & (parcels["area"] >= MIN_AREA)].to_crs(PROJ)
parcels["share"] = (parcels["lv"] / parcels["tv"]).clip(upper=1.0)
parcels = parcels[parcels.geometry.centroid.within(city_geom)].copy()
parcels["geometry"] = parcels.geometry.simplify(15)   # ~sub-pixel at this scale; speeds rendering
parcels["color"] = parcels["share"].apply(bin_color)

# ---- Water bodies (drawn white) so lakes & the river don't read as a share value ----
water = gpd.read_file(os.path.join(DATA, "water_dallas.geojson")).to_crs(PROJ)
water["geometry"] = water.geometry.apply(shapely.make_valid)
water = gpd.clip(water, city)

# ---- Highways (OSM motorway/trunk) drawn white, like the PD/zoning maps' basemap ----
roads = ox.features_from_place("Dallas, Texas, USA",
    tags={"highway": ["motorway", "motorway_link", "trunk", "trunk_link"]})
roads = roads[roads.geometry.geom_type.isin(["LineString", "MultiLineString"])]
roads = gpd.GeoDataFrame(roads[["highway", "geometry"]], geometry="geometry",
                         crs="EPSG:4326").to_crs(PROJ)
hw_main  = gpd.clip(roads[roads["highway"].isin(["motorway", "trunk"])], city)
hw_links = gpd.clip(roads[roads["highway"].isin(["motorway_link", "trunk_link"])], city)

# ---- Extent (north_up: fixed 14x16 canvas, 0.6" surround pad) ----
minx, miny, maxx, maxy = city.total_bounds
pad_x = 0.6 * ((maxx - minx) / FIG_W)
pad_y = 0.6 * ((maxy - miny) / FIG_H)
xlim = (minx - pad_x, maxx + pad_x)
ylim = (miny - pad_y, maxy + pad_y)

fig, ax = plt.subplots(1, 1, figsize=(FIG_W, FIG_H))
fig.patch.set_facecolor("white")
ax.set_xlim(*xlim)
ax.set_ylim(*ylim)
ax.set_facecolor(OUTSIDE)
ax.set_aspect("equal")

city.plot(ax=ax, color=CITY_FILL, edgecolor="none", zorder=1)
for c in parcels["color"].unique():
    parcels[parcels["color"] == c].plot(ax=ax, color=c, edgecolor="none", zorder=2)
# Bodies of water — white; masks any parcel that covers a lake or the river
if len(water):
    water.plot(ax=ax, color="white", edgecolor="none", zorder=3)
# Highways — white, on top of water so bridge crossings stay continuous
hw_links.plot(ax=ax, color="white", linewidth=0.7, alpha=0.8, zorder=4)
hw_main.plot(ax=ax, color="white", linewidth=2.0, alpha=0.9, zorder=4)
city.boundary.plot(ax=ax, color=BOUNDARY, linewidth=BOUNDARY_LW, zorder=6)

# ---- Legend (scaled like north_up: ~16.7 pt entries on the 14" canvas) ----
handles = [mpatches.Patch(facecolor=color, edgecolor="none", label=lbl)
           for _, color, lbl in SHARE_BINS]
leg = ax.legend(handles=handles, loc="upper right", fontsize=16.7, title="Land share of total value",
                title_fontsize=17.5, frameon=True, fancybox=False, edgecolor="#BBBBBB",
                facecolor="white", framealpha=1.0, borderpad=0.8, labelspacing=0.6, borderaxespad=0.6)
leg.set_zorder(20)
leg._legend_box.align = "left"   # left-align the title with the entries (default centers it)

# ---- Rectangular frame (#BBBBBB, scaled to 1.07 pt like north_up) ----
ax.set_axis_off()
ax.add_patch(mpatches.FancyBboxPatch(
    (0, 0), 1, 1, transform=ax.transAxes, boxstyle="square,pad=0",
    facecolor="none", edgecolor=FRAME_GRAY, linewidth=1.07, zorder=10, clip_on=False))
plt.subplots_adjust(left=0, right=1, top=1, bottom=0)
out = os.path.join(WEB, "report_map_land_share.png")
plt.savefig(out, dpi=DPI, bbox_inches="tight", facecolor="white", pad_inches=0.02)
plt.close()
print(f"saved {out}  ({len(parcels):,} parcels)")
try:
    shutil.copyfile(out, os.path.join(GDPC, "report_map_land_share.png"))
    print("copied to GDPC folder")
except OSError as e:
    print(f"(copy failed: {e})")
