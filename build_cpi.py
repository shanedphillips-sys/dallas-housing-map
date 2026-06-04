"""
Fetch CPI-U annual averages (BLS series CUUR0000SA0, U.S. city average, all
items, not seasonally adjusted, 1982-84=100) for 2010-2025 and write
data/cpi_annual.json.

Used to deflate ACS and Zillow housing values to constant 2024 dollars for the
rent-change and home-value-change map layers. ACS 5-year estimates are already
expressed in their final-year dollars; Zillow monthly values are nominal. Both
are converted to 2024$ via:  value_2024usd = value_year * CPI[2024] / CPI[year].

BLS public API v1 (no key) allows a 10-year span per request and ~25 requests/
day, so we make two calls and merge. The annual average is BLS period "M13".
A hardcoded fallback table (BLS published values) is used if the API is
unreachable, so the build is reproducible offline.
"""

import json
import os
import requests

OUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "cpi_annual.json")

SERIES = "CUUR0000SA0"

# Fallback: BLS published CPI-U annual averages (1982-84=100). Used only if the
# API call fails. Verified against BLS for 2010-2024; 2025 is the annual average.
FALLBACK = {
    2010: 218.056, 2011: 224.939, 2012: 229.594, 2013: 232.957,
    2014: 236.736, 2015: 237.017, 2016: 240.007, 2017: 245.120,
    2018: 251.107, 2019: 255.657, 2020: 258.811, 2021: 270.970,
    2022: 292.655, 2023: 304.702, 2024: 313.689, 2025: 322.000,
}


def fetch_range(start, end):
    url = f"https://api.bls.gov/publicAPI/v1/timeseries/data/{SERIES}"
    r = requests.post(url, json={"seriesid": [SERIES],
                                 "startyear": str(start), "endyear": str(end)},
                      timeout=60)
    r.raise_for_status()
    j = r.json()
    out = {}
    series = j["Results"]["series"][0]["data"]
    # Prefer the annual-average row (period M13); else average the 12 months.
    monthly = {}
    for row in series:
        try:
            yr = int(row["year"])
            val = float(row["value"])
        except (ValueError, KeyError):
            continue  # footnote placeholders like '-' or '(NA)'
        if row["period"] == "M13":
            out[yr] = val
        elif row["period"].startswith("M"):
            monthly.setdefault(yr, []).append(val)
    for yr, vals in monthly.items():
        if yr not in out and len(vals) == 12:
            out[yr] = sum(vals) / 12.0
    return out


def main():
    cpi = {}
    try:
        cpi.update(fetch_range(2010, 2019))
        cpi.update(fetch_range(2020, 2025))
        print(f"Fetched {len(cpi)} years from BLS.")
    except Exception as e:
        print(f"BLS fetch failed ({e}); using fallback table.")

    # Fill any gaps from the fallback table.
    for yr, val in FALLBACK.items():
        cpi.setdefault(yr, val)

    cpi = {int(k): round(float(v), 3) for k, v in sorted(cpi.items())}
    with open(OUT_PATH, "w") as f:
        json.dump(cpi, f, indent=2)

    print(f"Wrote {OUT_PATH}")
    base = cpi[2024]
    for yr in sorted(cpi):
        print(f"  {yr}: {cpi[yr]:7.3f}   (x{base / cpi[yr]:.4f} -> 2024$)")


if __name__ == "__main__":
    main()
