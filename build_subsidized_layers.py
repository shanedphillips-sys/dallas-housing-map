"""
One deduped, property-level inventory of income-restricted housing in the City of
Dallas, for the webmap's four "Subsidized housing" checkboxes.

Every property appears EXACTLY ONCE, with a single `category` assigned by priority:

    lihtc  >  pfc_hfc  >  public_housing  >  other

so the four map layers can never double-count a building. Every property also carries
`subsidies_json` -- the full list of programs active at that property (name, status,
units, start/end dates) -- so a LIHTC property that also has Section 8 and HOME shows
all three in the popup even though it is drawn once, in the LIHTC layer.

Sources
  NHPD (data/nhpd_lihtc_properties.xlsx)  LIHTC, public housing, project-based S8,
                                          202/811 PRAC, HOME, project-based vouchers,
                                          Mod Rehab -- and the end dates.
  TDHCA HTC Property Inventory            the LIHTC award universe. More complete and
                                          more current than NHPD (which keys on placed-
                                          in-service, so 2020+ awards are missing), but
                                          it has NO expiration dates. We union the two
                                          and graft NHPD's end date onto the match.
  data/pfc_hfc_projects.geojson           PFC / HFC (build_pfc_hfc_points.py, DCAD owner
                                          names). Not in any federal database.

EXCLUDED on purpose: properties whose only NHPD record is an FHA-insured mortgage.
HUD mortgage insurance is lender default cover, not an income restriction -- 8 of the
Dallas records are literally labelled "MKT RATE" -- so counting them would inflate the
inventory by ~888 units. Where an insured mortgage sits on a property that IS restricted
by another program, it is still listed in `subsidies_json` as context.

Output: data/subsidized_all.geojson
"""
import json
import os
import re
from difflib import SequenceMatcher

import geopandas as gpd
import numpy as np
import pandas as pd

WEB = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(WEB, "data")
NHPD_XLSX = os.path.join(DATA, "nhpd_lihtc_properties.xlsx")
NHPD_CACHE = os.path.join(DATA, "_nhpd_dallas_cache.parquet")
TDHCA_XLSX = (r"C:/Users/shane/OneDrive/Documents/Domain Consulting/Projects"
              r"/GDPC - Dallas Housing Report/GDPC Claude Stuff"
              r"/HTC Property Inventory as of May 29 2026.xlsx")
PFC_GEOJSON = os.path.join(DATA, "pfc_hfc_projects.geojson")
OUT = os.path.join(DATA, "subsidized_all.geojson")

FT = "EPSG:2276"
CO_SITE_FT, NAME_EXACT, NAME_NEAR, NEAR_NAME_FT = 250.0, 0.90, 0.70, 3000.0
STOP = (r"\b(APARTMENTS|APARTMENT|APTS|APT|THE|LP|LTD|LLC|INC|PHASE|SENIOR|SENIORS|"
        r"HOMES|HOME|RESIDENCES|RESIDENCE|VILLAS|HAP|AT|OF|II|III|IV)\b")

# NHPD subsidy blocks -> display label. `restricts` marks the ones that actually impose
# an income restriction (FHA does not; it is carried for context only).
BLOCKS = [
    ("LIHTC_1", "LIHTC", True), ("LIHTC_2", "LIHTC (2nd allocation)", True),
    ("PH_1", "Public housing", True), ("PH_2", "Public housing (2nd)", True),
    ("S8_1", "Project-based Section 8", True), ("S8_2", "Project-based Section 8 (2nd)", True),
    ("HOME_1", "HOME", True), ("HOME_2", "HOME (2nd)", True),
    ("Pbv_1", "Project-based voucher", True), ("Pbv_2", "Project-based voucher (2nd)", True),
    ("Mr_1", "Section 8 Moderate Rehab", True), ("Mr_2", "Section 8 Moderate Rehab (2nd)", True),
    ("S202_1", "Section 202", True), ("S236_1", "Section 236", True),
    ("RHS515_1", "USDA Section 515", True), ("RHS538_1", "USDA Section 538", True),
    ("NHTF_1", "National Housing Trust Fund", True), ("State_1", "State program", True),
    ("FHA_1", "HUD-insured mortgage", False), ("FHA_2", "HUD-insured mortgage (2nd)", False),
]


def norm(s):
    s = re.sub(r"[^A-Z0-9 ]", " ", str(s).upper())
    s = re.sub(STOP, " ", s)
    return re.sub(r"\s+", " ", s).strip()


def sim(x, y):
    return SequenceMatcher(None, x, y).ratio() if x and y else 0.0


def ival(v):
    n = pd.to_numeric(v, errors="coerce")
    return None if pd.isna(n) else int(n)


def dstr(v):
    d = pd.to_datetime(v, errors="coerce")
    return None if pd.isna(d) else d.strftime("%Y-%m-%d")


