"""
make_station_strip.py

Single-page (6.5 x 9 in) line-strip "small multiples" of every in-city rail-
station area. Each DART line/branch is a vertical column; each station is an
enlarged half-mile circle with the FAR map inside, the income-tier border
(black = below citywide median, solid red = >= citywide median, dashed red =
>= 75th-pctile), the station name above, and any area OUTSIDE the City of Dallas
hatched. Same FAR colors / income border rules as map_station_far_income.png.

Each physical station appears once (entrance / across-the-street duplicates
merged). The Silver Line is stacked beneath the short Blue — Northeast column to
save a column of horizontal space.
"""
import json
import os
import re
import time
import textwrap

import geopandas as gpd
import numpy as np
import pandas as pd
import requests
from PIL import Image
from shapely import affinity
from shapely.ops import unary_union

import matplotlib
matplotlib.use("Agg")
import matplotlib as mpl
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.lines import Line2D

mpl.rcParams["hatch.linewidth"] = 0.35
t0 = time.time()
WEB = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(WEB, "data")
CRS_FT = 2276
HALF_MILE_FT = 2640.0
AREA_RULE = 0.50


def log(m):
    print(f"[{time.time()-t0:5.1f}s] {m}", flush=True)


FAR_BINS = ["No Building", "< 0.25", "0.25 - 0.49", "0.5 - 0.99", "1.0 - 1.49",
            "1.5 - 2.0", "2.0 - 2.9", "3.0 - 4.9", "5.0 - 9.9", "10+"]
FAR_COLORS = {"No Building": "#B8B0A0", "< 0.25": "#22ecf0", "0.25 - 0.49": "#14b1fd",
              "0.5 - 0.99": "#2c7fdb", "1.0 - 1.49": "#6539b3", "1.5 - 2.0": "#a032b2",
              "2.0 - 2.9": "#d124a9", "3.0 - 4.9": "#fd4dab", "5.0 - 9.9": "#ff7911",
              "10+": "#ffdd00"}
LINE_BLACK, LINE_RED = "#000000", "#D62728"
OUT_FACE, OUT_HATCH, OUT_EDGE = "#e8e6e1", "////", "#8a857c"

LC = {"silver": "#8a8d8f", "red": "#c8102e", "blue": "#0033a0", "green": "#00843d",
      "down": "#555555", "mline": "#6a3d9a", "scar": "#b15928"}

# Each column is a list of (header, line-color, [stations top->bottom]) sections.
# The Blue — Northeast column carries the Silver Line as a second section below it.
COLUMNS = [
    [("Red / Orange — North", LC["red"], ["SHERMAN POCKET TRACK", "LBJ / CENTRAL STATION",
        "FOREST LN STATION", "WALNUT HILL STATION", "PARK LANE STATION", "LOVERS LANE STATION",
        "SMU/MOCKINGBIRD STATION"])],
    [("Blue — Northeast", LC["blue"], ["LBJ / SKILLMAN STATION", "LAKE HIGHLANDS STATION",
        "WHITE ROCK STATION"]),
     ("Silver Line", LC["silver"], ["KNOLL TRAIL STATION", "CYPRESS WATERS STATION"])],
    [("Green / Orange — Northwest", LC["green"], ["ROYAL LANE STATION", "WALNUT HILL/DENTON STATION",
        "BACHMAN STATION", "BURBANK STATION", "INWOOD/LOVE FIELD STATION",
        "SOUTHWEST MEDICAL DISTRICT/PARKLAND", "MEDICAL/MARKET CTR STATION", "MARKET CENTER STATION",
        "VICTORY STATION"])],
    [("Downtown core", LC["down"], ["CITYPLACE/UPTOWN STATION", "PEARL/ARTS DISTRICT STATION",
        "ST PAUL STATION", "AKARD STATION", "WEST END STATION", "EBJ UNION STATION",
        "CONVENTION CENTER STATION"])],
    [("M-Line Streetcar", LC["mline"], ["MCKINNEY @ HALL - N - NS", "MCKINNEY @ ALLEN - N - NS",
        "MCKINNEY @ MAPLE-ROUTH - N - NS", "ST PAUL @ ROSS - S - NS", "FEDERAL @ OLIVE - E - NS"])],
    [("Red — South (Oak Cliff)", LC["red"], ["CEDARS STATION", "8TH & CORINTH STATION",
        "ZOO STATION", "MORRELL STATION", "TYLER VERNON STATION", "HAMPTON STATION",
        "WESTMORELAND STATION"])],
    [("Blue — South", LC["blue"], ["ILLINOIS TC/STATION", "KIEST STATION", "VA MEDICAL CENTER STATION",
        "LEDBETTER STATION", "CAMP WISDOM STATION", "UNT DALLAS STATION"])],
    [("Green — Southeast", LC["green"], ["DEEP ELLUM STATION", "BAYLOR STATION", "FAIR PARK STATION",
        "MLK STATION", "HATCHER STATION", "LAWNVIEW STATION", "LAKE JUNE STATION", "BUCKNER STATION"])],
    [("Dallas Streetcar", LC["scar"], ["GREENBRIAR STREETCAR STATION", "OAKENWALD STREETCAR STATION",
        "BECKLEY STREETCAR STATION", "6TH STREETCAR STATION", "BISHOP ARTS STATION"])],
]

