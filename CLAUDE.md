# Dallas Housing & Land Use Webmap

Interactive web map of Dallas-area housing, zoning, land use, value, jobs, and demographic
change. Hosted as a static site at `https://github.com/shanedphillips-sys/dallas-housing-map`.

---

## User & context

- **Name:** Shane Phillips
- **Email:** shanedphillips@gmail.com
- **Client / org:** Greater Dallas Planning Council (the "GDPC" in the project tree)
- **Background:** housing policy researcher / consultant; also produces a housing-policy
  podcast (`~/*.txt` files in the home folder are interview transcripts — not project files)
- **Working environment:** Windows; Anaconda Python (`C:\Users\shane\anaconda3`); git-bash
  / PowerShell as the shell; CodeMirror-style editing in Claude Code
- **Hosting:** GitHub Pages from the `main` branch of this repo

Shane prefers concise, direct answers — no unnecessary preamble, no "let me know if you need
anything else" wrap-ups. He's technical enough to follow code but values clear explanations
of *why* a methodology choice matters (e.g. block-level vs. BG-level crosswalk). When in
doubt, propose a path and ask only the questions where the answer materially changes the
work.

---

## ⚠️ Critical: OneDrive history (do NOT re-enter that path)

**The original project lived at**
`C:\Users\shane\OneDrive\Documents\Domain Consulting\Projects\GDPC - Dallas Housing Report\webmap\`.

That location is **abandoned for git operations.** A previous session tried to push from
inside OneDrive; OneDrive Files-On-Demand "placeholder" files broke git's `mmap`. A
"repair" script then cross-contaminated 32 working-tree files (each held some other file's
bytes). Recovery succeeded only because the cloud copy was clean and OneDrive sync was
paused in time.

**Current canonical location: `C:\Users\shane\repos\dallas-housing-map\`** — outside OneDrive,
git works normally. **Always work from here.** If you see a path under
`OneDrive\Documents\...GDPC...\webmap\` in a request, redirect to the new path before doing
anything destructive.

The OneDrive copy still exists; it has not been deleted. We agreed to leave it alone for
now and revisit deletion / renaming once the new workflow is proven.

---

## What this map shows

A MapLibre GL JS map of the Dallas region with toggleable, draggable-to-reorder layers:

- **Base layers:** Light gray / OpenStreetMap / Satellite basemap
- **Boundaries:** City of Dallas, council districts, half-mile rail-station areas,
  county boundaries (7-county region, dashed lines + labels)
- **Permits:** Single-family and multifamily building permits 2000–2024, year-range slider
- **Parcels:** Assessor parcel boundaries (popup with full DCAD/CCAD/DCAD attributes)
- **Zoning:** Base zoning categories
- **Land use:** DCAD/Collin/Denton land-use categories (collapsed to ~17 display categories;
  see palette below)
- **Building FAR:** 10-bin categorical floor-area-ratio map
- **Decade built:** Year-built decade by parcel
- **Property value per acre (3D):** one grouped toggle with a Total value / Improvement value
  / Land value radio (mutually exclusive fill-extrusions; linear 1 m / $25k/acre; default
  $100M/acre cap, shared "Cap heights" checkbox, toggle to uncap)
- **Pop change 2010–2020:** Single grouped toggle with Block-group / Tract radio
- **Housing-unit change 2010–2020:** Same grouped pattern
- **Job density (workplace) 2022:** LODES WAC, by tract, heatmap fill
- **Street pattern (per tract):** OSM street-network connectivity — grouped toggle with a
  Dendricity / Dead-end share / Intersection density radio. Grid vs. cul-de-sac suburbia.
- **Median rent change:** Grouped toggle. ACS-tract (2012–2024) ↔ Zillow-ZIP/ZORI (2015–2025)
  source radio, $-change / %-change radio, dual-thumb year slider. All values are real
  (CPI-deflated) constant 2024$, so % change is real growth.
- **Median home value change:** Same pattern. ACS-tract (2012–2024) ↔ Zillow-ZIP/ZHVI
  (2010–2025). Zillow ZIPs whose series starts after the chosen start year are cross-hatched.

Reports panel (sliding sidebar): TOD Opportunity Areas (per rail station), Council
Districts (per district), and Value by Land Use (multi-select land uses + metric toggle).

---

## File layout

```
.
├── index.html                       # Sidebar layout & layer toggles
├── style.css                        # All styling
├── app.js                           # Map logic (LAYERS registry + report panels)
├── README.md
├── CLAUDE.md                        # this file
│
├── build_parcels_geojson.py         # Source DCAD GPKG -> 4 quadrant GeoJSONs
├── merge_collin_cad.py              # Patches Collin parcels in place
├── merge_denton_cad.py              # Patches Denton parcels in place
├── extract_denton_dallas.py         # Streams 19GB Denton protax JSON -> slim Dallas-only
├── patch_institutional.py           # Reclassifies totexempt=='X' parcels as Institutional
├── build_pop_hu_geojsons.py         # 7-county BG- and tract-level pop/HU change
├── build_jobs_tracts.py             # LODES8 WAC 2022 -> tract-level jobs GeoJSON
├── build_street_dendricity.py       # OSM (OSMnx) -> per-tract dendricity/dead-end/intx density
├── build_street_lines.py            # cached OSM graphs -> classified street lines (grid vs stub)
├── build_cpi.py                     # BLS CPI-U annual averages -> data/cpi_annual.json
├── build_county_boundaries.py       # Dissolve tracts -> 7 clean county outlines
├── build_acs_rent_value.py          # ACS 5yr median rent/value 2012-2024 -> tract GeoJSON
├── build_zillow_zip.py              # Zillow ZHVI/ZORI monthly -> annual ZIP (ZCTA) GeoJSON
├── precompute_district_reports.py   # Per-council-district aggregates
├── precompute_station_reports.py    # Per-rail-station aggregates
├── precompute_land_use_value.py     # City-wide land-use value summary
│
└── data/
    ├── parcels_{nw,ne,sw,se}.geojson  # 47-75 MB each (quadrant split for size)
    ├── permits.geojson                # ~10 MB
    ├── zoning.geojson, council.geojson, city_boundary.geojson
    ├── rail_stops.geojson, station_areas.geojson
    ├── tracts.geojson                 # 7 counties, ~1,600 tracts
    ├── block_groups.geojson           # 7 counties, ~4,100 BGs
    ├── jobs_tracts.geojson            # LODES, 7 counties
    ├── street_dendricity_tracts.geojson # OSM street-pattern metrics per tract (1.7 MB)
    ├── streets_dallas.geojson         # OSM street lines (City of Dallas), classified grid vs cul-de-sac
    ├── counties.geojson               # 7 dissolved county outlines + names
    ├── acs_rent_value_tracts.geojson  # ACS median rent/value 2012-2024 (real 2024$), 1,599 tracts
    ├── zillow_zip.geojson             # Zillow ZHVI/ZORI annual 2010-2025 (real 2024$), 218 ZIPs
    ├── cpi_annual.json                # CPI-U annual averages 2010-2025 (deflators)
    ├── station_reports.json, district_reports.json
    ├── land_use_value_summary.json
    ├── denton_dallas_slim.json        # extracted from huge protax JSON
    ├── Zip_zhvi_*.csv, Zip_zori_*.csv # RAW Zillow source (GITIGNORED — 122 MB ZHVI > GitHub limit)
    └── pop_hu_change_histograms.png   # Dist of changes (one-off chart)
