"""
make_station_far_maps.py

PNG maps of building floor-area ratio (FAR) inside half-mile rail-station areas,
City of Dallas. Visual style matches the GDPC zoning report figure
(generate_zoning_map_agriculture.py): warm matte background, off-white city
fill, bold navy city outline, framed border, bottom/​top-right swatch legend.

map_station_far_base.png
    FAR clipped to the half-mile circles of rail stations whose circle is
    >= 50% inside the City of Dallas. NE Lake Ray Hubbard lobe cropped off.
    Overlapping circles dissolve into one blob (internal arcs removed). Black
    station-area outline.

map_station_far_income.png
    Same base, but the station-area outline is coded by neighborhood income,
    using the share of each half-mile footprint that falls in higher-income
    tracts (>= 50% rule):
        black solid  -- below the citywide median
        red solid    -- >= citywide median income
        red dashed   -- >= 75th-percentile income
    "citywide median income" = ACS 2024 5-yr place-level Dallas median household
    income (B19013). "75th-percentile income" = 75th pctile of city-tract MHI
    (city tracts = centroid in the city boundary). FAR/income source same as the
    rest of the project.
"""
import json
import os
import time

import geopandas as gpd
import numpy as np
import pandas as pd
import requests
from shapely.geometry import box
from shapely.ops import unary_union

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.lines import Line2D

t0 = time.time()
WEB = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(WEB, "data")
KEY = os.environ.get("CENSUS_API_KEY", "86cf199069aa31e1593fc7012564f38af501b568")
COUNTIES = ["113", "085", "121", "439", "139", "257", "397"]
CRS_FT = 2276
HALF_MILE_FT = 2640.0
PLACE_FIPS = "19000"
CUT_LON = -96.638
AREA_RULE = 0.50

FAR_BINS = ["No Building", "< 0.25", "0.25 - 0.49", "0.5 - 0.99", "1.0 - 1.49",
            "1.5 - 2.0", "2.0 - 2.9", "3.0 - 4.9", "5.0 - 9.9", "10+"]
FAR_COLORS = {"No Building": "#B8B0A0", "< 0.25": "#22ecf0", "0.25 - 0.49": "#14b1fd",
              "0.5 - 0.99": "#2c7fdb", "1.0 - 1.49": "#6539b3", "1.5 - 2.0": "#a032b2",
              "2.0 - 2.9": "#d124a9", "3.0 - 4.9": "#fd4dab", "5.0 - 9.9": "#ff7911",
              "10+": "#ffdd00"}

# --- palette / style borrowed from generate_zoning_map_agriculture.py ---
MATTE = "#DDD5CA"          # axes background (outside city)
CITY_FILL = "#F7F6F3"      # city interior
CITY_EDGE = "#2C3E50"      # bold city outline + border + labels
LINE_BLACK = "#000000"     # ordinary station-area outline
LINE_RED = "#D62728"       # >= median income outline
STATION_DOT = "#1b2a38"
LW = 1.5                   # station-area outline thickness
FIG_W, FIG_H = 14, 16


def log(msg):
    print(f"[{time.time()-t0:5.1f}s] {msg}", flush=True)


# ---- 1. City boundary, cropped display copy, per-station half-mile circles --
city = gpd.read_file(os.path.join(DATA, "city_boundary.geojson")).to_crs(4326)
poly4326 = city.geometry.union_all()
b4 = poly4326.bounds
main4326 = poly4326.intersection(box(b4[0] - 0.02, b4[1] - 0.02, CUT_LON, b4[3] + 0.02))
if main4326.geom_type == "MultiPolygon":
    main4326 = max(main4326.geoms, key=lambda p: p.area)
city_disp = gpd.GeoSeries([main4326], crs=4326).to_crs(CRS_FT)
city_poly = gpd.GeoSeries([poly4326], crs=4326).to_crs(CRS_FT).iloc[0]

stops = gpd.read_file(os.path.join(DATA, "rail_stops.geojson")).to_crs(CRS_FT)
stops["circle"] = stops.geometry.buffer(HALF_MILE_FT)
stops["in_city_frac"] = stops["circle"].apply(
    lambda g: g.intersection(city_poly).area / g.area)
passing = stops[stops["in_city_frac"] >= 0.50].copy().reset_index(drop=True)
log(f"stations: {len(stops)} total, {len(passing)} with circle >=50% in City of Dallas")

circles = passing["circle"].tolist()
points = gpd.GeoSeries(passing.geometry.values, crs=CRS_FT)
all_union = unary_union(circles)
station_union = all_union.buffer(0)

# ---- 2. Income: tract MHI + thresholds + area-weighted tier ----------------
cache = os.path.join(DATA, "tract_mhi_2024.json")
if os.path.exists(cache):
    mhi = json.load(open(cache))
    log(f"tract MHI loaded from cache ({len(mhi)} tracts)")
