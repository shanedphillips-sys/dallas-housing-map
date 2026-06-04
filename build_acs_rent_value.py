"""
Build tract-level ACS 5-year median GROSS RENT and median HOME VALUE change
layers for the webmap, covering the 7-county region (Dallas + Collin, Denton,
Tarrant, Ellis, Kaufman, Rockwall).

Samples: ACS 5-year 2012 .. 2024 (13 vintages). The webmap's dual-thumb slider
lets the user pick any start/end pair, so we ship every vintage as a per-tract
property and difference them client-side.

Variables
---------
  B25064_001E  median gross rent (renter-occupied, incl. utilities)
  B25077_001E  median value (owner-occupied units)

Tract-boundary harmonization (2010 -> 2020)
-------------------------------------------
ACS 5-year vintages through ~2019 are published on 2010 census tracts; later
vintages are on 2020 tracts. The whole map uses 2020 tracts (data/tracts.geojson),
so pre-2020 values are mapped onto 2020 geometry via the Census 2010<->2020
tract relationship file: each 2020 tract takes the median of its dominant
(largest land-area overlap) 2010 parent. Tract SPLITS (the common case in
fast-growing DFW) inherit the parent median exactly; the rare MERGES take the
area-dominant parent. We don't average medians (medians don't aggregate).

Rather than hardcode the vintage cutoff year, each year is resolved per tract:
if the year provides the 2020 GEOID directly, use it; otherwise fall back to the
dominant 2010 parent's value. The build logs the direct/crosswalk split per year.

Inflation
---------
All dollars are deflated to constant 2024 dollars using CPI-U annual averages
(data/cpi_annual.json):  real_2024 = nominal_year * CPI[2024] / CPI[year].
ACS estimates are already in their final-year dollars, so year Y is deflated by
CPI[2024]/CPI[Y]. The webmap computes both $ change and % change off this real
series, so % change is real growth (inflation stripped).

Caveat: B25077 is top-coded (older vintages cap ~$1,000,001; newer ~$2,000,001),
so a handful of ultra-high-value tracts (e.g., Highland Park) can show an
inflated jump that is partly a cap artifact. Negligible outside a few tracts.

Output: data/acs_rent_value_tracts.geojson
  props per 2020 tract: geoid, plus rent_YYYY / rent_moe_YYYY and val_YYYY /
  val_moe_YYYY for YYYY in 2012..2024 — the estimate AND its margin of error,
  both integers in constant 2024$ (null where ACS has no estimate / MOE).

Reliability: ACS tract medians from small renter/owner samples carry large margins
of error; left in, they produce spurious "changes" (e.g. real-2024$ declines that
are pure sampling noise). Rather than drop them here, we SHIP the estimate + MOE
for every cell and let the webmap apply the rule (MOE/est > 30% ~= 18% CV → render
a gray "no reliable estimate" tract; popups show est ± MOE for both years and flag
exclusions). One source of truth, and a clicked tract can still show its excluded
estimate. ~9% of rent / ~7% of value cells fail the 30% rule. Zillow has no MOE.
"""

import json
import os
import time
import requests

WEBMAP_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(WEBMAP_DIR)
DATA_DIR = os.path.join(WEBMAP_DIR, "data")

TRACTS_GEOJSON = os.path.join(DATA_DIR, "tracts.geojson")
CPI_JSON = os.path.join(DATA_DIR, "cpi_annual.json")
REL_FILE = os.path.join(PROJECT_DIR, "tab20_tract20_tract10_natl.txt")
OUT_PATH = os.path.join(DATA_DIR, "acs_rent_value_tracts.geojson")

API_KEY = os.environ.get("CENSUS_API_KEY", "86cf199069aa31e1593fc7012564f38af501b568")

STATE_FIPS = "48"
COUNTY_FIPS = ["113", "085", "121", "439", "139", "257", "397"]
COUNTY_PREFIXES = {STATE_FIPS + c for c in COUNTY_FIPS}

YEARS = list(range(2012, 2025))   # 2012 .. 2024 inclusive
RENT_VAR,  RENT_MOE  = "B25064_001E", "B25064_001M"
VALUE_VAR, VALUE_MOE = "B25077_001E", "B25077_001M"