```

Source-only files (not in the repo, lived at the OneDrive project root):
- `GDPC Claude Stuff/PARCEL_CORE_MERGED.gpkg` — DCAD parcels GPKG
- `GDPC Claude Stuff/DCAD2025_CERTIFIED/ACCOUNT_APPRL_YEAR.CSV` — appraisal values
- `Collin_CAD_Appraisal_Data_-_2025_20260520.csv` — Collin County CAD
- `Denton-protaxExport-20250728.json` — 19 GB Denton CAD export
- `Denton County Appraisal District/...` — alternate Denton CAD fixed-width extracts (unused)
- `lodes_tx_wac_2022.csv.gz` — LODES8 TX workplace area characteristics
- `tl_2020_48_tract.zip`, `tl_2020_48_bg.zip` — TIGER tract + block group geometries
- `TAB2010_TAB2020_ST48.zip` — Census 2010↔2020 block relationship file
- `bg_xwalk_2010_2020.txt` — older national BG crosswalk (kept but not used in the new pipeline)
- `cb_2020_us_zcta520_500k.zip` — TIGER generalized ZCTA boundaries (national, ~67 MB), at
  the repo PARENT dir `C:\Users\shane\repos\`. Used by `build_zillow_zip.py` for ZIP polygons.
- `tab20_tract20_tract10_natl.txt` — Census 2010→2020 **tract** relationship file (national,
  18.7 MB), at the repo parent dir. Used by `build_acs_rent_value.py` for the ACS crosswalk.
  (The per-state `..._48.txt` URL 520/524-errors on Cloudflare; the national file works — filter
  `GEOID_TRACT_20` to the 7-county prefixes.)
- Raw Zillow CSVs (`data/Zip_zhvi_*.csv`, `data/Zip_zori_*.csv`) live IN the repo's `data/`
  but are **.gitignored** — the 122 MB ZHVI file exceeds GitHub's 100 MB hard limit. Only the
  derived `data/zillow_zip.geojson` (slim) is committed.

---

## Data sources & key methodology decisions

### Parcels (3 counties)

- **Dallas County:** DCAD 2025 Certified roll (`PARCEL_CORE_MERGED.gpkg` for geometry +
  `ACCOUNT_APPRL_YEAR.CSV` for values; account-level merge). 2026 file is pre-cert and has
  all values = 0, so we use 2025.
- **Collin County:** Collin CAD CSV; joins by stripping `"COL-"` prefix from
  `account_num` and parsing the remaining 10 digits → matches CCAD `propID`. 99.6% match
  rate.
- **Denton County:** 19 GB protax JSON; stream-parsed with `ijson`, filtered to
  `situses[0].city == 'DALLAS'` → 2,546 records → joined by `pID`. 99.8% match rate.
- **Pro-rating:** Multi-polygon DCAD accounts (some accounts cover several disjoint
  polygons) get their values pro-rated by area share to avoid replicating the full account
  value to each polygon (this is what fixed 403 REUNION BLVD, formerly $1.16B/acre).
- **"Institutional" reclassification:** DCAD parcels with `totexempt=='X'` AND prior
  land_use_cat in `{Commercial, Industrial, Other}` are reclassified as
  `"Institutional / Government"` so schools, churches, government buildings, etc. don't
  show up as Commercial.
- **Tiny parcels filtered:** Webmap 3D-value layers exclude `area_feet < 100` (TIF base-ROW
  placeholders, sliver records); 116 affected parcels.

### Population / housing-unit change 2010–2020 (CRITICAL methodology)

- Coverage: **Dallas County + 6 adjacent counties** (Collin, Denton, Tarrant, Ellis,
  Kaufman, Rockwall). Not just Dallas city; the surrounding suburban growth is the story.
- **Crosswalk is at the BLOCK level, NOT the BG level.** This was a fix — the prior
  BG-level area-weighted crosswalk dumped neighbor-BG population across redrawn boundaries,
  e.g. fabricating a "1,046-person loss" in BG 481130078153 that was really a +939 gain.
- 2020 pop/HU pulled directly from Decennial DHC at the BG level (matches Census exactly).
- 2010 pop/HU pulled at the BLOCK level, then area-weighted via
  `TAB2010_TAB2020_ST48.zip`'s block relationship file to 2020 BGs.
- Blocks are small enough (~50–100 people) that within-block uniform-density assumption
  introduces minimal error. Most 2010 blocks have weight = 1.0 (unchanged into 2020).
- Cross-check: our Dallas County 2010 total (2,368,849) is within 0.03% of Census published
  (2,368,139); 2020 is exact.

### Jobs (LODES8 WAC 2022)

- 7 counties same as pop/HU. 1,599 tracts. ~3.87M jobs total.
- Two wage estimation methods, shown side-by-side in the popup:
  - **Midpoint:** CE01 × $10k + CE02 × $27.5k + CE03 × $80k.
  - **BLS sector-weighted:** Σ CNS01..CNS20 × BLS QCEW 2022 Dallas-Fort Worth-Arlington
    MSA average annual wage by NAICS 2-digit sector.
- **3 sector-based wage bins** displayed (NOT the LODES wage buckets, which top out at
  $40k):
  - `<$50k`: retail, food/accom, arts, other services, agriculture
  - `$50k–$100k`: construction, manufacturing, education, health, public admin, etc.
  - `>$100k`: mining/oil&gas, utilities, info, finance, professional, mgmt

### Street pattern (dendricity / connectivity) — `build_street_dendricity.py`

- Per-tract OSM street-network connectivity, to distinguish **grid** from **cul-de-sac /
  dendritic suburbia**. Pulls the OSM `drive` network for each county via OSMnx (cached as
  graphml under `../osm_cache`), composes all 7 into ONE graph (shared OSM node IDs stitch
  county lines), classifies edges, then assigns each edge/node to a tract by location.
- **Dendricity** (after Barrington-Leigh & Millard-Ball): length-weighted share of street
  length that is a network **bridge** (removal disconnects the network — includes dead-ends)
  vs. part of a **cycle**. Bridges are computed on the WHOLE composed graph (a global property),
  not per-tract subgraphs (which would falsely read clipped through-streets as dead-ends).
- **Finding: length-weighted dendricity is compressed for DFW** (median 0.06, p90 0.17) because
  cul-de-sac stubs are *short*, so by length even pod suburbs read low. Ground-truth: downtown
  Dallas = 0.00 (textbook grid), but the suburban middle is muddy. So the layer is a **grouped
  toggle with a metric radio** — Dendricity / **Dead-end share** / Intersection density — all
  shipped per tract. **Dead-end share** (% of nodes that are culs-de-sac; grids 0–4%, cul-de-sac
  suburbs 17–22%) and **intersection density** (grids 140–273/mi², suburbs ~100) discriminate
  far better; dead-end share is the recommended default view.
- Palette: teal (grid / well-connected) → cream → red (cul-de-sac). Intersection density
  REVERSES the ramp (high density = grid = teal). Bin edges tuned to the 7-county distribution.
  Output `data/street_dendricity_tracts.geojson`: geoid, dendricity, pct_deadend,
  intersection_density, n_intersections, street_mi.

### Rent & home-value change (ACS tract + Zillow ZIP)

- **Two grouped layers** ("Median rent change", "Median home value change"). Each has a
  source radio (ACS-tract ↔ Zillow-ZIP), a $-change / %-change radio, and a dual-thumb year
  slider. The slider rebuilds a MapLibre `step` color expression live from the two chosen
  years (`build_acs_rent_value.py` / `build_zillow_zip.py` ship every year as a per-feature
  property; the frontend differences them). 7 counties, same footprint as jobs/pop-HU.
- **Real (constant 2024$).** Shane chose inflation-adjusted, not nominal — over 2012→2024 CPI
  rose ~35%, so nominal change badly overstates real housing-cost growth. Every year is
  deflated to 2024$ via CPI-U annual averages (`build_cpi.py` → `data/cpi_annual.json`):
  `real_2024 = nominal_year × CPI[2024]/CPI[year]`. **% change is therefore real growth too**
  (inflation stripped), since it's computed off the deflated series.
- **ACS variables:** `B25064_001E` median gross rent, `B25077_001E` median home value, ACS
  5-year vintages 2012–2024 (13 samples).
- **ACS 2010→2020 tract harmonization (methodology choice).** ACS 5-year switches tract
  geography at the **2020 sample** (2012–2019 are on 2010 tracts → 1,235 rows; 2020–2024 on
  2020 tracts → 1,599 rows). The whole map uses 2020 tracts, so each 2020 tract takes its
  pre-2020 values from its **dominant** (largest land-area overlap) 2010 parent, via the
  Census `tab20_tract20_tract10_natl.txt` relationship file. Tract SPLITS (common in DFW
  growth) inherit the parent median exactly; rare MERGES take the area-dominant parent. We
  don't average medians. The build resolves each year per-tract (direct 2020 GEOID else
  dominant 2010 parent), so the cutoff self-detects. Caveat: `B25077` is top-coded (older
  vintages ~$1M, newer ~$2M), so a few ultra-high-value tracts (Highland Park) can show an
  inflated jump that's partly a cap artifact.
- **ACS reliability filter (`MAX_MOE_RATIO = 0.30`).** Tract medians from small renter/owner
  samples have huge margins of error and, left in, produce *spurious* real-2024$ "declines"
  that are pure sampling noise (we investigated this: of the original nominal declines, **0 of
  22 rent** were statistically significant, and the worst value "declines" were physically
  impossible, e.g. a tract's owner value reading $23k with a ±$20k MOE). So `build_acs_rent_value.py`
  pulls the MOE (`B25064_001M` / `B25077_001M`) and ships the **estimate + MOE per cell** (both
  real 2024$, as `rent_moe_YYYY` / `val_moe_YYYY`). The **webmap** (`RV_MAX_MOE = 0.30`, kept in
  sync) applies the rule: a tract-year with **MOE/estimate > 30%** (≈ 18% CV — the Census
  "reliable/caution" border) **or no usable MOE** is **grayed** (legend "No reliable estimate"),
  and the popup shows est ± MOE for both years and flags the exclusion ("Estimate excluded
  because its margin of error exceeds 30% of the estimate"). No sample-size floor (the MOE
  subsumes it). ~9% of rent / ~7% of value cells fail. Shipping est+moe (rather than nulling in
  the build) keeps one source of truth and lets a clicked gray tract still show its excluded
  estimate. Cross-validated against Zillow (a smoothed index, no MOE) which shows **0
  declines** 2012→24 — confirming the ACS declines were the noise. Threshold was chosen from a
  full MOE sweep; 20% would suppress ~a third of rent tracts, 40% leaves more noise in.
  Conceptual note kept in mind: ACS medians track *the current housing stock*, so a tract can
  legitimately "decline" when its mix shifts (new cheaper units, owners→renters) — Zillow's
  constant-quality index answers "did homes appreciate," ACS answers "what do residents pay/own."
- **Zillow:** ZHVI (`Zip_zhvi_uc_sfrcondo_tier..._month.csv`, home value, monthly from 2000)
  and ZORI (`Zip_zori_uc_sfrcondomfr..._month.csv`, rent, monthly from **2015 only**). Per
  ZIP we average all available months in a year → one annual figure, deflate to 2024$.
  Geometry = generalized ZCTA polygons (`cb_2020_us_zcta520_500k`), filtered to the ZIPs
  Zillow assigns to the 7 counties (218 ZIPs). Because ZORI starts 2015, the Zillow **rent**
  slider floors at 2015 (no earlier data); Zillow **value** floors at 2010.
- **Cross-hatch (Shane's spec).** A Zillow ZIP that HAS the metric but lacks a value at the
  chosen start/end year (its series begins later) is **cross-hatched** (crossing-diagonal
  pattern, distinct from the vacant single-stripe) — distinguishing it from ZIPs with no data
  in *any* year (rendered as background). Per-metric `has_zhvi` / `has_zori` flags in the
  GeoJSON drive the three states (colored / hatched / background).

### County boundaries

- `build_county_boundaries.py` dissolves the shipped `tracts.geojson` by county FIPS (so the
  outlines align exactly with every other regional layer — no separate TIGER download).
  **Gotcha:** the shipped tracts are simplified (~10 m), so a naive dissolve leaves hundreds
  of sliver-holes (an unrenderable 600+-ring polygon). Fix = morphological close in a metric
  CRS (`buffer(150).buffer(-150)` in EPSG:3857), drop interior rings, then simplify → clean
  single-ring polygons. Dashed line + Noto Sans uppercase labels.

---

## Visual conventions Shane has settled on

These are the choices we've iterated to — don't volunteer changes unless asked.

### 3D value-per-acre layers
- **Palette (5 bins + transparent low-value):**
  - `< $100k/acre`: rendered as a 2D white fill at 1% opacity (a separate `fill` layer,
    not the extrusion, because MapLibre `fill-extrusion-opacity` is layer-wide). Clear
    bordered box in legend.
  - `$100k – $500k`: `#FED976` (pale yellow)
  - `$500k – $2M`:  `#FEA665` (soft orange)
  - `$2M – $10M`:   `#ED5752` (softer red)
  - `$10M – $50M`:  `#B5435A` (muted burgundy)
  - `$50M+`:        `#7E55B0` (muted purple)
