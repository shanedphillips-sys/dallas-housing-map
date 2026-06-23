"""
Re-chart the station vacant+surface-parking ranking as SHARE of the half-mile
station area (%), grouped into three Dallas regions, each ranked internally most
-> least. Reads data/station_vacant_parking.csv (produced by
analyze_station_vacant_parking.py) -- no need to re-run the heavy analysis.

Region assignment is a hand classification (edit REGION below). The South/East
boundary is the main judgment call: Fair Park / MLK / Hatcher / Lawnview / Lake
June / Buckner sit EAST of downtown but are placed in "South Dallas" under the
common "Southern Dallas" equity framing. Borderline: White Rock & Inwood/Love
Field (North vs Central), Cedars (Central vs South).
"""
import os

import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

WEB = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(WEB, "data")

GROUP_ORDER = ["South Dallas", "Central and East Dallas", "North Dallas"]
REGION = {
    # ---- South Dallas (Oak Cliff SW + South Dallas/Fair Park + Pleasant Grove) ----
    "LAWNVIEW STATION": "South Dallas", "UNT DALLAS STATION": "South Dallas",
    "8TH & CORINTH STATION": "South Dallas", "GREENBRIAR STREETCAR STATION": "South Dallas",
    "CAMP WISDOM STATION": "South Dallas", "LEDBETTER STATION": "South Dallas",
    "OAKENWALD STREETCAR STATION": "South Dallas", "FAIR PARK STATION": "South Dallas",
    "MLK STATION": "South Dallas", "HATCHER STATION": "South Dallas",
    "MORRELL STATION": "South Dallas", "ZOO STATION": "South Dallas",
    "BISHOP ARTS STATION": "South Dallas", "BECKLEY STREETCAR STATION": "South Dallas",
    "LAKE JUNE STATION": "South Dallas", "BUCKNER STATION": "South Dallas",
    "6TH STREETCAR STATION": "South Dallas", "ILLINOIS TC/STATION": "South Dallas",
    "KIEST STATION": "South Dallas", "TYLER VERNON STATION": "South Dallas",
    "WESTMORELAND STATION": "South Dallas", "HAMPTON STATION": "South Dallas",
    "VA MEDICAL CENTER STATION": "South Dallas",
    # ---- Central and East Dallas (downtown + Uptown + medical/market + Deep Ellum) ----
    "CEDARS STATION": "Central and East Dallas", "EBJ UNION STATION": "Central and East Dallas",
    "CONVENTION CENTER STATION": "Central and East Dallas", "UNION STREETCAR STATION": "Central and East Dallas",
    "WEST END STATION": "Central and East Dallas", "AKARD STATION": "Central and East Dallas",
    "MARKET CENTER STATION": "Central and East Dallas", "ST PAUL STATION": "Central and East Dallas",
    "ST PAUL @ ROSS - S - NS": "Central and East Dallas", "DEEP ELLUM STATION": "Central and East Dallas",
    "FEDERAL @ OLIVE - E - NS": "Central and East Dallas", "MEDICAL/MARKET CTR STATION": "Central and East Dallas",
    "PEARL/ARTS DISTRICT STATION": "Central and East Dallas", "BAYLOR STATION": "Central and East Dallas",
    "CITYPLACE/UPTOWN WEST": "Central and East Dallas", "CITYPLACE/UPTOWN STATION": "Central and East Dallas",
    "COLE @ BOWEN - S - NS": "Central and East Dallas", "MCKINNEY @ ALLEN - N - NS": "Central and East Dallas",
    "MCKINNEY @ HALL - N - NS": "Central and East Dallas", "SOUTHWEST MEDICAL DISTRICT/PARKLAND": "Central and East Dallas",
    "VICTORY STATION": "Central and East Dallas", "MCKINNEY @ MAPLE-ROUTH - N - NS": "Central and East Dallas",
    "MCKINNEY @ PEARL - S - NS": "Central and East Dallas",
    # ---- North Dallas (Mockingbird & north + NW) ----
    "KNOLL TRAIL STATION": "North Dallas", "CYPRESS WATERS STATION": "North Dallas",
    "SHERMAN POCKET TRACK": "North Dallas", "LBJ / CENTRAL STATION": "North Dallas",
    "FOREST LN STATION": "North Dallas", "LBJ / SKILLMAN STATION": "North Dallas",
    "ROYAL LANE STATION": "North Dallas", "WALNUT HILL STATION": "North Dallas",
    "WALNUT HILL/DENTON STATION": "North Dallas", "LAKE HIGHLANDS STATION": "North Dallas",
    "PARK LANE STATION": "North Dallas", "WHITE ROCK STATION": "North Dallas",
    "BACHMAN STATION": "North Dallas", "LOVERS LANE STATION": "North Dallas",
    "BURBANK STATION": "North Dallas", "SMU/MOCKINGBIRD STATION": "North Dallas",
    "INWOOD/LOVE FIELD STATION": "North Dallas",
}
GROUP_COLOR = {"South Dallas": "#fbf3e6", "Central and East Dallas": "#eef3f7",
               "North Dallas": "#f0f4ec"}