HEADER_SHORT = {
    "Red / Orange — North": "Red / Orange\nNorth", "Blue — Northeast": "Blue\nNortheast",
    "Green / Orange — Northwest": "Green / Orange\nNorthwest", "Downtown core": "Downtown\ncore",
    "M-Line Streetcar": "M-Line\nStreetcar", "Red — South (Oak Cliff)": "Red — South\n(Oak Cliff)",
    "Blue — South": "Blue\nSouth", "Green — Southeast": "Green\nSoutheast",
    "Dallas Streetcar": "Dallas\nStreetcar",
}
FIX = {"Mckinney": "McKinney", "Ebj": "EBJ", "Lbj": "LBJ", "Mlk": "MLK", "Va": "VA",
       "Unt": "UNT", "Smu": "SMU", "Tc": "TC", "8Th": "8th", "6Th": "6th"}


def clean(n):
    s = re.sub(r"\s*-\s*[NSE]\s*-\s*NS$", "", n.upper())
    s = s.replace(" STREETCAR", "").replace("/STATION", "").replace(" STATION", "").title()
    for a, b in FIX.items():
        s = re.sub(rf"\b{a}\b", b, s)
    return s.strip()


# ---- data prep -------------------------------------------------------------
city = gpd.read_file(os.path.join(DATA, "city_boundary.geojson")).to_crs(CRS_FT)
cp = city.geometry.union_all()
stops = gpd.read_file(os.path.join(DATA, "rail_stops.geojson")).to_crs(CRS_FT)
stops["circle"] = stops.geometry.buffer(HALF_MILE_FT)
stops["frac"] = stops["circle"].apply(lambda g: g.intersection(cp).area / g.area)
passing = stops[stops["frac"] >= 0.50].copy()
circ = {r["stop_name"]: r["circle"] for _, r in passing.iterrows()}
names = [n for col in COLUMNS for (_, _, sts) in col for n in sts]
assert all(n in circ for n in names), [n for n in names if n not in circ]
log(f"{len(circ)} in-city stations -> {len(names)} unique after merges")

mhi = json.load(open(os.path.join(DATA, "tract_mhi_2024.json")))
KEY = os.environ.get("CENSUS_API_KEY", "86cf199069aa31e1593fc7012564f38af501b568")
MED_THR = float(requests.get(f"https://api.census.gov/data/2024/acs/acs5?get=B19013_001E"
                             f"&for=place:19000&in=state:48&key={KEY}", timeout=120).json()[1][0])