def match_pairs(A, B, akey, bkey):
    """Greedy one-to-one match between two projected GeoDataFrames. Distance cannot gate
    the match -- the sources geocode the same building up to 5 mi apart -- so a near-exact
    name wins at any distance, a weaker name only nearby, co-located points on geometry."""
    if not len(A) or not len(B):
        return []
    D = np.hypot(A.geometry.x.values[:, None] - B.geometry.x.values[None, :],
                 A.geometry.y.values[:, None] - B.geometry.y.values[None, :])
    c = []
    for i in range(len(A)):
        for j in range(len(B)):
            s = sim(akey[i], bkey[j])
            d = D[i, j]
            if s >= NAME_EXACT or (s >= NAME_NEAR and d <= NEAR_NAME_FT) or d <= CO_SITE_FT:
                c.append((s, -d, i, j))
    c.sort(reverse=True)
    ui, uj, out = set(), set(), []
    for s, negd, i, j in c:
        if i in ui or j in uj:
            continue
        ui.add(i)
        uj.add(j)
        out.append((i, j, s, -negd))
    return out


# ---------------------------------------------------------------- load
city = gpd.read_file(os.path.join(DATA, "city_boundary.geojson")).to_crs(4326)
city_geom = city.geometry.union_all()

if os.path.exists(NHPD_CACHE):
    nh = gpd.read_parquet(NHPD_CACHE)
else:
    d = pd.read_excel(NHPD_XLSX, sheet_name="Sheet1")
    d = d[d["State"].astype(str).str.strip().str.upper() == "TX"]
    nh = gpd.GeoDataFrame(d, geometry=gpd.points_from_xy(d.Longitude, d.Latitude), crs=4326)
    nh = nh[nh.within(city_geom)].copy()
    nh.to_parquet(NHPD_CACHE)
nh = nh.reset_index(drop=True)

td = pd.read_excel(TDHCA_XLSX, sheet_name="PropInventory")
td = td[td["Project City"].astype(str).str.strip().str.upper() == "DALLAS"].copy()
td["lat"] = pd.to_numeric(td["Latitude11"], errors="coerce")
td["lon"] = pd.to_numeric(td["Longitude11"], errors="coerce")
td = td.dropna(subset=["lat", "lon"])
td["_t"] = pd.to_numeric(td["Total Units"], errors="coerce").fillna(0)
td = td.sort_values("_t", ascending=False).drop_duplicates(subset=["lat", "lon"])
tg = gpd.GeoDataFrame(td, geometry=gpd.points_from_xy(td.lon, td.lat), crs=4326)
tg = tg[tg.within(city_geom)].reset_index(drop=True)

pfc = gpd.GeoDataFrame.from_features(json.load(open(PFC_GEOJSON))["features"], crs=4326)
pfc = pfc.reset_index(drop=True)

print(f"inputs: NHPD {len(nh)} | TDHCA {len(tg)} | PFC/HFC {len(pfc)}")

# ---------------------------------------------------------------- NHPD -> records
def subsidies_of(r):
    out = []
    for pre, label, restricts in BLOCKS:
        sc = pre + "_Status"
        if sc not in r.index or pd.isna(r[sc]):
            continue
        prog = r.get(pre + "_ProgramName")
        # NHPD files 202/811 PRACs inside the Section 8 block; surface them by name.
        if pre.startswith("S8") and isinstance(prog, str) and re.search(r"202|811", prog):
            label = "Section 202 / 811 (PRAC)"
        out.append({
            "program": label,
            "detail": None if pd.isna(prog) else str(prog),
            "status": str(r[sc]),
            "units": ival(r.get(pre + "_AssistedUnits")),
            "start": dstr(r.get(pre + "_StartDate")),
            "end": dstr(r.get(pre + "_EndDate")),
            "restricts": restricts,
            "note": (str(r[pre + "_InacStatusDesc"])
                     if pre + "_InacStatusDesc" in r.index and pd.notna(r.get(pre + "_InacStatusDesc"))
                     else None),
        })
    return out


recs = []
for _, r in nh.iterrows():
    subs = subsidies_of(r)
    kinds = {s["program"] for s in subs if s["restricts"]}
    if not kinds:                                   # FHA-only / nothing restricting
        continue
    has = lambda *k: any(any(x in p for x in k) for p in kinds)
    if has("LIHTC"):
        cat = "lihtc"
    elif has("Public housing"):
        cat = "public_housing"
    else:
        cat = "other"
    recs.append({
        "name": None if pd.isna(r.PropertyName) else str(r.PropertyName),
        "address": None if pd.isna(r.PropertyAddress) else str(r.PropertyAddress),
        "total_units": ival(r.TotalUnits),
        "category": cat,
        "subsidies": subs,
        "source": "NHPD",
        "nhpd_id": None if pd.isna(r.NHPDPropertyID) else str(r.NHPDPropertyID),
        "owner": None if pd.isna(r.Owner) else str(r.Owner),
        "owner_type": None if pd.isna(r.OwnerType) else str(r.OwnerType),
        "lon": float(r.Longitude), "lat": float(r.Latitude),
    })
excluded_fha = len(nh) - len(recs)
print(f"NHPD -> {len(recs)} restricted properties ({excluded_fha} dropped: FHA-insured only / no restriction)")

R = gpd.GeoDataFrame(pd.DataFrame(recs),
                     geometry=gpd.points_from_xy([x["lon"] for x in recs], [x["lat"] for x in recs]),
                     crs=4326)

