"""
Report map: City of Dallas parcels colored by TAXABLE LAND value per acre (same
data, bins and palette as the webmap's 2D land-value layer, LAND_VALUE_BINS).
Styled after generate_zoning_map_north_up.py / make_report_map_value.py:
  - north-up / true proportions (EPSG:2276), equal aspect
  - same clipped city boundary (black 0.5 pt) with the Lake Ray Hubbard exclave AND
    the severed corridor stub trimmed off
  - tan (#DDD5CA) surround, near-white (#F7F6F3) city interior
  - 14x16" canvas at 600 DPI with the legend/frame scaled up (~1.94x) so they read
    the same when the image is placed at ~6.5" wide on a letter page
  - thin medium-light-gray frame

Legend per spec: title "Land value per acre"; everything LEFT-aligned (title +
entries); NO italics (text.parse_math disabled so the "$" in labels render as plain
text, not math mode); each range "$X – $Y" carries a "$" on both numbers and an en
dash with a space on each side; low bucket is "< $100k".

Output: report_map_land_value.png (repo) + a copy in the GDPC report-charts folder.
"""
import os
import shutil

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio
import shapely
import matplotlib
matplotlib.use("Agg")
# Render "$" in legend labels as a literal dollar sign rather than entering mathtext
# (which would italicize the enclosed text). Requires matplotlib >= 3.4.
matplotlib.rcParams["text.parse_math"] = False
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

WEB = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(WEB, "data")
GDPC = (r"C:\Users\shane\OneDrive\Documents\Domain Consulting\Projects"
        r"\GDPC - Dallas Housing Report\GDPC Claude Stuff")

PROJ = "EPSG:2276"
DPI = 600
FIG_W, FIG_H = 14, 16
OUTSIDE   = "#DDD5CA"      # surround (north_up style)
CITY_FILL = "#F7F6F3"      # near-white city interior (= "< $100k" / no-parcel areas)
BOUNDARY  = "#000000"
BOUNDARY_LW = 0.5
FRAME_GRAY = "#BBBBBB"

# Land-value-per-acre bins — match the webmap 2D land-value layer (LAND_VALUE_BINS):
# a narrower range than total value (land/acre runs much lower). Labels carry a "$"
# on both numbers and an en dash with a space on each side.
VALUE_BINS = [
    (500_000,      "#FEE49E", "$100k – $500k"),
    (1_000_000,    "#FEBE8C", "$500k – $1M"),
    (2_000_000,    "#F0827E", "$1M – $2M"),
    (5_000_000,    "#B5435A", "$2M – $5M"),
    (float("inf"), "#7E55B0", "$5M+"),
]
LOW_VALUE = 100_000
MIN_AREA = 100


def bin_color(v):
    for upper, color, _ in VALUE_BINS:
        if v < upper:
            return color
    return VALUE_BINS[-1][1]


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

# ---- Parcels colored by taxable land value per acre, kept inside the trimmed city ----
gdfs = [pyogrio.read_dataframe(os.path.join(DATA, f"parcels_{q}.geojson"),
                               columns=["land_per_acre", "area_feet"])
        for q in ["nw", "ne", "sw", "se"]]
parcels = gpd.GeoDataFrame(pd.concat(gdfs, ignore_index=True), geometry="geometry", crs=gdfs[0].crs)
parcels["lpa"] = pd.to_numeric(parcels["land_per_acre"], errors="coerce").fillna(0)
parcels["area"] = pd.to_numeric(parcels["area_feet"], errors="coerce").fillna(0)
parcels = parcels[(parcels["lpa"] >= LOW_VALUE) & (parcels["area"] >= MIN_AREA)].to_crs(PROJ)
parcels = parcels[parcels.geometry.centroid.within(city_geom)].copy()
parcels["geometry"] = parcels.geometry.simplify(15)   # ~sub-pixel at this scale; speeds rendering
parcels["color"] = parcels["lpa"].apply(bin_color)

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
city.boundary.plot(ax=ax, color=BOUNDARY, linewidth=BOUNDARY_LW, zorder=6)

# ---- Legend (scaled like north_up: ~16.7 pt entries on the 14" canvas) ----
handles = [mpatches.Patch(facecolor=CITY_FILL, edgecolor="#888888", linewidth=0.7, label="< $100k")]
for _, color, lbl in VALUE_BINS:
    handles.append(mpatches.Patch(facecolor=color, edgecolor="none", label=lbl))
leg = ax.legend(handles=handles, loc="upper right", fontsize=16.7, title="Land value per acre",
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
out = os.path.join(WEB, "report_map_land_value.png")
plt.savefig(out, dpi=DPI, bbox_inches="tight", facecolor="white", pad_inches=0.02)
plt.close()
print(f"saved {out}  ({len(parcels):,} parcels)")
try:
    shutil.copyfile(out, os.path.join(GDPC, "report_map_land_value.png"))
    print("copied to GDPC folder")
except OSError as e:
    print(f"(copy failed: {e})")
