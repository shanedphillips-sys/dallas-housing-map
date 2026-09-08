"""
One-time extract: stream the ~19 GB Denton protax JSON and cache OWNER NAMES + EXEMPTION
codes for every City-of-Dallas parcel in Denton County.

The in-repo Denton slim (denton_dallas_slim.json) carries geometry/value/size but NOT owner
names or exemptions, and the webmap parcel layer's busname/propnam are empty for Denton --
so this stream is the only way to identify who owns the Denton-County part of Dallas.
Written for the faith-based land analysis (build_faith_parcels.py) but deliberately generic:
it caches ALL Dallas-city Denton parcels, not just the ones matching one query.

  stream rec -> situses[0].city == DALLAS
  keep pID + every owner name + any exemption codes + state/use codes + acreage + lon/lat
  -> data/denton_dallas_owners.json  { "<pID>": {owners, exemptions, stateCd, useCd,
                                                  address, acres, lon, lat} }

Rerun only when the Denton source refreshes (~3 min). Read-only over the source.
"""
import json
import os

import ijson

WEB = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(WEB, "data", "denton_dallas_owners.json")
SRC = (r"C:\Users\shane\OneDrive\Documents\Domain Consulting\Projects"
       r"\GDPC - Dallas Housing Report\Denton-protaxExport-20250728.json")


def first(lst):
    return (lst or [{}])[0] if isinstance(lst, list) and lst else {}


def titlecase(s):
    return " ".join(w.capitalize() if not w.isdigit() else w for w in (s or "").split())


def rep_point(geom):
    # Denton protax stores geometry as a stringified WGS84 "[lat, lon]" point.
    try:
        arr = json.loads(geom) if isinstance(geom, str) else geom
        while isinstance(arr, list) and arr and isinstance(arr[0], list):
            arr = arr[0]
        if isinstance(arr, list) and len(arr) >= 2:
            lat, lon = float(arr[0]), float(arr[1])
            if -180 <= lon <= 180 and -90 <= lat <= 90:
                return round(lon, 6), round(lat, 6)
    except Exception:
        pass
    return None, None


def find_exemptions(rec):
    """The protax schema's exemption field name isn't documented here, so collect any
    key containing 'exempt' from the record and its first-level list/dict children."""
    out = []

    def scan(d, depth=0):
        if not isinstance(d, dict) or depth > 2:
            return
        for k, v in d.items():
            if "exempt" in k.lower() and v not in (None, "", [], {}):
                out.append(f"{k}={v}" if not isinstance(v, (list, dict)) else f"{k}={json.dumps(v, default=str)[:200]}")
            elif isinstance(v, dict):
                scan(v, depth + 1)
            elif isinstance(v, list) and v and isinstance(v[0], dict):
                scan(v[0], depth + 1)

    scan(rec)
    return out


hits = {}
n_total = n_dallas = 0
dumped = False
with open(SRC, "rb") as f:
    for rec in ijson.items(f, "item"):
        n_total += 1
        if n_total % 100000 == 0:
            print(f"  scanned {n_total:,} ({n_dallas:,} Dallas)", flush=True)
        situses = rec.get("situses") or []
        city = (situses[0].get("city") if situses else "") or ""
        if city.upper() != "DALLAS":
            continue
        n_dallas += 1

        if not dumped:                      # one-time schema diagnostic
            print("--- first Dallas record: top-level keys ---", flush=True)
            print(sorted(rec.keys()), flush=True)
            for key in ("propertyProfile", "propertyCharacteristics", "owners"):
                sub = first(rec.get(key))
                print(f"  {key}[0] keys: {sorted(sub.keys()) if sub else None}", flush=True)
            dumped = True

        owners = rec.get("owners") or []
        onames = [" ".join(x for x in [(o.get("name") or ""), (o.get("nameSecondary") or "")] if x).strip()
                  for o in owners]
        prof = first(rec.get("propertyProfile"))
        chars = first(rec.get("propertyCharacteristics"))
        s = situses[0]
        addr = " ".join(str(x).strip() for x in [s.get("streetNum"), s.get("streetPrefix"),
                        titlecase(s.get("streetName")), s.get("streetSuffix")] if x and str(x).strip())
        lon, lat = rep_point(rec.get("geometry"))
        acres = prof.get("landSizeAcres") or prof.get("legalAcreage")
        try:
            acres = float(acres) if acres not in (None, "") else None
        except (TypeError, ValueError):
            acres = None
        hits[str(rec.get("pID"))] = {
            "owners": [o for o in onames if o],
            "exemptions": find_exemptions(rec),
            "stateCd": (prof.get("stateCd") or prof.get("imprvStateCd") or ""),
            "useCd": (chars.get("useCd") or ""),
            "address": titlecase(addr),
            "acres": acres,
            "lon": lon, "lat": lat,
        }

json.dump(hits, open(OUT, "w"), indent=1, default=str)
print(f"\nDone. Scanned {n_total:,} records; {n_dallas:,} Dallas-city Denton parcels -> {OUT}")
ex = sum(1 for v in hits.values() if v["exemptions"])
print(f"  with any exemption field populated: {ex}")