# ---------------------------------------------------------------- graft TDHCA
Rp, Tp = R.to_crs(FT), tg.to_crs(FT)
rk = [norm(x) for x in R["name"]]
tk = [norm(x) for x in tg["Development Name"]]
pairs = match_pairs(Rp, Tp, rk, tk)
matched_t = {j for _, j, _, _ in pairs}
for i, j, s, d in pairs:
    t = tg.iloc[j]
    recs[i]["tdhca_num"] = str(t["TDHCA#"])
    recs[i]["award_year"] = ival(t["Year"])
    recs[i]["lihtc_units"] = ival(t["LIHTC Units"])
    recs[i]["pop_served"] = None if pd.isna(t["Population Served"]) else str(t["Population Served"])
    if recs[i]["category"] != "lihtc":               # TDHCA proves a tax credit NHPD missed
        recs[i]["category"] = "lihtc"
        recs[i]["subsidies"].append({
            "program": "LIHTC", "detail": str(t["Program Type"]), "status": "Active (TDHCA)",
            "units": ival(t["LIHTC Units"]), "start": None, "end": None, "restricts": True,
            "note": "TDHCA award; no expiration date published"})
print(f"TDHCA matched onto NHPD rows: {len(pairs)}")

for j in range(len(tg)):                             # TDHCA awards NHPD has never seen
    if j in matched_t:
        continue
    t = tg.iloc[j]
    recs.append({
        "name": str(t["Development Name"]), "address": str(t["Project Address "]).strip(),
        "total_units": ival(t["Total Units"]), "category": "lihtc",
        "subsidies": [{"program": "LIHTC", "detail": str(t["Program Type"]),
                       "status": "Active (TDHCA)", "units": ival(t["LIHTC Units"]),
                       "start": None, "end": None, "restricts": True,
                       "note": "TDHCA award; no expiration date published"}],
        "source": "TDHCA", "tdhca_num": str(t["TDHCA#"]), "award_year": ival(t["Year"]),
        "lihtc_units": ival(t["LIHTC Units"]),
        "pop_served": None if pd.isna(t["Population Served"]) else str(t["Population Served"]),
        "lon": float(t.lon), "lat": float(t.lat),
    })
print(f"TDHCA-only LIHTC awards added: {len(tg) - len(matched_t)}")

# ---------------------------------------------------------------- merge PFC/HFC
R2 = gpd.GeoDataFrame(pd.DataFrame(recs),
                      geometry=gpd.points_from_xy([x["lon"] for x in recs], [x["lat"] for x in recs]),
                      crs=4326).to_crs(FT)
Pp = pfc.to_crs(FT)
r2k = [norm(x) for x in [rr["name"] for rr in recs]]
pk = [norm(x) for x in pfc["name"]]
ppairs = match_pairs(R2, Pp, r2k, pk)
matched_p = {j for _, j, _, _ in ppairs}
for i, j, s, d in ppairs:
    p = pfc.iloc[j]
    recs[i]["subsidies"].append({
        "program": "PFC / HFC", "detail": None if pd.isna(p.get("owner")) else str(p.get("owner")),
        "status": "Active", "units": ival(p.get("total_units")), "start": None, "end": None,
        "restricts": True, "note": "Property-tax exemption; no statutory expiration"})
    if recs[i]["category"] not in ("lihtc",):        # LIHTC outranks PFC/HFC
        recs[i]["category"] = "pfc_hfc"
print(f"PFC/HFC merged into existing properties: {len(ppairs)}")

for j in range(len(pfc)):
    if j in matched_p:
        continue
    p = pfc.iloc[j]
    recs.append({
        "name": None if pd.isna(p.get("name")) else str(p.get("name")),
        "address": None if pd.isna(p.get("address")) else str(p.get("address")),
        "total_units": ival(p.get("total_units")), "category": "pfc_hfc",
        "subsidies": [{"program": "PFC / HFC",
                       "detail": None if pd.isna(p.get("owner")) else str(p.get("owner")),
                       "status": "Active", "units": ival(p.get("total_units")),
                       "start": None, "end": None, "restricts": True,
                       "note": "Property-tax exemption; no statutory expiration"}],
        "source": "DCAD", "year_built": ival(p.get("year_built")),
        "units_est": bool(p.get("units_est")) if p.get("units_est") is not None else False,
        "lon": float(p.geometry.x), "lat": float(p.geometry.y),
    })
print(f"PFC/HFC added as new properties: {len(pfc) - len(matched_p)}")

# ---------------------------------------------------------------- consolidate twins
# TDHCA lists some properties on two rows (original award + a later resyndication) at
# slightly different coordinates. The NHPD<->TDHCA match is one-to-one, so only one row can
# claim the NHPD property; the leftover arrives here as a second, unit-less dot for the same
# building. Fold any ZERO-unit record into a nearby same-name record. Restricted to unit-less
# records on purpose: they carry no count to lose, so the merge cannot change any total.
def consolidate(recs):
    G = gpd.GeoDataFrame(pd.DataFrame(recs),
                         geometry=gpd.points_from_xy([x["lon"] for x in recs],
                                                     [x["lat"] for x in recs]),
                         crs=4326).to_crs(FT)
    keys = [norm(x.get("name")) for x in recs]
    xs, ys = G.geometry.x.values, G.geometry.y.values
    drop = set()
    for i, r in enumerate(recs):
        if (r.get("total_units") or 0) > 0:
            continue
        best, bs = None, 0.0
        for j, o in enumerate(recs):
            if i == j or j in drop or (o.get("total_units") or 0) <= 0:
                continue
            d = float(np.hypot(xs[i] - xs[j], ys[i] - ys[j]))
            if d > 1500.0:
                continue
            s = sim(keys[i], keys[j])
            if s >= 0.70 and s > bs:
                bs, best = s, j
        if best is not None:
            have = {(s["program"], s.get("start"), s.get("end")) for s in recs[best]["subsidies"]}
            for s in r["subsidies"]:
                if (s["program"], s.get("start"), s.get("end")) not in have:
                    recs[best]["subsidies"].append(s)
            for k in ("award_year", "tdhca_num", "pop_served", "lihtc_units"):
                if recs[best].get(k) is None and r.get(k) is not None:
                    recs[best][k] = r[k]
            drop.add(i)
    return [r for i, r in enumerate(recs) if i not in drop], len(drop)


