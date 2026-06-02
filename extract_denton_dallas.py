"""
Stream the Denton CAD protax export (~19 GB JSON array of property records)
and extract a slim file containing only City-of-Dallas records, with just
the fields we need for the webmap. Avoids ever loading the full file.
"""
import ijson, json, os
from decimal import Decimal

class DecimalEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, Decimal):
            return float(o)
        return super().default(o)

SRC = r"C:\Users\shane\OneDrive\Documents\Domain Consulting\Projects\GDPC - Dallas Housing Report\Denton-protaxExport-20250728.json"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "denton_dallas_slim.json")

KEEP = []
n_total = 0
n_kept = 0

def first(lst):
    return (lst or [{}])[0] if isinstance(lst, list) else {}

with open(SRC, "rb") as f:
    for rec in ijson.items(f, "item"):
        n_total += 1
        situses = rec.get("situses") or []
        city = (situses[0].get("city") if situses else None) or ""
        if city.upper() != "DALLAS":
            if n_total % 100000 == 0:
                print(f"  scanned {n_total:,} ({n_kept:,} Dallas so far)", flush=True)
            continue

        # Pull the bits we need
        pid_info = first(rec.get("propertyIdentification"))
        prof     = first(rec.get("propertyProfile"))
        chars    = first(rec.get("propertyCharacteristics"))
        legal    = first(rec.get("propertyLegalDescription"))
        s        = situses[0]

        # Values: protax export stores appraised values in a "valuations"
        # array. Prefer the entry flagged isPrimary; fall back to the first.
        vlist = rec.get("valuations") or []
        v = None
        for vv in vlist:
            if vv.get("isPrimary"):
                v = vv; break
        if v is None and vlist:
            v = vlist[0]
        v = v or {}

        KEEP.append({
            "pID":         rec.get("pID"),
            "refID1":      pid_info.get("refID1"),
            "refID2":      pid_info.get("refID2"),
            "geoID":       pid_info.get("geoID"),
            "geometry":    rec.get("geometry"),
            "city":        s.get("city"),
            "streetNum":   s.get("streetNum"),
            "streetPrefix":s.get("streetPrefix"),
            "streetName":  s.get("streetName"),
            "streetSuffix":s.get("streetSuffix"),
            "zip":         s.get("zip"),
            "stateCd":     prof.get("stateCd"),
            "imprvStateCd":prof.get("imprvStateCd"),
            "landStateCd": prof.get("landStateCd"),
            "imprvClass":  prof.get("imprvClass"),
            "imprvActualYearBuilt": prof.get("imprvActualYearBuilt"),
            "imprvEffYearBuilt":    prof.get("imprvEffYearBuilt"),
            "imprvMainArea":        prof.get("imprvMainArea"),
            "imprvTotalArea":       prof.get("imprvTotalArea"),
            "imprvUnits":           prof.get("imprvUnits"),
            "landSizeAcres":        prof.get("landSizeAcres"),
            "landSizeSqft":         prof.get("landSizeSqft"),
            "legalAcreage":         legal.get("legalAcreage"),
            "subType":              chars.get("subType"),
            "useCd":                chars.get("useCd"),
            "zoning":               chars.get("zoning"),
            "valMarket":    v.get("value"),
            "valLand":      v.get("landValue"),
            "valStructure": v.get("structureValue"),
            "valImprHS":    v.get("improvementHSValue"),
            "valImprNHS":   v.get("improvementNHSValue"),
            "valuationType":v.get("valueType"),
        })
        n_kept += 1
        if n_total % 100000 == 0:
            print(f"  scanned {n_total:,} ({n_kept:,} Dallas so far)", flush=True)

print(f"\nDone. Scanned {n_total:,} records; kept {n_kept:,} Dallas records.")
with open(OUT, "w", encoding="utf-8") as f:
    json.dump(KEEP, f, cls=DecimalEncoder)
print(f"Wrote {OUT}")