- **Height scale:** 1 m / $25k/acre, linear.
- **Cap toggle:** default ON, capped at $100M/acre (= 4,000 m). One shared "Cap heights at
  $100M/acre" sub-checkbox (under the grouped toggle) drives the `valueCapEnabled` global and
  refreshes `fill-extrusion-height` on all three value layers. (The three are now one grouped
  toggle — "Property value per acre (3D)" with a Total / Improvement / Land radio, wired by
  `initValue3d` + `VALUE3D_MAP`; only the selected extrusion is shown at a time.)
- **Opacity:** 1.0 (fully opaque) — explicitly chosen.

### Land use (~17 categories)
- Single Family `#F5D6A8`, Townhouses / Condos `#E8A838`, Duplexes `#D4774E`,
  MF 3-4 / 5-19 / 20-49 / 50+ / Apartments (Unclassified) in escalating reds
  (`#C44E52` → `#5C0A0A`), Mobile Home `#BCAAA4`, Commercial `#4A90A4`,
  Industrial `#6B5B95`, **Institutional / Government `#37474F`** (Shane picked this
  specifically — a slate charcoal), Open Space `#7CB342`, Other `#C4BDB3`.
- Vacant variants reuse the parent color with a diagonal-stripe pattern overlay.

### Pop change bins (unchanged from original)
- BG: 7 bins (-300, -100, -50, ±50, 100, 300)
- Tract: 7 bins (-500, -300, -100, ±99, 100, 300, 500)
- Palette: deep red → light red → cream → light blue → dark navy.

