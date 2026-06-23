"""
Report-style scatterplot (matches chart_dallas_income_permits.png):
Opportunity Insights upward-mobility score (x) vs. new dwelling units permitted
2015-2024 (y), for the City-of-Dallas tracts in data/permits_oi.json.

Same teal report palette, white frame, framed legend, no fit line.
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
rows = json.load(open(os.path.join(WEB, "data", "permits_oi.json")))
x = np.array([r["oi"] for r in rows], dtype=float)
y = np.array([r["units"] for r in rows], dtype=float)

TEAL, TEAL_EDGE, GRID = "#4A90A4", "#23545F", "#DDDDDD"

fig, ax = plt.subplots(figsize=(9.5, 6.3), dpi=150)
ax.set_axisbelow(True)
ax.grid(color=GRID, linewidth=0.8)

ax.scatter(x, y, s=42, facecolor=TEAL, edgecolor=TEAL_EDGE, linewidths=0.4,
           alpha=0.75, zorder=3)

pad = (x.max() - x.min()) * 0.04
ax.set_xlim(x.min() - pad, x.max() + pad)
ax.set_ylim(-60, y.max() * 1.05)
ax.xaxis.set_major_formatter(FuncFormatter(lambda v, p: f"${int(v/1000)}k"))
ax.yaxis.set_major_formatter(FuncFormatter(lambda v, p: f"{int(v):,}"))
ax.set_xlabel("Predicted adult income — children from 25th-percentile families",
              fontsize=13, labelpad=8)
ax.set_ylabel("New dwelling units permitted, 2015–2024", fontsize=14, labelpad=8)
ax.tick_params(labelsize=12, color="black")

for s in ax.spines.values():
    s.set_color("black")
    s.set_linewidth(1.3)

handles = [
    Line2D([0], [0], marker="o", linestyle="none", markerfacecolor=TEAL,
           markeredgecolor=TEAL_EDGE, markersize=9, alpha=0.9, label="Census tract"),
]
leg = ax.legend(handles=handles, loc="upper right", frameon=True, fontsize=12)
leg.get_frame().set_edgecolor("black")
leg.get_frame().set_linewidth(1.0)

plt.tight_layout()
repo_out = os.path.join(WEB, "chart_dallas_oi_permits.png")
plt.savefig(repo_out, dpi=150, bbox_inches="tight", facecolor="white")
print(f"saved {repo_out}  (n={len(rows)})")

gdpc = (r"C:\Users\shane\OneDrive\Documents\Domain Consulting\Projects"
        r"\GDPC - Dallas Housing Report\GDPC Claude Stuff\chart_dallas_oi_permits.png")
try:
    shutil.copyfile(repo_out, gdpc)
    print(f"copied to {gdpc}")
except OSError as e:
    print(f"(could not copy to GDPC folder: {e})")
