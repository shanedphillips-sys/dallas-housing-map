"""
Convert the large parcel + building GeoJSON layers to vector PMTiles so the browser
streams only the visible tiles instead of loading ~250 MB of GeoJSON up front.

Uses pyogrio's bundled GDAL (3.11, PMTiles driver = rw). No ogr2ogr binary, no
tippecanoe, no WSL/Docker. Run:  python build_pmtiles.py

Output (source-layer name = the second arg, which the webmap references):
  data/parcels.pmtiles     source-layer "parcels"    z9-14
  data/buildings.pmtiles   source-layer "buildings"  z12-15
"""
import os

import geopandas as gpd
import pandas as pd
import pyogrio

WEB = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(WEB, "data")


def add_base_zone(gdf):
    """Bake the City base-zoning district (zone_norm) onto each parcel via a
    representative-point-in-polygon join against zoning.geojson, so the webmap can
    intersect land use with zoning as a cheap attribute filter (base_zone == 'PD').
    Parcels outside the City of Dallas (suburban/county) get base_zone = None."""
    zp = os.path.join(DATA, "zoning.geojson")
    if not os.path.exists(zp):
        print("  zoning.geojson missing; base_zone not added", flush=True)
        gdf = gdf.copy()
        gdf["base_zone"] = None
        return gdf
    zoning = gpd.read_file(zp).to_crs(3857)[["zone_norm", "geometry"]]
    pts = gdf.to_crs(3857).copy()
    pts["geometry"] = pts.geometry.representative_point()   # guaranteed inside each parcel
    joined = gpd.sjoin(pts, zoning, how="left", predicate="within")
    joined = joined[~joined.index.duplicated(keep="first")]  # boundary point in >1 poly -> keep first
    gdf = gdf.copy()
    gdf["base_zone"] = joined["zone_norm"].reindex(gdf.index).values
    n = int(gdf["base_zone"].notna().sum())
    print(f"  base_zone: {n}/{len(gdf)} parcels within City zoning; top:",
          gdf["base_zone"].value_counts().head(6).to_dict(), flush=True)
    return gdf


def build(out_name, layer_name, srcs, minzoom, maxzoom, sample_bbox, enrich=None):
    frames = []
    for s in srcs:
        p = os.path.join(DATA, s)
        if not os.path.exists(p):
            print(f"  MISSING {s}, skipping")
            continue
        g = pyogrio.read_dataframe(p)
        frames.append(g)
        print(f"  read {s}: {len(g)} features, {len(g.columns)} cols", flush=True)
    if not frames:
        print(f"  no inputs for {out_name}; skipped")
        return
    gdf = pd.concat(frames, ignore_index=True) if len(frames) > 1 else frames[0]
    gdf = gpd.GeoDataFrame(gdf, geometry="geometry", crs=(frames[0].crs or 4326))
    gdf = gdf.to_crs(4326)
    if enrich:
        gdf = enrich(gdf)
    n_src = len(gdf)

    out = os.path.join(DATA, out_name)
    if os.path.exists(out):
        os.remove(out)
    pyogrio.write_dataframe(
        gdf, out, driver="PMTiles", layer=layer_name,
        # MAX_SIZE / MAX_FEATURES are DATASET options for this driver (not layer options);
        # generous caps so dense tiles keep full geometry + every feature
        dataset_options={
            "MINZOOM": str(minzoom), "MAXZOOM": str(maxzoom),
            "MAX_SIZE": "2500000", "MAX_FEATURES": "1000000",
        },
    )
    sz = os.path.getsize(out) / 1e6
    info = pyogrio.read_info(out, layer=layer_name)
    fields = list(info.get("fields", []))
    # round-trip: GDAL returns tile geometry in EPSG:3857, so reproject to lon/lat before
    # counting features in a dense downtown bbox (confirms nothing was dropped in tiling)
    try:
        back = pyogrio.read_dataframe(out)
        if back.crs and back.crs.to_epsg() != 4326:
            back = back.to_crs(4326)
        b = sample_bbox
        nsamp = len(back.cx[b[0]:b[2], b[1]:b[3]])
    except Exception as e:
        nsamp = f"read-back err: {e}"
    print(f"wrote {out_name}: {sz:.1f} MB | source-layer '{layer_name}' | "
          f"src {n_src} feats | {len(fields)} fields | downtown-bbox: {nsamp}", flush=True)


# downtown Dallas bbox for the parcel sanity sample; same area works for buildings
build("parcels.pmtiles", "parcels",
      ["parcels_nw.geojson", "parcels_ne.geojson", "parcels_sw.geojson", "parcels_se.geojson"],
      11, 14, (-96.81, 32.77, -96.79, 32.79), enrich=add_base_zone)
build("buildings.pmtiles", "buildings",
      ["buildings_dallas.geojson"],
      12, 15, (-96.81, 32.77, -96.79, 32.79))
print("done")
