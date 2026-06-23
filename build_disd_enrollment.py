"""
Dallas ISD (county-district 057905) campus-level enrollment for the full decade
SY2015-16 -> 2025-26, joined to neighborhood INCOME (ACS) and OPPORTUNITY
(Opportunity Atlas / Chetty upward mobility), to surface the campuses that LOST
enrollment while sitting in higher-income AND higher-opportunity tracts.

ENROLLMENT -- one consistent backbone + the current-year tail
-------------------------------------------------------------
  SY2015-16 .. 2024-25 : NCES Common Core of Data via the Urban Institute
    Education Data API (schools/ccd/directory). One row per campus per year with
    total enrollment + lat/long + the TEA 9-digit campus id (in `seasch`, format
    "057905-057905212"). Urban "year" = fall of the school year, so year 2015 =
    SY2015-16 .. year 2024 = SY2024-25.
  SY2025-26 : TEA PEIMS ad-hoc broker (the ONLY machine source for the current
    year). Long-format by grade -> summed to campus totals. The broker is
    intermittently down server-side; if unreachable the build proceeds without
    2025-26 and logs it.

  We deliberately use CCD as the single backbone (rather than TEA's ArcGIS
  "Schools <year>" layers) because the ArcGIS layers have per-year schema and
  year-label drift -- they agree with CCD on the overlap years but are messier.
  ArcGIS IS still queried once for nicer grade-range / school-type / MAGNET flags,
  joined by campus id, so magnet/choice campuses can be filtered out.

NEIGHBORHOOD JOINS  (campus point -> 2020 census tract via data/tracts.geojson)
------------------------------------------------------------------------------
  Income      : ACS 5-yr median household income B19013_001E (7 counties).
  Opportunity : Opportunity Atlas kfr_pooled_pooled_p25 -- mean adult household-
    income RANK (0-1) for children who grew up in the tract with parents at the
    25th income percentile, pooled race/gender. Higher = more upward mobility.
    The Atlas is on 2010 tracts, so each 2020 tract takes its dominant (largest
    land-area overlap) 2010 parent's value via tab20_tract20_tract10_natl.txt --
    the same harmonization data/acs_rent_value_tracts uses.

CAVEATS (kept with the data so they are not forgotten)
------------------------------------------------------
  - tract_mhi / tract_opp describe the neighborhood of the school BUILDING. Fair
    for neighborhood schools; for MAGNET/choice campuses (see `magnet`) the
    building tract is NOT the student catchment.
  - Atlas cohorts grew up in the 1980s-90s: it measures the neighborhood's long-run
    child-outcome quality, not present-day affluence (that is tract_mhi).
  - 2025-26 broker totals sum unmasked grade cells; a few small-grade cells are
    FERPA-masked, so a handful of campuses undercount slightly (~0.8% district-wide).

OUTPUT: data/disd_enrollment.json + .csv  (per campus: enr_2016..enr_2026, change
metrics, tract, tract_mhi, tract_opp, magnet/grade/type) and prints the
lost-enrollment x higher-income x higher-opportunity shortlist.
"""
import csv
import io
import json
import os
import time

import geopandas as gpd
import requests
from shapely.geometry import Point

WEB = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(WEB)
DATA = os.path.join(WEB, "data")
CACHE = os.path.join(WEB, "cache")
os.makedirs(CACHE, exist_ok=True)
KEY = os.environ.get("CENSUS_API_KEY", "86cf199069aa31e1593fc7012564f38af501b568")

DISD = "057905"
DISD_LEAID = "4816230"                         # DISD NCES LEAID (for the CCD API)
COUNTIES = ["113", "085", "121", "439", "139", "257", "397"]
COUNTY_PREFIXES = {"48" + c for c in COUNTIES}
REL_FILE = os.path.join(PARENT, "tab20_tract20_tract10_natl.txt")
ATLAS_URL = "https://opportunityinsights.org/wp-content/uploads/2024/08/tract_outcomes_late_simple.csv"
ATLAS_CSV = os.path.join(CACHE, "tract_outcomes_late_simple.csv")
ORG = "https://services2.arcgis.com/5MVN2jsqIrNZD4tP/arcgis/rest/services"

CCD_YEARS = list(range(2015, 2025))            # fall 2015 .. 2024  == SY2015-16 .. 2024-25
YEARS = list(range(2016, 2027))                # SY end-years 2016 .. 2026 (columns)

S = requests.Session()
S.headers["User-Agent"] = "Mozilla/5.0"
t0 = time.time()
def log(m): print(f"[{time.time()-t0:4.0f}s] {m}", flush=True)


