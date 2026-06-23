"""
100%-stacked bar: share of City-of-Dallas new dwelling units permitted each year
2015-2024 by structure size, grouped 1 / 2-4 / 5-19 / 20-49 / 50+ units.
Report style (matches chart_cities_pct_change1.png): white frame, light gridlines,
black bar edges, framed legend.
"""
import json
import os
import shutil

import geopandas as gpd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from matplotlib.ticker import FuncFormatter

WEB = os.path.dirname(os.path.abspath(__file__))
GDPC = (r"C:\Users\shane\OneDrive\Documents\Domain Consulting\Projects"
        r"\GDPC - Dallas Housing Report\GDPC Claude Stuff")
ORDER = ["1 (single-family)", "2–4 units", "5–19 units", "20–49 units", "50+ units"]
PAL = {"1 (single-family)": "#B0B0B0", "2–4 units": "#A6CDE3", "5–19 units": "#4A90A4",
       "20–49 units": "#E8A0A0", "50+ units": "#C44E52"}
DARKTEXT = {"1 (single-family)", "2–4 units", "20–49 units"}
GRID = "#DDDDDD"


def binof(u):
    if u <= 1: return ORDER[0]
    if u <= 4: return ORDER[1]
    if u <= 19: return ORDER[2]
    if u <= 49: return ORDER[3]
    return ORDER[4]


# ---- permitted units by structure-size group x year (City of Dallas) -------
perm = gpd.read_file("data/permits.geojson")
new = perm[(perm["act"] == "new") & (perm["year"].between(2015, 2024))].copy()
new["units"] = new["units"].fillna(0); new["value"] = new["value"].fillna(0); new["date"] = new["date"].fillna("")
vpu = np.where(new["units"] > 0, new["value"] / new["units"].where(new["units"] > 0, 1), 0)
mfk = set(zip(new.loc[new["type"] == "mf", "addr"], new.loc[new["type"] == "mf", "date"]))
nov = np.array([ad not in mfk for ad in zip(new["addr"], new["date"])])
ismu = (new["type"] == "com") & (new["units"] >= 2) & (vpu >= 100000) & nov
new["res"] = np.where(new["type"].isin(["sf", "mf"]), new["type"], np.where(ismu, "mu", None))
res = new[new["res"].notna()].copy().to_crs(3857)
tr = gpd.read_file("data/tracts.geojson")[["geoid", "geometry"]].to_crs(3857)
city = gpd.read_file("data/city_boundary.geojson").to_crs(3857).geometry.union_all()
tr["incity"] = tr.geometry.centroid.within(city)
ct = tr[tr["incity"]][["geoid", "geometry"]]
res = gpd.sjoin(res[["units", "year", "geometry"]], ct, predicate="within", how="inner")
res = res[res["units"].astype(int) >= 1].copy()
res["bin"] = res["units"].astype(int).map(binof)
years = list(range(2015, 2025))
piv = res.pivot_table(index="bin", columns="year", values="units", aggfunc="sum", fill_value=0).reindex(ORDER)[years]
share = piv / piv.sum(axis=0) * 100.0

# ---- chart -----------------------------------------------------------------
fig, ax = plt.subplots(figsize=(9.5, 6.3), dpi=150)
ax.set_axisbelow(True)
ax.yaxis.grid(color=GRID, linewidth=0.8)
bottom = np.zeros(len(years))
for cat in ORDER:
    vals = share.loc[cat].values
    ax.bar(years, vals, bottom=bottom, width=0.8, color=PAL[cat],
           edgecolor="black", linewidth=0.7, label=cat, zorder=3)
    for x, v, b in zip(years, vals, bottom):
        if v >= 7:
            ax.text(x, b + v / 2, f"{v:.0f}%", ha="center", va="center",
                    fontsize=9, color=("#1A1A1A" if cat in DARKTEXT else "white"))
    bottom += vals

ax.set_xlim(2014.4, 2024.6)
ax.set_ylim(0, 100)
ax.set_xticks(years)
ax.yaxis.set_major_formatter(FuncFormatter(lambda v, p: f"{int(v)}%"))
ax.set_ylabel("Share of new units permitted", fontsize=14, labelpad=8)
ax.tick_params(labelsize=12, color="black")
for s in ax.spines.values():
    s.set_color("black")
    s.set_linewidth(1.3)

handles = [Patch(facecolor=PAL[c], edgecolor="black", linewidth=0.7, label=c) for c in ORDER]
leg = ax.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, -0.07),
                ncol=5, frameon=True, fontsize=11, columnspacing=1.2, handlelength=1.4)
leg.get_frame().set_edgecolor("black")
leg.get_frame().set_linewidth(1.0)

plt.tight_layout()
out = os.path.join(WEB, "chart_dallas_permit_structure_share.png")
plt.savefig(out, dpi=150, bbox_inches="tight", facecolor="white")
print(f"saved {out}")
try:
    shutil.copyfile(out, os.path.join(GDPC, "chart_dallas_permit_structure_share.png"))
    print("copied to GDPC")
except OSError as e:
    print("(no GDPC copy:", e, ")")
