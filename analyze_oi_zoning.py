"""
Re-run the Dallas single-family / multifamily zoning-share analysis, but with the
Opportunity Insights upward-mobility score on the x-axis instead of median income.

OI metric: predicted Household_Income_at_Age_35 for children born to parents at
the 25th income percentile (race- and gender-pooled), in dollars — the Opportunity
Atlas absolute-mobility measure. It is built on 2010 census tracts, so we map it
onto the 2020 tracts used for zoning via the same dominant-overlap crosswalk as
the ACS layers (direct 2020 GEOID else its dominant 2010 parent).

Reuses data/income_zoning.json (the SF/MF residential shares already computed per
2020 Dallas tract). Writes data/oi_zoning.json and prints the correlations.
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

# join to the zoning shares
z = json.load(open(os.path.join(DATA, "income_zoning.json")))
rows, n_direct, n_xwalk = [], 0, 0
for r in z:
    s, how = oi_for(r["geoid"])
    if s is None:
        continue
    n_direct += how == "direct"
    n_xwalk += how == "xwalk"
    rows.append({"geoid": r["geoid"], "oi": int(round(s)),
                 "sf_share": r["sf_share"], "mf_share": r["mf_share"]})

json.dump(rows, open(os.path.join(DATA, "oi_zoning.json"), "w"))

def pearson(xs, ys):
    n = len(xs)
    mx, my = st.mean(xs), st.mean(ys)
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sx = sum((x - mx) ** 2 for x in xs) ** 0.5
    sy = sum((y - my) ** 2 for y in ys) ** 0.5
    return cov / (sx * sy) if sx and sy else float("nan")

oi_x = [r["oi"] for r in rows]
print(f"n = {len(rows)} of {len(z)} Dallas tracts  ({n_direct} direct + {n_xwalk} via 2010 parent)")
print(f"  OI income@35 (p25 kids): median ${st.median(oi_x):,.0f}  range ${min(oi_x):,}-${max(oi_x):,}")
print(f"  corr(OI, SF share) = {pearson(oi_x, [r['sf_share'] for r in rows]):+.3f}")
print(f"  corr(OI, MF share) = {pearson(oi_x, [r['mf_share'] for r in rows]):+.3f}")
print("Wrote data/oi_zoning.json")