def jget(url, **params):
    for attempt in range(4):
        try:
            r = S.get(url, params=params or None, timeout=120)
            r.raise_for_status()
            return r.json()
        except Exception:
            if attempt == 3:
                raise
            time.sleep(2 * (attempt + 1))


# --------------------------------------------------------------------------- #
# 1. Enrollment backbone: NCES CCD via Urban Institute (SY2015-16 .. 2024-25)
# --------------------------------------------------------------------------- #
def ccd_year(year):
    """{tea_campus_id: {enr,lat,lon,name,level}} for DISD in a given CCD fall year."""
    out = {}
    url = f"https://educationdata.urban.org/api/v1/schools/ccd/directory/{year}/"
    params = {"leaid": DISD_LEAID}
    while url:
        j = jget(url, **(params or {}))
        for a in j.get("results", []):
            sea = (a.get("seasch") or "").strip()
            tea = sea.split("-")[-1] if sea else ""
            if len(tea) != 9 or not tea.startswith(DISD):
                continue
            try:
                enr = int(a.get("enrollment"))
                if enr < 0:
                    enr = None
            except (TypeError, ValueError):
                enr = None
            out[tea] = {"enr": enr, "lat": a.get("latitude"), "lon": a.get("longitude"),
                        "name": a.get("school_name"), "level": a.get("school_level")}
        url = j.get("next")          # full URL incl. querystring; drop params when paging
        params = None
    return out


# --------------------------------------------------------------------------- #
# 2. Current year tail: TEA PEIMS broker (SY2025-26), grade rows -> campus totals
# --------------------------------------------------------------------------- #
def broker_2026():
    url = ("https://rptsvr1.tea.texas.gov/cgi/sas/broker?_service=marykay"
           "&_program=adhoc.addispatch.sas&endyear=26&major=st&minor=e&format=c"
           "&selsumm=ic&linespg=60&charsln=120&grouping=g&loop=2&key=" + DISD + "&_debug=0")
    try:
        txt = S.get(url, timeout=90).text
    except Exception as e:
        log(f"  2025-26 broker: request failed ({e}) -> skipping current year")
        return {}, {}
    if "Error connecting to the SAS server" in txt or '"YEAR"' not in txt:
        log("  2025-26 broker: service down / no CSV -> skipping current year")
        return {}, {}
    lines = txt.splitlines()
    hi = next(i for i, l in enumerate(lines) if l.startswith('"YEAR"'))
    rdr = csv.DictReader(io.StringIO("\n".join(lines[hi:])))
    tot, name = {}, {}
    for row in rdr:
        camp = (row.get("CAMPUS") or "").strip()
        if not camp.startswith(DISD):
            continue
        try:
            e = int(row.get("ENROLLMENT"))
        except (TypeError, ValueError):
            continue
        if e < 0:                                  # -999 FERPA mask
            continue
        tot[camp] = tot.get(camp, 0) + e
        name.setdefault(camp, (row.get("CAMPUS NAME") or "").strip())
    return tot, name


# --------------------------------------------------------------------------- #
# 3. Neighborhood measures
# --------------------------------------------------------------------------- #
def acs_income():
    """{geoid20: median household income}; tries recent ACS 5-yr vintages."""
    for vintage in (2023, 2022, 2021):
        mhi, ok = {}, True
        for c in COUNTIES:
            url = (f"https://api.census.gov/data/{vintage}/acs/acs5?get=B19013_001E"
                   f"&for=tract:*&in=state:48&in=county:{c}&key={KEY}")
            try:
                rows = requests.get(url, timeout=120).json()
            except Exception:
                ok = False
                break
            for row in rows[1:]:
                try:
                    v = float(row[0])
                except (TypeError, ValueError):
                    v = None
                mhi[row[1] + row[2] + row[3]] = int(v) if (v and v > 0) else None
        if ok and mhi:
            return mhi, vintage
    return {}, None


def parent_2010():
    """{geoid20: dominant 2010 parent geoid} for the 7 counties (largest land overlap)."""
    best = {}
    with open(REL_FILE, encoding="utf-8-sig") as f:
        h = f.readline().rstrip("\n").split("|")
        g20i, g10i, ai = h.index("GEOID_TRACT_20"), h.index("GEOID_TRACT_10"), h.index("AREALAND_PART")
        for line in f:
            p = line.rstrip("\n").split("|")
            g20 = p[g20i]
            if g20[:5] not in COUNTY_PREFIXES:
                continue
            try:
                area = float(p[ai])
            except ValueError:
                area = 0.0
            if g20 not in best or area > best[g20][0]:
                best[g20] = (area, p[g10i])
    return {g: g10 for g, (_, g10) in best.items()}


