"""
Report-style scatterplot (matches chart_cities_pct_change1.png):
ACS median household income (x) vs. single-family share of residentially zoned
land (y), for the 312 City-of-Dallas tracts in data/income_zoning.json.

White box frame, light gridlines, the teal/red report palette, framed legend.
Saved to the GDPC report-charts folder (and a repo copy).
"""
import json
import os
import shutil

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import FuncFormatter

WEB = os.path.dirname(os.path.abspath(__file__))
rows = json.load(open(os.path.join(WEB, "data", "income_zoning.json")))
x = np.array([r["mhi"] for r in rows], dtype=float)
y = np.array([r["sf_share"] * 100 for r in rows], dtype=float)
r = np.corrcoef(x, y)[0, 1]

TEAL, TEAL_EDGE, RED, GRID = "#4A90A4", "#23545F", "#D9534F", "#DDDDDD"

fig, ax = plt.subplots(figsize=(9.5, 6.3), dpi=150)
ax.set_axisbelow(True)
ax.grid(color=GRID, linewidth=0.8)

ax.scatter(x, y, s=42, facecolor=TEAL, edgecolor=TEAL_EDGE, linewidths=0.4,
           alpha=0.75, zorder=3)

ax.set_xlim(10000, 262000)
ax.set_ylim(-3, 103)
ax.xaxis.set_major_formatter(FuncFormatter(lambda v, p: f"${int(v/1000)}k"))
ax.yaxis.set_major_formatter(FuncFormatter(lambda v, p: f"{int(v)}%"))
ax.set_xlabel("Median household income", fontsize=14, labelpad=8)
ax.set_ylabel("Single-family share of residential land (%)", fontsize=14, labelpad=8)
ax.tick_params(labelsize=12, color="black")

for s in ax.spines.values():
    s.set_color("black")
    s.set_linewidth(1.3)

handles = [
    Line2D([0], [0], marker="o", linestyle="none", markerfacecolor=TEAL,
           markeredgecolor=TEAL_EDGE, markersize=9, alpha=0.9, label="Census tract"),
]
leg = ax.legend(handles=handles, loc="lower right", frameon=True, fontsize=12)
leg.get_frame().set_edgecolor("black")
leg.get_frame().set_linewidth(1.0)

plt.tight_layout()
repo_out = os.path.join(WEB, "chart_dallas_income_sf_zoning.png")
plt.savefig(repo_out, dpi=150, bbox_inches="tight", facecolor="white")
print(f"saved {repo_out}  (n={len(rows)}, r={r:+.3f})")

gdpc = (r"C:\Users\shane\OneDrive\Documents\Domain Consulting\Projects"
        r"\GDPC - Dallas Housing Report\GDPC Claude Stuff\chart_dallas_income_sf_zoning.png")
try:
    shutil.copyfile(repo_out, gdpc)
    print(f"copied to {gdpc}")
except OSError as e:
    print(f"(could not copy to GDPC folder: {e})")
