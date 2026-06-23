"""
Multifamily permits (projects of 10+ units) by Market Value Analysis (MVA) cluster,
City of Dallas, for two periods: 2013-2018 and 2020-2024, with zoning breakdowns.

WHAT IT DOES
  For each MVA cluster (A = strongest market ... I = weakest), sums the dwelling
  units permitted in multifamily projects of 10+ units, split into 2013-2018 and
  2020-2024. Each permit is assigned to the cluster whose MVA block group CONTAINS
  its point (point-in-polygon). Three zoning slices are reported per period:
    - all   : every qualifying project, any zoning
    - MF_MU : projects on parcels zoned MF-1/MF-2/MF-3 or MU-1/MU-2/MU-3
              (includes the (A) and (SAH) variants; excludes MF-4)
    - PD    : projects on parcels zoned PD (Planned Development)

SOURCES
  - MVA boundaries: City of Dallas 2023 Housing Market Value Analysis (block groups;
    field `clusterletter` = A..I; A = strongest market -> I = weakest, confirmed
    against its Median_Sales_Price_21_22). Path = MVA_PATH below. (An older 2018 MVA
    file, field `mvacluster`, covers only ~146 of 384 sq mi -- do NOT use it.)
  - Permits: data/permits.geojson -- City of Dallas construction permits 2000-2024,
    deduped, with `type` (sf/mf/com), `units` (dwelling units), `year`, point geometry.
  - Zoning: data/zoning.geojson -- current base zoning, field `zone_dist` (raw code).
    NOTE: this is CURRENT zoning, not necessarily the zoning in force at permit time;
    for PD-rezoned projects the two usually agree, but a parcel rezoned after the
    permit would be classified by its current code.
  - City boundary: data/city_boundary.geojson (coverage diagnostics only).

DEFINITIONS
  - "Multifamily, 10+ units" = permits with type == 'mf' AND units >= 10.
  - "Including mixed-use" additionally counts type == 'com' permits with units >= 10
    (mixed-use buildings whose dwelling units are coded commercial in the permit data).
  - A permit's MVA cluster / zoning = the polygon that CONTAINS its point.

OUTPUT
  Prints the tables + a coverage summary, and writes:
    data/mva_mf_permits_by_cluster.csv               (multifamily only)
    data/mva_mf_permits_by_cluster_inclmixeduse.csv  (multifamily + mixed-use)
  Each CSV has units by cluster x period x zoning slice (all / MF_MU / PD).

All spatial ops are done in EPSG:2276 (Texas N Central, US feet).
"""
import os
import re

import geopandas as gpd
import pandas as pd
import shapely

# ---- configuration --------------------------------------------------------
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
MVA_PATH = (
    r"C:\Users\shane\OneDrive\Documents\Domain Consulting\Projects"
    r"\GDPC - Dallas Housing Report\GDPC Claude Stuff\Market Value Analysis"
    r"\City_of_Dallas_2023_Housing_Market_Value_Analysis_.geojson"
)
PERMITS_PATH = os.path.join(DATA, "permits.geojson")
ZONING_PATH = os.path.join(DATA, "zoning.geojson")
CITY_PATH = os.path.join(DATA, "city_boundary.geojson")

CLUSTER_FIELD = "clusterletter"
MIN_UNITS = 10
PERIODS = {"2013-2018": range(2013, 2019), "2020-2024": range(2020, 2025)}
CLUSTER_ORDER = list("ABCDEFGHI")
WORK_CRS = "EPSG:2276"
SQMI = 27_878_400.0  # square feet per square mile (EPSG:2276 is in US feet)

# zoning slices: parcels zoned MF-1/2/3 or MU-1/2/3 (incl (A)/(SAH) variants), and PD
MF_MU_RE = re.compile(r"^(MF-[123]|MU-[123])", re.I)


def period_of(year):
    for name, yrs in PERIODS.items():
        if year in yrs:
            return name
    return None


def zone_slice(zone_dist):
    s = "" if zone_dist is None else str(zone_dist)
    if MF_MU_RE.match(s):
        return "MF_MU"
    if s.upper().startswith("PD"):
        return "PD"
    return "other"


