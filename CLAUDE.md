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
- **Boundaries:** City of Dallas, council districts, half-mile rail-station areas
- **Permits:** Single-family and multifamily building permits 2000–2024, year-range slider
- **Parcels:** Assessor parcel boundaries (popup with full DCAD/CCAD/DCAD attributes)
- **Zoning:** Base zoning categories
- **Land use:** DCAD/Collin/Denton land-use categories (collapsed to ~17 display categories;
  see palette below)
- **Building FAR:** 10-bin categorical floor-area-ratio map
- **Decade built:** Year-built decade by parcel
- **3D Value/Acre layers (three):** Total value, improvement value, taxable land value;
  fill-extrusion, linear 1 m / $25k/acre, default $100M/acre cap (toggle to uncap)
- **Pop change 2010–2020:** Single grouped toggle with Block-group / Tract radio
- **Housing-unit change 2010–2020:** Same grouped pattern
- **Job density (workplace) 2022:** LODES WAC, by tract, heatmap fill

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
    ├── station_reports.json, district_reports.json
    ├── land_use_value_summary.json
    ├── denton_dallas_slim.json        # extracted from huge protax JSON
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
- **Cap toggle:** default ON, capped at $100M/acre (= 4,000 m). Each of the three value
  layers shows a sub-checkbox "Cap heights at $100M/acre" that drives a shared
  `valueCapEnabled` global. Toggling any one syncs the others and refreshes
  `fill-extrusion-height` on all three layers.
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

---

## UX patterns settled on

- **Grouped layer toggles with sub-radios:** "Population change" and "Housing unit change"
  are each ONE parent checkbox with Block-group / Tract sub-radios (BG default). When the
  radio changes while the parent is checked, the layers swap. Implemented via
  `data-layer-group` attribute + `GROUP_MAP`.
- **Permits sub-controls** use the same pattern (SF / MF checkboxes + dual-slider).
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

## Current state (as of latest push)

- **Branch:** `main`, in sync with `origin/main` at `544088a` "Update parcels with
  Collin/Denton CAD data; add jobs and land-use layers".
- **Everything Shane and I have built is on GitHub.** A duplicate commit was created in
  this session locally and then soft-reset because the remote already had the same content
  (the laptop pushed it Jun 1 after the OneDrive recovery).
- **Working tree clean.**
- **All layers and reports listed above are wired and tested locally.**

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