tr = gpd.read_file(os.path.join(DATA, "tracts.geojson"))[["geoid", "geometry"]].to_crs(CRS_FT)
tr["geometry"] = tr.geometry.buffer(0)
tr["mhi"] = tr["geoid"].map(mhi.get)
P75_THR = float(np.percentile(tr.loc[tr.geometry.centroid.within(cp) & tr["mhi"].notna(), "mhi"]
                              .astype(float), 75))
tsi, tgeom, tmhi = tr.sindex, tr.geometry.values, tr["mhi"].values


def tier(circle):
    a, sm, sp = circle.area, 0.0, 0.0
    for i in tsi.query(circle, predicate="intersects"):
        m = tmhi[i]
        if m is None or (isinstance(m, float) and np.isnan(m)):
            continue
        inter = circle.intersection(tgeom[i]).area
        if m >= MED_THR:
            sm += inter
        if m >= P75_THR:
            sp += inter
    if sp / a >= AREA_RULE:
        return "D"
    return "R" if sm / a >= AREA_RULE else "B"


union = unary_union(list(circ.values()))
mask4326 = gpd.GeoSeries([union], crs=CRS_FT).to_crs(4326).iloc[0]
parts = []
for q in ["nw", "ne", "sw", "se"]:
    g = gpd.read_file(os.path.join(DATA, f"parcels_{q}.geojson"), mask=mask4326, columns=["far_cat"])
    parts.append(g.to_crs(CRS_FT))
parc = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), crs=CRS_FT)
parc = parc[parc["far_cat"].notna()].copy()
parc["geometry"] = parc.geometry.buffer(0)
parc = parc[~parc.geometry.is_empty]
psi, pgeom, pcat = parc.sindex, parc.geometry.values, parc["far_cat"].values
log(f"{len(parc)} FAR parcels in footprint")

STA = {}
for n in names:
    c = circ[n]
    far = {}
    for i in psi.query(c, predicate="intersects"):
        g = pgeom[i].intersection(c)
        if not g.is_empty:
            far.setdefault(pcat[i], []).append(g)
    STA[n] = {"circle": c, "tier": tier(c),
              "far": {k: unary_union(v) for k, v in far.items()}, "out": c.difference(cp)}
log("per-station FAR + tiers + out-of-city computed")

# ---- render to an exact 6.5 x 9 in page ------------------------------------
PAGE_W, PAGE_H, MARGIN = 6.5, 9.0, 0.12
NCOL = len(COLUMNS)
COL_PITCH = (PAGE_W - 2 * MARGIN) / NCOL
R = 0.30
NAME_H, GAP_BELOW = 0.17, 0.05
ROW_H = NAME_H + 2 * R + GAP_BELOW
HEADER_H, HDR_TO_STA, BAR_W, BOT_TRIM = 0.16, 0.05, 0.27, 0.12
TOP_Y = PAGE_H - MARGIN - 0.03
SCALE = R / HALF_MILE_FT
TIER_STYLE = {"B": ("-", LINE_BLACK), "R": ("-", LINE_RED), "D": ("--", LINE_RED)}


def name_top_y(k):           # mpl-y of the name-top of grid row k (shared by all columns)
    return TOP_Y - (HEADER_H + HDR_TO_STA) - k * ROW_H


def circ_y(k):               # mpl-y of the circle center of grid row k
    return name_top_y(k) - NAME_H - R


def put(geom, cx, cy, gx, gy):
    g = affinity.translate(geom, -cx, -cy)
    g = affinity.scale(g, xfact=SCALE, yfact=SCALE, origin=(0, 0))
    return affinity.translate(g, gx, gy)


fig = plt.figure(figsize=(PAGE_W, PAGE_H))
fig.patch.set_facecolor("white")
ax = fig.add_axes([0, 0, 1, 1])
ax.set_xlim(0, PAGE_W)
ax.set_ylim(0, PAGE_H)
ax.set_aspect("equal")
ax.axis("off")