recs, n_merged = consolidate(recs)


def restricted_of(r):
    """Income-restricted unit count. Programs STACK on the same units (a LIHTC property
    with project-based Section 8 does not have lihtc+s8 restricted units), so the estimate
    is the LARGEST single program's assisted count, clamped to total units -- never a sum.
    Zero is treated as missing, not as a real zero. PFC/HFC is excluded: DCAD reports no
    set-aside count, and a PFC deal is typically mostly market-rate, so counting its total
    as restricted would be flatly wrong."""
    subs = [s for s in r["subsidies"] if s.get("restricts")]
    lihtc = [s for s in subs if s["program"].startswith("LIHTC")]
    if lihtc and not any(s.get("units") for s in lihtc) and not r.get("lihtc_units"):
        return None      # LIHTC restricts an unknown share here, and a co-program's smaller
                         # count is not evidence about it -- e.g. Rosemont at Cedar Crest has
                         # an uncounted LIHTC record plus 31 vouchers on 256 units; reporting
                         # 31 (12%) would be far more wrong than reporting unknown.
    vals = [s["units"] for s in subs if s.get("units") and s["program"] != "PFC / HFC"]
    if r.get("lihtc_units"):
        vals.append(r["lihtc_units"])
    if not vals:
        return None
    t = r.get("total_units")
    return min(max(vals), t) if t else max(vals)


# ---------------------------------------------------------------- cross-source twins
# NHPD and TDHCA sometimes carry the same building under DIFFERENT names, usually because
# the property was renamed at a resyndication (TDHCA keeps the original award name, NHPD
# picks up the new one). The name-similarity matcher never fires on those, so the building
# lands in the file twice. The tell is an identical income-restricted unit count at the
# same street address. Each pair below was checked by hand before this rule was written:
#   Willow Pond Apartments / Willow Pond (fka Glen Hills)        6003 Abrams Rd      386u
#   Treymore Eastfield / Treymore at LaPrada                     2631 John West Rd   150u
#   Rosemont at Sierra Vista Scyene / Rosemont at Scyene         9901 Scyene Rd      250u
#   Providence on the Park / Rose Court at Thorntree             8501 Old Hickory    280u
#   Rosemont at Meadow Lane / Southern Terrace Apartments        4722 Meadow St      264u
#   High Point Senior Living / Wynnewood Seniors Housing         1615 S Zang Blvd    140u
# Deliberately NOT merged, because the addresses are genuinely different buildings:
#   Cliff View Village II / III (2425 vs 2628 Simpson Stuart), Southfair Fair Park
#   Estates III / IV / V (three scattered sites, three different HOME end dates),
#   Carroll Townhomes / Jaipur Lofts (2202 Kirby vs Annex Ave; TDHCA #00004T vs #22285 --
#   both happen to have 71 units), and Fairway Village / Ridgecrest Terrace (both 250u and
#   both Steele Properties, but 18 vs 19 buildings and different streets -- unresolved).
ADDR_STOP = re.compile(r"\b(APT|UNIT|STE|SUITE|BLDG)\b.*$")
ADDR_SUFFIX = {"STREET": "ST", "AVENUE": "AVE", "ROAD": "RD", "DRIVE": "DR", "LANE": "LN",
               "BOULEVARD": "BLVD", "PARKWAY": "PKWY", "HIGHWAY": "HWY", "COURT": "CT",
               "TRAIL": "TRL", "CIRCLE": "CIR", "COMMONS": "CMNS", "PLACE": "PL"}
# Verified twins whose ADDRESSES differ for a documented reason, so the rule cannot see them:
#   Frazier Fellowship -- Hatcher St was renamed Elsie Faye Heggins St, so TDHCA's "4848
#     Hatcher Street" and NHPD's "4848 Elsie Faye Heggins St" are one address, 98 ft apart.
#   Buckeye Trail Commons / Buckeye I -- 6707 vs 6655 Buckeye Commons Way, one 323-unit DHA
#     development; HUD lists 207 units of low-income housing there and our separate "Buckeye
#     Trail Commons II" carries the other 116. The 207-unit LIHTC record and the 207-unit
#     public-housing record are the same units.
#   2400 Bryan / Galbraith Exempt -- one building at 2400 Bryan St recorded twice: NHPD as a
#     LIHTC property (111 restricted of 212) and DCAD as a PFC/HFC one (109 of 217). Same
#     address, near-identical counts, two sources, two programs.
#   Parks at Wynnewood / Highpoint at Wynnewood -- 1910 Argentia Dr. The 1998 allocation
#     (172 units, ending 2028) was redeveloped under a 2022 TDHCA award (220 units), so the
#     records are one site; merging lets the resyndication rule below re-date it correctly.
VERIFIED_TWINS = [("FRAZIER FELLOWSHIP", "FRAZIER FELLOWSHIP"),
                  ("BUCKEYE TRAIL COMMONS", "BUCKEYE I"),
                  ("2400 BRYAN", "GALBRAITH EXEMPT"),
                  ("PARKS WYNNEWOOD", "HIGHPOINT WYNNEWOOD")]


