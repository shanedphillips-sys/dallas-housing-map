"""
Report map, sized for a letter page with 1" margins (fits within 6.5" x 9"):
the City of Dallas boundary with a light-gray fill, plus the through-street
("Streets") network in the same blue as the online map. Styled after the GDPC
generate_parcel_map.py. Rendered at 600 DPI.

Output: report_map_streets.png (repo) + a copy in the GDPC report-charts folder.
"""
import os
import shutil

import geopandas as gpd
import numpy as np
import shapely
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.lines import Line2D

WEB = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(WEB, "data")
GDPC = (r"C:\Users\shane\OneDrive\Documents\Domain Consulting\Projects"
        r"\GDPC - Dallas Housing Report\GDPC Claude Stuff")

PROJ = "EPSG:2276"          # Texas N Central (US ft) -> true shape, equal aspect
MAX_W, MAX_H = 6.5, 9.0     # letter page minus 1" margins
DPI = 600
CITY_FILL   = "#E8E8E8"     # light gray within the city boundary
BOUNDARY    = "#000000"     # city outline (black)
STREET_BLUE = "#1D4F66"     # same blue as the online "Streets" layer
STREET_LW   = 0.3
BOUNDARY_LW = 0.5

city = gpd.read_file(os.path.join(DATA, "city_boundary.geojson")).to_crs(PROJ)
city_geom = shapely.make_valid(city.geometry.union_all())

# Drop the eastern Lake Ray Hubbard exclave (matching generate_parcel_map.py, whose
# parcel-union boundary never reaches it): clip off everything east of the narrow
# neck where the exclave's corridor attaches to the main city body. The neck is the
# minimum vertical extent of the polygon ~20.5-23 mi east of the western edge.
b = city_geom.bounds
xs = np.linspace(b[0] + 20.5 * 5280, b[0] + 23.0 * 5280, 200)
vext = [city_geom.intersection(shapely.LineString([(x, b[1] - 1e3), (x, b[3] + 1e3)])).length
        for x in xs]
neck_x = xs[int(np.argmin(vext))]
city_geom = shapely.make_valid(city_geom.intersection(shapely.box(b[0], b[1], neck_x, b[3])))
city = gpd.GeoDataFrame(geometry=[city_geom], crs=PROJ)

streets = gpd.read_file(os.path.join(DATA, "streets_dallas.geojson")).to_crs(PROJ)
streets = streets[streets["kind"] != "stub"]    # "Streets" = grid (excludes dead-ends)
streets = gpd.clip(streets, city_geom)          # trim to the (clipped) city boundary

# Figure sized to the city's true aspect ratio, fit within MAX_W x MAX_H.
minx, miny, maxx, maxy = city_geom.bounds
span = max(maxx - minx, maxy - miny)
pad = 0.02 * span
minx, miny, maxx, maxy = minx - pad, miny - pad, maxx + pad, maxy + pad
aspect = (maxy - miny) / (maxx - minx)
if aspect >= MAX_H / MAX_W:
    fig_h, fig_w = MAX_H, MAX_H / aspect
else:
    fig_w, fig_h = MAX_W, MAX_W * aspect

fig, ax = plt.subplots(figsize=(fig_w, fig_h), dpi=DPI)
fig.patch.set_facecolor("white")
ax.set_facecolor("white")
ax.set_aspect("equal")
ax.set_xlim(minx, maxx)
ax.set_ylim(miny, maxy)
ax.set_axis_off()

city.plot(ax=ax, color=CITY_FILL, edgecolor="none", zorder=1)
streets.plot(ax=ax, color=STREET_BLUE, linewidth=STREET_LW, zorder=2)
city.boundary.plot(ax=ax, color=BOUNDARY, linewidth=BOUNDARY_LW, zorder=3)

handles = [
    Line2D([0], [0], color=STREET_BLUE, linewidth=1.8, label="Streets"),
    Line2D([0], [0], color=BOUNDARY, linewidth=1.8, label="City of Dallas boundary"),
]
# Legend padding/spacing are in fontsize units, so the whole box scales with fontsize.
ax.legend(handles=handles, loc="upper right", fontsize=8.6, frameon=True,
          fancybox=False, edgecolor="#BBBBBB", facecolor="white", framealpha=1.0,
          borderpad=0.8, labelspacing=0.6, borderaxespad=0.6)

# Rectangular border around the map (matches generate_zoning_map_agriculture.py)
ax.add_patch(mpatches.FancyBboxPatch(
    (0, 0), 1, 1, transform=ax.transAxes, boxstyle="square,pad=0",
    facecolor="none", edgecolor="#BBBBBB", linewidth=0.55, zorder=10, clip_on=False))

# very thin inset = the white-space buffer outside the border (shrunk ~80%, 1% -> 0.2%)
plt.subplots_adjust(left=0.002, right=0.998, bottom=0.002, top=0.998)
out = os.path.join(WEB, "report_map_streets.png")
plt.savefig(out, dpi=DPI, facecolor="white")
plt.close()
print(f"saved {out}  ({fig_w:.2f} x {fig_h:.2f} in @ {DPI} dpi)")
try:
    shutil.copyfile(out, os.path.join(GDPC, "report_map_streets.png"))
    print("copied to GDPC folder")
except OSError as e:
    print(f"(copy failed: {e})")