### HU change bins (8 bins each, asymmetric)
- **BG:** Loss ≥150 / 50–149 / 25–49 / Stable ±25 / Gain 25–49 / 50–149 / 150–299 / ≥300
- **Tract:** Loss ≥250 / 150–249 / 50–149 / Stable ±49 / Gain 50–149 / 150–249 / 250–499 / ≥500
- Asymmetric because heavy losses are uncommon — top loss bucket caps low; gains extend high.

### Jobs density layer
- YlOrRd heatmap, jobs/acre bins: <1 / 1–5 / 5–15 / 15–50 / 50–100 / 100+.

### Rent / home-value change bins (diverging, real 2024$)
- Asymmetric diverging scheme (real housing costs mostly rose, so the gain side is finer):
  2 loss bins + a stable band + 3–4 gain bins. Reds = real decline, cream = stable, blues =
  real growth. Defined per (metric, mode) in `RV_SCHEME` (app.js) as explicit `{edges, labels,
  colors}` — easy to tune. `RV_PAL6` (6-bin) / `RV_PAL7` (7-bin) share the pop/HU ramp.
  - **Rent $ (6 bins):** Loss > $300 / $100–$300 / **Stable ±$100** / Gain $100–$300 / $300–$500 / > $500
  - **Rent % (7 bins):** Loss > 15% / 5–15% / **Stable ±5%** / Gain 5–15% / 15–30% / 30–50% / > 50%
  - **Value $ (7 bins):** Loss > $50k / $15k–$50k / **±$15k** / Gain $15k–$100k / $100k–$250k / $250k–$450k / > $450k
  - **Value % (7 bins):** Loss > 15% / 5–15% / **±5%** / Gain 5–25% / 25–60% / 60–100% / > 100%