def norm_addr(a):
    a = re.sub(r"[^A-Z0-9 ]", " ", str(a).upper())
    a = ADDR_STOP.sub("", a)
    a = " ".join(ADDR_SUFFIX.get(w, w) for w in a.split())
    return re.sub(r"\s+", " ", a).strip()


def merge_twins(recs):
    """Fold a cross-source duplicate into its twin, keeping the union of both subsidy
    lists and the larger unit counts. Only fires on identical restricted-unit counts."""
    G = gpd.GeoDataFrame(pd.DataFrame(recs),
                         geometry=gpd.points_from_xy([x["lon"] for x in recs],
                                                     [x["lat"] for x in recs]),
                         crs=4326).to_crs(FT)
    xs, ys = G.geometry.x.values, G.geometry.y.values
    rest = [restricted_of(r) for r in recs]
    addr = [norm_addr(r.get("address")) for r in recs]
    names = [norm(r.get("name")) for r in recs]
    drop, merged = set(), []
    tot = [r.get("total_units") or 0 for r in recs]
    for i in range(len(recs)):
        if i in drop:
            continue
        for j in range(i + 1, len(recs)):
            if j in drop:
                continue
            # Hand-verified pairs are checked FIRST and bypass every other gate -- each was
            # confirmed individually, and two of them (2400 Bryan / Galbraith Exempt, Parks
            # at Wynnewood / Highpoint at Wynnewood) differ on both unit count and distance
            # precisely because the two sources describe the building differently.
            verified = any({names[i], names[j]} == {a, b} or (names[i] == a and names[j] == b)
                           for a, b in VERIFIED_TWINS)
            if not verified:
                # Same building, seen twice. Requiring identical RESTRICTED counts missed the
                # cases where one source publishes no count at all, so accept any of:
                #   equal restricted units | equal total units | one side carries no units
                same_units = (
                    (rest[i] and rest[j] and rest[i] == rest[j])
                    or (tot[i] and tot[j] and tot[i] == tot[j])
                    or (not rest[i] and not tot[i]) or (not rest[j] and not tot[j]))
                # An identical street address (with a house number) plus a matching unit count
                # is decisive on its own, so it is NOT distance-gated: the two sources geocode
                # the same building anywhere from 300 ft to 5 miles apart, and a 900 ft gate
                # was silently blocking real twins -- Artisan Ridge / Preakness Ranch (both
                # "5480 Preakness Ln", 264 units) at 1,338 ft, and Pegasus Villas / The Pegasus
                # (both "7200 N Stemmons Fwy", 124 units) at 906 ft, six feet over the line.
                same_addr = (bool(addr[i]) and addr[i] == addr[j]
                             and any(c.isdigit() for c in addr[i]))
                if not (same_addr and same_units):
                    continue
            keep, lose = (i, j) if (recs[i].get("total_units") or 0) >= (recs[j].get("total_units") or 0) else (j, i)
            have = {(s["program"], s.get("start"), s.get("end")) for s in recs[keep]["subsidies"]}
            for s in recs[lose]["subsidies"]:
                if (s["program"], s.get("start"), s.get("end")) not in have:
                    recs[keep]["subsidies"].append(s)
            for k in ("award_year", "tdhca_num", "pop_served", "lihtc_units", "address",
                      "owner", "owner_type", "nhpd_id", "hud_id"):
                if recs[keep].get(k) is None and recs[lose].get(k) is not None:
                    recs[keep][k] = recs[lose][k]
            merged.append((recs[lose].get("name"), recs[keep].get("name"), rest[i]))
            drop.add(lose)
            if lose == i:
                break
    return [r for k, r in enumerate(recs) if k not in drop], merged


recs, twins = merge_twins(recs)
print(f"cross-source twins merged: {len(twins)}")
for a, b, u in twins:
    print(f"    {str(a)[:36]:38s} -> {str(b)[:36]:38s} ({u} restricted units)")
print(f"unit-less duplicate dots folded into their twin: {n_merged}")


# ---------------------------------------------------------------- impute LIHTC end dates
# 92 of the 167 LIHTC properties carry a published expiration; the rest do not, and none of
# them has a placed-in-service date either (they are TDHCA award records, or NHPD rows whose
# LIHTC block reads "End Date Missing"). What every one DOES have is a TDHCA award year.
# Calibrated on the 71 Dallas properties that have both (analyze_lihtc_terms.py): the median
# award-to-expiration span is 32 years -- the 30-year federal minimum extended-use period
# plus a ~2-year build lag. Dallas's own median term is 30 yrs (61% land on exactly 30).
# Awards from 2020 on are deliberately NOT imputed: their expirations sit past the reporting
# horizon and the credits are too new for the estimate to add anything.
IMPUTE_SPAN, IMPUTE_MAX_AWARD = 32, 2019
n_imputed = 0
for r in recs:
    aw = r.get("award_year")
    if not aw or aw > IMPUTE_MAX_AWARD:
        continue
    lih = [s for s in r["subsidies"] if s["program"].startswith("LIHTC")]
    if not lih or any(s.get("end") for s in lih):
        continue
    lih[0]["end"] = f"{int(aw) + IMPUTE_SPAN}-12-31"
    lih[0]["imputed"] = True
    lih[0]["note"] = (f"Estimated: {int(aw)} TDHCA award + {IMPUTE_SPAN} yr "
                      f"(median Dallas award-to-expiration). Not a published date.")
    n_imputed += 1
