"""
One-time extract: stream the ~19 GB Denton protax JSON and cache the City-of-Dallas
parcels owned by a PFC / HFC (owner-name match), for the Subsidized-housing PFC/HFC map
layer. The in-repo Denton slim (denton_dallas_slim.json) omits owner names, so this is the
only way to identify PFC/HFC ownership in the Denton-County part of Dallas.

  stream rec -> situses[0].city == DALLAS  AND  any owners[].name/nameSecondary is PFC/HFC
  keep pID + owner + address + units + year + state/use codes + a representative lon/lat
        (from the record's own geometry, so parcels missing from the webmap still locate)
  -> data/denton_pfc_hfc.json  { "<pID>": {name,address,owner,total_units,year_built,
                                            acquired,lihtc,stateCd,useCd,lon,lat} }

build_pfc_hfc_points.py reads this cache: it locates each via the DEN-<pID> webmap parcel,
falling back to the cached lon/lat for parcels the webmap doesn't have. Rerun only when the
Denton source refreshes. Read-only.
"""
import json
import os
import re

import ijson

WEB = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(WEB, "data", "denton_pfc_hfc.json")
SRC = (r"C:\Users\shane\OneDrive\Documents\Domain Consulting\Projects"
       r"\GDPC - Dallas Housing Report\Denton-protaxExport-20250728.json")
PFC_RE = ("HOUSING FINANCE", "PUBLIC FACILIT")


def first(lst):
    return (lst or [{}])[0] if isinstance(lst, list) and lst else {}


def titlecase(s):
    return " ".join(w.capitalize() if not w.isdigit() else w for w in (s or "").split())


def rep_point(geom):
    # Denton protax stores geometry as a stringified WGS84 "[lat, lon]" point.
    try:
        arr = json.loads(geom) if isinstance(geom, str) else geom
        while isinstance(arr, list) and arr and isinstance(arr[0], list):
            arr = arr[0]                              # descend into a ring, if any
        if isinstance(arr, list) and len(arr) >= 2:
            lat, lon = float(arr[0]), float(arr[1])
            if -180 <= lon <= 180 and -90 <= lat <= 90:
                return round(lon, 6), round(lat, 6)
    except Exception:
        pass
    return None, None


def prof_units(profiles):
    best = 0
    for p in profiles or []:
        u = p.get("imprvUnits")
        try:
            u = int(float(u)) if u not in (None, "") else 0
        except (TypeError, ValueError):
            u = 0
        best = max(best, u)
    return best


hits = {}
n_total = n_dallas = 0
with open(SRC, "rb") as f:
    for rec in ijson.items(f, "item"):
        n_total += 1
        if n_total % 100000 == 0:
            print(f"  scanned {n_total:,} ({n_dallas:,} Dallas, {len(hits)} PFC/HFC)", flush=True)
        situses = rec.get("situses") or []
        city = (situses[0].get("city") if situses else "") or ""
        if city.upper() != "DALLAS":
            continue
        n_dallas += 1
        owners = rec.get("owners") or []
        onames = [((o.get("name") or "") + " " + (o.get("nameSecondary") or "")).upper() for o in owners]
        if not any(any(k in nm for k in PFC_RE) for nm in onames):
            continue

        profiles = rec.get("propertyProfile") or []
        prof = first(profiles)
        chars = first(rec.get("propertyCharacteristics"))
        s = situses[0]
        addr = " ".join(str(x).strip() for x in [s.get("streetNum"), s.get("streetPrefix"),
                        titlecase(s.get("streetName")), s.get("streetSuffix")] if x and str(x).strip())
        owner = next((o.get("name") for o, nm in zip(owners, onames)
                      if any(k in nm for k in PFC_RE)), owners[0].get("name") if owners else "")
        yb = prof.get("imprvActualYearBuilt") or prof.get("imprvEffYearBuilt")
        try:
            yb = int(yb) if yb and int(yb) > 1850 else None
        except (TypeError, ValueError):
            yb = None
        legal = str(first(rec.get("propertyLegalDescription")).get("legalDescription") or "")
        lon, lat = rep_point(rec.get("geometry"))
        hits[str(rec.get("pID"))] = {
            "name": titlecase(addr) or titlecase(owner),
            "address": titlecase(addr),
            "owner": titlecase(owner),
            "total_units": prof_units(profiles),
            "year_built": yb,
            "acquired": None,
            "lihtc": "TDHCA" in (legal.upper() + " " + " ".join(onames)),
            "stateCd": (prof.get("stateCd") or prof.get("imprvStateCd") or ""),
            "useCd": (chars.get("useCd") or ""),
            "lon": lon, "lat": lat,
        }
        # diagnostic: dump per-building units for each hit
        print(f"  HIT pID={rec.get('pID')} owner={owner!r} addr={addr!r} "
              f"profiles={len(profiles)} units_per_profile="
              f"{[p.get('imprvUnits') for p in profiles]} yr={yb} lonlat=({lon},{lat})", flush=True)

json.dump(hits, open(OUT, "w"), indent=1)
print(f"\nDone. Scanned {n_total:,} records; {n_dallas:,} Dallas; "
      f"{len(hits)} PFC/HFC-owned Dallas parcels -> {OUT}")
