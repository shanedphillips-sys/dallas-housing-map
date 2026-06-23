"""
Permit scatterplots with BOTH tenures on one plot:
  market-rate units per tract = blue (teal), every tract;
  LIHTC units per tract        = red, only tracts with >0 LIHTC permitted.
A tract with LIHTC therefore appears twice (a blue market-rate dot and a red
LIHTC dot). Two charts: median household income x, and OI adult-earnings x.

market / LIHTC per tract from data/permits_tenure.json (LIHTC = inventory units
of in-window-confirmed developments, capped at the tract total; market = total - LIHTC).
Saved to the repo and the GDPC report-charts folder.
"""
import json
import os
import shutil

import numpy as np
import requests
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import FuncFormatter

WEB = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(WEB, "data")
GDPC = (r"C:\Users\shane\OneDrive\Documents\Domain Consulting\Projects"
        r"\GDPC - Dallas Housing Report\GDPC Claude Stuff")
TEAL, TEAL_EDGE = "#4A90A4", "#23545F"
RED, RED_EDGE = "#D9534F", "#99312E"
GRID = "#DDDDDD"

ten = {r["geoid"]: r for r in json.load(open(os.path.join(DATA, "permits_tenure.json")))}
inc = json.load(open(os.path.join(DATA, "permits_income.json")))
oi = json.load(open(os.path.join(DATA, "permits_oi.json")))


def citywide_mhi():
    """Citywide median household income, SAME ACS sample as the tract data:
    ACS 2024 5-year, B19013_001E, Dallas city (state 48 / place 19000)."""
    key = os.environ.get("CENSUS_API_KEY", "86cf199069aa31e1593fc7012564f38af501b568")
    url = ("https://api.census.gov/data/2024/acs/acs5?get=B19013_001E"
           f"&for=place:19000&in=state:48&key={key}")
    try:
        return int(requests.get(url, timeout=30).json()[1][0])
    except Exception as e:
        print(f"(ACS fetch failed, using cached value: {e})")
        return 70518  # ACS 2024 5-year, Dallas city


CITY_MHI = citywide_mhi()


def draw_citywide_mhi(ax):
    """Dark-gray round-dashed vertical line at the citywide median income, labeled."""
    ax.axvline(CITY_MHI, color="#404040", linewidth=3.0, zorder=2,
               linestyle=(0, (3, 5)), dash_capstyle="round")
    ax.text(CITY_MHI + 4000, ax.get_ylim()[1] * 0.94,
            f"Citywide median household\nincome: ${CITY_MHI:,.0f}",
            color="black", fontsize=13, ha="left", va="top", linespacing=1.5, zorder=5)


def chart(rows, xkey, xlabel, xlim, fname, vline=False):
    mx, my, lx, ly = [], [], [], []
    for r in rows:
        lihtc = ten.get(r["geoid"], {}).get("lihtc_units", 0)
        mx.append(r[xkey]); my.append(r["units"] - lihtc)          # market-rate (all tracts)
        if lihtc > 0:
            lx.append(r[xkey]); ly.append(lihtc)                   # LIHTC (only where >0)

    fig, ax = plt.subplots(figsize=(9.5, 6.3), dpi=150)
    ax.set_axisbelow(True)
    ax.grid(color=GRID, linewidth=0.8)
    ax.scatter(mx, my, s=42, facecolor=TEAL, edgecolor=TEAL_EDGE, linewidths=0.4, alpha=0.75, zorder=3)
    ax.scatter(lx, ly, s=42, facecolor=RED, edgecolor=RED_EDGE, linewidths=0.4, alpha=0.85, zorder=4)

    if xlim:
        ax.set_xlim(*xlim)
    else:
        x = np.array(mx, float)
        pad = (x.max() - x.min()) * 0.04
        ax.set_xlim(x.min() - pad, x.max() + pad)
    ymax = max(max(my), 1)
    ax.set_ylim(-ymax * 0.03, ymax * 1.05)
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, p: f"${int(v/1000)}k"))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, p: f"{int(v):,}"))
    ax.set_xlabel(xlabel, fontsize=13, labelpad=8)
    ax.set_ylabel("New dwelling units permitted, 2015–2024", fontsize=14, labelpad=8)
    ax.tick_params(labelsize=12, color="black")
    for s in ax.spines.values():
        s.set_color("black")
        s.set_linewidth(1.3)

    if vline:
        draw_citywide_mhi(ax)

    h = [Line2D([0], [0], marker="o", linestyle="none", markerfacecolor=TEAL,
                markeredgecolor=TEAL_EDGE, markersize=9, alpha=0.9, label="Market-rate"),
         Line2D([0], [0], marker="o", linestyle="none", markerfacecolor=RED,
                markeredgecolor=RED_EDGE, markersize=9, alpha=0.9, label="LIHTC")]
    leg = ax.legend(handles=h, loc="upper right", frameon=True, fontsize=12)
    leg.get_frame().set_edgecolor("black")
    leg.get_frame().set_linewidth(1.0)

    plt.tight_layout()
    out = os.path.join(WEB, fname)
    plt.savefig(out, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close()
    try:
        shutil.copyfile(out, os.path.join(GDPC, fname))
    except OSError:
        pass
    print(f"saved {fname}  (market n={len(mx)}, LIHTC dots n={len(lx)})")


chart(inc, "mhi", "Median household income", (10000, 262000),
      "chart_dallas_income_permits_overlay.png", vline=True)
chart(oi, "oi", "Predicted adult income — children from 25th-percentile families", None,
      "chart_dallas_oi_permits_overlay.png")
