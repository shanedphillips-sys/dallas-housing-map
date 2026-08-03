# Data sources & methods — map layers

One-line source + method for every layer and report on the webmap. The **build
script** column is the authoritative, runnable detail; `CLAUDE.md` has the deeper
methodology narrative. Keep this file updated whenever a layer is added or changed.

Raw source files marked *(OneDrive)* live under
`…\GDPC - Dallas Housing Report\` and are not in the repo (read-only inputs).

---

## Jurisdiction & transit

| Layer | Source | Method | Build script → data |
|---|---|---|---|
| City of Dallas boundary | City of Dallas municipal boundary | As provided | `data/city_boundary.geojson` |
| County boundaries | 7-county tracts | Dissolve `tracts.geojson` by county FIPS; morphological close to remove sliver-holes | `build_county_boundaries.py` → `data/counties.geojson` |
| Council districts | City of Dallas Council_Boundaries *(OneDrive)* | As provided | `data/council.geojson` |
| Rail stations | DART Rail_Stops *(OneDrive)* | As provided | `data/rail_stops.geojson` |
| Half-mile station areas | DART rail stops | 0.5-mi (2,640 ft) buffers around station points | `data/station_areas.geojson` |
| Transit network (DART) | DART GTFS feed | Weekday routes; **frequent** = ≤20-min headway in *both* 7–9am & 4–6pm peaks (rail service resolved via `calendar_dates`); rail drawn with cross-ties, bus in 3 headway tiers | `build_frequent_transit.py` → `data/transit_routes.geojson` |

## Streets, alleys & parking (OpenStreetMap)

| Layer | Source | Method | Build script → data |
|---|---|---|---|
| Street grid — Streets / Dead-ends | OSM `drive` network | Pull City+1.5 km, classify each segment grid (in a cycle) vs. stub (network bridge / dead-end); clip to city | `build_street_lines.py` → `data/streets_dallas.geojson` (`kind`) |
| Street names | OSM `name` on the same network | `name` tag carried on each segment, labeled z14+ | (same `streets_dallas.geojson`) |
| Alleys | OSM `service=alley` | Pull alleys, clip to city | `build_alleys.py` → `data/alleys_dallas.geojson` |
| Surface parking | OSM `amenity=parking` | Surface + untagged polygons (excludes multi-storey/underground/carport); centroid-in-city | `build_parking.py` → `data/parking_dallas.geojson` |
| Street pattern (dendricity / dead-end share / intersection density) | OSM via OSMnx | Per-tract connectivity metrics (length-weighted bridge share, cul-de-sac node %, intersections/mi²) | `build_street_dendricity.py` → `data/street_dendricity_tracts.geojson` |
| Water mask (internal, not a toggle) | OSM `natural=water` | Lakes + river clipped to city; auto-masks water on the zoning / land-use / FAR / decade fills so it doesn't read as a category | `build_water.py` → `data/water_dallas.geojson` |

## Buildings

| Layer | Source | Method | Build script → data |
|---|---|---|---|
| Building footprints (3D) | Microsoft GlobalMLBuildingFootprints + OSM | MS ML footprints (centroid-in-city) + `meanHeight`; OSM `height`/`building:levels` overlaid for the towers MS leaves blank; 6 m default | `build_buildings.py` → `data/buildings_dallas.geojson` (`height_m`, `src`) → `data/buildings.pmtiles` (`build_pmtiles.py`, source-layer `buildings`) |

## Parcels & parcel attributes

All parcel layers share one vector-tile source **`data/parcels.pmtiles`** (source-layer
`parcels`), built from `data/parcels_{nw,ne,sw,se}.geojson` by `build_pmtiles.py` (pyogrio /
GDAL PMTiles driver — the browser streams only visible tiles instead of loading ~215 MB of
GeoJSON up front). The quadrant GeoJSONs remain the editable source of truth.

**Parcel base:** DCAD 2025 Certified (Dallas Co.) + Collin CAD + Denton CAD, account-level merge.
Pipeline: `build_parcels_geojson.py` → `merge_collin_cad.py` → `merge_denton_cad.py`
→ `patch_institutional.py` (exempt → Institutional) → `add_missing_parcels.py`
(downtown/condo parcels from PARCEL_GEOM) → `build_footprint_far.py` (building_sf + FAR).

| Layer | Field / source | Method |
|---|---|---|
| Assessor parcels | full DCAD/CCAD/Denton attributes | Popup only; neutral fill |
| Base zoning | City of Dallas Base_Zoning *(OneDrive)* | `data/zoning.geojson`; colored by `category`; collapsible per-category picker filters to individual base districts (`zone_norm`; (A)/(SAH) parentheticals merged) (catalog: `build_zoning_districts.py` → `data/zoning_districts.json`) |
| Land use | CAD SPTD land-use code | Collapsed to ~17 display categories; `totexempt=='X'` reclassified Institutional |
| Building floor-area ratio (FAR) | CAD `building_sf` ÷ lot area | Footprint-attributed FAR (`foot_far`): building floor area split across overlapping footprints; `build_footprint_far.py` |
| Decade structure built | CAD `year_built` | Binned by decade |
| Improvement / land value ratio | CAD `impr_val` ÷ `land_val` (as reported) | Parcels < $100k/acre and Institutional/Government excluded |
| Property value per acre (3D & 2D) | CAD total / improvement / land value | Value ÷ acres; multi-polygon accounts pro-rated by area share; `area_feet < 100` and < $100k/acre excluded. Same data offered two ways — **3D** extrusion (height ∝ value, cappable) and **2D** flat choropleth — each with a Total / Improvement / Land radio |

## Permits

| Layer | Source | Method | Data |
|---|---|---|---|
| Building permits (SF / MF, 2000–2024) | City of Dallas NewPermit_1971_2024 *(OneDrive)* | Building permits, deduped by activity/date/address; SF/MF type, units, year-range slider | `data/permits.geojson` |

## Demographics & change (7-county region)

| Layer | Source | Method | Build script → data |
|---|---|---|---|
| Demographics (income, renter %, rent burden, poverty, race/ethnicity) | Census ACS 2020–24 5-yr | `B19013` income, `B25003` tenure, `B25070` rent burden, `B17001` poverty, `B03002` race → % Hispanic / NH White / Black / Asian; by tract, single toggle + metric radio | `build_acs_demographics.py` → `data/acs_demographics_tracts.geojson` |
| Population change 2010–2020 (BG / tract) | Census Decennial (2020 DHC; 2010 blocks) | 2020 pop at BG; 2010 pulled at BLOCK level, area-weighted to 2020 BGs via TAB2010/2020 block relationship | `build_pop_hu_geojsons.py` → `data/block_groups.geojson`, `data/tracts.geojson` |
| Housing-unit change 2010–2020 (BG / tract) | Census Decennial | Same block-level crosswalk as pop | (same files) |
| Job density | LODES8 WAC 2022 | Workplace jobs/acre by tract; 3 BLS sector-weighted wage bins | `build_jobs_tracts.py` → `data/jobs_tracts.geojson` |
| Expected adult earnings | Opportunity Insights (Opportunity Atlas) | Predicted adult income, children from 25th-pct families; 2010→2020 tract crosswalk | `build_oi_tracts.py` → `data/oi_tracts.geojson` |
| Median rent change | ACS 5-yr `B25064` (tract) ↔ Zillow ZORI (ZIP) | Real (CPI-deflated 2024$); MOE/est > 30% grayed; dual-year slider | `build_acs_rent_value.py`, `build_zillow_zip.py`, `build_cpi.py` |
| Median home value change | ACS 5-yr `B25077` (tract) ↔ Zillow ZHVI (ZIP) | Real 2024$; same MOE filter; Zillow late-start ZIPs cross-hatched | (same scripts) |

## Subsidized housing & hazards

| Layer | Source | Method | Build script → data |
|---|---|---|---|
| Subsidized (LIHTC) housing | TDHCA HTC Property Inventory (May 2026) | Tax-credit properties; dedup by lat/lon (keep max Total Units); clip to city; circle area ∝ unit count | `build_subsidized_housing.py` → `data/subsidized_housing.geojson` |
| Floodplain (100-yr / 500-yr) | FEMA National Flood Hazard Layer | 1%-annual SFHA (`A*`/`V*`) vs 0.2%-annual zones; grid-tiled ArcGIS fetch (10k-record cap), dedup by OBJECTID, clip to city; gray cross-hatch fills (100-yr thicker) | `build_floodplain.py` → `data/floodplain.geojson` |

## Place search

| Feature | Source | Method |
|---|---|---|
| Address / place geocoder | Photon (OpenStreetMap) | Header search box; autocomplete biased to the Dallas area; flies to the picked result | (client-side, no data file) |

## Reports (side panel)

| Report | Source | Method | Build script → data |
|---|---|---|---|
| TOD Opportunity Areas (per rail station) | parcels + ACS + zoning | Per-station aggregates | `precompute_station_reports.py` → `data/station_reports.json` |
| Council Districts (per district) | parcels + ACS + zoning + permits | Area-weighted ACS; zoning/land-use/FAR mix; permitted units | `precompute_district_reports.py` → `data/district_reports.json` |
| Value by Land Use | parcels | City-wide value per land use | `precompute_land_use_value.py` → `data/land_use_value_summary.json` |

---

*Supporting builds:* `build_cpi.py` (BLS CPI-U deflators → `data/cpi_annual.json`).
*Standalone analyses* (charts/tables, not map layers) live in `analyze_*.py` / `make_*.py`.