print(f"LIHTC end dates imputed (award <= {IMPUTE_MAX_AWARD}): {n_imputed}")

# ---------------------------------------------------------------- resyndications
# A property that took a NEW tax-credit award years after its recorded allocation began has
# been resyndicated: the fresh award restarts the compliance clock, so the end date NHPD
# holds for the old allocation no longer governs. The tell is a TDHCA award year well after
# the recorded LIHTC start (e.g. Rosemont at Ash Creek, allocation 2004 -> 2034, but a 2023
# TDHCA award and a new HUD-insured mortgage running to 2065).
# Terrace at Highland Hills is the control: NHPD DID record its post-resyndication dates,
# and its published end (2055) equals its 2023 award + 32 exactly -- so award + IMPUTE_SPAN
# reproduces the observed value in the one case where it can be checked. Properties whose
# new allocation is already dated are left alone.
RESYND_GAP = 5
n_resynd = 0
for r in recs:
    aw = r.get("award_year")
    if not aw:
        continue
    dated = [s for s in r["subsidies"]
             if s["program"].startswith("LIHTC") and s.get("end") and s.get("start")]
    if not dated:
        continue
    start_yr = min(int(s["start"][:4]) for s in dated)
    end_yr = max(int(s["end"][:4]) for s in dated)
    if int(aw) <= start_yr + RESYND_GAP:
        continue                                  # award belongs to the recorded allocation
    if end_yr >= int(aw) + IMPUTE_SPAN - 2:
        continue                                  # new allocation already dated (the control)
    gov = max(dated, key=lambda s: s["end"])
    gov["end"] = f"{int(aw) + IMPUTE_SPAN}-12-31"
    gov["imputed"] = True
    gov["note"] = (f"Superseded: a new {int(aw)} TDHCA award resyndicated this property, so "
                   f"the {end_yr} expiration on the {start_yr} allocation no longer governs. "
                   f"Estimated {int(aw)} + {IMPUTE_SPAN} yr.")
    n_resynd += 1
print(f"resyndications re-dated (new award supersedes the old expiration): {n_resynd}")

# ---------------------------------------------------------------- owner class
# Two independent sources, used in that order:
#   1. NHPD OwnerType -- describes the OWNING ENTITY.
#   2. HUD LIHTC database NON_PROF -- "Non-profit sponsor", 1=Yes / 2=No. This is a
#      SPONSOR-level flag, so it sees a nonprofit general partner that NHPD's entity-level
#      field would record as "For Profit" (nearly every tax-credit deal is held by a
#      single-purpose LP). Used only where NHPD reports nothing.
# The two agree on 66 of 67 Dallas properties where both carry a value, and HUD's own
# sponsor flag puts Texas at 4.2% / Dallas at 6.2% nonprofit against 23% nationally -- so
# the low nonprofit share here is a real feature of the Texas market, not a coding artifact.
FOR_PROFIT = {"For Profit", "Profit Motivated", "Limited Profit", "Limited Dividend"}
NONPROFIT = {"Non-Profit", "Public Entity"}
HUD_LIHTC_XLSX = os.path.join(DATA, "lihtcpub", "LIHTCPUB.xlsx")
HUD_CACHE = os.path.join(DATA, "_hud_lihtc_dallas.parquet")


def owner_class(t):
    if t in FOR_PROFIT:
        return "for_profit"
    if t in NONPROFIT:
        return "nonprofit_public"
    return "unknown"          # not reported, or "Multiple"


def load_hud_lihtc():
    """City-of-Dallas rows of the HUD LIHTC database. Cached: openpyxl trips over a
    worksheet property in HUD's workbook, so patch that away before reading."""
    if os.path.exists(HUD_CACHE):
        return gpd.read_parquet(HUD_CACHE)
    import openpyxl.worksheet.properties as wp
    _orig = wp.WorksheetProperties.__init__

    def _patched(self, *a, **k):
        for bad in ("synchVertical", "synchHorizontal", "synchRef",
                    "transitionEvaluation", "transitionEntry"):
            k.pop(bad, None)
        _orig(self, *a, **k)

    wp.WorksheetProperties.__init__ = _patched
    h = pd.read_excel(HUD_LIHTC_XLSX, sheet_name="Data")
    wp.WorksheetProperties.__init__ = _orig
    h = h[h.proj_st.astype(str).str.upper() == "TX"].copy()
    h["lat"] = pd.to_numeric(h.latitude, errors="coerce")
    h["lon"] = pd.to_numeric(h.longitude, errors="coerce")
    h = h.dropna(subset=["lat", "lon"])
    g = gpd.GeoDataFrame(h, geometry=gpd.points_from_xy(h.lon, h.lat), crs=4326)
    g = g[g.within(city_geom)].reset_index(drop=True)
    g.to_parquet(HUD_CACHE)
    return g