def opportunity_atlas():
    """{geoid10: kfr_pooled_pooled_p25} for the 7 counties (Opportunity Atlas)."""
    if not os.path.exists(ATLAS_CSV):
        log("  downloading Opportunity Atlas tract file ...")
        with S.get(ATLAS_URL, timeout=300, stream=True) as r:
            r.raise_for_status()
            with open(ATLAS_CSV, "wb") as f:
                for chunk in r.iter_content(1 << 20):
                    f.write(chunk)
    atlas = {}
    with open(ATLAS_CSV, newline="") as f:
        for row in csv.DictReader(f):
            try:
                st, co, tr = int(row["state"]), int(row["county"]), int(row["tract"])
            except (TypeError, ValueError):
                continue
            if st != 48 or f"{co:03d}" not in COUNTIES:
                continue
            try:
                atlas[f"{st:02d}{co:03d}{tr:06d}"] = float(row["kfr_pooled_pooled_p25"])
            except (TypeError, ValueError):
                pass
    return atlas


def arcgis_meta():
    """{tea_id: {grade,type,magnet,instr}} from the two most recent ArcGIS layers."""
    meta = {}
    for svc in ("Schools_2023_to_2024", "Schools_2024_to_2025"):   # later overwrites
        base = f"{ORG}/{svc}/FeatureServer/0/query"
        try:
            j = jget(base, where="USER_School_Number LIKE '%57905%'",
                     outFields="USER_School_Number,USER_Grade_Range,School_Type,"
                               "USER_Magnet_Status,USER_Instruction_Type",
                     returnGeometry="false", f="json")
        except Exception:
            continue
        for ft in j.get("features", []):
            a = ft["attributes"]
            cid = str(a.get("USER_School_Number", "")).lstrip("'").strip()[:9]
            if not cid.startswith(DISD):
                continue
            meta[cid] = {
                "grade": (a.get("USER_Grade_Range") or "").lstrip("'").strip(),
                "type": (a.get("School_Type") or "").strip(),
                "magnet": (a.get("USER_Magnet_Status") or "").strip(),
                "instr": (a.get("USER_Instruction_Type") or "").strip(),
            }
    return meta