- Labels use a consistent **Loss / Stable / Gain** naming. % bins were re-cut (was −20..20,
  which dumped most tracts into ">20%") to better spread the distribution.
- **No-data styling differs by source:** ACS tracts that are unreliable/unsampled render
  **gray** (`LOW_DENS_COLOR` `#B8B0A0`, matching the low-density tracts in the pop/HU layers),
  legend "No reliable estimate". Zillow ZIPs whose series starts after the chosen start render
  **crossing-diagonal hatch** (`cross-hatch` image), legend "No data before YYYY"; Zillow ZIPs
  with no record at all stay transparent (background).

---

## UX patterns settled on

- **Grouped layer toggles with sub-radios:** "Population change" and "Housing unit change"
  are each ONE parent checkbox with Block-group / Tract sub-radios (BG default). When the
  radio changes while the parent is checked, the layers swap. Implemented via
  `data-layer-group` attribute + `GROUP_MAP`.
- **Permits sub-controls** use the same pattern (SF / MF checkboxes + dual-slider).
- **Rent / home-value change** use a *custom* grouped controller (`initChangeLayers` in
  app.js, not the generic `GROUP_MAP`): one parent checkbox + a **source** radio (ACS/Zillow)
  + a **measure** radio ($/%) + a dual-thumb slider. Switching source swaps geometry
  (tract↔ZIP), the slider's min/max, and the legend; the slider/measure rebuild the color
  expression live. Each metric has its own `LAYERS.{rent,value}_change` entry (with a dynamic
  `legend()` + `layerIds`) so the legend + drag-reorder machinery still work; `applyLayerOrder`
  resolves those two `data-layer-group`s directly to their LAYERS key.
