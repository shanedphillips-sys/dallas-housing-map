"""
Summary of residential zoning districts — multifamily, mixed-use, community-area
(CA), and townhouse/cluster (TH, CH) — by base district (zone_norm), ordered by name.

Columns per zone:
  - Parcels        : all parcels whose centroid falls in the zone (any land use)
  - Land area sqmi : zoning-polygon area (clipped to the city)
  - Total units    : sum of recorded total_units over ALL parcels in the zone
  - Total MF units : total_units over multifamily parcels = MF land-use categories
                     (Duplexes + MF 3-4/5-19/20-49/50+/Apartments) PLUS commercial-
                     coded parcels whose building class is apartment/loft (DCAD codes
                     some apartments "Commercial" — see APARTMENT_CLASSES)
  - MF units 2010+ : same multifamily parcels with year_built >= 2010
  - MF from comm   : apartment units recovered from the Commercial code (a subset of
                     Total MF units — i.e. how many units "moved")

All parcels (DCAD + Collin + Denton); the apartment-class recovery is DCAD-only
(bldg_class is a DCAD field). Senior/assisted-living/nursing classes are NOT counted.
NOTE: DCAD NUM_UNITS on commercial parcels also counts storage lockers, hotel rooms,
office suites, etc., so we include ONLY apartment/loft building classes, never all
commercial units. Writes data/mf_zones_summary.csv.
"""
import os
import re

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

WEB = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(WEB, "data")
SQFT_PER_SQMI = 27_878_400.0
MF_CATS = {"Duplexes", "MF 3-4 Units", "MF 5-19 Units", "MF 20-49 Units",
           "MF 50+ Units", "MF Apartments (Unclassified)"}
# DCAD building classes for apartments coded under the "Commercial" land use
APARTMENT_CLASSES = {"APARTMENT (BRICK EXTERIOR)", "APARTMENT (FRAME EXTERIOR)", "LOFT BUILDING"}
CATEGORIES = ["Multifamily", "Mixed-Use", "Community Area", "Townhouse / Cluster"]
PREFIX_ORDER = {"CA": 0, "CH": 1, "MF": 2, "MU": 3, "TH": 4, "UC": 5, "WMU": 6}


def num(s):
    return pd.to_numeric(s, errors="coerce")


def sort_key(zn):
    m = re.match(r"([A-Za-z]+)-?(\d*)", zn)
    if not m:
        return (99, 0)
    num_part = int(m.group(2)) if m.group(2) else 0
    return (PREFIX_ORDER.get(m.group(1), 99), num_part)


# ---- MF/MU zoning districts: land area per base district --------------------
z = gpd.read_file(os.path.join(DATA, "zoning.geojson"))[["zone_norm", "category", "geometry"]].to_crs(2276)
z["geometry"] = shapely.make_valid(z.geometry.values)
z = z[z.category.isin(CATEGORIES + ["Planned Development"])]   # +PD, broken out at the bottom
city = gpd.read_file(os.path.join(DATA, "city_boundary.geojson")).to_crs(2276)
z = gpd.clip(z, shapely.make_valid(city.geometry.union_all()))
zd = z.dissolve("zone_norm").reset_index()
zd["land_sqmi"] = zd.geometry.area / SQFT_PER_SQMI

# ---- parcels -> zone via centroid ------------------------------------------
p = pd.concat([gpd.read_file(os.path.join(DATA, f"parcels_{q}.geojson"))
               [["land_use_cat", "total_units", "year_built", "bldg_class", "geometry"]]
               for q in ["nw", "ne", "sw", "se"]], ignore_index=True)
p = gpd.GeoDataFrame(p, crs="EPSG:4326").to_crs(2276)
p["total_units"] = num(p.total_units).fillna(0)
p["year_built"] = num(p.year_built)
cent = p.drop(columns="geometry")
cent = gpd.GeoDataFrame(cent, geometry=shapely.centroid(shapely.make_valid(p.geometry.values)), crs=2276)
j = gpd.sjoin(cent, zd[["zone_norm", "geometry"]], predicate="within", how="inner")

# multifamily = MF land-use categories OR a commercial parcel of an apartment/loft class
comm_apt = (j.land_use_cat == "Commercial") & j.bldg_class.isin(APARTMENT_CLASSES)
is_mf = j.land_use_cat.isin(MF_CATS) | comm_apt
j["mf_u"] = np.where(is_mf, j.total_units, 0.0)
j["mf_u_2010"] = np.where(is_mf & (j.year_built >= 2010), j.total_units, 0.0)
j["mf_comm"] = np.where(comm_apt, j.total_units, 0.0)
agg = j.groupby("zone_norm").agg(parcels=("total_units", "size"),
                                 total_units=("total_units", "sum"),
                                 total_mf_units=("mf_u", "sum"),
                                 mf_units_2010plus=("mf_u_2010", "sum"),
                                 mf_from_comm=("mf_comm", "sum"))

out = zd[["zone_norm", "land_sqmi"]].merge(agg, on="zone_norm", how="left").fillna(0)
for c in ["parcels", "total_units", "total_mf_units", "mf_units_2010plus", "mf_from_comm"]:
    out[c] = out[c].astype(int)
out["land_sqmi"] = out["land_sqmi"].round(2)
out = out.rename(columns={"zone_norm": "zone"})[
    ["zone", "parcels", "land_sqmi", "total_units", "total_mf_units", "mf_units_2010plus", "mf_from_comm"]]

# residential districts sorted by name; PD broken out as a comparison row at the bottom
pd_row = out[out.zone == "PD"]
res = out[out.zone != "PD"].sort_values("zone", key=lambda s: s.map(sort_key)).reset_index(drop=True)
total = {"zone": "TOTAL (excl. PD)", "parcels": res.parcels.sum(), "land_sqmi": round(res.land_sqmi.sum(), 2),
         "total_units": res.total_units.sum(), "total_mf_units": res.total_mf_units.sum(),
         "mf_units_2010plus": res.mf_units_2010plus.sum(), "mf_from_comm": res.mf_from_comm.sum()}
final = pd.concat([res, pd.DataFrame([total]), pd_row], ignore_index=True)

final.to_csv(os.path.join(DATA, "mf_zones_summary.csv"), index=False)
pd.set_option("display.width", 200)
print("Residential zoning districts (MF / MU / CA / TH / CH) + PD — summary (all CAD)")
print("MF units now include commercial-coded apartment/loft buildings (mf_from_comm = recovered).\n")
print(final.to_string(index=False))
