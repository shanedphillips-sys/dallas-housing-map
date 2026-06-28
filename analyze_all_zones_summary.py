"""
Summary of EVERY base zoning district in the City of Dallas (zone_norm — (A)/(SAH)
parentheticals merged), grouped by category (PD first, then SF / MF / TH / Mixed-Use,
then the rest), ordered logically within each (SF by lot size, MF/TH/MU by intensity;
the CA districts fold into Mixed-Use; other categories largest-area first).

Columns: category, zone, parcels, land area (sq mi), total units, total MF units,
MF units built 2010+. Total MF units = MF land-use categories (Duplexes + MF 3-4/
5-19/20-49/50+/Apartments) PLUS commercial-coded apartment/loft buildings (DCAD
bldg_class; senior housing excluded). All parcels (DCAD + Collin + Denton); the
commercial-apartment recovery is DCAD-only. Writes data/all_zones_summary.csv.
"""
import os

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

WEB = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(WEB, "data")
SQFT_PER_SQMI = 27_878_400.0
MF_CATS = {"Duplexes", "MF 3-4 Units", "MF 5-19 Units", "MF 20-49 Units",
           "MF 50+ Units", "MF Apartments (Unclassified)"}
APARTMENT_CLASSES = {"APARTMENT (BRICK EXTERIOR)", "APARTMENT (FRAME EXTERIOR)", "LOFT BUILDING"}
CAT_ORDER = ["Planned Development", "Single-Family", "Multifamily", "Townhouse / Cluster",
             "Mixed-Use", "Commercial", "Industrial", "Conservation District", "Other"]
# explicit within-category order for the residential families; other categories fall
# back to largest-area-first. CA-1/CA-2 are folded into Mixed-Use (see below).
ZONE_ORDER = {
    "Single-Family": ["R-5", "R-7.5", "R-10", "R-13", "R-16", "R-1/2ac", "R-1ac", "A", "D", "MH"],
    "Multifamily": ["MF-1", "MF-2", "MF-3", "MF-4"],
    "Townhouse / Cluster": ["TH-1", "TH-2", "TH-3", "CH"],
    "Mixed-Use": ["MU-1", "MU-2", "MU-3", "CA-1", "CA-2", "UC-2", "WMU-3", "WMU-5", "WMU-8"],
}


def num(s):
    return pd.to_numeric(s, errors="coerce")


def within_rank(cat, zone):
    order = ZONE_ORDER.get(cat, [])
    return order.index(zone) if zone in order else 999


# ---- every base zoning district: land area + category ----------------------
z = gpd.read_file(os.path.join(DATA, "zoning.geojson"))[["zone_norm", "category", "geometry"]].to_crs(2276)
z["geometry"] = shapely.make_valid(z.geometry.values)
z["category"] = z["category"].fillna("Other")
city = gpd.read_file(os.path.join(DATA, "city_boundary.geojson")).to_crs(2276)
z = gpd.clip(z, shapely.make_valid(city.geometry.union_all()))
cat_of = z.groupby("zone_norm").category.agg(lambda s: s.value_counts().idxmax())
zd = z.dissolve("zone_norm").reset_index()
zd["land_sqmi"] = zd.geometry.area / SQFT_PER_SQMI

# ---- parcels -> zone via centroid; multifamily incl. commercial apartments ---
p = pd.concat([gpd.read_file(os.path.join(DATA, f"parcels_{q}.geojson"))
               [["land_use_cat", "total_units", "year_built", "bldg_class", "geometry"]]
               for q in ["nw", "ne", "sw", "se"]], ignore_index=True)
p = gpd.GeoDataFrame(p, crs="EPSG:4326").to_crs(2276)
p["total_units"] = num(p.total_units).fillna(0)
p["year_built"] = num(p.year_built)
cent = p.drop(columns="geometry")
cent = gpd.GeoDataFrame(cent, geometry=shapely.centroid(shapely.make_valid(p.geometry.values)), crs=2276)
j = gpd.sjoin(cent, z[["zone_norm", "geometry"]], predicate="within", how="inner")

is_mf = j.land_use_cat.isin(MF_CATS) | ((j.land_use_cat == "Commercial") & j.bldg_class.isin(APARTMENT_CLASSES))
j["mf_u"] = np.where(is_mf, j.total_units, 0.0)
j["mf_u_2010"] = np.where(is_mf & (j.year_built >= 2010), j.total_units, 0.0)
agg = j.groupby("zone_norm").agg(parcels=("total_units", "size"),
                                 total_units=("total_units", "sum"),
                                 total_mf_units=("mf_u", "sum"),
                                 mf_units_2010plus=("mf_u_2010", "sum"))

out = zd[["zone_norm", "land_sqmi"]].merge(agg, on="zone_norm", how="left").fillna(0)
out["category"] = out.zone_norm.map(cat_of)
out.loc[out.zone_norm.isin(["CA-1", "CA-2"]), "category"] = "Mixed-Use"   # fold CA into Mixed-Use
out["catord"] = out.category.map({c: i for i, c in enumerate(CAT_ORDER)}).fillna(99).astype(int)
out["zord"] = [within_rank(c, z) for c, z in zip(out.category, out.zone_norm)]
out = out.sort_values(["catord", "zord", "land_sqmi"], ascending=[True, True, False]).reset_index(drop=True)
for c in ["parcels", "total_units", "total_mf_units", "mf_units_2010plus"]:
    out[c] = out[c].astype(int)
out["land_sqmi"] = out["land_sqmi"].round(2)
out = out.rename(columns={"zone_norm": "zone"})[
    ["category", "zone", "parcels", "land_sqmi", "total_units", "total_mf_units", "mf_units_2010plus"]]

total = {"category": "(all zones)", "zone": "TOTAL", "parcels": out.parcels.sum(),
         "land_sqmi": round(out.land_sqmi.sum(), 2), "total_units": out.total_units.sum(),
         "total_mf_units": out.total_mf_units.sum(), "mf_units_2010plus": out.mf_units_2010plus.sum()}
final = pd.concat([out, pd.DataFrame([total])], ignore_index=True)

final.to_csv(os.path.join(DATA, "all_zones_summary.csv"), index=False)
pd.set_option("display.max_rows", None, "display.width", 200)
print("Every base zoning district in the City of Dallas — summary (all CAD)")
print("Total MF units include commercial-coded apartment/loft buildings.\n")
print(final.to_string(index=False))