pos = {}
for j, col in enumerate(COLUMNS):
    gx = MARGIN + COL_PITCH * (j + 0.5)
    row = 0
    for sec, (header, lcolor, stations) in enumerate(col):
        first_row = 0 if sec == 0 else row + 1            # snap later sections onto the grid
        htop = TOP_Y if sec == 0 else name_top_y(first_row) + HDR_TO_STA + HEADER_H
        ax.text(gx, htop, HEADER_SHORT.get(header, header), ha="center", va="top",
                fontsize=6.0, fontweight="bold", color="#2C3E50", linespacing=1.0)
        ax.plot([gx - BAR_W, gx + BAR_W], [htop - HEADER_H] * 2, color=lcolor, lw=2.1,
                solid_capstyle="butt")
        for i, n in enumerate(stations):
            ccy = circ_y(first_row + i)
            st = STA[n]
            cx, cy = st["circle"].centroid.x, st["circle"].centroid.y
            for cat in FAR_BINS:
                if cat in st["far"]:
                    gpd.GeoSeries([put(st["far"][cat], cx, cy, gx, ccy)]).plot(
                        ax=ax, color=FAR_COLORS[cat], edgecolor=FAR_COLORS[cat],
                        linewidth=0.05, zorder=2)
            if not st["out"].is_empty:
                gpd.GeoSeries([put(st["out"], cx, cy, gx, ccy)]).plot(
                    ax=ax, facecolor=OUT_FACE, alpha=0.55, hatch=OUT_HATCH,
                    edgecolor=OUT_EDGE, linewidth=0.0, zorder=3)
            lsr, lcr = TIER_STYLE[st["tier"]]
            gpd.GeoSeries([put(st["circle"], cx, cy, gx, ccy).boundary]).plot(
                ax=ax, color=lcr, linestyle=lsr, linewidth=0.9, zorder=4)
            ax.text(gx, ccy + R + 0.012, "\n".join(textwrap.wrap(clean(n), 17)),
                    ha="center", va="bottom", fontsize=4.5, color="#222222", linespacing=0.95)
            pos[n] = (gx, ccy)
        row = first_row + len(stations)

handles = [mpatches.Patch(facecolor=FAR_COLORS[c], edgecolor="#888", linewidth=0.3,
                          label=f"FAR {c}") for c in FAR_BINS]
handles += [
    Line2D([0], [0], color=LINE_BLACK, lw=1.0, label="Below citywide median"),
    Line2D([0], [0], color=LINE_RED, lw=1.0, label="≥ citywide median"),
    Line2D([0], [0], color=LINE_RED, lw=1.0, linestyle="--", label="≥ 75th-pctile income"),
    mpatches.Patch(facecolor=OUT_FACE, alpha=0.6, hatch=OUT_HATCH, edgecolor=OUT_EDGE,
                   label="Outside Dallas city"),
]
vx, vy = pos["VICTORY STATION"]            # legend: right of Victory, centered on the station
leg = ax.legend(handles=handles, loc="center",
                bbox_to_anchor=((vx + R + 0.30 + PAGE_W - MARGIN) / 2, vy),
                bbox_transform=ax.transData, ncol=4, fontsize=5.0, frameon=True,
                edgecolor="#BBBBBB", facecolor="white", framealpha=1.0, borderpad=0.7,
                labelspacing=0.4, handlelength=1.5, columnspacing=1.2, handletextpad=0.5)

fig.canvas.draw()
lb = leg.get_window_extent()
leg_bottom = ax.transData.inverted().transform((lb.x0, lb.y0))[1]
content_bottom = min(vy - R, leg_bottom)

out = os.path.join(WEB, "map_station_strip.png")
fig.savefig(out, dpi=600, facecolor="white")
plt.close(fig)

crop_px = min(round((PAGE_H - (content_bottom - BOT_TRIM)) * 600), 5400)
im = Image.open(out)
im.crop((0, 0, im.width, crop_px)).save(out)
log(f"wrote map_station_strip.png -> {im.width}x{crop_px} px (6.5 in wide, bottom trimmed)")