else:
    mhi = {}
    for c in COUNTIES:
        url = (f"https://api.census.gov/data/2024/acs/acs5?get=B19013_001E"
               f"&for=tract:*&in=state:48&in=county:{c}&key={KEY}")
        for row in requests.get(url, timeout=120).json()[1:]:
            try:
                v = float(row[0])
            except (TypeError, ValueError):
                v = None
            mhi[row[1] + row[2] + row[3]] = v if (v is not None and v > 0) else None
    json.dump(mhi, open(cache, "w"))
    log(f"tract MHI pulled from ACS ({len(mhi)} tracts)")

purl = (f"https://api.census.gov/data/2024/acs/acs5?get=B19013_001E"
        f"&for=place:{PLACE_FIPS}&in=state:48&key={KEY}")
city_mhi_place = float(requests.get(purl, timeout=120).json()[1][0])

tr = gpd.read_file(os.path.join(DATA, "tracts.geojson"))[["geoid", "geometry"]].to_crs(CRS_FT)
tr["geometry"] = tr.geometry.buffer(0)
tr["mhi"] = tr["geoid"].map(lambda g: mhi.get(g))
tr["incity"] = tr.geometry.centroid.within(city_poly)
city_vals = tr.loc[tr["incity"] & tr["mhi"].notna(), "mhi"].astype(float)
p50 = float(np.median(city_vals))
p75 = float(np.percentile(city_vals, 75))
MED_THR = city_mhi_place          # "citywide median income" = place-level Dallas MHI
P75_THR = p75                     # "75th-percentile income" = city-tract 75th pctile
log(f"thresholds: citywide median ${MED_THR:,.0f} (tract P50 ${p50:,.0f}), 75th pctile ${P75_THR:,.0f}")

sidx = tr.sindex
tr_geom = tr.geometry.values
tr_mhi = tr["mhi"].values


def hi_income_share(circle_geom, thr):
    area, cov = circle_geom.area, 0.0
    for i in sidx.query(circle_geom, predicate="intersects"):
        m = tr_mhi[i]
        if m is None or (isinstance(m, float) and np.isnan(m)):
            continue
        if m >= thr:
            cov += circle_geom.intersection(tr_geom[i]).area
    return cov / area


passing["share_med"] = [hi_income_share(g, MED_THR) for g in circles]
passing["share_p75"] = [hi_income_share(g, P75_THR) for g in circles]
passing["tier"] = np.where(passing["share_p75"] >= AREA_RULE, "D",
                  np.where(passing["share_med"] >= AREA_RULE, "R", "B"))
n_med_tract = int((np.array([hi_income_share(g, p50) for g in circles]) >= AREA_RULE).sum())
log(f"tiers: below-median {int((passing['tier']=='B').sum())}, "
    f">=median {int((passing['tier']!='B').sum())} (tract-P50 would give {n_med_tract}), "
    f">=P75 {int((passing['tier']=='D').sum())}")

# ---- 3. FAR parcels: mask-read to station union, clip, dissolve ------------
mask4326 = gpd.GeoSeries([all_union], crs=CRS_FT).to_crs(4326).iloc[0]
parts = []
for q in ["nw", "ne", "sw", "se"]:
    g = gpd.read_file(os.path.join(DATA, f"parcels_{q}.geojson"),
                      mask=mask4326, columns=["far_cat"])
    if len(g):
        parts.append(g.to_crs(CRS_FT))
parc = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), crs=CRS_FT)
parc = parc[parc["far_cat"].notna()].copy()
parc["geometry"] = parc.geometry.buffer(0)
parc = parc[~parc.geometry.is_empty]
diss = parc.dissolve("far_cat")
diss["geometry"] = diss.geometry.intersection(station_union)
diss = diss[~diss.geometry.is_empty]
present = [b for b in FAR_BINS if b in diss.index]
log(f"FAR categories present: {len(present)}")

# ---- 4. Render -------------------------------------------------------------
bb = city_disp.total_bounds
pad_x = 0.2 * ((bb[2] - bb[0]) / FIG_W)
pad_y = 0.2 * ((bb[3] - bb[1]) / FIG_H)

TIER_STYLE = {"B": dict(color=LINE_BLACK, linestyle="-", zorder=4),
              "R": dict(color=LINE_RED, linestyle="-", zorder=5),
              "D": dict(color=LINE_RED, linestyle="--", zorder=6)}


def draw_outlines(ax, mode):
    if mode == "base":
        gpd.GeoSeries([all_union.boundary], crs=CRS_FT).plot(
            ax=ax, color=LINE_BLACK, linewidth=LW, zorder=4)
        return
    tiers = passing["tier"].values
    u = {}
    for t in ("B", "R", "D"):
        cs = [c for c, tt in zip(circles, tiers) if tt == t]
        u[t] = unary_union(cs) if cs else None
    for t in ("B", "R", "D"):
        if u[t] is None or u[t].is_empty:
            continue
        oth = [u[o] for o in ("B", "R", "D") if o != t and u[o] is not None]
        line = u[t].boundary
        if oth:
            line = line.difference(unary_union(oth))
        if not line.is_empty:
            gpd.GeoSeries([line], crs=CRS_FT).plot(ax=ax, linewidth=LW, **TIER_STYLE[t])