- **Grouped legend blocks.** Layers can set `legendGroup` + `legendRow()` + `legendOrder` to
  collapse into one legend block instead of one block each. City boundary, counties, and
  council districts share **"Jurisdiction boundaries"** (rows: City of Dallas, Counties, City
  Council Districts). `refreshLegend` renders the group where its first enabled layer falls.
- **Three reports** in the side panel: TOD Opportunity Areas, Council Districts,
  Value by Land Use.
  - First two use the existing `<select>` dropdown.
  - Land Use report hides the select and uses inline multi-select checkboxes plus a
    Total / Improvement / Taxable-land metric radio toggle. Per-row share % updates with
    the metric, and the bottom summary shows per-land-use average $/acre, sorted desc.
  - Default selection = all categories checked. `luInitialized` flag prevents the Clear
    button from immediately re-checking everything.
- **Popup conventions:** BG/tract change popups show absolute change AND % change.
  Land area row, 2010, 2020, Change with sign + percentage in parens.

---

## Working conventions

- Shane wants me to ship and explain, not to over-ask. Use `AskUserQuestion` only when
  the choice materially affects the work (palette, methodology, scope), not for trivia.
- Long-running work (downloads, big builds) should run in background via Bash
  `run_in_background: true` — Shane will see the task complete notification.