for r in recs:
    r["owner_class"] = owner_class(r.get("owner_type"))
    r["owner_source"] = "NHPD OwnerType" if r["owner_class"] != "unknown" else None

hud = load_hud_lihtc()
Rh = gpd.GeoDataFrame(pd.DataFrame(recs),
                      geometry=gpd.points_from_xy([x["lon"] for x in recs],
                                                  [x["lat"] for x in recs]),
                      crs=4326).to_crs(FT)
hp = hud.to_crs(FT)
hpairs = match_pairs(Rh, hp, [norm(x.get("name")) for x in recs],
                     [norm(x) for x in hud["project"]])
n_hud = 0
for i, j, s, dist in hpairs:
    np_flag = pd.to_numeric(hud["non_prof"].iat[j], errors="coerce")
    cls = {1.0: "nonprofit_public", 2.0: "for_profit"}.get(np_flag)
    recs[i]["hud_id"] = str(hud["hud_id"].iat[j])
    if cls and recs[i]["owner_class"] == "unknown":
        recs[i]["owner_class"] = cls
        recs[i]["owner_source"] = "HUD LIHTC non_prof (sponsor)"
        n_hud += 1
print(f"HUD LIHTC matched: {len(hpairs)} properties | owner class newly resolved: {n_hud}")


# ---------------------------------------------------------------- restricted units
SUFFIX = {"STREET": "ST", "AVENUE": "AVE", "ROAD": "RD", "DRIVE": "DR", "LANE": "LN",
          "BOULEVARD": "BLVD", "PARKWAY": "PKWY", "HIGHWAY": "HWY", "COURT": "CT",
          "TRAIL": "TRL", "CIRCLE": "CIR", "NORTHWEST": "NW", "NORTHEAST": "NE"}


def norm_addr(s):
    s = re.sub(r"[^A-Z0-9 ]", " ", str(s).upper())
    return re.sub(r"\s+", " ", " ".join(SUFFIX.get(w, w) for w in s.split())).strip()


def load_pfc_overrides():
    """Published income-restricted counts for Dallas PFC leasing properties
    (data/pfc_restricted_units.json, scraped from dallaspfc.com). DCAD reports ownership
    but no set-aside, so without this every PFC dot is sized by TOTAL units."""
    path = os.path.join(DATA, "pfc_restricted_units.json")
    if not os.path.exists(path):
        return {}
    src = json.load(open(path))
    out = {}
    for p in src["properties"]:
        for a in p["addresses"]:
            out[norm_addr(a)] = p
    return out


PFC_OVERRIDES = load_pfc_overrides()


def pfc_restricted(r):
    """Restricted units for a PFC parcel from the published DPFC figures, or None.
    A published development can span several DCAD parcels (Co/Op Maple is 5907 + 5908
    Maple Ave), so use the absolute count only when the parcel's own total matches the
    published total; otherwise apply the published affordable SHARE to this parcel."""
    p = PFC_OVERRIDES.get(norm_addr(r.get("address")))
    if not p:
        return None, None
    t, pub_t, pub_r = r.get("total_units"), p["total_units"], p["restricted_units"]
    if not t:
        return pub_r, p["name"]
    if abs(t - pub_t) <= 5:                      # same building, minor count drift
        return min(pub_r, t), p["name"]
    return int(round(t * pub_r / pub_t)), p["name"]


# Standalone PFC/HFC deals set aside HALF their units and no more. Evidence:
#   - all 12 Dallas PFC properties that publish a set-aside (dallaspfc.com) land between
#     50.0% and 52.6%, median 50.1%; none exceeds 55%
#   - Ch. 394 requires half the units at <=80% AMI (~$88k for DFW), and Ch. 303 as amended
#     by HB 2071 requires less still, so 50% is the statutory floor AND the observed value
#   - the only PFC/HFC properties above 52.6% are the six that ALSO carry LIHTC (85-100%
#     restricted) -- and those are categorised `lihtc`, take their count from LIHTC data,
#     and never reach this branch. Every `pfc_hfc` property is by construction standalone.
# So for a standalone PFC/HFC parcel with no published count, 50% is a far better estimate
# than the total-units fallback, which overstates by ~2x. Flagged as ASSUMED, never as data.
# Applied with a CEILING: an odd-unit building gets one more restricted unit than market-rate.
PFC_ASSUMED_SHARE = 0.50