def render(mode, outfile, dpi=200):
    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H))
    fig.patch.set_facecolor("white")
    ax.set_xlim(bb[0] - pad_x, bb[2] + pad_x)
    ax.set_ylim(bb[1] - pad_y, bb[3] + pad_y)
    ax.set_facecolor(MATTE)
    ax.set_aspect("equal")

    city_disp.plot(ax=ax, color=CITY_FILL, edgecolor="none", zorder=1)
    for cat in present:
        diss.loc[[cat]].plot(ax=ax, color=FAR_COLORS[cat],
                             edgecolor=FAR_COLORS[cat], linewidth=0.15, zorder=2)
    draw_outlines(ax, mode)
    city_disp.boundary.plot(ax=ax, color=CITY_EDGE, linewidth=3.0, zorder=7)
    points.plot(ax=ax, color=STATION_DOT, markersize=11, zorder=8,
                marker="o", edgecolor="white", linewidth=0.4)

    handles = [mpatches.Patch(facecolor=FAR_COLORS[c], edgecolor="#888888",
                              linewidth=0.3, label=f"FAR {c}") for c in present]
    if mode == "base":
        handles.append(Line2D([0], [0], color=LINE_BLACK, lw=LW, label="Half-mile station area"))
    else:
        handles += [
            Line2D([0], [0], color=LINE_BLACK, lw=LW, label="Half-mile station area"),
            Line2D([0], [0], color=LINE_RED, lw=LW, label="≥ citywide median income"),
            Line2D([0], [0], color=LINE_RED, lw=LW, linestyle="--", label="≥ 75th percentile income"),
        ]
    handles += [
        Line2D([0], [0], marker="o", color="none", markerfacecolor=STATION_DOT,
               markeredgecolor="white", markersize=8, lw=0, label="Rail station"),
        Line2D([0], [0], color=CITY_EDGE, lw=2.4, label="City of Dallas boundary"),
    ]
    leg = ax.legend(handles=handles, loc="upper right", ncol=2, fontsize=10,
                    frameon=True, fancybox=False, edgecolor="#BBBBBB", facecolor="white",
                    framealpha=1.0, borderpad=1, labelspacing=0.7, columnspacing=1.4)
    leg.set_zorder(20)
    fig.canvas.draw()
    px = leg.get_window_extent()
    inv = ax.transData.inverted()
    (lx0, ly0) = inv.transform((px.x0, px.y0))
    (lx1, ly1) = inv.transform((px.x1, px.y1))
    legbox = box(min(lx0, lx1), min(ly0, ly1), max(lx0, lx1), max(ly0, ly1))
    hits = [n for n, c in zip(passing["stop_name"], circles) if c.intersects(legbox)]
    log(f"[{mode}] legend overlaps {len(hits)} station areas: {hits}")

    border = mpatches.FancyBboxPatch(
        (0, 0), 1, 1, transform=ax.transAxes, boxstyle="square,pad=0",
        facecolor="none", edgecolor=CITY_EDGE, linewidth=1.09, zorder=10, clip_on=False)
    ax.add_patch(border)

    ax.set_axis_off()
    plt.subplots_adjust(left=0, right=1, top=1, bottom=0)
    fig.savefig(os.path.join(WEB, outfile), dpi=dpi, bbox_inches="tight",
                facecolor="white", pad_inches=0.02)
    plt.close(fig)
    log(f"wrote {outfile}")


render("base", "map_station_far_base.png")
render("combined", "map_station_far_income.png", dpi=600)

# ---- 5. Transparency summary ----------------------------------------------
summary = {
    "rule": ">= 50% of half-mile footprint in tracts with MHI >= threshold",
    "median_threshold_citywide_place_mhi": round(MED_THR),
    "city_tract_median_mhi_for_reference": round(p50),
    "p75_threshold_city_tract_mhi": round(P75_THR),
    "stations_total": int(len(stops)),
    "stations_ge50pct_in_city": int(len(passing)),
    "tier_below_median": int((passing["tier"] == "B").sum()),
    "tier_ge_median": int((passing["tier"] == "R").sum()),
    "tier_ge_p75": int((passing["tier"] == "D").sum()),
    "stations_ge_median_solid_red": sorted(passing.loc[passing["tier"] == "R", "stop_name"].tolist()),
    "stations_ge_p75_dashed_red": sorted(passing.loc[passing["tier"] == "D", "stop_name"].tolist()),
}
json.dump(summary, open(os.path.join(DATA, "station_far_maps_summary.json"), "w"), indent=2)
log("wrote data/station_far_maps_summary.json")
log("DONE")
