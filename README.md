# Dallas Housing & Land Use Web Map

Interactive web map for the City of Dallas. Toggle layers to overlay parcels,
zoning, council districts, DART rail station areas, and 2010–2020
population/housing-unit change at the block group and tract levels. Click any
feature for details.

## Layers

| Layer | Source | What it shows |
|---|---|---|
| **Parcels (neutral)** | DCAD | All ~292K Dallas parcels; click for assessor info |
| **Land use** | DCAD | Parcels colored by use (SF, MF tiers, commercial, etc.) |
| **Building FAR** | DCAD-derived | Parcels colored by floor-area ratio bin |
| **Base zoning** | City of Dallas | Color-coded by zoning category |
| **DART stations & areas** | DART, City | Rail stops and half-mile buffers |
| **Council districts** | City of Dallas | District boundaries with member info |
| **Pop change (BG)** | 2010 + 2020 Census | Block-group population change, 2010 → 2020 |
| **HU change (BG)** | 2010 + 2020 Census | Block-group housing unit change |
| **Pop change (tract)** | 2010 + 2020 Census | Tract-level population change |
| **HU change (tract)** | 2010 + 2020 Census | Tract-level housing unit change |

Parcels render only at zoom ≥ 12 to keep the city-wide view performant.

## Local preview

```bash
cd webmap
python -m http.server 8000
# then open http://localhost:8000
```

## Deploying to GitHub Pages

1. **Create a GitHub repo** (e.g. `dallas-housing-map`).
2. **Push the contents of this `webmap/` folder** to the root of the repo:
   ```bash
   cd webmap
   git init
   git add .
   git commit -m "Initial webmap"
   git branch -M main
   git remote add origin git@github.com:YOUR_USERNAME/dallas-housing-map.git
   git push -u origin main
   ```
3. **Enable Pages**: Settings → Pages → Source: `Deploy from a branch`, Branch: `main` / `/` (root).
4. The site will publish at `https://YOUR_USERNAME.github.io/dallas-housing-map/`.

## File layout

```
webmap/
├── index.html
├── style.css
├── app.js
├── data/
│   ├── parcels_nw.geojson      (~33 MB)   ← split into 4 quadrants
│   ├── parcels_ne.geojson      (~32 MB)
│   ├── parcels_sw.geojson      (~53 MB)
│   ├── parcels_se.geojson      (~41 MB)
│   ├── zoning.geojson          (~8 MB)
│   ├── council.geojson         (~1 MB)
│   ├── block_groups.geojson    (~2 MB)
│   ├── tracts.geojson          (~1 MB)
│   ├── rail_stops.geojson      (~20 KB)
│   └── station_areas.geojson   (~280 KB)
├── build_parcels_geojson.py    ← regenerate parcel files from DCAD source
└── README.md
```

Total payload: ~170 MB. Each individual file is well under GitHub's 100 MB
single-file limit. The parcel layer loads ~160 MB on first toggle (split into
4 parallel fetches) — first toggle takes a few seconds; after that it's cached
and instant.

### Why parcels are split into quadrants

GitHub has a 100 MB single-file limit. The full parcel layer is ~160 MB
GeoJSON, so it's split at lat 32.81 / lon -96.78 into NW/NE/SW/SE quadrants.
The webmap loads all four in parallel and merges them into one MapLibre source.

For a future performance upgrade, convert to PMTiles using
[tippecanoe](https://github.com/felt/tippecanoe) (one-time conversion):

```bash
tippecanoe -o parcels.pmtiles -zg --drop-densest-as-needed \
  parcels_nw.geojson parcels_ne.geojson parcels_sw.geojson parcels_se.geojson
```

PMTiles render smoothly at any zoom and the file would be ~50–80 MB. Tippecanoe
doesn't run natively on Windows; use WSL or Docker.

## Regenerating data

If new DCAD or Census data comes in, the relevant scripts are:

- **Parcels**: `build_parcels_geojson.py` (in `webmap/`) reads
  `GDPC Claude Stuff/PARCEL_CORE_MERGED.gpkg`
- **Census BG/Tract**: `pull_decennial_block_data.py` (in project root)
- **Zoning, council districts**: Already in repo as static files

## Color scheme

Population/housing-unit change uses a diverging palette anchored at zero:

| Bin | Color |
|---|---|
| Heavy loss | Dark red `#9E2A2B` |
| Loss | Red `#D64550` |
| Mild loss | Pink `#F4A6A6` |
| **Stable** | **Pale yellow `#FAF5C5`** |
| Mild gain | Light blue `#A6CDE3` |
| Gain | Blue `#4A90A4` |
| Heavy gain | Dark blue `#1D4F66` |
| Low density (<1,000 / sq mi) | Warm gray `#B8B0A0` |

Stable areas use yellow (rather than gray) so they stand out — stability in a
growing city is itself a finding.
