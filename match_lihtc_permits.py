"""
Flag which City-of-Dallas dwelling-unit permits (2015-2024, new sf/mf/mu) belong
to a LIHTC (subsidized) development vs. market-rate, by matching permit points to
the TDHCA Housing Tax Credit Property Inventory (as of May 29 2026).

Match = a permit point within 250 m of a Dallas LIHTC property (award Year >= 2012)
whose award year is within +/-5 of the permit year (guards against matching to an
old unrelated LIHTC complex nearby). Matched permits are "in a LIHTC development";
the rest are presumed market-rate.

Two subsidized measures are reported:
  - development units: full permit units of matched developments (mixed-income
    deals counted whole).
  - income-restricted units: the LIHTC-restricted share, prorated from the
    inventory's LIHTC Units / Total Units for matched properties.

Writes data/permits_lihtc.json {geoid, units, market_units, sub_units, sub_li_units}.
"""
import json
import os

import geopandas as gpd
import numpy as np
import pandas as pd

WEB = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(WEB, "data")
HTC = r"C:\Users\shane\OneDrive\Documents\Domain Consulting\Projects\GDPC - Dallas Housing Report\GDPC Claude Stuff\HTC Property Inventory as of May 29 2026.xlsx"
M = 32614   # UTM 14N (meters) for distance matching

# ---- 1. Dallas LIHTC properties (recent awards, valid coords) --------------
htc = pd.read_excel(HTC, sheet_name="PropInventory")
htc["lat"] = pd.to_numeric(htc["Latitude11"], errors="coerce")
htc["lon"] = pd.to_numeric(htc["Longitude11"], errors="coerce")
htc["yr"] = pd.to_numeric(htc["Year"], errors="coerce")
htc["u_tot"] = pd.to_numeric(htc["Total Units"], errors="coerce")
htc["u_li"] = pd.to_numeric(htc["LIHTC Units"], errors="coerce")
h = htc[htc.lat.between(32.4, 33.2) & htc.lon.between(-97.2, -96.3)
        & htc.yr.between(2012, 2025)].copy()
gh = gpd.GeoDataFrame(h, geometry=gpd.points_from_xy(h.lon, h.lat), crs=4326)

city = gpd.read_file(os.path.join(DATA, "city_boundary.geojson")).to_crs(4326).geometry.union_all()
gh = gh[gh.within(city)].copy()
print(f"Dallas LIHTC properties (award 2012-2025, in city): {len(gh)}")
print("  ConType:", gh["ConType"].value_counts(dropna=False).to_dict())
# new construction generates 'new' permits; acq/rehab/recon do not -> drop them
# (NaN ConType kept: older records simply lack the field)
gh = gh[~gh["ConType"].astype(str).str.contains("Acquisition|Rehab|Reconstruction", case=False, na=False)].copy()
print(f"  kept (new-construction + unclassified): {len(gh)}  "
      f"({int(gh.u_tot.sum()):,} total units, {int(gh.u_li.sum()):,} LIHTC units)")

# ---- 2. City-of-Dallas residential permits 2015-2024 (sf/mf/mu) -------------
perm = gpd.read_file(os.path.join(DATA, "permits.geojson"))
new = perm[(perm["act"] == "new") & (perm["year"].between(2015, 2024))].copy()
new["units"] = new["units"].fillna(0); new["value"] = new["value"].fillna(0); new["date"] = new["date"].fillna("")
vpu = np.where(new["units"] > 0, new["value"] / new["units"].where(new["units"] > 0, 1), 0)
mfkeys = set(zip(new.loc[new["type"] == "mf", "addr"], new.loc[new["type"] == "mf", "date"]))
not_ov = np.array([ad not in mfkeys for ad in zip(new["addr"], new["date"])])
is_mu = (new["type"] == "com") & (new["units"] >= 2) & (vpu >= 100000) & not_ov
new["res"] = np.where(new["type"].isin(["sf", "mf"]), new["type"], np.where(is_mu, "mu", None))
res = new[new.res.notna()].copy().to_crs(3857)

tr = gpd.read_file(os.path.join(DATA, "tracts.geojson"))[["geoid", "geometry"]].to_crs(3857)
city3857 = gpd.read_file(os.path.join(DATA, "city_boundary.geojson")).to_crs(3857).geometry.union_all()
tr["incity"] = tr.geometry.centroid.within(city3857)
ct = tr[tr.incity][["geoid", "geometry"]]
res = gpd.sjoin(res[["units", "res", "year", "addr", "geometry"]], ct, predicate="within", how="inner").drop(columns="index_right")
print(f"city residential permits 2015-2024: {len(res):,}  ({int(res.units.sum()):,} units)")

# ---- 3. Proximity + year match ---------------------------------------------
resM = res.to_crs(M)
hM = gh[["TDHCA#", "Development Name", "yr", "u_tot", "u_li", "ConType", "geometry"]].to_crs(M)
near = gpd.sjoin_nearest(resM, hM, max_distance=250, distance_col="dist", how="left")
near = near[~near.index.duplicated(keep="first")].copy()      # drop tie duplicates
gap = near["year"] - near["yr"]                               # permit year minus award year
near["match"] = near.yr.notna() & (gap >= -1) & (gap <= 3)    # construction follows allocation
m = near[near.match]
print(f"\nmatched permits: {len(m):,}  ({int(m.units.sum()):,} dev units)  "
      f"-> {m['TDHCA#'].nunique()} distinct LIHTC developments")
