"""
Per-council-district scatterplots: multifamily units permitted (5+ unit buildings,
new construction 2015-2024) vs. the district's multifamily-zoned share.

Y (both charts): sum of units on new permits 2015-2024 in 5+ unit multifamily
buildings. Uses the project's residential permit classification — type 'mf' plus
commercial-coded residential ('mu' = a 'com' permit with >=2 units and >= $100k per
unit and not duplicating an 'mf' permit at the same address/date). The value-per-unit
test screens out hotels/motels; retail/office carry no dwelling units. All MF counts
(no market-rate/subsidized distinction).

X (two versions, each a share of the district's residential-zoned land):
  denominator (both) = R + D + MF + CA + MU + TH/CH base districts
  x1 "any MF"   = (MF + CA + MU + TH/CH) / denominator
  x2 "dense MF" = (MF-3 + MF-4 + MU + CA, but NOT MU-1) / denominator
Residential-zoned land excludes A/MH, PD, and all non-residential zones (as specified).

Writes data/district_mf_permits_zoning.csv and one combined scatterplot PNG
(both zoning definitions on one chart). Chart style follows chart_cities_income.py.
"""
import os

import geopandas as gpd
import matplotlib as mpl
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd
import shapely

WEB = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(WEB, "data")
# palette + conventions from chart_cities_income.py (GDPC house style)
BLUE, RED, TEXT, BORDER_LW = "#5b9aab", "#d95660", "black", 0.5


def zone_group(cat, zn):
    if cat == "Multifamily":
        return "MF"
    if cat == "Community Area":
        return "CA"
    if cat == "Mixed-Use":
        return "MU"
    if cat == "Townhouse / Cluster":
        return "THCH"
    if cat == "Single-Family":
        if str(zn).startswith("R-"):
            return "R"
        if zn == "D":
            return "D"
    return None   # A, MH, Commercial, Industrial, PD, CD, Other -> not residential-zoned


# ---- X: multifamily-zoned share of residential land, per district ------------
z = gpd.read_file(os.path.join(DATA, "zoning.geojson"))[["zone_norm", "category", "geometry"]].to_crs(2276)
z["geometry"] = shapely.make_valid(z.geometry.values)
z["grp"] = [zone_group(c, zn) for c, zn in zip(z.category, z.zone_norm)]
z = z[z.grp.notna()].copy()                                    # residential base districts only
z["in_numA"] = z.grp.isin(["MF", "CA", "MU", "THCH"])
z["in_numB"] = ((z.grp.isin(["MU", "CA"]) & (z.zone_norm != "MU-1"))   # MU-1 excluded from dense
                | z.zone_norm.isin(["MF-3", "MF-4"]))

council = gpd.read_file(os.path.join(DATA, "council.geojson"))[["district", "geometry"]].to_crs(2276)
council["geometry"] = shapely.make_valid(council.geometry.values)

ov = gpd.overlay(z, council, how="intersection")
ov["area"] = ov.geometry.area
rows = []
for d, g in ov.groupby("district"):
    denom = g.area.sum()
    rows.append({"district": d,
                 "x1_anyMF_pct": round(g.loc[g.in_numA, "area"].sum() / denom * 100, 1),
                 "x2_denseMF_pct": round(g.loc[g.in_numB, "area"].sum() / denom * 100, 1),
                 "resid_sqmi": round(denom / 27_878_400.0, 2)})
zdf = pd.DataFrame(rows)

# ---- Y: MF units permitted (5+ units, new, 2015-2024) per district -----------
perm = gpd.read_file(os.path.join(DATA, "permits.geojson")).rename(columns={"type": "ptype"})
new = perm[(perm.act == "new") & perm.year.between(2015, 2024)].copy()
new["units"] = pd.to_numeric(new.units, errors="coerce").fillna(0)
new["value"] = pd.to_numeric(new.value, errors="coerce").fillna(0)
vpu = np.where(new.units > 0, new.value / np.where(new.units > 0, new.units, 1), 0)
mfkeys = set(zip(new.loc[new.ptype == "mf", "addr"], new.loc[new.ptype == "mf", "date"]))
not_ov = np.array([ad not in mfkeys for ad in zip(new.addr, new.date)])
is_mu = (new.ptype == "com") & (new.units >= 2) & (vpu >= 100000) & not_ov
new["res"] = np.where(new.ptype.isin(["sf", "mf"]), new.ptype, np.where(is_mu, "mu", None))
mf5 = new[new.res.isin(["mf", "mu"]) & (new.units >= 5)].to_crs(2276)
mf5 = gpd.sjoin(mf5, council[["district", "geometry"]], predicate="within", how="left")
ydf = mf5.groupby("district").units.sum().round().astype(int).rename("mf_units_5plus").reset_index()

df = zdf.merge(ydf, on="district", how="left").fillna({"mf_units_5plus": 0})
df["mf_units_5plus"] = df["mf_units_5plus"].astype(int)
df["district"] = df["district"].astype(str)
df = df.sort_values("district", key=lambda s: s.astype(int)).reset_index(drop=True)
df.to_csv(os.path.join(DATA, "district_mf_permits_zoning.csv"), index=False)
print(df.to_string(index=False))


# ---- combined scatter: both zoning definitions on one chart ------------------
x1 = df["x1_anyMF_pct"].to_numpy(dtype=float)
x2 = df["x2_denseMF_pct"].to_numpy(dtype=float)
yv = df["mf_units_5plus"].to_numpy(dtype=float)

with mpl.rc_context({"font.family": "sans-serif", "font.sans-serif": ["Arial"],
                     "font.size": 11, "text.color": TEXT, "axes.labelcolor": TEXT,
                     "xtick.color": TEXT, "ytick.color": TEXT}):
    fig, ax = plt.subplots(figsize=(6.5, 4.5))
    # trend lines first so they sit underneath the points
    for xs, col in ((x1, BLUE), (x2, RED)):
        m, b = np.polyfit(xs, yv, 1)
        xr = np.array([xs.min(), xs.max()])
        ax.plot(xr, m * xr + b, "--", color=col, linewidth=1.4, zorder=2)
    ax.scatter(x1, yv, s=55, color=BLUE, edgecolor=TEXT, linewidth=BORDER_LW,
               zorder=3, label="Any multifamily zone")
    ax.scatter(x2, yv, s=55, color=RED, edgecolor=TEXT, linewidth=BORDER_LW,
               zorder=3, label="Dense multifamily only")
    r1 = np.corrcoef(x1, yv)[0, 1]
    r2 = np.corrcoef(x2, yv)[0, 1]
    ax.text(26.3, 6600, f"r = {r2:.2f}", color=RED, fontsize=9,
            ha="center", va="center", zorder=4)
    ax.text(28, 2700, f"r = {r1:.2f}", color=BLUE, fontsize=9,
            ha="center", va="center", zorder=4)
    ax.set_ylabel("Multifamily Units Permitted, 2015–2024", fontsize=11)
    ax.set_xlabel("Share of Residential Land That Allows Multifamily", fontsize=11)
    ax.xaxis.set_major_formatter(mticker.PercentFormatter(xmax=100, decimals=0))
    ax.yaxis.set_major_formatter(mticker.StrMethodFormatter("{x:,.0f}"))
    ax.set_xlim(left=-1)
    ax.legend(fontsize=9, loc="upper left", framealpha=0.9, handletextpad=0.4)
    ax.grid(alpha=0.3, zorder=0)
    ax.tick_params(axis="both", labelsize=11)
    plt.tight_layout()
    out = os.path.join(WEB, "chart_district_mf_permits_vs_zoning.png")
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print("wrote", os.path.basename(out))
