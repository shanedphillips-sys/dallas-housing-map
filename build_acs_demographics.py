"""
Tract-level ACS 5-year demographic layers for the webmap (7-county region:
Dallas + Collin, Denton, Tarrant, Ellis, Kaufman, Rockwall). Latest ACS 5-year.
One geojson feeds a single grouped "Demographics" toggle + metric radio.

Metrics per 2020 tract:
  income        B19013_001E  median household income ($)
  renter_pct    B25003_003E / B25003_001E   renter-occupied share (%)
  rent_burden   B25070  renters paying >=30% of income (excl. not-computed) (%)
  poverty_pct   B17001_002E / B17001_001E   (%)
  hisp/white/black/asian_pct  B03002 shares (% Hispanic any race; NH White/Black/Asian)

Joined to data/tracts.geojson by geoid (current ACS is on 2020 tracts -> direct join).
Output: data/acs_demographics_tracts.geojson
"""
import json
import os

import requests

WEB = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(WEB, "data")
API_KEY = os.environ.get("CENSUS_API_KEY", "86cf199069aa31e1593fc7012564f38af501b568")
YEAR = 2024                      # ACS 5-year (2020-2024)
STATE = "48"
COUNTIES = ["113", "085", "121", "439", "139", "257", "397"]
VARS = ["B19013_001E",
        "B25003_001E", "B25003_003E",
        "B25070_001E", "B25070_007E", "B25070_008E", "B25070_009E", "B25070_010E", "B25070_011E",
        "B17001_001E", "B17001_002E",
        "B03002_001E", "B03002_003E", "B03002_004E", "B03002_006E", "B03002_012E"]


def num(v):
    try:
        x = float(v)
        return x if x > -666666660 else None   # ACS missing / jam-value annotation
    except (TypeError, ValueError):
        return None


def pct(n, d):
    n, d = num(n), num(d)
    if n is None or not d or d <= 0:
        return None
    return round(n / d * 100, 1)


acs = {}
for co in COUNTIES:
    r = requests.get(f"https://api.census.gov/data/{YEAR}/acs/acs5",
                     params={"get": ",".join(VARS), "for": "tract:*",
                             "in": f"state:{STATE} county:{co}", "key": API_KEY}, timeout=60)
    r.raise_for_status()
    rows = r.json()
    idx = {h: i for i, h in enumerate(rows[0])}
    for row in rows[1:]:
        g = row[idx["state"]] + row[idx["county"]] + row[idx["tract"]]

        def v(k):
            return row[idx[k]]

        inc = num(v("B19013_001E"))
        rb_num = sum(x for x in (num(v("B25070_007E")), num(v("B25070_008E")),
                                 num(v("B25070_009E")), num(v("B25070_010E"))) if x is not None)
        rb_den = (num(v("B25070_001E")) or 0) - (num(v("B25070_011E")) or 0)
        acs[g] = {
            "income": int(inc) if inc is not None else None,
            "renter_pct": pct(v("B25003_003E"), v("B25003_001E")),
            "rent_burden_pct": round(rb_num / rb_den * 100, 1) if rb_den > 0 else None,
            "poverty_pct": pct(v("B17001_002E"), v("B17001_001E")),
            "hisp_pct": pct(v("B03002_012E"), v("B03002_001E")),
            "white_pct": pct(v("B03002_003E"), v("B03002_001E")),
            "black_pct": pct(v("B03002_004E"), v("B03002_001E")),
            "asian_pct": pct(v("B03002_006E"), v("B03002_001E")),
        }
    print(f"county {co}: {len(rows) - 1} tracts", flush=True)

tracts = json.load(open(os.path.join(DATA, "tracts.geojson")))
feats, matched = [], 0
for f in tracts["features"]:
    g = str(f["properties"]["geoid"])
    m = acs.get(g)
    if m:
        matched += 1
    feats.append({"type": "Feature", "geometry": f["geometry"],
                  "properties": {"geoid": g, **(m or {})}})
op = os.path.join(DATA, "acs_demographics_tracts.geojson")
json.dump({"type": "FeatureCollection", "features": feats}, open(op, "w"), allow_nan=False)
print(f"wrote {op}: {len(feats)} tracts, {matched} with ACS, {os.path.getsize(op) / 1e6:.1f} MB")
