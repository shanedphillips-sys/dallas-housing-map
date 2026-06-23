"""
Report map: surface parking lots in CENTRAL Dallas, over the (label-free) CARTO
light-gray basemap used by the webmap. Cropped to a north-south corridor through
central Dallas (extent set by the two given lat/lon points); the frame is a bit
wider than it is tall. 600 DPI. Same legend font size + outer rectangular border
as make_report_map_streets.py.

Output: report_map_parking.png (repo) + a copy in the GDPC report-charts folder.
"""
import os
import shutil

import contextily as cx
import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

WEB = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(WEB, "data")
GDPC = (r"C:\Users\shane\OneDrive\Documents\Domain Consulting\Projects"
        r"\GDPC - Dallas Housing Report\GDPC Claude Stuff")

CRS = "EPSG:3857"           # Web Mercator (matches the XYZ basemap tiles)
DPI = 600
# CARTO Positron WITHOUT labels = the webmap's light-gray basemap, minus street/place names
BASEMAP = "https://a.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}@2x.png"
BASEMAP_ZOOM = 15
PARK_FILL, PARK_EDGE = "#8E6FB0", "#5E4B8B"   # same violet as the webmap parking layer

# Central-Dallas extent: north/south latitudes given; centered on the average
# longitude; width = 1.1 x height (a bit wider than tall).
N_LAT, N_LON = 32.816425707986596, -96.80102380088363
S_LAT, S_LON = 32.75195094326892, -96.80049797229279
WIDER = 1.1

pts = gpd.GeoSeries(gpd.points_from_xy([N_LON, S_LON], [N_LAT, S_LAT]), crs="EPSG:4326").to_crs(CRS)
cx_center = float(pts.x.mean())
miny, maxy = float(pts.y.min()), float(pts.y.max())
height = maxy - miny
width = height * WIDER
minx, maxx = cx_center - width / 2, cx_center + width / 2

parking = gpd.read_file(os.path.join(DATA, "parking_dallas.geojson")).to_crs(CRS)
parking = parking.cx[minx:maxx, miny:maxy]

fig_w = 6.5
fig_h = fig_w / WIDER
fig, ax = plt.subplots(figsize=(fig_w, fig_h), dpi=DPI)
fig.patch.set_facecolor("white")
ax.set_xlim(minx, maxx)
ax.set_ylim(miny, maxy)
ax.set_aspect("equal")

cx.add_basemap(ax, source=BASEMAP, zoom=BASEMAP_ZOOM, crs=CRS, attribution=False)
ax.set_xlim(minx, maxx)   # re-assert the exact corridor after tiles load
ax.set_ylim(miny, maxy)
parking.plot(ax=ax, facecolor=PARK_FILL, edgecolor=PARK_EDGE, linewidth=0.25, alpha=0.8, zorder=2)
ax.set_axis_off()

handles = [mpatches.Patch(facecolor=PARK_FILL, edgecolor=PARK_EDGE, linewidth=0.6,
                          label="Surface parking lot")]
ax.legend(handles=handles, loc="upper right", fontsize=8.6, frameon=True, fancybox=False,
          edgecolor="#BBBBBB", facecolor="white", framealpha=1.0,
          borderpad=0.8, labelspacing=0.6, borderaxespad=0.6)

# Rectangular border (same as make_report_map_streets.py)
ax.add_patch(mpatches.FancyBboxPatch(
    (0, 0), 1, 1, transform=ax.transAxes, boxstyle="square,pad=0",
    facecolor="none", edgecolor="#BBBBBB", linewidth=0.55, zorder=10, clip_on=False))
plt.subplots_adjust(left=0.002, right=0.998, bottom=0.002, top=0.998)

out = os.path.join(WEB, "report_map_parking.png")
plt.savefig(out, dpi=DPI, facecolor="white")
plt.close()
print(f"saved {out}  ({fig_w:.2f} x {fig_h:.2f} in @ {DPI} dpi, {len(parking)} lots)")
try:
    shutil.copyfile(out, os.path.join(GDPC, "report_map_parking.png"))
    print("copied to GDPC folder")
except OSError as e:
    print(f"(copy failed: {e})")