VAC_C, PARK_C = "#8B9E4F", "#4A6FA5"

df = pd.read_csv(os.path.join(DATA, "station_vacant_parking.csv"))
df["region"] = df["station"].map(REGION)
missing = df[df["region"].isna()]["station"].tolist()
assert not missing, f"unassigned stations: {missing}"
# split combined share into vacant vs parking-beyond-vacant (sums to pct_of_area)
df["vac_pct"] = df["pct_of_area"] * df["vacant_ac"] / df["combined_ac"]
df["park_pct"] = df["pct_of_area"] - df["vac_pct"]

# ---- layout: groups top->bottom, each sorted desc; headers in the gaps -------
GAP = 2.0
positions, headers, band = [], [], []
y = 0.0
for gname in GROUP_ORDER:
    g = df[df["region"] == gname].sort_values("pct_of_area", ascending=False)
    headers.append((y, gname))
    y += 1.2
    top = y
    for _, r in g.iterrows():
        positions.append((y, r))
        y += 1.0
    band.append((gname, top - 0.6, y - 0.4))
    y += GAP
ymax = y

fig, ax = plt.subplots(figsize=(11.5, 16))
for gname, lo, hi in band:                                   # group background bands
    ax.axhspan(ymax - hi, ymax - lo, color=GROUP_COLOR[gname], zorder=0)
for yy, r in positions:
    ay = ymax - yy
    ax.barh(ay, r["vac_pct"], color=VAC_C, zorder=3)
    ax.barh(ay, r["park_pct"], left=r["vac_pct"], color=PARK_C, zorder=3)
    ax.text(r["pct_of_area"] + 0.4, ay, f"{r['pct_of_area']:.0f}%", va="center",
            fontsize=6.8, color="#333333")
for yy, gname in headers:
    ax.text(-0.5, ymax - yy + 0.5, gname, fontsize=12, fontweight="bold",
            color="#2C3E50", va="center", ha="left")

ax.set_yticks([ymax - yy for yy, _ in positions])
ax.set_yticklabels([r["station"] for _, r in positions], fontsize=7.3)
ax.set_ylim(-0.5, ymax + 1)
ax.set_xlim(0, max(df["pct_of_area"]) * 1.08)
ax.set_xlabel("Vacant + surface parking as share of ½-mile station area (%)", fontsize=11)
ax.set_title("Dallas rail-station areas by underused land, grouped by region\n"
             "(ranked most → least within each region)", fontsize=13, loc="left", pad=12)
ax.legend(handles=[Patch(facecolor=VAC_C, label="Vacant land"),
                   Patch(facecolor=PARK_C, label="Surface parking (beyond vacant)")],
          loc="lower right", fontsize=10, frameon=True, edgecolor="#BBBBBB")
ax.grid(axis="x", color="#dddddd", linewidth=0.6, zorder=1)
ax.set_axisbelow(True)
for s in ("top", "right", "left"):
    ax.spines[s].set_visible(False)
ax.tick_params(axis="y", length=0)
fig.tight_layout()
fig.savefig(os.path.join(WEB, "chart_station_vacant_parking_grouped.png"), dpi=200, facecolor="white")
plt.close(fig)

for gname in GROUP_ORDER:
    g = df[df["region"] == gname].sort_values("pct_of_area", ascending=False)
    print(f"\n{gname}  (n={len(g)}, median {g['pct_of_area'].median():.0f}% of area)")
    for _, r in g.iterrows():
        print(f"   {r['pct_of_area']:5.1f}%  {r['station']}")
print("\nwrote chart_station_vacant_parking_grouped.png")