def load():
    mva = gpd.read_file(MVA_PATH)[[CLUSTER_FIELD, "geometry"]].to_crs(WORK_CRS)
    mva = mva.rename(columns={CLUSTER_FIELD: "cluster"})
    mva["geometry"] = shapely.make_valid(mva.geometry.values)
    zoning = gpd.read_file(ZONING_PATH)[["zone_dist", "geometry"]].to_crs(WORK_CRS)
    zoning["geometry"] = shapely.make_valid(zoning.geometry.values)
    permits = gpd.read_file(PERMITS_PATH).to_crs(WORK_CRS)
    city = gpd.read_file(CITY_PATH).to_crs(WORK_CRS)
    city_geom = shapely.make_valid(city.geometry.union_all())
    return mva, zoning, permits, city_geom


def assign_by_containment(points, polys, value_col):
    """Each point -> the value of the polygon that contains it (point-in-polygon)."""
    j = gpd.sjoin(points, polys[[value_col, "geometry"]], predicate="within", how="left")
    j = j[~j.index.duplicated(keep="first")]  # polygons don't overlap; guard anyway
    return j[value_col]


def build_table(permits, mva, zoning, city_geom, types, label):
    sel = permits[permits["type"].isin(types) & (permits["units"] >= MIN_UNITS)].copy()
    sel["period"] = sel["year"].apply(period_of)
    sel = sel[sel["period"].notna()].copy()
    sel["cluster"] = assign_by_containment(sel, mva, "cluster")
    sel["zone_dist"] = assign_by_containment(sel, zoning, "zone_dist")
    sel["zslice"] = sel["zone_dist"].apply(zone_slice)
    sel["in_city"] = sel.geometry.within(city_geom)

    def units_pivot(df):
        return (df.pivot_table(index="cluster", columns="period", values="units",
                               aggfunc="sum", fill_value=0)
                  .reindex(CLUSTER_ORDER, fill_value=0))

    slices = {"all": sel, "MF_MU": sel[sel["zslice"] == "MF_MU"], "PD": sel[sel["zslice"] == "PD"]}
    pivots = {k: units_pivot(v) for k, v in slices.items()}

    table = pd.DataFrame(index=CLUSTER_ORDER)
    table.index.name = "mva_cluster"
    for sl in ["all", "MF_MU", "PD"]:
        for per in PERIODS:
            table[f"{sl}_{per}"] = pivots[sl].get(per, 0)
    table.loc["A-I total"] = table.sum()
    # percent change between the two periods, per slice (NaN where the base period is 0)
    p1, p2 = list(PERIODS)
    cols = []
    for sl in ["all", "MF_MU", "PD"]:
        a, b = table[f"{sl}_{p1}"], table[f"{sl}_{p2}"]
        table[f"{sl}_pct_change"] = ((b - a) / a.where(a != 0) * 100).round(1)
        cols += [f"{sl}_{p1}", f"{sl}_{p2}", f"{sl}_pct_change"]
    table = table[cols]

    print(f"\n===== {label} =====")
    print(table.to_string())
    for per in PERIODS:
        ai = int(pivots["all"].get(per, pd.Series(dtype=int)).sum())
        city_total = int(sel[(sel["period"] == per) & sel["in_city"]]["units"].sum())
        print(f"  {per}: A-I {ai} units | in-city total {city_total} | outside A-I {city_total - ai}")
    return table


def main():
    mva, zoning, permits, city_geom = load()
    print(f"MVA coverage: {mva.geometry.area.sum() / SQMI:,.0f} sq mi | "
          f"city: {city_geom.area / SQMI:,.0f} sq mi "
          f"| clusters A..I (A = strongest market -> I = weakest)")

    mf = build_table(permits, mva, zoning, city_geom, ["mf"], "MULTIFAMILY (type=mf), 10+ units")
    mf.to_csv(os.path.join(DATA, "mva_mf_permits_by_cluster.csv"))
    mfx = build_table(permits, mva, zoning, city_geom, ["mf", "com"],
                      "INCLUDING MIXED-USE (type=mf or com), 10+ units")
    mfx.to_csv(os.path.join(DATA, "mva_mf_permits_by_cluster_inclmixeduse.csv"))
    print("\nWrote data/mva_mf_permits_by_cluster.csv and data/mva_mf_permits_by_cluster_inclmixeduse.csv")


if __name__ == "__main__":
    main()