- For PowerShell pipelines, prefer the foreground Bash tool (which uses git-bash on his
  machine) rather than PowerShell — earlier PowerShell quirks (5.1 chaining, encoding) bit
  us multiple times.
- Census API key: `86cf199069aa31e1593fc7012564f38af501b568` — Shane's key tied to his
  Gmail. Pass via `CENSUS_API_KEY=... python build_pop_hu_geojsons.py`.
- Local preview workflow: `python -m http.server 8000` in this folder, then
  `http://localhost:8000` in a browser. Hard-refresh (Ctrl+Shift+R) after edits — browser
  caches GeoJSON aggressively.

---

## Current state

- **Branch:** `main`, pushed to `origin/main`. The June 2026 session shipped in commit
  `c53559f` "Add rent/value change layers, county boundaries, and UI refinements":
  - County boundaries; Median rent change + Median home value change (ACS tract 2012–2024 ↔
    Zillow ZIP, $/% + dual-thumb year slider, real 2024$); CPI-U deflation; ACS 2010→2020
    tract harmonization.
  - ACS reliability: the build ships estimate + MOE per cell; the webmap grays tract-years
    with MOE/est > 30% ("No reliable estimate", `#B8B0A0`) and shows est ± MOE for both years
    in popups with an exclusion note. Zillow late-starting series are cross-hatched.
  - UI: the three 3D value layers are one grouped "Property value per acre (3D)" toggle
    (Total / Improvement / Land radio); City/County/Council collapse into one "Jurisdiction
    boundaries" legend block.
