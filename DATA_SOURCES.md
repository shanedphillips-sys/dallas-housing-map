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
| Transit network (DART) | DART GTFS feed | Three independent toggles — Rail (light-rail + commuter, cross-ties), Frequent buses, Other buses. **Frequent** = ≤20-min headway in *both* 7–9am & 4–6pm weekday peaks (rail service resolved via `calendar_dates`); rail dark/light purple by frequency, buses green (≤20 min) / blue (>20 min) | `build_frequent_transit.py` → `data/transit_routes.geojson` |

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
GeoJSON up front). The quadrant GeoJSONs remain the editable source of truth. During the
tile build each parcel is also stamped with **`base_zone`** — the City base-zoning district
(`zone_norm`) whose polygon contains the parcel's representative point — so the webmap can
intersect land use with zoning as a cheap attribute filter.

**Parcel base:** DCAD 2025 Certified (Dallas Co.) + Collin CAD + Denton CAD, account-level merge.
Pipeline: `build_parcels_geojson.py` → `merge_collin_cad.py` → `merge_denton_cad.py`
→ `patch_institutional.py` (exempt → Institutional) → `add_missing_parcels.py`
(downtown/condo parcels from PARCEL_GEOM) → `build_footprint_far.py` (building_sf + FAR).

| Layer | Field / source | Method |
|---|---|---|
| Assessor parcels | full DCAD/CCAD/Denton attributes | Popup only; neutral fill |
| Base zoning | City of Dallas Base_Zoning *(OneDrive)* | `data/zoning.geojson`; colored by `category`; collapsible per-category picker filters to individual base districts (`zone_norm`; (A)/(SAH) parentheticals merged) (catalog: `build_zoning_districts.py` → `data/zoning_districts.json`) |
| Land use | CAD SPTD land-use code | Collapsed to ~17 display categories; `totexempt=='X'` reclassified Institutional; collapsible family→category picker (mirrors the zoning one). **Intersection:** an "only within selected zoning districts" toggle clips the layer to parcels whose `base_zone` is in the Base-zoning picker's current selection |
| Building floor-area ratio (FAR) | CAD `building_sf` ÷ lot area | Footprint-attributed FAR (`foot_far`): building floor area split across overlapping footprints; `build_footprint_far.py` |
| Decade structure built | CAD `year_built` | Binned by decade |
| Improvement / land value ratio | CAD `impr_val` ÷ `land_val` (as reported) | Parcels < $100k/acre and Institutional/Government excluded |
| Property value per acre (3D & 2D) | CAD total / improvement / land value | Value ÷ acres; multi-polygon accounts pro-rated by area share; `area_feet < 100` and < $100k/acre excluded. Same data offered two ways — **3D** extrusion (height ∝ value, cappable) and **2D** flat choropleth — each with a Total / Improvement / Land radio |
| Faith-owned land | DCAD 2025 (`bldg_cl`, `totexempt`, ACCOUNT_INFO owners) + Collin CAD 2025 + Denton protax | Parcels owned by faith **congregations** in the City of Dallas, split Vacant (no assessed improvement) vs Developed. Dallas is the only CAD with a religious building class, so it gets the full protocol: seed on `bldg_cl` = CHURCH BUILDING AND totally exempt, add every other exempt parcel held by a seed owner (the vacant lot next door, the parking lot, the parsonage), then sweep the remaining exempt non-homestead parcels by owner-name vocabulary. Collin has no church class but a usable exemption, so name match + `EX-XV`; Denton has neither, so name match only on unambiguous words. Government, transit, school-district and charter owners are screened out first — **84.9% of all tax-exempt land in the city is public**. Schools, cemeteries and faith institutions (hospital / senior / shelter) are categorised out of the mapped set but kept in `output/faith_all_categories.csv`. Vacancy is improvement value = $0, not floor area: DCAD records exempt buildings as a 100 sq ft placeholder, so no FAR is available for the churches themselves. Denton owner names come from the 19 GB protax export, cached once by `build_denton_owners.py` → `data/denton_dallas_owners.json`. Built by `build_faith_parcels.py` → `data/faith_parcels.geojson` |

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
| Subsidized housing (4 categories) | **NHPD** (National Housing Preservation Database, all subsidy families + expiration dates) + **TDHCA** HTC Property Inventory (May 2026, the LIHTC award universe) + **DCAD/Collin/Denton** owner names (PFC/HFC) | ONE deduped property list; each property appears exactly once, category by priority **LIHTC > PFC/HFC > public housing > other**, so the four map checkboxes can never double-count a building. Every property carries `subsidies_json` — all active programs with units and end dates — so the popup lists them all regardless of which layer drew the dot. NHPD and TDHCA are matched on name-first (the two geocode the same building up to 5 mi apart, so distance cannot gate the match); TDHCA supplies awards NHPD lacks (it keys on placed-in-service, so 2020+ awards are missing), NHPD supplies the expiration dates TDHCA has none of. Properties whose only record is an FHA-insured mortgage are **excluded** — HUD mortgage insurance is lender default cover, not an income restriction (8 Dallas records are labelled "MKT RATE"). Circle area ∝ unit count | `build_subsidized_layers.py` → `data/subsidized_all.geojson` |
| ↳ PFC / HFC restricted units | [dallaspfc.com/leasing-properties](https://dallaspfc.com/leasing-properties/) (accessed 2026-09-06) | Income-restricted counts by AMI band, published by the Dallas PFC for its own leasing properties — the only public source found that states set-asides for PFC deals. Covers **12 of 51** PFC/HFC properties (1,017 restricted of 2,017 units, ~50%). Validated against TDHCA's PFC monitoring report for Ascent at Mountain Creek (162 of 324 — exact match). A published development can span several DCAD parcels, so the absolute count is used when a parcel's total matches the published total and the published affordable SHARE otherwise. **Dallas HFC** (dallashfc.com) publishes a Google My Maps of 31 DHFC + 25 DPFC projects with names and locations but **no unit data**, so it contributes nothing. The other **39** PFC/HFC properties publish nothing, so they are **assumed 50%** (`restricted_source: "assumed"`, flagged in the popup as an estimate). Justification: all 12 published Dallas PFC properties fall in a 50.0–52.6% band (median 50.1%, none above 55%); Ch. 394 requires half the units at =<80% AMI (~$88k DFW) and HB 2071's Ch. 303 standard is lower still, so 50% is both the statutory floor and the observed value. The only PFC/HFC properties above 52.6% are the six that ALSO carry LIHTC (85–100% restricted) — those are categorised `lihtc`, take their count from LIHTC data, and never hit this branch, so every property the assumption touches is by construction a standalone PFC/HFC deal. Web searches of the individual traveling-HFC properties (Pecos, Cameron County, La Villa, Maverick County) returned no set-aside counts: their leasing sites do not mention affordability at all | `data/pfc_restricted_units.json` → `build_subsidized_layers.py` |
| ↳ PFC / HFC source points | DCAD 2025 (ACCOUNT_INFO + COM_DETAIL) + Collin CAD 2025 + Denton protax | Apartment parcels owned by a public facility / housing finance corporation (owner-name match, City of Dallas), **all years**; units + earliest year built; located via parcel geometry. Denton owner names come from the 19 GB protax export, cached once by `build_denton_pfc.py` → `data/denton_pfc_hfc.json`. Feeds the unified build above | `build_pfc_hfc_points.py` → `data/pfc_hfc_projects.geojson` |
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
