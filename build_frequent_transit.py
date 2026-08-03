"""
DART transit network + frequent-service flag for the webmap, from the DART GTFS feed
(cache/dart_gtfs.zip). A route is "frequent" if, on a typical weekday (monday service),
some direction runs >=6 trips (<= ~20 min average headway) in BOTH the 7-9am and
4-6pm windows. Rail vs bus falls out of the same rule (light rail qualifies; TRE
commuter rail does not).

Output: data/transit_routes.geojson — one feature per route (MultiLineString of its
main-pattern shapes) with: route, name, kind (rail/bus), color, frequent (bool),
hw_am / hw_pm (peak headways, min). The webmap radio filters All vs Frequent-only.
"""
import datetime
import json
import os
import zipfile

import pandas as pd
from shapely.geometry import LineString, MultiLineString, mapping

WEB = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(WEB, "data")
Z = zipfile.ZipFile(os.path.join(WEB, "cache", "dart_gtfs.zip"))
AM, PM, MINTRIPS = (420, 540), (960, 1080), 6   # 7-9am, 4-6pm; >=6 trips/2h = <=20 min


def rd(f):
    return pd.read_csv(Z.open(f), dtype=str)


cal = rd("calendar.txt")
cd = rd("calendar_dates.txt")
# Services active on a representative weekday (first Wednesday in the feed). DART puts
# bus service in calendar.txt but RAIL service in calendar_dates.txt, so resolve by date.
_d = datetime.datetime.strptime(cal.start_date.min(), "%Y%m%d").date()
while _d.weekday() != 2:
    _d += datetime.timedelta(days=1)
_tgt, _wd = _d.strftime("%Y%m%d"), _d.strftime("%A").lower()
weekday = set(cal.loc[(cal.start_date <= _tgt) & (cal.end_date >= _tgt) & (cal[_wd] == "1"), "service_id"])
weekday |= set(cd.loc[(cd.date == _tgt) & (cd.exception_type == "1"), "service_id"])
weekday -= set(cd.loc[(cd.date == _tgt) & (cd.exception_type == "2"), "service_id"])
routes = rd("routes.txt").drop_duplicates("route_id").set_index("route_id")
trips = rd("trips.txt")
trips = trips[trips.service_id.isin(weekday)].copy()
trips["direction_id"] = trips.direction_id.fillna("0")

# trip start time (min after midnight) = earliest departure among its stop_times
st = rd("stop_times.txt")[["trip_id", "departure_time"]].dropna()
st = st[st.trip_id.isin(set(trips.trip_id))]
hm = st.departure_time.str.split(":", expand=True)
st["m"] = pd.to_numeric(hm[0], errors="coerce") * 60 + pd.to_numeric(hm[1], errors="coerce")
st = st.dropna(subset=["m"])
trips["start"] = trips.trip_id.map(st.groupby("trip_id")["m"].min())
trips = trips.dropna(subset=["start"])

# per-route frequency (best direction) + peak headways
freq, hw = {}, {}
for rid, g in trips.groupby("route_id"):
    is_freq, bam, bpm = False, 0, 0
    for _, gd in g.groupby("direction_id"):
        nam = int(((gd.start >= AM[0]) & (gd.start < AM[1])).sum())
        npm = int(((gd.start >= PM[0]) & (gd.start < PM[1])).sum())
        bam, bpm = max(bam, nam), max(bpm, npm)
        if nam >= MINTRIPS and npm >= MINTRIPS:
            is_freq = True
    freq[rid] = is_freq
    hw[rid] = (round(120 / bam) if bam else None, round(120 / bpm) if bpm else None)

# representative shape per (route, direction) -> LineStrings
sh = rd("shapes.txt")
sh["seq"] = pd.to_numeric(sh.shape_pt_sequence, errors="coerce")
sh = sh.dropna(subset=["seq"]).sort_values("seq")
lines = {}
for sid, g in sh.groupby("shape_id"):
    pts = [(round(float(lo), 5), round(float(la), 5)) for lo, la in zip(g.shape_pt_lon, g.shape_pt_lat)]
    if len(pts) >= 2:
        lines[sid] = LineString(pts)

feats = []
for rid, g in trips.groupby("route_id"):
    sids = []
    for _, gd in g.groupby("direction_id"):
        vc = gd.shape_id.value_counts()
        if len(vc):
            sids.append(vc.index[0])
    ls = [lines[s] for s in dict.fromkeys(sids) if s in lines]
    if not ls:
        continue
    geom = ls[0] if len(ls) == 1 else MultiLineString(ls)
    rr = routes.loc[rid] if rid in routes.index else None
    rtype = rr.route_type if rr is not None else "3"
    col = rr.route_color if (rr is not None and pd.notna(rr.route_color)) else None
    feats.append({"type": "Feature", "geometry": mapping(geom), "properties": {
        "route": (rr.route_short_name if rr is not None and pd.notna(rr.route_short_name) else rid),
        "name": (rr.route_long_name if rr is not None and pd.notna(rr.route_long_name) else ""),
        "kind": "rail" if rtype in ("0", "1", "2", "5") else "bus",
        "color": ("#" + col) if col else None,
        "frequent": bool(freq.get(rid, False)),
        "hw_am": hw[rid][0], "hw_pm": hw[rid][1],
        "hw": max(hw[rid][0] or 999, hw[rid][1] or 999),   # worst peak headway, for style tiers
    }})

op = os.path.join(DATA, "transit_routes.geojson")
json.dump({"type": "FeatureCollection", "features": feats}, open(op, "w"), allow_nan=False)
nf = sum(1 for f in feats if f["properties"]["frequent"])
print(f"wrote {op}: {len(feats)} routes ({nf} frequent), {os.path.getsize(op) / 1e6:.1f} MB")
print("frequent:", sorted(f["properties"]["route"] for f in feats if f["properties"]["frequent"]))