# Reliability threshold ENFORCED IN THE WEBMAP (kept here only for the diagnostic
# log + as the canonical value): a tract-year with MOE/estimate > 0.30 (~18% CV),
# or no usable MOE, is treated as unreliable. The frontend grays those tracts and
# flags them in the popup. Keep this in sync with RV_MAX_MOE in app.js.
MAX_MOE_RATIO = 0.30

t0 = time.time()
def log(msg): print(f"[{time.time()-t0:.0f}s] {msg}", flush=True)


def census_get(url):
    last = None
    for attempt in range(4):
        try:
            r = requests.get(url, timeout=120)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last = e
            time.sleep(1.5 * (attempt + 1))
    raise last


def to_val(x):
    """ACS median -> float, or None for jam values / blanks / nonpositive."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if v > 0 else None


def to_moe(x):
    """ACS margin of error -> float >= 0, or None for jam (e.g. -555555555) /
    blanks. A missing MOE means reliability can't be verified -> suppress."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if v >= 0 else None


# ---------------------------------------------------------------------------
# 1. CPI deflators (-> constant 2024$)
# ---------------------------------------------------------------------------
with open(CPI_JSON) as f:
    cpi = {int(k): float(v) for k, v in json.load(f).items()}
base = cpi[2024]
deflator = {y: base / cpi[y] for y in YEARS}
log(f"CPI loaded; deflators 2012={deflator[2012]:.4f} .. 2024={deflator[2024]:.4f}")


# ---------------------------------------------------------------------------
# 2. Pull ACS rent + value for every year x county
#    acs[year][geoid] = {"rent": float|None, "val": float|None}
# ---------------------------------------------------------------------------
acs = {y: {} for y in YEARS}
for year in YEARS:
    n = 0
    for cfips in COUNTY_FIPS:
        url = (f"https://api.census.gov/data/{year}/acs/acs5"
               f"?get={RENT_VAR},{RENT_MOE},{VALUE_VAR},{VALUE_MOE}"
               f"&for=tract:*&in=state:{STATE_FIPS}&in=county:{cfips}&key={API_KEY}")
        j = census_get(url)
        hdr = j[0]
        ri, rmi = hdr.index(RENT_VAR), hdr.index(RENT_MOE)
        vi, vmi = hdr.index(VALUE_VAR), hdr.index(VALUE_MOE)
        si, ci, ti = hdr.index("state"), hdr.index("county"), hdr.index("tract")
        for row in j[1:]:
            geoid = row[si] + row[ci] + row[ti]
            acs[year][geoid] = {"rent": to_val(row[ri]), "rent_m": to_moe(row[rmi]),
                                "val":  to_val(row[vi]), "val_m":  to_moe(row[vmi])}
            n += 1
    log(f"ACS {year}: {n} tract rows")


# ---------------------------------------------------------------------------
# 3. Dominant 2010 parent for each 2020 tract (from relationship file)
# ---------------------------------------------------------------------------
log("Building 2020->2010 dominant-parent map ...")
best = {}   # geoid20 -> (area_part, geoid10)
with open(REL_FILE, encoding="utf-8-sig") as f:
    header = f.readline().rstrip("\n").split("|")
    g20i = header.index("GEOID_TRACT_20")
    g10i = header.index("GEOID_TRACT_10")
    api = header.index("AREALAND_PART")
    for line in f:
        p = line.rstrip("\n").split("|")
        g20 = p[g20i]
        if g20[:5] not in COUNTY_PREFIXES:
            continue
        try:
            area = float(p[api])
        except ValueError:
            area = 0.0
        if g20 not in best or area > best[g20][0]:
            best[g20] = (area, p[g10i])
parent = {g20: g10 for g20, (_, g10) in best.items()}
log(f"  dominant parents for {len(parent)} 2020 tracts")


# ---------------------------------------------------------------------------
# 4. Resolve each year per 2020 tract (direct GEOID else dominant parent),
#    deflate to 2024$.
# ---------------------------------------------------------------------------
def resolve(year, g20):
    """ACS record (rent/val estimates + MOEs) for this 2020 tract in the given
    year — its own GEOID if present, else its dominant 2010 parent's."""
    rec = acs[year].get(g20)                    # 2020-vintage year or unchanged tract
    if rec is None:
        g10 = parent.get(g20)
        rec = acs[year].get(g10) if g10 else None   # pre-2020 vintage
    return rec