- New build scripts (`build_cpi`, `build_county_boundaries`, `build_acs_rent_value`,
  `build_zillow_zip`) + data (`counties`, `acs_rent_value_tracts`, `zillow_zip` GeoJSON,
  `cpi_annual.json`). Raw Zillow CSVs are gitignored; `.claude/launch.json` is left untracked.
- **Working tree clean; all layers and reports wired and tested.**

---

## Known limitations / parking lot

- A few hundred parcels (~35) are unmatched between geometry and CAD records (recently-split
  parcels, non-real-property accounts). Negligible.
- The Denton extract slim file is regeneratable but slow (~3 min stream over 19 GB).
- The "Job density" tooltip's wage estimates are model-based, not measured — the BLS
  sector-weighted figure tends to run ~30% higher than the midpoint estimate. Both shown
  so the methodology is transparent.
- No "switch over" UX yet for when somebody points the map at a future LODES year or a
  newer DCAD roll — just re-run the build scripts.
- **ACS home value is top-coded** (~$1M older vintages, ~$2M newer); a few Highland Park-area
  tracts can show an inflated change that's partly a cap-bracket artifact. Negligible
  elsewhere.
- **Zillow ZIP = ZCTA proxy.** Zillow keys on USPS ZIPs; we render TIGER ZCTA polygons (the
  standard polygon proxy) — a handful of PO-box/point ZIPs have no ZCTA and are dropped.
- **MapLibre gotchas to remember:** (1) the demotiles glyph server only has **Noto Sans**
  (Open Sans 404s) — use `"text-font": ["Noto Sans Regular"]`. (2) `json.dump` writes bare
  `NaN` for pandas-missing strings, which the browser's `JSON.parse` rejects though Python
  tolerates it — coerce NaN→None and dump with `allow_nan=False`. (3) Dissolving simplified
  polygons needs a buffer-close or you get unrenderable many-ring geometry.
- The ACS rent/value build hits the Census API 13 yrs × 7 counties (~90 calls, ~70 s). The
  Zillow build reads the 122 MB ZHVI CSV (~a few seconds). Both regenerate from scratch.