print("  year gap (permit-award) counts:", (m.year - m.yr).astype(int).value_counts().sort_index().to_dict())
print("  match distance (m): median {:.0f}  p90 {:.0f}".format(m.dist.median(), m.dist.quantile(.9)))
print("  matched ConType:", m["ConType"].value_counts(dropna=False).to_dict())

print("\nmatched LIHTC developments (permit units summed vs inventory):")
dev = m.groupby(["TDHCA#", "Development Name"]).agg(
    permits=("units", "size"), permit_u=("units", "sum"),
    yr=("yr", "first"), inv_tot=("u_tot", "first"), inv_li=("u_li", "first")).sort_values("permit_u", ascending=False)
for (tid, name), r in dev.iterrows():
    print(f"  {int(r.permit_u):4d}u permitted ({int(r.permits)} permits)  "
          f"inv {int(r.inv_tot)}/{int(r.inv_li)}LI  {int(r.yr)}  {str(name)[:40]}")

# ---- 4. Inventory-anchored subsidized estimate + diagnostics ---------------
matched_ids = set(m["TDHCA#"])
gh["matched"] = gh["TDHCA#"].isin(matched_ids)
print("\nkept new-construction LIHTC by award year (devs matched/total, inv units):")
for y in range(2012, 2026):
    s = gh[gh.yr == y]
    if len(s):
        print(f"  {int(y)}: {int(s.matched.sum())}/{len(s)} matched a permit, {int(s.u_tot.sum()):,} inv units")

TOTAL = int(res["units"].sum())
core = gh[(gh.yr >= 2014) & (gh.yr <= 2022)]    # cleanly permitted within 2015-2024
broad = gh[(gh.yr >= 2013) & (gh.yr <= 2023)]   # include the edge award years
conf = gh[gh["matched"]]                         # strictly permit-confirmed


def line(lbl, d):
    t, li = int(d.u_tot.sum()), int(d.u_li.sum())
    print(f"  {lbl}: {len(d):2d} devs | {t:,} units ({t/TOTAL*100:4.1f}%) | "
          f"{li:,} income-restricted ({li/TOTAL*100:4.1f}%) | {int(d.matched.sum())} permit-confirmed")


print(f"\n=== CITY OF DALLAS, new dwelling units permitted 2015-2024: {TOTAL:,} ===")
print("Subsidized = units in new-construction LIHTC developments (TDHCA inventory):")
line("award 2014-2022 (core) ", core)
line("award 2013-2023 (broad)", broad)
line("permit-confirmed floor ", conf)
print(f"  => market-rate is ~{(1-broad.u_tot.sum()/TOTAL)*100:.0f}-{(1-conf.u_tot.sum()/TOTAL)*100:.0f}% of new units "
      f"(best estimate ~{(1-core.u_tot.sum()/TOTAL)*100:.0f}% market / ~{core.u_tot.sum()/TOTAL*100:.0f}% subsidized)")

# per-tract subsidized, keyed by the inventory's own 2020 tract (CT 2020 == full GEOID)
broad = broad.copy()
broad["geoid_ct"] = broad["CT 2020"].astype(float).astype("Int64").astype(str)
sub_by_ct = broad.groupby("geoid_ct")[["u_tot", "u_li"]].sum()
ptot = near.groupby("geoid")["units"].sum()
out = []
for g, u in ptot.items():
    r = sub_by_ct.loc[g] if g in sub_by_ct.index else None
    out.append({"geoid": g, "units": int(u),
                "sub_units": int(r["u_tot"]) if r is not None else 0,
                "sub_li_units": int(r["u_li"]) if r is not None else 0})
json.dump(out, open(os.path.join(DATA, "permits_lihtc.json"), "w"))
print(f"Wrote data/permits_lihtc.json  (subsidized units on {sum(1 for o in out if o['sub_units']>0)} tracts)")

# Per-tract tenure split for the scatterplots. LIHTC units = INVENTORY units of
# the developments confirmed built in-window (>=1 on-site 2015-2024 permit -- which
# excludes pre-2015 developments the award-year window would wrongly add), assigned
# to the tract holding most of their permits, and CAPPED at that tract's total
# permitted units (can't permit more LIHTC than total). market = total - LIHTC, so
# the two always sum to the permit total with no negatives. Inventory units are used
# because permit-point matching counts units unreliably (geocoding offsets, over-grab).
mm = near[near["match"]].copy()
dev = mm.groupby("TDHCA#").agg(tract=("geoid", lambda s: s.mode().iloc[0]),
                               inv_tot=("u_tot", "first"), inv_li=("u_li", "first"))
li_by_tract = dev.groupby("tract")[["inv_tot", "inv_li"]].sum()
ptot = near.groupby("geoid")["units"].sum()
ten = []
for g, u in ptot.items():
    u = int(u)
    lt = min(int(li_by_tract.loc[g, "inv_tot"]), u) if g in li_by_tract.index else 0
    ll = min(int(li_by_tract.loc[g, "inv_li"]), u) if g in li_by_tract.index else 0
    ten.append({"geoid": g, "units": u, "lihtc_units": lt, "lihtc_li_units": ll, "market_units": u - lt})
json.dump(ten, open(os.path.join(DATA, "permits_tenure.json"), "w"))
TL = sum(t["lihtc_units"] for t in ten)
print(f"Wrote data/permits_tenure.json  (LIHTC {TL:,} units / {sum(t['lihtc_li_units'] for t in ten):,} "
      f"income-restricted on {sum(1 for t in ten if t['lihtc_units'] > 0)} tracts, {len(dev)} confirmed devs)")