# Diagnostic: how many tracts resolve directly vs via crosswalk, per year.
geoids20 = sorted(parent.keys())
for year in YEARS:
    direct = sum(1 for g in geoids20 if g in acs[year])
    log(f"  {year}: {direct}/{len(geoids20)} direct (rest via 2010 parent)")


# Ship the estimate AND its margin of error (both deflated to 2024$) for every
# tract-year. The 30%-MOE reliability decision is applied in the webmap, so the
# gray "no reliable estimate" fill and the popup share one source of truth and a
# clicked tract can still show its excluded estimate ± MOE. MAX_MOE_RATIO only
# drives the diagnostic below here.
props = {}   # geoid20 -> {rent_YYYY, rent_moe_YYYY, val_YYYY, val_moe_YYYY, ...}
have = {"rent": 0, "val": 0}         # tract-years with an estimate
unreliable = {"rent": 0, "val": 0}   # of those, how many fail MOE/est <= 30%
for g20 in geoids20:
    d = {}
    for year in YEARS:
        rec = resolve(year, g20) or {}
        defl = deflator[year]
        for metric, est_k, moe_k in (("rent", "rent", "rent_m"), ("val", "val", "val_m")):
            est, moe = rec.get(est_k), rec.get(moe_k)
            d[f"{metric}_{year}"]     = int(round(est * defl)) if est is not None else None
            d[f"{metric}_moe_{year}"] = int(round(moe * defl)) if moe is not None else None
            if est is not None:
                have[metric] += 1
                if moe is None or (moe / est) > MAX_MOE_RATIO:
                    unreliable[metric] += 1
    props[g20] = d

log(f"Shipping estimate + MOE per cell (real 2024$). Webmap enforces reliability "
    f"at MOE/est > {MAX_MOE_RATIO:.0%}: that flags "
    f"rent {unreliable['rent']}/{have['rent']} ({unreliable['rent']/max(have['rent'],1)*100:.1f}%), "
    f"val {unreliable['val']}/{have['val']} ({unreliable['val']/max(have['val'],1)*100:.1f}%).")


# ---------------------------------------------------------------------------
# 5. Attach to 2020 tract geometry, write GeoJSON (manual, to keep clean nulls)
# ---------------------------------------------------------------------------
log("Loading tract geometry ...")
with open(TRACTS_GEOJSON) as f:
    tracts = json.load(f)

features, with_rent, with_val = [], 0, 0
for feat in tracts["features"]:
    g20 = str(feat["properties"]["geoid"])
    p = props.get(g20)
    if p is None:
        p = {f"rent_{y}": None for y in YEARS}
        p.update({f"val_{y}": None for y in YEARS})
    if p.get(f"rent_{YEARS[-1]}") is not None or p.get(f"rent_{YEARS[0]}") is not None:
        with_rent += 1
    if p.get(f"val_{YEARS[-1]}") is not None or p.get(f"val_{YEARS[0]}") is not None:
        with_val += 1
    features.append({
        "type": "Feature",
        "properties": {"geoid": g20, **p},
        "geometry": feat["geometry"],
    })

out = {"type": "FeatureCollection", "name": "acs_rent_value_tracts",
       "features": features}
with open(OUT_PATH, "w") as f:
    json.dump(out, f)

size_mb = os.path.getsize(OUT_PATH) / 1e6
log(f"Wrote {OUT_PATH}  ({len(features)} tracts, {size_mb:.1f} MB)")
log(f"  tracts with rent (endpoint years): {with_rent}; with value: {with_val}")

# Spot-check a couple of tracts.
for g20 in geoids20[:1] + [g for g in geoids20 if props[g].get("val_2012") and props[g].get("val_2024")][:2]:
    p = props[g20]
    log(f"  e.g. {g20}: rent {p['rent_2012']}->{p['rent_2024']} (2024$), "
        f"val {p['val_2012']}->{p['val_2024']} (2024$)")
log("Done.")
