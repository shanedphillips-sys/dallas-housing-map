"""
Report-style scatterplot (matches chart_dallas_income_sf_zoning.png):
ACS median household income (x) vs. new dwelling units permitted 2015-2024 (y),
for the City-of-Dallas tracts in data/permits_income.json.

Same teal report palette, white frame, framed legend, no fit line.
Saved to the GDPC report-charts folder (and a repo copy).
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
rows = json.load(open(os.path.join(WEB, "data", "permits_income.json")))
x = np.array([r["mhi"] for r in rows], dtype=float)
y = np.array([r["units"] for r in rows], dtype=float)


def citywide_mhi():
    """Citywide median household income from the SAME ACS sample as the tract data:
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

TEAL, TEAL_EDGE, GRID = "#4A90A4", "#23545F", "#DDDDDD"

fig, ax = plt.subplots(figsize=(9.5, 6.3), dpi=150)
ax.set_axisbelow(True)
ax.grid(color=GRID, linewidth=0.8)

ax.scatter(x, y, s=42, facecolor=TEAL, edgecolor=TEAL_EDGE, linewidths=0.4,
           alpha=0.75, zorder=3)

ax.set_xlim(10000, 262000)
ax.set_ylim(-60, y.max() * 1.05)
ax.xaxis.set_major_formatter(FuncFormatter(lambda v, p: f"${int(v/1000)}k"))
ax.yaxis.set_major_formatter(FuncFormatter(lambda v, p: f"{int(v):,}"))
ax.set_xlabel("Median household income", fontsize=14, labelpad=8)
ax.set_ylabel("New dwelling units permitted, 2015–2024", fontsize=14, labelpad=8)
ax.tick_params(labelsize=12, color="black")

for s in ax.spines.values():
    s.set_color("black")
    s.set_linewidth(1.3)

# Citywide median household income reference line (round-dashed, dark gray) + label
ax.axvline(CITY_MHI, color="#404040", linewidth=3.0, zorder=2,
           linestyle=(0, (3, 5)), dash_capstyle="round")
ax.text(CITY_MHI + 4000, ax.get_ylim()[1] * 0.94,
        f"Citywide median household income:\n${CITY_MHI:,.0f}",
        color="black", fontsize=11, ha="left", va="top", linespacing=1.5, zorder=5)

handles = [
    Line2D([0], [0], marker="o", linestyle="none", markerfacecolor=TEAL,
           markeredgecolor=TEAL_EDGE, markersize=9, alpha=0.9, label="Census tract"),
]
leg = ax.legend(handles=handles, loc="upper right", frameon=True, fontsize=12)
leg.get_frame().set_edgecolor("black")
leg.get_frame().set_linewidth(1.0)

plt.tight_layout()
repo_out = os.path.join(WEB, "chart_dallas_income_permits.png")
plt.savefig(repo_out, dpi=150, bbox_inches="tight", facecolor="white")
print(f"saved {repo_out}  (n={len(rows)})")

gdpc = (r"C:\Users\shane\OneDrive\Documents\Domain Consulting\Projects"
        r"\GDPC - Dallas Housing Report\GDPC Claude Stuff\chart_dallas_income_permits.png")
try:
    shutil.copyfile(repo_out, gdpc)
    print(f"copied to {gdpc}")
except OSError as e:
    print(f"(could not copy to GDPC folder: {e})")
