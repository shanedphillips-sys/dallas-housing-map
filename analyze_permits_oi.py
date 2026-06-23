"""
Join Opportunity Insights upward-mobility score to the per-tract permitted-units
counts (data/permits_income.json), for the OI vs. permits scatterplot.

OI metric: predicted household income at age 35 for children of 25th-percentile
parents (Opportunity Atlas, dollars), built on 2010 tracts -> mapped to the 2020
tracts via the same dominant-overlap crosswalk as the ACS / zoning layers.

Writes data/permits_oi.json {geoid, oi, units} and prints the correlation.
"""
import json
import os
import statistics as st

import pandas as pd

WEB = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(WEB)
DATA = os.path.join(WEB, "data")
OI = r"C:\Users\shane\OneDrive\Documents\Domain Consulting\Projects\GDPC - Dallas Housing Report\GDPC Claude Stuff\opportunity_insights_tract_kfr_rP_gP_p25.csv"
REL = os.path.join(PROJECT, "tab20_tract20_tract10_natl.txt")
PREF = {"48113", "48085", "48121", "48439", "48139", "48257", "48397"}

# OI score by 2010 tract (drop 0 / missing)
oi = pd.read_csv(OI, dtype={"tract": str})
oi["v"] = pd.to_numeric(oi["Household_Income_at_Age_35_rP_gP_p25"], errors="coerce")
oimap = {t: v for t, v in zip(oi["tract"], oi["v"]) if pd.notna(v) and v > 0}

# dominant 2010 parent for each 2020 tract (7 counties)
best = {}
with open(REL, encoding="utf-8-sig") as f:
    h = f.readline().rstrip("\n").split("|")
    i20, i10, ia = h.index("GEOID_TRACT_20"), h.index("GEOID_TRACT_10"), h.index("AREALAND_PART")
    for line in f:
        p = line.rstrip("\n").split("|")
        if p[i20][:5] not in PREF:
            continue
        try:
            a = float(p[ia])
        except ValueError:
            a = 0.0
        if p[i20] not in best or a > best[p[i20]][0]:
            best[p[i20]] = (a, p[i10])
parent = {g: v[1] for g, v in best.items()}


def oi_for(g20):
    if g20 in oimap:
        return oimap[g20], "direct"
    par = parent.get(g20)
    return (oimap.get(par), "xwalk") if par and par in oimap else (None, "none")


# join to per-tract permitted units
pj = json.load(open(os.path.join(DATA, "permits_income.json")))
rows, n_direct, n_xwalk = [], 0, 0
for r in pj:
    s, how = oi_for(r["geoid"])
    if s is None:
        continue
    n_direct += how == "direct"
    n_xwalk += how == "xwalk"
    rows.append({"geoid": r["geoid"], "oi": int(round(s)), "units": r["units"]})

json.dump(rows, open(os.path.join(DATA, "permits_oi.json"), "w"))


def pearson(xs, ys):
    mx, my = st.mean(xs), st.mean(ys)
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sx = sum((x - mx) ** 2 for x in xs) ** 0.5
    sy = sum((y - my) ** 2 for y in ys) ** 0.5
    return cov / (sx * sy) if sx and sy else float("nan")


u = [r["units"] for r in rows]
oi_x = [r["oi"] for r in rows]
print(f"n = {len(rows)} of {len(pj)} Dallas tracts  ({n_direct} direct + {n_xwalk} via 2010 parent)")
print(f"  OI income@35: median ${st.median(oi_x):,.0f}  range ${min(oi_x):,}-${max(oi_x):,}")
print(f"  corr(OI, units) = {pearson(oi_x, u):+.3f}")
print("Wrote data/permits_oi.json")