# --------------------------------------------------------------------------- #
# 4. Assemble
# --------------------------------------------------------------------------- #
def main():
    log("CCD enrollment (Urban Institute), SY2015-16 .. 2024-25 ...")
    ccd = {}
    for y in CCD_YEARS:
        ccd[y] = ccd_year(y)
        tot = sum(v["enr"] for v in ccd[y].values() if v["enr"])
        log(f"  CCD {y} (SY{y}-{(y+1)%100:02d}): {len(ccd[y])} campuses, total {tot:,}")

    log("TEA broker, SY2025-26 ...")
    br_tot, br_name = broker_2026()
    if br_tot:
        log(f"  2025-26: {len(br_tot)} campuses, total {sum(br_tot.values()):,}")

    # master campus list + per-year series keyed on SY end-year
    campuses = {}
    for y in CCD_YEARS:
        end = y + 1
        for cid, d in ccd[y].items():
            rec = campuses.setdefault(cid, {"enr": {}, "name": "", "lat": None, "lon": None, "level": None})
            if d["enr"] is not None:
                rec["enr"][end] = d["enr"]
            if d["name"]:
                rec["name"] = d["name"]
            if d["lat"] and d["lon"]:
                rec["lat"], rec["lon"] = d["lat"], d["lon"]
            if d["level"] is not None:
                rec["level"] = d["level"]
    for cid, e in br_tot.items():
        rec = campuses.setdefault(cid, {"enr": {}, "name": "", "lat": None, "lon": None, "level": None})
        rec["enr"][2026] = e
        if not rec["name"]:
            rec["name"] = br_name.get(cid, "")
    log(f"\n{len(campuses)} distinct DISD campuses across SY2015-16 .. 2025-26")

    # campus point -> 2020 tract
    tracts = gpd.read_file(os.path.join(DATA, "tracts.geojson"))[["geoid", "geometry"]].to_crs(4326)
    ids = [c for c, r in campuses.items() if r["lon"]]
    pts = gpd.GeoDataFrame({"campus": ids},
                           geometry=[Point(campuses[c]["lon"], campuses[c]["lat"]) for c in ids], crs=4326)
    sj = gpd.sjoin(pts, tracts, predicate="within", how="left")
    tof = dict(zip(sj["campus"], sj["geoid"]))
    log(f"geocoded {len(ids)}/{len(campuses)} campuses; "
        f"{sum(1 for v in tof.values() if isinstance(v, str))} fell in a tract")

    # neighborhood joins
    mhi, vintage = acs_income()
    log(f"ACS {vintage} median household income: {len(mhi)} tracts")
    atlas10 = opportunity_atlas()
    parent = parent_2010()
    atlas20 = {g20: atlas10.get(parent.get(g20)) for g20 in parent}
    log(f"Opportunity Atlas kfr_pooled_pooled_p25: {len(atlas10)} 2010 tracts "
        f"-> {sum(1 for v in atlas20.values() if v is not None)} 2020 tracts via crosswalk")
    meta = arcgis_meta()
    log(f"ArcGIS metadata (grade/type/magnet): {len(meta)} campuses")

    # build rows + change metrics
    out = []
    for cid, rec in campuses.items():
        geoid = tof.get(cid)
        geoid = geoid if isinstance(geoid, str) else None
        m = meta.get(cid, {})
        row = {
            "campus": cid, "name": rec["name"], "grade": m.get("grade", ""),
            "type": m.get("type", ""), "magnet": m.get("magnet", ""),
            "lon": rec["lon"], "lat": rec["lat"], "tract": geoid,
            "tract_mhi": mhi.get(geoid) if geoid else None,
            "tract_opp": round(atlas20.get(geoid), 4) if geoid and atlas20.get(geoid) is not None else None,
            "open_2026": 2026 in rec["enr"],     # False -> closed or renumbered (new campus id)
        }
        for y in YEARS:
            row[f"enr_{y}"] = rec["enr"].get(y)
        s = rec["enr"]
        if s:
            ys = sorted(s)
            f_, l_ = ys[0], ys[-1]
            pk = max(s, key=s.get)
            row.update({"first_year": f_, "last_year": l_, "enr_first": s[f_], "enr_last": s[l_],
                        "change": s[l_] - s[f_],
                        "pct": round(100 * (s[l_] - s[f_]) / s[f_], 1) if s[f_] else None,
                        "peak_year": pk, "peak_enr": s[pk], "peak_to_last": s[l_] - s[pk]})
        out.append(row)

    out.sort(key=lambda r: r.get("change") if r.get("change") is not None else 0)
    json.dump(out, open(os.path.join(DATA, "disd_enrollment.json"), "w"))
    cols = (["campus", "name", "grade", "type", "magnet", "open_2026", "tract", "tract_mhi", "tract_opp"]
            + [f"enr_{y}" for y in YEARS]
            + ["first_year", "last_year", "enr_first", "enr_last", "change", "pct",
               "peak_year", "peak_enr", "peak_to_last", "lon", "lat"])
    with open(os.path.join(DATA, "disd_enrollment.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(out)
    log(f"Wrote data/disd_enrollment.json + .csv ({len(out)} campuses)")

    # district trajectory + cross-check
    tot = {y: sum(r[f"enr_{y}"] for r in out if r.get(f"enr_{y}")) for y in YEARS}
    log("District totals by SY end-year: "
        + "  ".join(f"{y}:{tot[y]//1000}k" for y in YEARS if tot[y]))

    # --- headline: lost enrollment x higher-income x higher-opportunity ---
    incs = sorted(r["tract_mhi"] for r in out if r.get("tract_mhi"))
    opps = sorted(r["tract_opp"] for r in out if r.get("tract_opp") is not None)
    if incs and opps:
        inc_cut = incs[int(0.75 * len(incs))]
        opp_cut = opps[int(0.75 * len(opps))]
        log(f"\nHigher-income  = tract MHI >= ${inc_cut:,} (top quartile of DISD-campus tracts)")
        log(f"Higher-opportunity = Atlas kfr_p25 >= {opp_cut:.3f} (top quartile; natl avg ~0.43)")
        both = [r for r in out if r.get("change") is not None and r["change"] < 0
                and r.get("tract_mhi") and r["tract_mhi"] >= inc_cut
                and r.get("tract_opp") is not None and r["tract_opp"] >= opp_cut]
        both.sort(key=lambda r: r["change"])
        print(f"\n{len(both)} campuses LOST enrollment AND are in BOTH a higher-income "
              f"AND higher-opportunity tract  (M=magnet, X=closed/renumbered before 2025-26):\n")
        print(f"  {'campus':9} {'name':32} {'MHI':>5} {'opp':>5} {'fl':>2}  series(first->last)     chg")
        for r in both:
            fl = ("M" if r["magnet"] == "Y" else "") + ("" if r["open_2026"] else "X")
            print(f"  {r['campus']:9} {r['name'][:32]:32} ${r['tract_mhi']//1000:>3}k "
                  f"{r['tract_opp']:.2f} {fl:>2}  {r['first_year']}:{r['enr_first']:<5}->"
                  f"{r['last_year']}:{r['enr_last']:<5} {r['change']:>6} ({r['pct']}%)")


if __name__ == "__main__":
    main()