# ---------------------------------------------------------------- write
feats = []
for r in recs:
    subs = r["subsidies"]
    ends = [s["end"] for s in subs if s.get("end") and s.get("restricts")]
    rest = restricted_of(r)
    pfc_rest, pfc_name = pfc_restricted(r)
    rest_src = None
    if pfc_rest is not None:
        rest = pfc_rest if rest is None else max(rest, pfc_rest)
        rest_src = "published"
        for s in subs:
            if s["program"] == "PFC / HFC":
                s["units"] = pfc_rest
                s["note"] = (f"{pfc_rest} income-restricted of {r.get('total_units')} "
                             f"(published by Dallas PFC); no statutory expiration")
    elif r["category"] == "pfc_hfc" and rest is None and r.get("total_units"):
        # standalone PFC/HFC with nothing published -- see PFC_ASSUMED_SHARE. Rounded UP, so
        # an odd-unit building gets one more restricted unit than market-rate: "at least half"
        # is the statutory test, and round() would bank an odd count down and miss it.
        rest = int(np.ceil(r["total_units"] * PFC_ASSUMED_SHARE))
        rest_src = "assumed"
        for s in subs:
            if s["program"] == "PFC / HFC":
                s["units"] = rest
                s["note"] = (f"Assumed: {rest} of {r.get('total_units')} units (half, rounded "
                             f"up) — the statutory minimum and the share every Dallas PFC "
                             f"property that publishes one reports. NOT a published figure. "
                             f"No statutory expiration.")
    props = {
        "name": r.get("name"), "address": r.get("address"),
        "total_units": r.get("total_units"), "category": r["category"],
        "restricted_units": rest,
        "restricted_known": rest is not None,
        "restricted_source": rest_src,       # "published" | "assumed" | None (measured)
        "source": r.get("source"), "award_year": r.get("award_year"),
        "owner": r.get("owner"), "owner_type": r.get("owner_type"),
        "owner_class": r.get("owner_class"), "owner_source": r.get("owner_source"),
        "hud_id": r.get("hud_id"),
        "lihtc_units": r.get("lihtc_units"), "pop_served": r.get("pop_served"),
        "tdhca_num": r.get("tdhca_num"), "year_built": r.get("year_built"),
        "units_est": r.get("units_est"),
        "n_subsidies": len([s for s in subs if s["restricts"]]),
        "earliest_end": min(ends) if ends else None,
        "subsidies_json": json.dumps(subs, allow_nan=False),
    }
    feats.append({"type": "Feature",
                  "geometry": {"type": "Point",
                               "coordinates": [round(r["lon"], 5), round(r["lat"], 5)]},
                  "properties": {k: v for k, v in props.items() if v is not None}})

json.dump({"type": "FeatureCollection", "features": feats}, open(OUT, "w"), allow_nan=False)

cat = pd.Series([f["properties"]["category"] for f in feats]).value_counts()
un = pd.Series([f["properties"].get("total_units") or 0 for f in feats])
print("\n" + "=" * 62)
print(f"wrote {os.path.basename(OUT)}: {len(feats)} properties, {int(un.sum()):,} total units")
print("\nby map category (each property counted ONCE):")
for k in ("lihtc", "pfc_hfc", "public_housing", "other"):
    sel = [f for f in feats if f["properties"]["category"] == k]
    u = sum(f["properties"].get("total_units") or 0 for f in sel)
    print(f"  {k:15s} {len(sel):4d} properties  {u:7,} units")
multi = [f for f in feats if f["properties"]["n_subsidies"] > 1]
print(f"\nproperties stacking 2+ restricting programs: {len(multi)} "
      f"(drawn once, all programs listed in the popup)")

kn = [f["properties"] for f in feats if f["properties"].get("restricted_units") is not None]
mixed = [p for p in kn if (p.get("total_units") or 0) > p["restricted_units"]]
full = [p for p in kn if (p.get("total_units") or 0) <= p["restricted_units"]]
unk = [f["properties"] for f in feats if f["properties"].get("restricted_units") is None]
print(f"\nincome-restricted unit counts (circle sizing):")
print(f"  known           {len(kn):4d} properties  "
      f"{sum(p['restricted_units'] for p in kn):7,} restricted of "
      f"{sum(p.get('total_units') or 0 for p in kn):,} total")
print(f"    100% restricted {len(full):4d}")
print(f"    MIXED           {len(mixed):4d}  (restricted < total)")
print(f"  unknown         {len(unk):4d} properties  "
      f"{sum(p.get('total_units') or 0 for p in unk):7,} total units "
      f"-- {sum(1 for p in unk if p['category'] == 'pfc_hfc')} are PFC/HFC (no set-aside "
      f"count published); these fall back to total units for sizing")

pf = [f["properties"] for f in feats if f["properties"]["category"] == "pfc_hfc"]
def _tot(x, k="total_units"):
    return sum(p.get(k) or 0 for p in x)


pub = [p for p in pf if p.get("restricted_source") == "published"]
asm = [p for p in pf if p.get("restricted_source") == "assumed"]
none = [p for p in pf if not p.get("restricted_source")]
print(f"\nPFC / HFC restricted units, {len(pf)} properties / {_tot(pf):,} total units:")
print(f"  published (dallaspfc.com) {len(pub):3d} props  "
      f"{_tot(pub, 'restricted_units'):5,} restricted of {_tot(pub):6,} "
      f"({_tot(pub, 'restricted_units') / max(_tot(pub), 1) * 100:.0f}%)")
print(f"  ASSUMED {int(PFC_ASSUMED_SHARE * 100)}%              {len(asm):3d} props  "
      f"{_tot(asm, 'restricted_units'):5,} restricted of {_tot(asm):6,} "
      f"-- estimate, flagged in the popup")
if none:
    print(f"  still none               {len(none):3d} props  {_tot(none):6,} total units")
print(f"  LAYER TOTAL                      "
      f"{_tot(pf, 'restricted_units'):5,} restricted of {_tot(pf):6,} total")
