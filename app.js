/* Dallas Housing & Land Use webmap
 * MapLibre GL JS + OSM raster basemap.
 * Layers are GeoJSON loaded once and rendered as fill / line layers,
 * with toggle visibility and click popups.
 */

// ---- Map setup --------------------------------------------------------------

const DALLAS_CENTER = [-96.80, 32.78];

// Basemap definitions. We register all three sources up front and toggle
// which raster layer is visible. This avoids `setStyle` (which would tear
// down all overlay layers and require re-adding them).
const BASEMAPS = {
  light: {
    sourceId: "basemap-light-src",
    layerId: "basemap-light",
    tiles: [
      "https://a.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png",
      "https://b.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png",
      "https://c.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png",
    ],
    attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors © <a href="https://carto.com/attributions">CARTO</a>',
    maxzoom: 19,
  },
  osm: {
    sourceId: "basemap-osm-src",
    layerId: "basemap-osm",
    tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
    attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    maxzoom: 19,
  },
  satellite: {
    sourceId: "basemap-sat-src",
    layerId: "basemap-sat",
    tiles: [
      "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    ],
    attribution: 'Tiles © <a href="https://www.esri.com/">Esri</a>, Maxar, Earthstar Geographics, and the GIS User Community',
    maxzoom: 19,
  },
};

function buildInitialStyle() {
  const sources = {};
  const layers = [];
  for (const [key, b] of Object.entries(BASEMAPS)) {
    sources[b.sourceId] = {
      type: "raster",
      tiles: b.tiles,
      tileSize: 256,
      attribution: b.attribution,
      maxzoom: b.maxzoom,
    };
    layers.push({
      id: b.layerId,
      type: "raster",
      source: b.sourceId,
      layout: { visibility: key === "light" ? "visible" : "none" },
    });
  }
  return {
    version: 8,
    sources,
    layers,
    glyphs: "https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf",
  };
}

// Register the PMTiles protocol so vector sources can stream .pmtiles archives
// (parcels + buildings are served as vector tiles instead of giant GeoJSON).
if (typeof pmtiles !== "undefined") {
  maplibregl.addProtocol("pmtiles", new pmtiles.Protocol().tile);
}

const map = new maplibregl.Map({
  container: "map",
  style: buildInitialStyle(),
  center: DALLAS_CENTER,
  zoom: 10.2,
  maxZoom: 18,
});

function setBasemap(key) {
  if (!BASEMAPS[key]) return;
  for (const [k, b] of Object.entries(BASEMAPS)) {
    if (map.getLayer(b.layerId)) {
      map.setLayoutProperty(b.layerId, "visibility", k === key ? "visible" : "none");
    }
  }
}

map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), "top-right");
map.addControl(new maplibregl.ScaleControl({ unit: "imperial" }), "bottom-right");


// ---- Color palettes --------------------------------------------------------

const POP_CHANGE_COLORS = {
  bg: {
    edges: [-300, -100, -50, 50, 100, 300],
    palette: ["#9E2A2B", "#D64550", "#F4A6A6", "#FAF5C5",
              "#A6CDE3", "#4A90A4", "#1D4F66"],
    labels: ["Loss > 300", "Loss 100–300", "Loss 50–100",
             "Stable (±50)", "Gain 50–100", "Gain 100–300", "Gain > 300"],
  },
  tract: {
    edges: [-500, -300, -100, 100, 300, 500],
    palette: ["#9E2A2B", "#D64550", "#F4A6A6", "#FAF5C5",
              "#A6CDE3", "#4A90A4", "#1D4F66"],
    labels: ["Loss > 500", "Loss 300–499", "Loss 100–299",
             "Stable (±99)", "Gain 100–299", "Gain 300–499", "Gain > 500"],
  },
};

// Housing-unit change uses tighter bins than population change (each BG / tract
// typically has fewer housing units than residents).  3 loss bins + stable + 4
// gain bins = 8 colors.  The biggest-loss bucket is capped lower than the
// biggest-gain bucket because heavy losses are uncommon.
const HU_CHANGE_COLORS = {
  bg: {
    edges:   [-150, -50, -25, 25, 50, 150, 300],
    palette: ["#9E2A2B", "#D64550", "#F4A6A6", "#FAF5C5",
              "#A6CDE3", "#4A90A4", "#2E6F86", "#1D4F66"],
    labels: ["Loss ≥ 150", "Loss 50–149", "Loss 25–49",
             "Stable (±25)",
             "Gain 25–49", "Gain 50–149", "Gain 150–299", "Gain ≥ 300"],
  },
  tract: {
    edges:   [-250, -150, -50, 50, 150, 250, 500],
    palette: ["#9E2A2B", "#D64550", "#F4A6A6", "#FAF5C5",
              "#A6CDE3", "#4A90A4", "#2E6F86", "#1D4F66"],
    labels: ["Loss ≥ 250", "Loss 150–249", "Loss 50–149",
             "Stable (±49)",
             "Gain 50–149", "Gain 150–249", "Gain 250–499", "Gain ≥ 500"],
  },
};
const LOW_DENS_COLOR = "#B8B0A0";

// Jobs density (workplace jobs per acre). Uses a heatmap-style YlOrRd ramp.
const JOBS_BINS = {
  edges:   [1, 5, 15, 50, 100],
  palette: ["#FFF7BC", "#FEE391", "#FEC44F", "#FE9929", "#D95F0E", "#993404"],
  labels:  ["< 1", "1–5", "5–15", "15–50", "50–100", "100+"],
};
const JOBS_ZERO_COLOR = "#EEE9DF";
const LOW_DENS_LABEL = "Low density (<1,000 / sq mi)";

// Opportunity Insights — predicted adult earnings for kids who grew up in
// 25th-percentile-income families (Opportunity Atlas). Sequential YlGn:
// darker green = higher upward mobility. Bins tuned to the 7-county spread.
const OI_BINS = {
  edges:   [25000, 30000, 35000, 42000, 50000],
  palette: ["#FFFFCC", "#D9F0A3", "#ADDD8E", "#78C679", "#31A354", "#006837"],
  labels:  ["< $25k", "$25k–$30k", "$30k–$35k", "$35k–$42k", "$42k–$50k", "≥ $50k"],
};
const OI_NODATA = "#D9D2C5";

// Zoning palette — colors mirror the land-use map where possible:
//   Single-Family     → land-use SF yellow-tan
//   Townhouse/Cluster → land-use Townhouse orange
//   Multifamily       → land-use MF (3-4 units shade) red
//   Commercial        → land-use Commercial teal-blue
//   Industrial        → land-use Industrial purple
// New categories pick distinct hues that don't collide with the above.
const ZONING_COLORS = {
  "Single-Family":         "#F5D6A8",
  "Townhouse / Cluster":   "#E8A838",
  "Multifamily":           "#C44E52",
  "Mixed-Use":             "#B85C8E",
  "Community Area":        "#2D9B83",
  "Commercial":            "#4A90A4",
  "Industrial":            "#6B5B95",
  "Conservation District": "#C4A57B",
  "Planned Development":   "#888888",
  "Other":                 "#C4BDB3",
};

// ---- Base-zoning district selection -----------------------------------------
// One fill+outline pair, colored by category (ZONING_COLORS). A collapsible
// per-category menu (built from data/zoning_districts.json) lets the user filter
// the layer to individual zone_dist values. zoningState.selected = Set of checked
// districts, or null = show all.
const zoningState = { selected: null, catOf: {}, total: 0, built: false };
let zoningMenuReady = null;   // promise that resolves once the zoning district menu is built

function zoningFillColor() {
  const e = ["match", ["get", "category"]];
  Object.entries(ZONING_COLORS).forEach(([cat, c]) => e.push(cat, c));
  e.push("#C4BDB3");
  return e;
}

function zoningFilter() {
  if (!zoningState.selected || zoningState.selected.size >= zoningState.total) return null;
  return ["in", ["get", "zone_norm"], ["literal", [...zoningState.selected]]];   // base district (parentheticals merged)
}

function buildZoningLegend() {
  let cats = Object.keys(ZONING_COLORS);
  const filtered = zoningState.selected && zoningState.selected.size < zoningState.total;
  if (filtered) {
    const have = new Set();
    for (const zd of zoningState.selected) { const c = zoningState.catOf[zd]; if (c) have.add(c); }
    cats = cats.filter((c) => have.has(c));
  }
  const rows = cats.map((cat) =>
    `<div class="swatch-row"><span class="swatch" style="background:${ZONING_COLORS[cat]}"></span>${cat}</div>`).join("");
  const sub = filtered
    ? `<div class="muted" style="margin:-2px 0 5px 0">${zoningState.selected.size} of ${zoningState.total} districts shown</div>`
    : "";
  return `<div class="legend-block"><h3>Base Zoning</h3>${sub}${rows || '<div class="muted">No districts selected</div>'}</div>`;
}

// Apply the current district selection to the live layer (filter) + legend.
function applyZoningSelection() {
  if (LAYERS.zoning && LAYERS.zoning.enabled && map.getLayer("zoning-fill")) {
    const f = zoningFilter();
    map.setFilter("zoning-fill", f);
    map.setFilter("zoning-outline", f);
  }
  if (intersectState.on) applyLandUseSelection();   // intersection clips land use to this selection
  refreshLegend();
}

function recomputeZoningSelection() {
  const checked = [...document.querySelectorAll("#zoning-zone-menu .zone-cb:checked")].map((b) => b.dataset.zd);
  zoningState.selected = checked.length === zoningState.total ? null : new Set(checked);
  applyZoningSelection();
  scheduleHashWrite();
}

function syncZoningCatAll(catEl) {
  const all = catEl.querySelector(".zone-cat-all");
  const boxes = [...catEl.querySelectorAll(".zone-cb")];
  const on = boxes.filter((b) => b.checked).length;
  all.checked = on === boxes.length;
  all.indeterminate = on > 0 && on < boxes.length;
}

// Build the collapsible category -> district checkbox menu under "Base zoning".
async function initZoningMenu() {
  const host = document.getElementById("zoning-zone-menu");
  if (!host) return;
  let cats;
  try {
    cats = (await (await fetch("data/zoning_districts.json")).json()).categories;
  } catch (e) { return; }
  zoningState.catOf = {};
  zoningState.total = 0;
  for (const g of cats) for (const z of g.zones) { zoningState.catOf[z.zd] = g.category; zoningState.total++; }

  const actions = '<div class="zone-actions">' +
    '<button type="button" class="zone-act" data-act="all">Select all</button>' +
    '<span class="zone-act-sep">·</span>' +
    '<button type="button" class="zone-act" data-act="none">Deselect all</button></div>';
  host.innerHTML = actions + cats.map((g) => {
    const sw = ZONING_COLORS[g.category] || "#C4BDB3";
    const items = g.zones.map((z) => {
      const a = z.sqmi >= 0.01 ? z.sqmi.toFixed(2) : "<0.01";
      return `<label class="zone-item"><input type="checkbox" class="zone-cb" data-zd="${z.zd}" checked />` +
        `<span class="zone-text">${z.zd} <span class="zone-area">(${a} sq mi)</span></span></label>`;
    }).join("");
    return `<div class="zone-cat">
      <div class="zone-cat-head">
        <span class="zone-caret">▸</span>
        <input type="checkbox" class="zone-cat-all" checked title="Toggle all ${g.category}" />
        <span class="zone-sw" style="background:${sw}"></span>
        <span class="zone-cat-name">${g.category}</span>
        <span class="zone-cat-count">${g.zones.length}</span>
      </div>
      <div class="zone-cat-list">${items}</div>
    </div>`;
  }).join("");

  host.querySelectorAll(".zone-cat-head").forEach((head) => {
    head.addEventListener("click", (e) => {
      if (e.target.classList.contains("zone-cat-all")) return;   // checkbox handles itself
      const cat = head.parentElement;
      cat.classList.toggle("open");
      head.querySelector(".zone-caret").textContent = cat.classList.contains("open") ? "▾" : "▸";
    });
  });
  host.querySelectorAll(".zone-cat-all").forEach((cb) => {
    cb.addEventListener("change", () => {
      cb.closest(".zone-cat").querySelectorAll(".zone-cb").forEach((z) => { z.checked = cb.checked; });
      cb.indeterminate = false;
      recomputeZoningSelection();
    });
  });
  host.querySelectorAll(".zone-cb").forEach((cb) => {
    cb.addEventListener("change", () => {
      syncZoningCatAll(cb.closest(".zone-cat"));
      recomputeZoningSelection();
    });
  });
  host.querySelectorAll(".zone-act").forEach((b) => {
    b.addEventListener("click", () => {
      const on = b.dataset.act === "all";
      host.querySelectorAll(".zone-cb").forEach((z) => { z.checked = on; });
      host.querySelectorAll(".zone-cat-all").forEach((c) => { c.checked = on; c.indeterminate = false; });
      recomputeZoningSelection();
    });
  });
  zoningState.built = true;
}

// Land use definitions (data-driven). The `dataValue` is what the GeoJSON
// stores in the `land_use_cat` property; `label` is what we show in UI.
// Vacant entries reuse the non-vacant color and get a diagonal-stripe
// pattern overlay (set up below) instead of an outline.
const LAND_USE_DEFS = [
  { dataValue: "Single Family",                 label: "Single Family",         color: "#F5D6A8" },
  { dataValue: "Townhouses",                    label: "Townhouse",             color: "#E8A838" },
  { dataValue: "SFR Condominiums",              label: "Condominium",           color: "#E8A838" },
  { dataValue: "Duplexes",                      label: "Duplex",                color: "#D4774E" },
  { dataValue: "MF 3-4 Units",                  label: "MF 3-4 Units",          color: "#C44E52" },
  { dataValue: "MF 5-19 Units",                 label: "MF 5-19 Units",         color: "#A83232" },
  { dataValue: "MF 20-49 Units",                label: "MF 20-49 Units",        color: "#8B1A1A" },
  { dataValue: "MF 50+ Units",                  label: "MF 50+ Units",          color: "#5C0A0A" },
  { dataValue: "MF Apartments (Unclassified)",  label: "MF Apartments (Unclassified)", color: "#9E2B2B" },
  { dataValue: "Mobile Home",                   label: "Mobile Home",           color: "#BCAAA4" },
  { dataValue: "Commercial",                    label: "Commercial",            color: "#4A90A4" },
  { dataValue: "Industrial",                    label: "Industrial",            color: "#6B5B95" },
  { dataValue: "Institutional",                 label: "Institutional / Government", color: "#37474F" },
  { dataValue: "Vacant - Single Family",        label: "Vacant - Single Family", color: "#F5D6A8", vacant: true },
  { dataValue: "Vacant - Commercial",           label: "Vacant - Commercial",   color: "#4A90A4", vacant: true },
  { dataValue: "Vacant - Industrial",           label: "Vacant - Industrial",   color: "#6B5B95", vacant: true },
  { dataValue: "Open Space",                    label: "Open Space",            color: "#7CB342" },
  { dataValue: "Other",                         label: "Other",                 color: "#C4BDB3" },
];

const LAND_USE_LABEL_BY_VALUE = Object.fromEntries(
  LAND_USE_DEFS.map((d) => [d.dataValue, d.label])
);
const VACANT_DATA_VALUES = LAND_USE_DEFS.filter((d) => d.vacant).map((d) => d.dataValue);
const LAND_USE_COLOR_BY_VALUE = Object.fromEntries(LAND_USE_DEFS.map((d) => [d.dataValue, d.color]));

// ---- Land-use picker (mirrors the base-zoning district menu) ----------------
// Collapsible families -> land_use_cat values. The layer is filtered to the
// checked values exactly like the zoning layer is filtered to zone_norm.
const LAND_USE_GROUPS = [
  { category: "Residential", color: "#C44E52", values: [
    "Single Family", "Townhouses", "SFR Condominiums", "Duplexes",
    "MF 3-4 Units", "MF 5-19 Units", "MF 20-49 Units", "MF 50+ Units",
    "MF Apartments (Unclassified)", "Mobile Home"] },
  { category: "Commercial & Industrial", color: "#4A90A4", values: ["Commercial", "Industrial"] },
  { category: "Institutional / Government", color: "#37474F", values: ["Institutional"] },
  { category: "Vacant", color: "#BCA88F", values: [
    "Vacant - Single Family", "Vacant - Commercial", "Vacant - Industrial"] },
  { category: "Open space & Other", color: "#7CB342", values: ["Open Space", "Other"] },
];
const luState = { selected: null, total: 0, built: false };   // selected=null => all shown

function landUseFilter() {
  if (!luState.selected || luState.selected.size >= luState.total) return null;
  return ["in", ["get", "land_use_cat"], ["literal", [...luState.selected]]];
}

// Intersection: clip the land-use layer to the current Base-zoning picker selection.
// Uses "base_zone" (the City zone_norm) baked onto each parcel by build_pmtiles.py.
const intersectState = { on: false };
function zoneIntersectFilter() {
  if (!intersectState.on) return null;
  const sel = zoningState.selected;
  if (sel && sel.size === 0) return null;   // no districts chosen -> no zoning clip (don't blank the map)
  if (sel && sel.size < zoningState.total) {
    return ["in", ["get", "base_zone"], ["literal", [...sel]]];
  }
  return ["has", "base_zone"];   // all districts selected -> within the City zoning footprint
}
function landUseEffectiveFilter() {
  const parts = [landUseFilter(), zoneIntersectFilter()].filter(Boolean);
  if (!parts.length) return null;
  return parts.length === 1 ? parts[0] : ["all", ...parts];
}

function applyLandUseSelection() {
  if (LAYERS.land_use && LAYERS.land_use.enabled && map.getLayer("land-use-fill")) {
    const f = landUseEffectiveFilter();
    map.setFilter("land-use-fill", f);       // null clears the filter (show all)
    map.setFilter("land-use-outline", f);
    const vac = ["in", ["get", "land_use_cat"], ["literal", VACANT_DATA_VALUES]];
    map.setFilter("land-use-vacant-pattern", f ? ["all", vac, f] : vac);
  }
  refreshLegend();
}

function recomputeLandUseSelection() {
  const checked = [...document.querySelectorAll("#land-use-menu .zone-cb:checked")].map((b) => b.dataset.lu);
  luState.selected = checked.length === luState.total ? null : new Set(checked);
  applyLandUseSelection();
}

function syncLuCatAll(catEl) {
  const all = catEl.querySelector(".zone-cat-all");
  const boxes = [...catEl.querySelectorAll(".zone-cb")];
  const on = boxes.filter((b) => b.checked).length;
  all.checked = on === boxes.length;
  all.indeterminate = on > 0 && on < boxes.length;
}

function buildLandUseLegend() {
  const filtered = luState.selected && luState.selected.size < luState.total;
  const defs = filtered ? LAND_USE_DEFS.filter((d) => luState.selected.has(d.dataValue)) : LAND_USE_DEFS;
  const rows = defs.map((d) => {
    if (d.vacant) {
      return `<div class="swatch-row"><span class="swatch" style="background:` +
        `repeating-linear-gradient(45deg, #1A1A1A 0 0.7px, transparent 0.7px 5px), ${d.color}"></span>${d.label}</div>`;
    }
    return `<div class="swatch-row"><span class="swatch" style="background:${d.color}"></span>${d.label}</div>`;
  }).join("");
  const sub = filtered
    ? `<div class="muted" style="margin:-2px 0 5px 0">${luState.selected.size} of ${luState.total} land uses shown</div>`
    : "";
  let ixNote = "";
  if (intersectState.on) {
    const zsel = zoningState.selected;
    if (zsel && zsel.size === 0) {
      ixNote = `<div class="muted" style="margin:-2px 0 5px 0">◇ No zoning districts selected — showing all</div>`;
    } else {
      const label = (zsel && zsel.size < zoningState.total)
        ? (zsel.size <= 3 ? [...zsel].join(", ") : `${zsel.size} zoning districts`)
        : "the City zoning area";
      ixNote = `<div class="muted" style="margin:-2px 0 5px 0">◇ Within ${label}</div>`;
    }
  }
  return `<div class="legend-block"><h3>Land Use</h3>${sub}${ixNote}${rows || '<div class="muted">No land uses selected</div>'}</div>`;
}

// Build the collapsible family -> land-use checkbox menu under "Land use".
function initLandUseMenu() {
  const host = document.getElementById("land-use-menu");
  if (!host) return;
  luState.total = LAND_USE_GROUPS.reduce((n, g) => n + g.values.length, 0);
  const actions = '<div class="zone-actions">' +
    '<button type="button" class="zone-act" data-act="all">Select all</button>' +
    '<span class="zone-act-sep">·</span>' +
    '<button type="button" class="zone-act" data-act="none">Deselect all</button></div>';
  host.innerHTML = actions + LAND_USE_GROUPS.map((g) => {
    const items = g.values.map((v) =>
      `<label class="zone-item"><input type="checkbox" class="zone-cb" data-lu="${v}" checked />` +
      `<span class="zone-sw" style="background:${LAND_USE_COLOR_BY_VALUE[v]}"></span>` +
      `<span class="zone-text">${LAND_USE_LABEL_BY_VALUE[v] || v}</span></label>`).join("");
    return `<div class="zone-cat">
      <div class="zone-cat-head">
        <span class="zone-caret">▸</span>
        <input type="checkbox" class="zone-cat-all" checked title="Toggle all ${g.category}" />
        <span class="zone-sw" style="background:${g.color}"></span>
        <span class="zone-cat-name">${g.category}</span>
        <span class="zone-cat-count">${g.values.length}</span>
      </div>
      <div class="zone-cat-list">${items}</div>
    </div>`;
  }).join("");

  host.querySelectorAll(".zone-cat-head").forEach((head) => {
    head.addEventListener("click", (e) => {
      if (e.target.classList.contains("zone-cat-all")) return;
      const cat = head.parentElement;
      cat.classList.toggle("open");
      head.querySelector(".zone-caret").textContent = cat.classList.contains("open") ? "▾" : "▸";
    });
  });
  host.querySelectorAll(".zone-cat-all").forEach((cb) => {
    cb.addEventListener("change", () => {
      cb.closest(".zone-cat").querySelectorAll(".zone-cb").forEach((z) => { z.checked = cb.checked; });
      cb.indeterminate = false;
      recomputeLandUseSelection();
    });
  });
  host.querySelectorAll(".zone-cb").forEach((cb) => {
    cb.addEventListener("change", () => {
      syncLuCatAll(cb.closest(".zone-cat"));
      recomputeLandUseSelection();
    });
  });
  host.querySelectorAll(".zone-act").forEach((b) => {
    b.addEventListener("click", () => {
      const on = b.dataset.act === "all";
      host.querySelectorAll(".zone-cb").forEach((z) => { z.checked = on; });
      host.querySelectorAll(".zone-cat-all").forEach((c) => { c.checked = on; c.indeterminate = false; });
      recomputeLandUseSelection();
    });
  });
  const ix = document.getElementById("lu-intersect");
  if (ix) ix.addEventListener("change", () => {
    intersectState.on = ix.checked;
    applyLandUseSelection();
  });
  luState.built = true;
}

// FAR palette (consistent with station_area_analysis.py)
const FAR_BINS = [
  "No Building", "< 0.25", "0.25 - 0.49", "0.5 - 0.99", "1.0 - 1.49",
  "1.5 - 2.0", "2.0 - 2.9", "3.0 - 4.9", "5.0 - 9.9", "10+",
];
const FAR_COLORS = {
  "No Building":  "#B8B0A0",
  "< 0.25":       "#22ecf0",
  "0.25 - 0.49":  "#14b1fd",
  "0.5 - 0.99":   "#2c7fdb",
  "1.0 - 1.49":   "#6539b3",
  "1.5 - 2.0":    "#a032b2",
  "2.0 - 2.9":    "#d124a9",
  "3.0 - 4.9":    "#fd4dab",
  "5.0 - 9.9":    "#ff7911",
  "10+":          "#ffdd00",
};

// Decade-built palette — same cool-to-warm progression as the FAR colors
// (older = cool, newer = warm), extended with a deep red for the 2020s.
// "No data" covers year_built = 0 or pre-1850 implausible values.
const DECADE_BINS = [
  { label: "No data",        color: "#B8B0A0" },
  { label: "Pre-1940",       color: "#22ecf0" },
  { label: "1940s",          color: "#14b1fd" },
  { label: "1950s",          color: "#2c7fdb" },
  { label: "1960s",          color: "#6539b3" },
  { label: "1970s",          color: "#a032b2" },
  { label: "1980s",          color: "#d124a9" },
  { label: "1990s",          color: "#fd4dab" },
  { label: "2000s",          color: "#ff7911" },
  { label: "2010 or later",  color: "#ffdd00" },
];

// Improvement / land value ratio bins (DCAD as-reported impr_val / land_val).
// Same cool-to-warm palette as the FAR / Decade-built layers; index 0 (gray) is
// the no-land-value sentinel (ratio undefined).
const ILR_BINS = [
  { label: "No land value", color: "#B8B0A0" },
  { label: "< 0.25",        color: "#22ecf0" },
  { label: "0.25 - 0.49",   color: "#14b1fd" },
  { label: "0.5 - 0.99",    color: "#2c7fdb" },
  { label: "1.0 - 1.49",    color: "#6539b3" },
  { label: "1.5 - 1.99",    color: "#a032b2" },
  { label: "2.0 - 2.99",    color: "#d124a9" },
  { label: "3.0 - 3.99",    color: "#fd4dab" },
  { label: "4.0 - 4.99",    color: "#ff7911" },
  { label: "≥ 5.0",         color: "#ffdd00" },
];

// Value-per-acre bins (used for 3D fill-extrusion layers). Color thresholds
// chosen to match the ordinal feel of the FAR palette. Extrusion height is
// linear: 1 metre per $100,000 of value per acre.
// Anything below this value/acre is rendered transparent (and at zero height)
// so wide, non-privately-owned parcels — lakes, levees, ROW, parks, etc. —
// don't clutter the map with low-info bright blue swaths.
const LOW_VALUE_THRESHOLD = 100_000;
const TRANSPARENT_COLOR = "rgba(0,0,0,0)";

const VALUE_PER_ACRE_BINS = [
  { upper: 1_000_000,  label: "$100k – $1M",  color: "#FEE49E" },  // lighter pale yellow
  { upper: 2_000_000,  label: "$1M – $2M",    color: "#FEBE8C" },  // lighter soft orange
  { upper: 5_000_000,  label: "$2M – $5M",    color: "#F0827E" },  // lighter red
  { upper: 20_000_000, label: "$5M – $20M",   color: "#B5435A" },  // muted burgundy (dark red)
  { upper: Infinity,   label: "$20M+",        color: "#7E55B0" },  // muted purple
];
// Land value per acre runs much lower than total/improvement value, so it uses its
// own narrower bins (same 5-color palette).
const LAND_VALUE_BINS = [
  { upper: 500_000,   label: "$100k – $500k", color: "#FEE49E" },
  { upper: 1_000_000, label: "$500k – $1M",   color: "#FEBE8C" },
  { upper: 2_000_000, label: "$1M – $2M",     color: "#F0827E" },
  { upper: 5_000_000, label: "$2M – $5M",     color: "#B5435A" },
  { upper: Infinity,  label: "$5M+",          color: "#7E55B0" },
];
// Linear extrusion: 1 m per $25k/acre, capped at the height that $300M/acre
// would produce ($300M / $25k = 12,000 m).
const VALUE_HEIGHT_PER_M    = 25_000;
const VALUE_HEIGHT_CAP_VALUE = 100_000_000;
const VALUE_HEIGHT_CAP_M     = VALUE_HEIGHT_CAP_VALUE / VALUE_HEIGHT_PER_M;   // 4,000 m
// Minimum parcel area to render — drops TIF / placeholder accounts that
// have a few sq ft of geometry and produce absurd per-acre numbers.
const MIN_RENDER_AREA_SQFT = 100;

function valuePerAcreColorExpr(propName, bins = VALUE_PER_ACRE_BINS) {
  // Anything below the low-value threshold (including value=0 "no data") is
  // returned transparent; positive values at/above threshold step through the
  // binned palette.
  const expr = [
    "step", ["coalesce", ["get", propName], 0],
    TRANSPARENT_COLOR,
    LOW_VALUE_THRESHOLD, bins[0].color,
  ];
  for (let i = 0; i < bins.length - 1; i++) {
    expr.push(bins[i].upper, bins[i + 1].color);
  }
  return expr;
}

// Global state: whether the $100M/acre height cap is on (true by default).
// Toggleable via the per-layer "Cap heights at $100M/acre" sub-checkbox.
let valueCapEnabled = true;

function valuePerAcreHeightExpr(propName) {
  const v = ["coalesce", ["get", propName], 0];
  const scaled = ["/", v, VALUE_HEIGHT_PER_M];
  const heightExpr = valueCapEnabled
    ? ["min", VALUE_HEIGHT_CAP_M, scaled]
    : scaled;
  return [
    "case",
    ["<", v, LOW_VALUE_THRESHOLD], 0,
    heightExpr,
  ];
}

// Rebuild fill-extrusion-height for all currently-added value layers when the
// cap toggle changes. We have to call setPaintProperty on each layer because
// the expression is captured at addLayer() time.
function refreshValueHeightExprs() {
  const layerKeys = ["value_per_acre", "impr_per_acre", "land_per_acre"];
  const propMap = {
    value_per_acre: "value_per_acre",
    impr_per_acre:  "impr_per_acre",
    land_per_acre:  "land_per_acre",
  };
  for (const k of layerKeys) {
    const layerId = `${k.replace(/_per_acre$/, "-per-acre")}-3d`;
    if (!map.getLayer(layerId)) continue;
    map.setPaintProperty(layerId, "fill-extrusion-height", valuePerAcreHeightExpr(propMap[k]));
  }
}

function makeValuePerAcreLayer(layerKey, propName, label, bins = VALUE_PER_ACRE_BINS) {
  const fillLayerId    = `${layerKey}-3d`;
  const lowLayerId     = `${layerKey}-low`;
  return {
    label,
    sourceId: "parcels-src",
    sourceFile: null,
    layerIds: [lowLayerId, fillLayerId],
    customLoad: async () => {
      await ensureParcelsSource();
    },
    addLayers: () => {
      // Low-value parcels: rendered as a flat 2D fill at 1% opacity. We use
      // a fill layer instead of fill-extrusion because fill-extrusion-opacity
      // is layer-wide and can't be set per-feature; a plain `fill` layer
      // supports both per-feature alpha and a low layer-level opacity.
      map.addLayer({
        id: lowLayerId,
        type: "fill",
        source: "parcels-src",
        "source-layer": "parcels",
        minzoom: 11,
        filter: ["all",
          ["<", ["coalesce", ["get", propName], 0], LOW_VALUE_THRESHOLD],
          [">=", ["coalesce", ["get", "area_feet"], 0], MIN_RENDER_AREA_SQFT],
        ],
        paint: {
          "fill-color": "#FFFFFF",
          "fill-opacity": 0.01,
        },
      }, beneathTopLayers());

      // Value parcels: 3D extrusion at full opacity.
      map.addLayer({
        id: fillLayerId,
        type: "fill-extrusion",
        source: "parcels-src",
        "source-layer": "parcels",
        minzoom: 11,
        filter: ["all",
          [">=", ["coalesce", ["get", propName], 0], LOW_VALUE_THRESHOLD],
          [">=", ["coalesce", ["get", "area_feet"], 0], MIN_RENDER_AREA_SQFT],
        ],
        paint: {
          "fill-extrusion-color": valuePerAcreColorExpr(propName, bins),
          "fill-extrusion-height": valuePerAcreHeightExpr(propName),
          "fill-extrusion-base": 0,
          "fill-extrusion-opacity": 1.0,
        },
      }, beneathTopLayers());
    },
    popup: (props) => parcelPopup(props),
    clickLayer: [fillLayerId, lowLayerId],
    legend: () => {
      const rows = bins.map((b) =>
        `<div class="swatch-row"><span class="swatch" style="background:${b.color}"></span>${b.label}</div>`).join("");
      const lowRow = `<div class="swatch-row"><span class="swatch" style="background:transparent;border:1px solid #888"></span>&lt; $100k / acre</div>`;
      return `<div class="legend-block">
        <h3>${label}</h3>
        ${lowRow}
        ${rows}
        <div class="muted" style="margin-top:4px">Height: 1 m per $25k/acre${valueCapEnabled ? ", capped at $100M/acre (4,000 m)" : " (uncapped)"}. Right-drag or shift-drag to tilt for 3D.</div>
        <div class="muted legend-vintage">DCAD 2025 Certified</div>
      </div>`;
    },
  };
}

// 2D companion to makeValuePerAcreLayer: same value-per-acre data and binned
// palette, but a flat choropleth fill (no extrusion / height / cap). Parcels
// below $100k/acre (and tiny placeholder geometry) are not rendered.
function make2DValuePerAcreLayer(layerKey, propName, label, bins = VALUE_PER_ACRE_BINS) {
  const fillId = `${layerKey}-2d`;
  return {
    label,
    minzoom: 11,
    sourceId: "parcels-src",
    sourceFile: null,
    layerIds: [fillId],
    customLoad: async () => {
      await ensureParcelsSource();
    },
    addLayers: () => {
      map.addLayer({
        id: fillId,
        type: "fill",
        source: "parcels-src",
        "source-layer": "parcels",
        minzoom: 11,
        filter: ["all",
          [">=", ["coalesce", ["get", propName], 0], LOW_VALUE_THRESHOLD],
          [">=", ["coalesce", ["get", "area_feet"], 0], MIN_RENDER_AREA_SQFT]],
        paint: {
          "fill-color": valuePerAcreColorExpr(propName, bins),
          "fill-opacity": ["interpolate", ["linear"], ["zoom"], 11, 0.6, 14, 0.85],
        },
      }, beneathTopLayers());
    },
    popup: (props) => parcelPopup(props),
    clickLayer: fillId,
    legend: () => {
      const rows = bins.map((b) =>
        `<div class="swatch-row"><span class="swatch" style="background:${b.color}"></span>${b.label}</div>`).join("");
      const lowRow = `<div class="swatch-row"><span class="swatch" style="background:transparent;border:1px solid #888"></span>&lt; $100k / acre</div>`;
      return `<div class="legend-block"><h3>${label}</h3>${lowRow}${rows}<div class="muted legend-vintage">DCAD 2025 Certified</div></div>`;
    },
  };
}


function popChangeFillColor(propertyName, scheme) {
  // Build a generic ["step", ...] expression for an N-bin palette.
  // (Used by both pop-change [7 bins] and hu-change [8 bins].)
  const stepExpr = ["step", ["get", propertyName], scheme.palette[0]];
  for (let i = 0; i < scheme.edges.length; i++) {
    stepExpr.push(scheme.edges[i], scheme.palette[i + 1]);
  }
  return [
    "case",
    ["==", ["get", "low_density"], true],
    LOW_DENS_COLOR,
    stepExpr,
  ];
}


// ---- Diagonal-stripe pattern (used as fill-pattern on vacant land use) ----

function ensureDiagonalPatternImage() {
  if (map.hasImage("diag-stripes")) return;
  const size = 8;
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = size;
  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, size, size);
  ctx.strokeStyle = "#1A1A1A";  // closer to black than the previous #333
  ctx.lineWidth = 0.7;          // 30% narrower than the previous 1.0
  ctx.lineCap = "square";
  // Three parallel diagonal strokes that tile cleanly.
  ctx.beginPath();
  ctx.moveTo(-1,         size + 1);   ctx.lineTo(size + 1,         -1);
  ctx.moveTo(-1 - size,  size + 1);   ctx.lineTo(1,                -1);
  ctx.moveTo(size - 1,   size + 1);   ctx.lineTo(2 * size + 1,     -1);
  ctx.stroke();
  const img = ctx.getImageData(0, 0, size, size);
  map.addImage("diag-stripes", img, { pixelRatio: 1 });
}


// ---- Parcels: load all 4 quadrants in parallel and merge into one source ---

const PARCEL_QUADRANTS = ["nw", "ne", "sw", "se"];
let parcelsCombined = null;

async function loadParcelsCombined() {
  if (parcelsCombined) return parcelsCombined;
  console.log("Loading parcel quadrants...");
  const fetches = PARCEL_QUADRANTS.map((q) =>
    fetch(`data/parcels_${q}.geojson`).then((r) => r.json())
  );
  const parts = await Promise.all(fetches);
  // flatMap (not features.push(...p.features)) — spreading 100k+ elements as
  // call arguments overflows the stack.
  const features = parts.flatMap((p) => p.features);
  parcelsCombined = { type: "FeatureCollection", features };
  console.log(`Loaded ${features.length.toLocaleString()} parcels.`);
  return parcelsCombined;
}

// Ensure the shared parcels VECTOR source (PMTiles) exists. Every parcel-based
// layer (value 3D/2D, land use, FAR, decade, imp/land ratio, parcels) shares it.
// loadParcelsCombined() above is retained as a GeoJSON fallback but no longer wired.
async function ensureParcelsSource() {
  if (!map.getSource("parcels-src")) {
    map.addSource("parcels-src", { type: "vector", url: "pmtiles://data/parcels.pmtiles" });
  }
}


// ---- Layer registry --------------------------------------------------------

const LAYERS = {
  council: {
    label: "Council districts",
    sourceId: "council-src",
    sourceFile: "data/council.geojson",
    layerIds: ["council-fill", "council-line"],
    addLayers: () => {
      map.addLayer({
        id: "council-fill",
        type: "fill",
        source: "council-src",
        paint: { "fill-color": "#888888", "fill-opacity": 0 },
      });
      map.addLayer({
        id: "council-line",
        type: "line",
        source: "council-src",
        paint: { "line-color": "#2A2A2A", "line-width": 1.4, "line-opacity": 0.8 },
      });
    },
    popup: (props) => `
      <div class="popup-title">Council District ${props.district}</div>
      <div class="popup-row"><span class="label">Member</span><span class="value">${props.council_member ?? ""}</span></div>
      <div class="popup-row" style="margin-top:8px">
        <a href="#" onclick="openReportPanel('district', '${props.district}'); return false;"
           style="color:#4A90A4;font-weight:500">Show district report →</a>
      </div>
    `,
    clickLayer: null,   // councilmember popup disabled — that info lives in the Council District report
    legendGroup: "Jurisdiction boundaries",
    legendOrder: 3,
    legendRow: () => `<div class="swatch-row"><span class="line-swatch" style="border-top-color:#2A2A2A"></span>City Council Districts</div>`,
  },

  city_boundary: {
    label: "City boundary",
    sourceId: "city-boundary-src",
    sourceFile: "data/city_boundary.geojson",
    layerIds: ["city-boundary-line"],
    addLayers: () => {
      map.addLayer({
        id: "city-boundary-line",
        type: "line",
        source: "city-boundary-src",
        paint: { "line-color": "#222222", "line-width": 2.4 },
      });
    },
    popup: () => `<div class="popup-title">City of Dallas</div>`,
    clickLayer: null,
    legendGroup: "Jurisdiction boundaries",
    legendOrder: 1,
    legendRow: () => `<div class="swatch-row"><span class="line-swatch" style="border-top-width:2px;border-top-color:#222222"></span>City of Dallas</div>`,
  },

  zoning: {
    label: "Base zoning",
    sourceId: "zoning-src",
    sourceFile: "data/zoning.geojson",
    layerIds: ["zoning-fill", "zoning-outline"],
    addLayers: () => {
      map.addLayer({
        id: "zoning-fill",
        type: "fill",
        source: "zoning-src",
        paint: { "fill-color": zoningFillColor(), "fill-opacity": 0.65 },
      }, beneathTopLayers());
      map.addLayer({
        id: "zoning-outline",
        type: "line",
        source: "zoning-src",
        paint: { "line-color": "#FFFFFF", "line-width": 0.3, "line-opacity": 0.5 },
      }, beneathTopLayers());
      const f = zoningFilter();              // honor the currently-selected mode
      map.setFilter("zoning-fill", f);
      map.setFilter("zoning-outline", f);
    },
    popup: (props) => `
      <div class="popup-title">Zoning: ${props.zone_dist ?? ""}</div>
      <div class="popup-row"><span class="label">Category</span><span class="value">${props.category ?? ""}</span></div>
      ${props.common_name ? `<div class="popup-row"><span class="label">Name</span><span class="value">${props.common_name}</span></div>` : ""}
      ${props.pd_num ? `<div class="popup-row"><span class="label">PD #</span><span class="value">${props.pd_num}</span></div>` : ""}
      ${props.cd_num ? `<div class="popup-row"><span class="label">CD #</span><span class="value">${props.cd_num}</span></div>` : ""}
    `,
    clickLayer: "zoning-fill",
    legend: () => buildZoningLegend(),
  },

  parcels: {
    label: "Parcels (neutral)",
    minzoom: 12,
    sourceId: "parcels-src",
    sourceFile: null, // loaded separately via loadParcelsCombined()
    layerIds: ["parcels-fill", "parcels-outline"],
    customLoad: async () => {
      await ensureParcelsSource();
    },
    addLayers: () => {
      // Invisible fill — preserved so clicks still register on parcels
      map.addLayer({
        id: "parcels-fill",
        type: "fill",
        source: "parcels-src",
        "source-layer": "parcels",
        minzoom: 12,
        paint: {
          "fill-color": "#D9CFC0",
          "fill-opacity": 0,
        },
      }, beneathTopLayers());
      map.addLayer({
        id: "parcels-outline",
        type: "line",
        source: "parcels-src",
        "source-layer": "parcels",
        minzoom: 12,
        paint: {
          "line-color": "#5A5048",
          "line-width": [
            "interpolate", ["linear"], ["zoom"],
            12, 0.2, 13, 0.4, 16, 1.0,
          ],
          "line-opacity": 0.85,
        },
      }, beneathTopLayers());
    },
    popup: (props) => parcelPopup(props),
    clickLayer: "parcels-fill",
    legend: () => `
      <div class="legend-block">
        <h3>Parcels</h3>
        <div class="swatch-row"><span class="line-swatch" style="border-top-color:#5A5048;border-top-width:2px"></span>Parcel boundary (zoom in to see them)</div>
        <div class="muted" style="margin-top:4px">Click any parcel for assessor info.</div>
      </div>`,
  },

  land_use: {
    label: "Land use",
    minzoom: 11,
    sourceId: "parcels-src",
    sourceFile: null,
    layerIds: ["land-use-fill", "land-use-vacant-pattern", "land-use-outline"],
    customLoad: async () => {
      await ensureParcelsSource();
      ensureDiagonalPatternImage();
    },
    addLayers: () => {
      const colorExpr = ["match", ["get", "land_use_cat"]];
      LAND_USE_DEFS.forEach((d) => {
        if (d.dataValue !== "Other") colorExpr.push(d.dataValue, d.color);
      });
      colorExpr.push(LAND_USE_LABEL_BY_VALUE["Other"] === "Other"
        ? LAND_USE_DEFS.find((d) => d.dataValue === "Other").color
        : "#C4BDB3");

      // Respect the land-use picker selection (and any zoning intersection) at (re)add time.
      const luF = landUseEffectiveFilter();
      const luVac = ["in", ["get", "land_use_cat"], ["literal", VACANT_DATA_VALUES]];

      // Base fill — every parcel colored by category (vacant uses the same
      // base color as its non-vacant counterpart).
      const luFill = {
        id: "land-use-fill",
        type: "fill",
        source: "parcels-src",
        "source-layer": "parcels",
        minzoom: 11,
        paint: {
          "fill-color": colorExpr,
          "fill-opacity": ["interpolate", ["linear"], ["zoom"], 11, 0.6, 14, 0.85],
        },
      };
      if (luF) luFill.filter = luF;
      map.addLayer(luFill, beneathTopLayers());

      // Diagonal-stripe pattern overlay applied ONLY to vacant categories still
      // selected. Transparent background lets the underlying base color show.
      map.addLayer({
        id: "land-use-vacant-pattern",
        type: "fill",
        source: "parcels-src",
        "source-layer": "parcels",
        minzoom: 11,
        filter: luF ? ["all", luVac, luF] : luVac,
        paint: {
          "fill-pattern": "diag-stripes",
          "fill-opacity": ["interpolate", ["linear"], ["zoom"], 11, 0.85, 14, 1.0],
        },
      }, beneathTopLayers());

      const luOutline = {
        id: "land-use-outline",
        type: "line",
        source: "parcels-src",
        "source-layer": "parcels",
        minzoom: 14,
        paint: { "line-color": "#FFFFFF", "line-width": 0.2, "line-opacity": 0.4 },
      };
      if (luF) luOutline.filter = luF;
      map.addLayer(luOutline, beneathTopLayers());
    },
    popup: (props) => parcelPopup(props),
    clickLayer: "land-use-fill",
    legend: () => buildLandUseLegend(),
  },

  far_footprint: {
    label: "Building floor-area ratio (FAR)",
    minzoom: 11,
    sourceId: "parcels-src",
    sourceFile: null,
    layerIds: ["far-foot-fill", "far-foot-outline"],
    customLoad: async () => {
      await ensureParcelsSource();
    },
    addLayers: () => {
      // Numeric step on foot_far, reusing the FAR palette. Each parcel's CAD floor
      // area is redistributed across the building footprints overlapping it, so a
      // building that spans several lots lights up every lot it sits on.
      const EDGE = { "< 0.25": 0.0001, "0.25 - 0.49": 0.25, "0.5 - 0.99": 0.5,
        "1.0 - 1.49": 1.0, "1.5 - 2.0": 1.5, "2.0 - 2.9": 2.0, "3.0 - 4.9": 3.0,
        "5.0 - 9.9": 5.0, "10+": 10.0 };
      const expr = ["step", ["coalesce", ["get", "foot_far"], 0], FAR_COLORS["No Building"]];
      ["< 0.25", "0.25 - 0.49", "0.5 - 0.99", "1.0 - 1.49", "1.5 - 2.0",
       "2.0 - 2.9", "3.0 - 4.9", "5.0 - 9.9", "10+"].forEach((b) => expr.push(EDGE[b], FAR_COLORS[b]));
      map.addLayer({
        id: "far-foot-fill",
        type: "fill",
        source: "parcels-src",
        "source-layer": "parcels",
        minzoom: 11,
        paint: {
          "fill-color": expr,
          "fill-opacity": ["interpolate", ["linear"], ["zoom"], 11, 0.6, 14, 0.85],
        },
      }, beneathTopLayers());
      map.addLayer({
        id: "far-foot-outline",
        type: "line",
        source: "parcels-src",
        "source-layer": "parcels",
        minzoom: 14,
        paint: { "line-color": "#FFFFFF", "line-width": 0.2, "line-opacity": 0.4 },
      }, beneathTopLayers());
    },
    popup: (props) => parcelPopup(props),
    clickLayer: "far-foot-fill",
    legend: () => {
      const rows = FAR_BINS.map((bin) =>
        `<div class="swatch-row"><span class="swatch" style="background:${FAR_COLORS[bin]}"></span>FAR ${bin}</div>`).join("");
      return `<div class="legend-block"><h3>Building floor-area ratio (FAR)</h3>${rows}` +
        `<div class="muted" style="margin-top:4px">CAD floor area split across the building footprints overlapping each lot.</div></div>`;
    },
  },

  decade_built: {
    label: "Decade structure built",
    minzoom: 11,
    sourceId: "parcels-src",
    sourceFile: null,
    layerIds: ["decade-built-fill", "decade-built-outline"],
    customLoad: async () => {
      await ensureParcelsSource();
    },
    addLayers: () => {
      // year_built < 1850 (includes the 0-coded "no data" bucket) → gray.
      // Otherwise step through the decade thresholds.
      const colorExpr = [
        "case",
        ["<", ["get", "year_built"], 1850],
        DECADE_BINS[0].color,  // No data
        ["step", ["get", "year_built"],
          DECADE_BINS[1].color,  // 1850-1939: Pre-1940
          1940, DECADE_BINS[2].color,
          1950, DECADE_BINS[3].color,
          1960, DECADE_BINS[4].color,
          1970, DECADE_BINS[5].color,
          1980, DECADE_BINS[6].color,
          1990, DECADE_BINS[7].color,
          2000, DECADE_BINS[8].color,
          2010, DECADE_BINS[9].color,  // 2010 or later
        ],
      ];

      map.addLayer({
        id: "decade-built-fill",
        type: "fill",
        source: "parcels-src",
        "source-layer": "parcels",
        minzoom: 11,
        paint: {
          "fill-color": colorExpr,
          "fill-opacity": [
            "interpolate", ["linear"], ["zoom"],
            11, 0.6, 14, 0.85,
          ],
        },
      }, beneathTopLayers());
      map.addLayer({
        id: "decade-built-outline",
        type: "line",
        source: "parcels-src",
        "source-layer": "parcels",
        minzoom: 14,
        paint: { "line-color": "#FFFFFF", "line-width": 0.2, "line-opacity": 0.4 },
      }, beneathTopLayers());
    },
    popup: (props) => parcelPopup(props),
    clickLayer: "decade-built-fill",
    legend: () => {
      const rows = DECADE_BINS.map((d) =>
        `<div class="swatch-row"><span class="swatch" style="background:${d.color}"></span>${d.label}</div>`).join("");
      return `<div class="legend-block"><h3>Decade structure built</h3>${rows}</div>`;
    },
  },

  imp_land_ratio: {
    label: "Improvement / land value ratio",
    minzoom: 11,
    sourceId: "parcels-src",
    sourceFile: null,
    layerIds: ["imp-land-ratio-fill", "imp-land-ratio-outline"],
    customLoad: async () => {
      await ensureParcelsSource();
    },
    addLayers: () => {
      // ratio = DCAD improvement value / land value (as reported).
      // land_val <= 0 -> -1 sentinel (no land value); missing impr -> 0.
      const ratio = ["case", [">", ["get", "land_val"], 0],
        ["/", ["coalesce", ["get", "impr_val"], 0], ["get", "land_val"]], -1];
      const colorExpr = ["step", ratio,
        ILR_BINS[0].color,          // ratio < 0  (sentinel: no land value)
        0,    ILR_BINS[1].color,    // 0    – 0.25
        0.25, ILR_BINS[2].color,    // 0.25 – 0.5
        0.5,  ILR_BINS[3].color,    // 0.5  – 1.0
        1.0,  ILR_BINS[4].color,    // 1.0  – 1.5
        1.5,  ILR_BINS[5].color,    // 1.5  – 2.0
        2.0,  ILR_BINS[6].color,    // 2.0  – 3.0
        3.0,  ILR_BINS[7].color,    // 3.0  – 4.0
        4.0,  ILR_BINS[8].color,    // 4.0  – 5.0
        5.0,  ILR_BINS[9].color];   // >= 5.0
      // Hide parcels under $100k/acre total value (like the 3D value layer) and
      // Institutional / Government parcels (their assessed split is unreliable).
      const valFilter = ["all",
        [">=", ["coalesce", ["get", "value_per_acre"], 0], 100000],
        ["!=", ["coalesce", ["get", "land_use_cat"], ""], "Institutional"]];
      map.addLayer({
        id: "imp-land-ratio-fill",
        type: "fill",
        source: "parcels-src",
        "source-layer": "parcels",
        minzoom: 11,
        filter: valFilter,
        paint: {
          "fill-color": colorExpr,
          "fill-opacity": ["interpolate", ["linear"], ["zoom"], 11, 0.6, 14, 0.85],
        },
      }, beneathTopLayers());
      map.addLayer({
        id: "imp-land-ratio-outline",
        type: "line",
        source: "parcels-src",
        "source-layer": "parcels",
        minzoom: 14,
        filter: valFilter,
        paint: { "line-color": "#FFFFFF", "line-width": 0.2, "line-opacity": 0.4 },
      }, beneathTopLayers());
    },
    popup: (props) => parcelPopup(props),
    clickLayer: "imp-land-ratio-fill",
    legend: () => {
      const rows = ILR_BINS.map((d) =>
        `<div class="swatch-row"><span class="swatch" style="background:${d.color}"></span>${d.label}</div>`).join("");
      return `<div class="legend-block"><h3>Improvement / land value ratio</h3>${rows}</div>`;
    },
  },

  // 3D value-per-acre layers (Urban3-style). Each renders parcels as
  // `fill-extrusion` polygons with height proportional to the chosen
  // value-per-acre property and color binned by value.
  value_per_acre: makeValuePerAcreLayer("value-per-acre", "value_per_acre", "Total value per acre"),
  impr_per_acre:  makeValuePerAcreLayer("impr-per-acre",  "impr_per_acre",  "Improvement value per acre"),
  land_per_acre:  makeValuePerAcreLayer("land-per-acre",  "land_per_acre",  "Taxable land value per acre", LAND_VALUE_BINS),
  // 2D flat-fill companions (same data + palette, no extrusion)
  value_per_acre_2d: make2DValuePerAcreLayer("value-per-acre", "value_per_acre", "Total value per acre"),
  impr_per_acre_2d:  make2DValuePerAcreLayer("impr-per-acre",  "impr_per_acre",  "Improvement value per acre"),
  land_per_acre_2d:  make2DValuePerAcreLayer("land-per-acre",  "land_per_acre",  "Taxable land value per acre", LAND_VALUE_BINS),

  rail_stops: {
    label: "Rail stations",
    sourceId: "rail-stops-src",
    sourceFile: "data/rail_stops.geojson",
    layerIds: ["rail-stops"],
    addLayers: () => {
      map.addLayer({
        id: "rail-stops",
        type: "circle",
        source: "rail-stops-src",
        paint: {
          "circle-radius": [
            "interpolate", ["linear"], ["zoom"],
            9, 3, 14, 6,
          ],
          "circle-color": "#1A1A1A",
          "circle-stroke-color": "#FFFFFF",
          "circle-stroke-width": 1.5,
        },
      });
    },
    popup: (props) => {
      const name = props.stop_name || props.STATIONNAM || props.NAME || "Rail station";
      const stopId = props.stop_id;
      const safeName = (name || "").replace(/'/g, "\\'");
      return `
        <div class="popup-title">${name}</div>
        ${stopId ? `<div class="popup-row"><span class="label">Stop ID</span><span class="value">${stopId}</span></div>` : ""}
        <div class="popup-row" style="margin-top:8px">
          <a href="#" onclick="openReportFor('${safeName}'); return false;"
             style="color:#4A90A4;font-weight:500">Show TOD Opportunity Areas report →</a>
        </div>
      `;
    },
    clickLayer: "rail-stops",
    legend: () => `
      <div class="legend-block">
        <h3>Rail Stations</h3>
        <div class="swatch-row">
          <span style="display:inline-block;width:12px;height:12px;border-radius:50%;background:#1A1A1A;border:1.5px solid white;margin-right:8px"></span>
          DART rail station
        </div>
      </div>`,
  },

  station_areas: {
    label: "Half-mile station areas",
    sourceId: "station-areas-src",
    sourceFile: "data/station_areas.geojson",
    layerIds: ["station-areas-line"],
    addLayers: () => {
      // Outline only, dissolved upstream so no internal lines from
      // overlapping buffers.
      map.addLayer({
        id: "station-areas-line",
        type: "line",
        source: "station-areas-src",
        paint: { "line-color": "#1A1A1A", "line-width": 1.6, "line-opacity": 0.9 },
      });
    },
    popup: () => `<div class="popup-title">Half-mile station area</div>`,
    clickLayer: null,
    legend: () => `
      <div class="legend-block">
        <h3>Half-mile station areas</h3>
        <div class="swatch-row"><span class="line-swatch" style="border-top-color:#1A1A1A"></span>Half-mile boundary</div>
      </div>`,
  },

  block_groups: {
    label: "Pop change (BG)",
    sourceId: "bg-src",
    sourceFile: "data/block_groups.geojson",
    layerIds: ["bg-fill", "bg-outline"],
    addLayers: () => {
      map.addLayer({
        id: "bg-fill",
        type: "fill",
        source: "bg-src",
        paint: {
          "fill-color": popChangeFillColor("pop_change", POP_CHANGE_COLORS.bg),
          "fill-opacity": 0.75,
        },
      }, beneathTopLayers());
      map.addLayer({
        id: "bg-outline",
        type: "line",
        source: "bg-src",
        paint: { "line-color": "#FFFFFF", "line-width": 0.3 },
      }, beneathTopLayers());
    },
    popup: (props) => bgPopup(props),
    clickLayer: "bg-fill",
    legend: () => buildChangeLegend("Population Change, BG", POP_CHANGE_COLORS.bg),
  },

  bg_hu: {
    label: "Housing unit change (BG)",
    sourceId: "bg-hu-src",
    sourceFile: "data/block_groups.geojson",
    layerIds: ["bg-hu-fill", "bg-hu-outline"],
    addLayers: () => {
      map.addLayer({
        id: "bg-hu-fill",
        type: "fill",
        source: "bg-hu-src",
        paint: {
          "fill-color": popChangeFillColor("hu_change", HU_CHANGE_COLORS.bg),
          "fill-opacity": 0.75,
        },
      }, beneathTopLayers());
      map.addLayer({
        id: "bg-hu-outline",
        type: "line",
        source: "bg-hu-src",
        paint: { "line-color": "#FFFFFF", "line-width": 0.3 },
      }, beneathTopLayers());
    },
    popup: (props) => bgPopup(props),
    clickLayer: "bg-hu-fill",
    legend: () => buildChangeLegend("Housing Unit Change, BG", HU_CHANGE_COLORS.bg),
  },

  tracts: {
    label: "Pop change (tract)",
    sourceId: "tract-src",
    sourceFile: "data/tracts.geojson",
    layerIds: ["tract-fill", "tract-outline"],
    addLayers: () => {
      map.addLayer({
        id: "tract-fill",
        type: "fill",
        source: "tract-src",
        paint: {
          "fill-color": popChangeFillColor("pop_change", POP_CHANGE_COLORS.tract),
          "fill-opacity": 0.75,
        },
      }, beneathTopLayers());
      map.addLayer({
        id: "tract-outline",
        type: "line",
        source: "tract-src",
        paint: { "line-color": "#FFFFFF", "line-width": 0.5 },
      }, beneathTopLayers());
    },
    popup: (props) => tractPopup(props),
    clickLayer: "tract-fill",
    legend: () => buildChangeLegend("Population Change, Tract", POP_CHANGE_COLORS.tract),
  },

  tract_hu: {
    label: "Housing unit change (tract)",
    sourceId: "tract-hu-src",
    sourceFile: "data/tracts.geojson",
    layerIds: ["tract-hu-fill", "tract-hu-outline"],
    addLayers: () => {
      map.addLayer({
        id: "tract-hu-fill",
        type: "fill",
        source: "tract-hu-src",
        paint: {
          "fill-color": popChangeFillColor("hu_change", HU_CHANGE_COLORS.tract),
          "fill-opacity": 0.75,
        },
      }, beneathTopLayers());
      map.addLayer({
        id: "tract-hu-outline",
        type: "line",
        source: "tract-hu-src",
        paint: { "line-color": "#FFFFFF", "line-width": 0.5 },
      }, beneathTopLayers());
    },
    popup: (props) => tractPopup(props),
    clickLayer: "tract-hu-fill",
    legend: () => buildChangeLegend("Housing Unit Change, Tract", HU_CHANGE_COLORS.tract),
  },

  jobs_density: {
    label: "Job density",
    sourceId: "jobs-src",
    sourceFile: "data/jobs_tracts.geojson",
    layerIds: ["jobs-fill", "jobs-outline"],
    addLayers: () => {
      const colorExpr = [
        "case",
        ["==", ["get", "jobs_total"], 0], JOBS_ZERO_COLOR,
        ["step", ["get", "jobs_per_acre"],
          JOBS_BINS.palette[0],
          JOBS_BINS.edges[0], JOBS_BINS.palette[1],
          JOBS_BINS.edges[1], JOBS_BINS.palette[2],
          JOBS_BINS.edges[2], JOBS_BINS.palette[3],
          JOBS_BINS.edges[3], JOBS_BINS.palette[4],
          JOBS_BINS.edges[4], JOBS_BINS.palette[5],
        ],
      ];
      map.addLayer({
        id: "jobs-fill",
        type: "fill",
        source: "jobs-src",
        paint: { "fill-color": colorExpr, "fill-opacity": 0.75 },
      }, beneathTopLayers());
      map.addLayer({
        id: "jobs-outline",
        type: "line",
        source: "jobs-src",
        paint: { "line-color": "#FFFFFF", "line-width": 0.4 },
      }, beneathTopLayers());
    },
    popup: (props) => jobsPopup(props),
    clickLayer: "jobs-fill",
    legend: () => buildJobsLegend(),
  },

  oi_earnings: {
    label: "Expected adult earnings",
    sourceId: "oi-src",
    sourceFile: "data/oi_tracts.geojson",
    layerIds: ["oi-fill", "oi-outline"],
    addLayers: () => {
      const v = ["coalesce", ["get", "oi"], -1];
      const colorExpr = [
        "case",
        ["<", v, 0], OI_NODATA,
        ["step", v,
          OI_BINS.palette[0],
          OI_BINS.edges[0], OI_BINS.palette[1],
          OI_BINS.edges[1], OI_BINS.palette[2],
          OI_BINS.edges[2], OI_BINS.palette[3],
          OI_BINS.edges[3], OI_BINS.palette[4],
          OI_BINS.edges[4], OI_BINS.palette[5],
        ],
      ];
      map.addLayer({
        id: "oi-fill",
        type: "fill",
        source: "oi-src",
        paint: { "fill-color": colorExpr, "fill-opacity": 0.75 },
      }, beneathTopLayers());
      map.addLayer({
        id: "oi-outline",
        type: "line",
        source: "oi-src",
        paint: { "line-color": "#FFFFFF", "line-width": 0.4 },
      }, beneathTopLayers());
    },
    popup: (props) => oiPopup(props),
    clickLayer: "oi-fill",
    legend: () => buildOiLegend(),
  },
};

// Helper: ensure new fill layers appear under top-priority outline/point layers
function beneathTopLayers() {
  for (const candidate of [
    "city-boundary-line",
    "council-line",
    "station-areas-line",
    "rail-stops",
  ]) {
    if (map.getLayer(candidate)) return candidate;
  }
  return undefined;
}


// ---- Popup formatters ------------------------------------------------------

function fmt(n) {
  if (n === undefined || n === null || Number.isNaN(n)) return "";
  return Number(n).toLocaleString();
}

function changeRow(label, change, base) {
  const cls = change > 0 ? "positive" : change < 0 ? "negative" : "";
  const sign = change > 0 ? "+" : "";
  let pctStr = "";
  if (base !== undefined && base !== null && Number(base) > 0) {
    const pct = (Number(change) / Number(base)) * 100;
    const pctSign = pct > 0 ? "+" : "";
    pctStr = ` (${pctSign}${pct.toFixed(1)}%)`;
  }
  return `<div class="popup-row popup-change ${cls}">
    <span class="label">${label}</span>
    <span class="value">${sign}${fmt(change)}${pctStr}</span>
  </div>`;
}

function parcelPopup(props) {
  const luLabel = props.land_use_cat
    ? (LAND_USE_LABEL_BY_VALUE[props.land_use_cat] || props.land_use_cat)
    : null;
  const totVal  = props.tot_val  || 0;
  const imprVal = props.impr_val || 0;
  const landVal = props.land_val || 0;
  const fmtMoney = (v) => v ? "$" + Number(v).toLocaleString() : null;

  // Building type: bldg_cl gives specific descriptions for commercial parcels
  // ("OFFICE BUILDING", "STORAGE WAREHOUSE", etc.). For residential parcels
  // it's mostly numeric construction codes — skip those.
  let bldgType = null;
  if (props.bldg_class && !/^\d{1,3}$/.test(String(props.bldg_class).trim())) {
    bldgType = props.bldg_class;
  }

  const lines = [
    `<div class="popup-title">${props.address || "Parcel " + (props.account_num || "")}</div>`,
    luLabel ? `<div class="popup-row"><span class="label">Land use</span><span class="value">${luLabel}</span></div>` : "",
    bldgType ? `<div class="popup-row"><span class="label">Building type</span><span class="value">${bldgType}</span></div>` : "",
    props.property_name ? `<div class="popup-row"><span class="label">Property name</span><span class="value">${props.property_name}</span></div>` : "",
    props.zoning_assessor ? `<div class="popup-row"><span class="label">Zoning</span><span class="value">${props.zoning_assessor}</span></div>` : "",
    props.area_feet ? `<div class="popup-row"><span class="label">Lot size</span><span class="value">${fmt(props.area_feet)} sq ft</span></div>` : "",
    props.building_sf ? `<div class="popup-row"><span class="label">Building</span><span class="value">${fmt(props.building_sf)} sq ft</span></div>` : "",
    props.floor_area_ratio ? `<div class="popup-row"><span class="label">FAR</span><span class="value">${props.floor_area_ratio} (${props.far_cat || ""})</span></div>` : "",
    props.foot_far ? `<div class="popup-row"><span class="label">FAR (footprint-adj.)</span><span class="value">${props.foot_far}</span></div>` : "",
    props.total_units ? `<div class="popup-row"><span class="label">Units</span><span class="value">${props.total_units}</span></div>` : "",
    props.year_built ? `<div class="popup-row"><span class="label">Year built</span><span class="value">${props.year_built}</span></div>` : "",
    totVal  ? `<div class="popup-row"><span class="label">Total appraised value (2025)</span><span class="value">${fmtMoney(totVal)}</span></div>` : "",
    imprVal ? `<div class="popup-row"><span class="label">Improvement value</span><span class="value">${fmtMoney(imprVal)}</span></div>` : "",
    landVal ? `<div class="popup-row"><span class="label">Land value</span><span class="value">${fmtMoney(landVal)}</span></div>` : "",
    landVal ? `<div class="popup-row"><span class="label">Improvement / land ratio</span><span class="value">${(imprVal / landVal).toFixed(2)}</span></div>` : "",
    props.value_per_acre ? `<div class="popup-row"><span class="label">Value / acre</span><span class="value">${fmtMoney(props.value_per_acre)}</span></div>` : "",
    props.account_num ? `<div class="popup-row"><span class="label">Account</span><span class="value" style="font-size:11px">${props.account_num}</span></div>` : "",
    props.dart_station ? `<div class="popup-row" style="margin-top:4px;color:#4A90A4;font-size:12px">★ Within Half-mile DART station area</div>` : "",
  ];
  return lines.filter((s) => s).join("");
}

function bgOrTractBody(props) {
  return `
    <div class="popup-row"><span class="label">Land area</span><span class="value">${props.land_sq_mi} sq mi</span></div>

    <div class="popup-row" style="margin-top:6px;font-weight:600;color:#444;font-size:11px;text-transform:uppercase;letter-spacing:0.4px">Population</div>
    <div class="popup-row"><span class="label">2010</span><span class="value">${fmt(props.pop_2010)}</span></div>
    <div class="popup-row"><span class="label">2020</span><span class="value">${fmt(props.pop_2020)}</span></div>
    ${changeRow("Change", props.pop_change, props.pop_2010)}

    <div class="popup-row" style="margin-top:6px;font-weight:600;color:#444;font-size:11px;text-transform:uppercase;letter-spacing:0.4px">Housing Units</div>
    <div class="popup-row"><span class="label">2010</span><span class="value">${fmt(props.hu_2010)}</span></div>
    <div class="popup-row"><span class="label">2020</span><span class="value">${fmt(props.hu_2020)}</span></div>
    ${changeRow("Change", props.hu_change, props.hu_2010)}

    ${props.low_density ? '<div class="popup-row" style="margin-top:6px;color:#888;font-size:11px">⚠ Low density — interpret with caution</div>' : ""}
  `;
}

function bgPopup(props) {
  return `<div class="popup-title">Block Group ${props.geoid}</div>${bgOrTractBody(props)}`;
}

function tractPopup(props) {
  return `<div class="popup-title">Tract ${props.geoid}</div>${bgOrTractBody(props)}`;
}

// Jobs / wages popup -------------------------------------------------------

const JOB_SECTOR_LABELS = {
  sec_CNS01: "Agriculture & Forestry",
  sec_CNS02: "Mining / Oil & Gas",
  sec_CNS03: "Utilities",
  sec_CNS04: "Construction",
  sec_CNS05: "Manufacturing",
  sec_CNS06: "Wholesale Trade",
  sec_CNS07: "Retail Trade",
  sec_CNS08: "Transportation & Warehousing",
  sec_CNS09: "Information",
  sec_CNS10: "Finance & Insurance",
  sec_CNS11: "Real Estate",
  sec_CNS12: "Professional Services",
  sec_CNS13: "Mgmt of Companies",
  sec_CNS14: "Admin & Support",
  sec_CNS15: "Educational Services",
  sec_CNS16: "Health Care",
  sec_CNS17: "Arts & Entertainment",
  sec_CNS18: "Accommodation & Food",
  sec_CNS19: "Other Services",
  sec_CNS20: "Public Administration",
};

function fmtMoney(n) {
  if (n === undefined || n === null || Number.isNaN(n)) return "—";
  n = Number(n);
  if (n >= 1e9)  return "$" + (n / 1e9).toFixed(2) + "B";
  if (n >= 1e6)  return "$" + (n / 1e6).toFixed(1) + "M";
  if (n >= 1e3)  return "$" + (n / 1e3).toFixed(0) + "K";
  return "$" + Math.round(n).toLocaleString();
}

function jobsPopup(props) {
  const tot = props.jobs_total || 0;
  // CNS fields in the GeoJSON come through with their raw names CNS01..CNS20.
  // (We stored them that way in build_jobs_tracts.py.)
  const sectorRows = Object.keys(JOB_SECTOR_LABELS)
    .map((k) => {
      const raw = k.replace("sec_", "");
      const v = Number(props[raw] || 0);
      return { label: JOB_SECTOR_LABELS[k], value: v };
    })
    .filter((r) => r.value > 0)
    .sort((a, b) => b.value - a.value);

  const topSectors = sectorRows.slice(0, 5);
  const sectorHtml = topSectors.length
    ? topSectors
        .map((r) => {
          const pct = tot > 0 ? ((r.value / tot) * 100).toFixed(1) + "%" : "—";
          return `<div class="popup-row"><span class="label">${r.label}</span><span class="value">${fmt(r.value)} (${pct})</span></div>`;
        })
        .join("")
    : '<div class="popup-row"><span class="label" style="color:#888">No sector data</span></div>';

  const u50  = Number(props.jobs_under_50k  || 0);
  const m50  = Number(props.jobs_50_to_100k || 0);
  const o100 = Number(props.jobs_over_100k  || 0);
  const u50Pct  = tot > 0 ? ((u50  / tot) * 100).toFixed(0) + "%" : "—";
  const m50Pct  = tot > 0 ? ((m50  / tot) * 100).toFixed(0) + "%" : "—";
  const o100Pct = tot > 0 ? ((o100 / tot) * 100).toFixed(0) + "%" : "—";

  return `
    <div class="popup-title">Tract ${props.geoid}</div>
    <div class="popup-row"><span class="label">Land area</span><span class="value">${props.land_sq_mi} sq mi</span></div>

    <div class="popup-row" style="margin-top:6px;font-weight:600;color:#444;font-size:11px;text-transform:uppercase;letter-spacing:0.4px">Jobs (workplace, 2022)</div>
    <div class="popup-row"><span class="label">Total jobs</span><span class="value">${fmt(tot)}</span></div>
    <div class="popup-row"><span class="label">Density</span><span class="value">${fmt(props.jobs_per_acre)} / acre</span></div>
    <div class="popup-row"><span class="label">Share of 7-county total</span><span class="value">${(props.jobs_share_pct || 0).toFixed(3)}%</span></div>

    <div class="popup-row" style="margin-top:6px;font-weight:600;color:#444;font-size:11px;text-transform:uppercase;letter-spacing:0.4px">Estimated annual wages</div>
    <div class="popup-row"><span class="label">Midpoint method</span><span class="value">${fmtMoney(props.wages_midpoint)}</span></div>
    <div class="popup-row"><span class="label">BLS sector-weighted</span><span class="value">${fmtMoney(props.wages_sector)}</span></div>

    <div class="popup-row" style="margin-top:6px;font-weight:600;color:#444;font-size:11px;text-transform:uppercase;letter-spacing:0.4px">Wage mix (by sector)</div>
    <div class="popup-row"><span class="label">&lt; $50k/yr</span><span class="value">${fmt(u50)} (${u50Pct})</span></div>
    <div class="popup-row"><span class="label">$50k–$100k</span><span class="value">${fmt(m50)} (${m50Pct})</span></div>
    <div class="popup-row"><span class="label">&gt; $100k/yr</span><span class="value">${fmt(o100)} (${o100Pct})</span></div>

    <div class="popup-row" style="margin-top:6px;font-weight:600;color:#444;font-size:11px;text-transform:uppercase;letter-spacing:0.4px">Top sectors</div>
    ${sectorHtml}
  `;
}

function oiPopup(props) {
  if (props.oi === null || props.oi === undefined) {
    return `<div class="popup-title">Tract ${props.geoid}</div>
      <div class="popup-row"><span class="label" style="color:#888">No mobility estimate</span></div>`;
  }
  return `<div class="popup-title">Tract ${props.geoid}</div>
    <div class="popup-row"><span class="label">Expected adult earnings</span><span class="value">$${Number(props.oi).toLocaleString()}</span></div>
    <div class="popup-row" style="margin-top:4px;color:#888;font-size:11px;line-height:1.4">Predicted household income at age 35 for children who grew up in this tract in 25th-percentile-income families (Opportunity Atlas).</div>`;
}

function buildOiLegend() {
  const rows = OI_BINS.palette
    .map((c, i) => `<div class="swatch-row"><span class="swatch" style="background:${c}"></span>${OI_BINS.labels[i]}</div>`)
    .join("");
  const nd = `<div class="swatch-row"><span class="swatch" style="background:${OI_NODATA}"></span>No estimate</div>`;
  return `<div class="legend-block"><h3>Expected adult earnings</h3>${rows}${nd}</div>`;
}

function buildJobsLegend() {
  const swatches = JOBS_BINS.palette
    .map((c, i) => `<div class="swatch-row"><span class="swatch" style="background:${c}"></span>${JOBS_BINS.labels[i]}</div>`)
    .join("");
  const zero = `<div class="swatch-row"><span class="swatch" style="background:${JOBS_ZERO_COLOR}"></span>No jobs</div>`;
  return `
      <div class="legend-block">
        <h3>Workplace jobs / acre</h3>
        ${swatches}
        ${zero}
      </div>`;
}


// ---- Legend ----------------------------------------------------------------

function buildChangeLegend(title, scheme) {
  const rows = scheme.palette
    .map((c, i) => `<div class="swatch-row"><span class="swatch" style="background:${c}"></span>${scheme.labels[i]}</div>`)
    .join("");
  const lowDens = `<div class="swatch-row"><span class="swatch" style="background:${LOW_DENS_COLOR}"></span>${LOW_DENS_LABEL}</div>`;
  return `<div class="legend-block"><h3>${title}</h3>${rows}${lowDens}</div>`;
}

function refreshLegend() {
  const enabled = Object.entries(LAYERS).filter(([k, v]) => v.enabled);
  const wrapper = document.getElementById("legend");
  const content = document.getElementById("legend-content");
  if (enabled.length === 0) {
    wrapper.classList.add("empty");
    content.innerHTML = "";
    return;
  }
  wrapper.classList.remove("empty");
  // Layers sharing a legendGroup collapse into one block (e.g. jurisdiction
  // boundaries). The block sits where the group's first enabled layer falls;
  // rows are ordered by legendOrder. Everything else uses its own legend() block.
  const blocks = [];
  const groupRows = {};
  for (const [k, v] of enabled) {
    if (v.legendGroup) {
      if (!(v.legendGroup in groupRows)) {
        groupRows[v.legendGroup] = [];
        blocks.push({ group: v.legendGroup });
      }
      groupRows[v.legendGroup].push({ o: v.legendOrder ?? 0, html: v.legendRow() });
    } else {
      blocks.push({ html: v.legend(), key: k });
    }
  }
  content.innerHTML = blocks.map((b) => {
    if (b.group) {
      let inner = `<div class="legend-block"><h3>${b.group}</h3>` +
        groupRows[b.group].sort((a, c) => a.o - c.o).map((r) => r.html).join("");
      if (VINTAGE_GROUP[b.group]) inner += `<div class="muted legend-vintage">${VINTAGE_GROUP[b.group]}</div>`;
      return inner + `</div>`;
    }
    return withVintage(b.html, VINTAGE[b.key]);
  }).join("");
}


// ---- Layer init / load -----------------------------------------------------

const sourcesAdded = new Set();
const layersAdded = new Set();

async function ensureSource(layer) {
  if (layer.customLoad) {
    await layer.customLoad();
    return;
  }
  if (sourcesAdded.has(layer.sourceId)) return;
  const resp = await fetch(layer.sourceFile);
  const data = await resp.json();
  map.addSource(layer.sourceId, { type: "geojson", data });
  sourcesAdded.add(layer.sourceId);
}

async function enableLayer(key) {
  const layer = LAYERS[key];
  await ensureSource(layer);
  if (!layersAdded.has(key)) {
    layer.addLayers();
    layer.layerIds.forEach((id) => layersAdded.add(id));
    if (layer.clickLayer) {
      const clickTargets = Array.isArray(layer.clickLayer) ? layer.clickLayer : [layer.clickLayer];
      for (const target of clickTargets) {
        map.on("click", target, (e) => {
          const f = e.features?.[0];
          if (!f) return;
          new maplibregl.Popup({ closeButton: true })
            .setLngLat(e.lngLat)
            .setHTML(layer.popup(f.properties))
            .addTo(map);
        });
        map.on("mouseenter", target, () => map.getCanvas().style.cursor = "pointer");
        map.on("mouseleave", target, () => map.getCanvas().style.cursor = "");
      }
    }
  }
  layer.layerIds.forEach((id) => map.setLayoutProperty(id, "visibility", "visible"));
  layer.enabled = true;
  refreshLegend();
  applyLayerOrder();   // place this layer in the user's preferred stack position
  updateZoomHint();
}

function disableLayer(key) {
  const layer = LAYERS[key];
  if (!layer || !layer.enabled) return;
  layer.layerIds.forEach((id) => {
    if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", "none");
  });
  layer.enabled = false;
  refreshLegend();
  updateZoomHint();
  updateWaterMask();
}

// Zoom hint: when an enabled layer is hidden because the user is zoomed out past
// its minzoom, show a small "zoom in to see ..." pill so it doesn't look broken.
let zoomHintEl = null;
function layerDisplayName(key) {
  const cb = document.querySelector(`input[data-layer="${key}"]`);
  const span = cb && cb.closest("label") && cb.closest("label").querySelector("span");
  const name = span ? span.textContent.trim() : (LAYERS[key] ? LAYERS[key].label : key);
  return name.replace(/^Show\s+/i, "");   // "Show street names" -> "street names"
}
function updateZoomHint() {
  if (!zoomHintEl) return;
  const z = map.getZoom();
  const names = [];
  for (const [key, l] of Object.entries(LAYERS)) {
    if (l.enabled && typeof l.minzoom === "number" && z < l.minzoom - 0.01) {
      names.push(layerDisplayName(key));
    }
  }
  const uniq = [...new Set(names)];
  if (!uniq.length) { zoomHintEl.style.display = "none"; return; }
  const list = uniq.length <= 3 ? uniq.join(", ")
    : `${uniq.slice(0, 2).join(", ")} +${uniq.length - 2} more`;
  zoomHintEl.textContent = `🔍 Zoom in to see ${list}`;
  zoomHintEl.style.display = "";
}

// Water mask: covers OSM water bodies on the zoning / land-use / FAR / decade fills
// so lakes and the river don't read as a zoning or land-use category. Visible only
// while one of those four layers is on; positioned just above the topmost of them.
const WATER_MASK_LAYERS = ["zoning", "land_use", "far_footprint", "decade_built"];
const WATER_MASK_FILLS = ["decade-built-fill", "far-foot-fill", "land-use-fill", "zoning-fill"];
let waterMaskPromise = null;
function ensureWaterMask() {
  if (!waterMaskPromise) {
    waterMaskPromise = (async () => {
      const data = await (await fetch("data/water_dallas.geojson")).json();
      if (!map.getSource("water-mask-src")) map.addSource("water-mask-src", { type: "geojson", data });
      if (!map.getLayer("water-mask-fill")) {
        map.addLayer({
          id: "water-mask-fill", type: "fill", source: "water-mask-src",
          layout: { visibility: "none" },
          paint: { "fill-color": "#b3cdd9" },   // pale water, masks the choropleth beneath
        }, beneathTopLayers());
      }
    })();
  }
  return waterMaskPromise;
}
function updateWaterMask() {
  const anyOn = WATER_MASK_LAYERS.some((k) => LAYERS[k] && LAYERS[k].enabled);
  if (!anyOn) {
    if (map.getLayer("water-mask-fill")) map.setLayoutProperty("water-mask-fill", "visibility", "none");
    return;
  }
  ensureWaterMask().then(() => {
    if (!map.getLayer("water-mask-fill")) return;
    map.setLayoutProperty("water-mask-fill", "visibility", "visible");
    const order = map.getStyle().layers.map((l) => l.id);
    let topIdx = -1;
    for (const f of WATER_MASK_FILLS) { const i = order.indexOf(f); if (i > topIdx) topIdx = i; }
    const before = topIdx >= 0 ? order[topIdx + 1] : undefined;
    if (before !== "water-mask-fill") {
      try { map.moveLayer("water-mask-fill", before); } catch (e) { /* already topmost */ }
    }
  });
}


// ---- Layer reorder logic ---------------------------------------------------
// Convention: TOP of sidebar list = TOPMOST on map.
// Each sidebar item maps to one or more MapLibre layers (e.g. fill + outline
// for parcels). Within an entry, layers are listed in bottom-to-top order
// already (fill first, outline second).
//
// To apply the order, we walk the sidebar from bottom to top and call
// map.moveLayer(id) for each sub-layer. moveLayer with no `before` arg
// promotes the layer to the very top, so the *last* one moved wins.
function applyLayerOrder() {
  const items = Array.from(document.querySelectorAll("#layer-list .layer-toggle"));
  // Iterate sidebar from bottom to top
  for (let i = items.length - 1; i >= 0; i--) {
    const cb = items[i].querySelector('input[type="checkbox"]');
    if (!cb) continue;
    // "Street grid" is a master over several sub-layers (no data-layer of its own):
    // order its sub-layers as a unit — Streets, Dead-ends, Alleys, then labels on top.
    if (cb.id === "street-grid-master") {
      for (const id of ["streets-grid-line", "streets-stub-line", "alley-line", "street-labels-symbol"]) {
        if (map.getLayer(id)) map.moveLayer(id);
      }
      continue;
    }
    let key = cb.dataset.layer;
    // Grouped (pop_change / hu_change): pick whichever sub-layer's radio
    // is currently selected.
    if (!key && cb.dataset.layerGroup) {
      const group = cb.dataset.layerGroup;
      const groupMap = {
        pop_change: { bg: "block_groups", tract: "tracts" },
        hu_change:  { bg: "bg_hu",        tract: "tract_hu" },
        value3d:    { total: "value_per_acre", improvement: "impr_per_acre", land: "land_per_acre" },
        value2d:    { total: "value_per_acre_2d", improvement: "impr_per_acre_2d", land: "land_per_acre_2d" },
      }[group];
      if (groupMap) {
        const rb = document.querySelector(`input[name="${group}_level"]:checked`);
        if (rb) key = groupMap[rb.value];
      } else {
        key = group;   // rent_change / value_change map directly to a LAYERS entry
      }
    }
    const layer = LAYERS[key];
    if (!layer) continue;
    layer.layerIds.forEach((id) => {
      if (map.getLayer(id)) map.moveLayer(id);
    });
  }
  // Active district highlight sits above normal overlays.
  if (map.getLayer("active-district-fill")) map.moveLayer("active-district-fill");
  // Permits sit above the district highlight, but below the active-station rings.
  for (const id of ["permits-sf", "permits-mf"]) {
    if (map.getLayer(id)) map.moveLayer(id);
  }
  // Active station radius circles must always sit above every overlay.
  // Move them in fill→line order so the overlay sits beneath the rings.
  for (const id of ["active-half-fill", "active-half-line", "active-quarter-line"]) {
    if (map.getLayer(id)) map.moveLayer(id);
  }
  updateWaterMask();   // keep the water mask above the zoning/land-use/FAR/decade fills
}


// ---- UI wiring -------------------------------------------------------------

map.on("load", async () => {
  // Basemap selector
  document.querySelectorAll('input[name="basemap"]').forEach((rb) => {
    rb.addEventListener("change", () => {
      if (rb.checked) setBasemap(rb.value);
    });
  });

  // Zoom hint pill — created once, then refreshed on zoom and on layer toggles.
  zoomHintEl = document.createElement("div");
  zoomHintEl.className = "zoom-hint";
  zoomHintEl.style.display = "none";
  map.getContainer().appendChild(zoomHintEl);
  map.on("zoom", updateZoomHint);

  document.querySelectorAll('.layer-toggle input[type="checkbox"]').forEach((cb) => {
    cb.addEventListener("change", async (e) => {
      const key = cb.dataset.layer;
      if (!LAYERS[key]) return;
      if (cb.checked) {
        cb.parentElement.classList.add("loading");
        try { await enableLayer(key); }
        finally { cb.parentElement.classList.remove("loading"); }
      } else {
        disableLayer(key);
      }
    });
  });

  for (const cb of document.querySelectorAll('.layer-toggle input[type="checkbox"]:checked')) {
    const key = cb.dataset.layer;
    if (LAYERS[key]) await enableLayer(key);
  }

  // Grouped checkbox + radio orchestration.
  // Two groups today: "pop_change" (BG -> block_groups / Tract -> tracts) and
  // "hu_change" (BG -> bg_hu / Tract -> tract_hu). The parent checkbox enables
  // the *currently-selected radio's* layer; switching the radio while the
  // parent is checked swaps between the two underlying layers.
  const GROUP_MAP = {
    pop_change: { bg: "block_groups", tract: "tracts" },
    hu_change:  { bg: "bg_hu",        tract: "tract_hu" },
  };
  const groupBoxes = document.querySelectorAll('input[data-layer-group]');
  groupBoxes.forEach((cb) => {
    const group = cb.dataset.layerGroup;
    const map_ = GROUP_MAP[group];
    if (!map_) return;
    const radioName = `${group}_level`;
    const selectedLevel = () => {
      const r = document.querySelector(`input[name="${radioName}"]:checked`);
      return r ? r.value : "bg";
    };
    cb.addEventListener("change", async () => {
      const level = selectedLevel();
      const key = map_[level];
      const other = map_[level === "bg" ? "tract" : "bg"];
      if (cb.checked) {
        cb.parentElement.classList.add("loading");
        try {
          if (LAYERS[other]) disableLayer(other);
          if (LAYERS[key])   await enableLayer(key);
        } finally {
          cb.parentElement.classList.remove("loading");
        }
      } else {
        if (LAYERS[map_.bg])    disableLayer(map_.bg);
        if (LAYERS[map_.tract]) disableLayer(map_.tract);
      }
    });
    document.querySelectorAll(`input[name="${radioName}"]`).forEach((rb) => {
      rb.addEventListener("change", async () => {
        if (!rb.checked || !cb.checked) return;
        const level = rb.value;
        const key = map_[level];
        const other = map_[level === "bg" ? "tract" : "bg"];
        cb.parentElement.classList.add("loading");
        try {
          if (LAYERS[other]) disableLayer(other);
          if (LAYERS[key])   await enableLayer(key);
        } finally {
          cb.parentElement.classList.remove("loading");
        }
      });
    });
  });

  // Drag-and-drop reordering of the layer list.
  const layerList = document.getElementById("layer-list");
  if (layerList && window.Sortable) {
    Sortable.create(layerList, {
      handle: ".drag-handle",
      animation: 150,
      ghostClass: "sortable-ghost",
      chosenClass: "sortable-chosen",
      dragClass: "sortable-drag",
      onEnd: () => applyLayerOrder(),
    });
  }

  // Wire the per-layer "Cap heights at $100M/acre" sub-checkbox. The three
  // copies (one under each value-per-acre layer toggle) all drive a single
  // shared state, and any change refreshes the height expression on every
  // currently-rendered value layer.
  document.querySelectorAll('input[data-value-cap]').forEach((cb) => {
    cb.addEventListener("change", () => {
      valueCapEnabled = cb.checked;
      document.querySelectorAll('input[data-value-cap]').forEach((other) => {
        if (other !== cb) other.checked = valueCapEnabled;
      });
      refreshValueHeightExprs();
      refreshLegend();
    });
  });

  initReports();
  initPermits();
  initChangeLayers();
  initValue3d();
  initValue2d();
  initStreetPattern();
  initFloodplain();
  initTransit();
  initDemographics();
  initGeocoder();
  injectTooltips();
  zoningMenuReady = initZoningMenu();
  initLandUseMenu();

  // Legend collapse / expand
  const legendEl = document.getElementById("legend");
  const collapseBtn = document.getElementById("legend-collapse");
  if (legendEl && collapseBtn) {
    collapseBtn.addEventListener("click", () => {
      legendEl.classList.toggle("collapsed");
      collapseBtn.textContent = legendEl.classList.contains("collapsed") ? "+" : "−";
    });
  }

  // ---- Shareable view URLs: restore from the hash, then keep it in sync ----
  await applyMapState(location.hash.replace(/^#/, ""));
  map.on("moveend", scheduleHashWrite);
  const sidebarEl = document.getElementById("sidebar");
  if (sidebarEl) sidebarEl.addEventListener("change", scheduleHashWrite);
  const copyBtn = document.getElementById("copy-view-link");
  if (copyBtn) {
    copyBtn.addEventListener("click", async () => {
      history.replaceState(null, "", "#" + serializeMapState());
      try {
        await navigator.clipboard.writeText(location.href);
        copyBtn.textContent = "✓ Link copied";
      } catch (e) {
        copyBtn.textContent = "Press Ctrl+C to copy";
      }
      setTimeout(() => { copyBtn.textContent = "🔗 Copy link to this view"; }, 1800);
    });
  }
});


// ---- Shareable view URL state ----------------------------------------------
// Serialize map view + control state into the URL hash so every view has a unique
// shareable link; applyMapState() restores it on load. List separator "~" (zone
// codes contain ".", e.g. R-7.5); key:value pairs joined with ":".
function serializeMapState() {
  const c = map.getCenter();
  const params = new URLSearchParams();
  params.set("m", [c.lng.toFixed(5), c.lat.toFixed(5), map.getZoom().toFixed(2),
                   Math.round(map.getPitch()), Math.round(map.getBearing())].join(","));
  const base = document.querySelector('input[name="basemap"]:checked');
  if (base) params.set("base", base.value);
  const on = [];
  document.querySelectorAll('input[data-layer]:checked, input[data-layer-group]:checked')
    .forEach((cb) => on.push(cb.dataset.layer || cb.dataset.layerGroup));
  params.set("on", on.join("~"));
  const rad = [];
  document.querySelectorAll('input[type="radio"]:checked').forEach((rb) => {
    if (rb.name && rb.name !== "basemap") rad.push(`${rb.name}:${rb.value}`);
  });
  if (rad.length) params.set("rad", rad.join("~"));
  const cap = document.querySelector('input[data-value-cap]');
  if (cap) params.set("cap", cap.checked ? "1" : "0");
  const sld = [];
  ["permits-year-start", "permits-year-end", "rent-yr-start", "rent-yr-end",
   "value-yr-start", "value-yr-end"].forEach((id) => {
    const el = document.getElementById(id);
    if (el) sld.push(`${id}:${el.value}`);
  });
  if (sld.length) params.set("s", sld.join("~"));
  if (zoningState.selected && zoningState.total && zoningState.selected.size < zoningState.total)
    params.set("zon", [...zoningState.selected].join("~"));
  return params.toString();
}

let _hashWriteTimer = null;
function scheduleHashWrite() {
  clearTimeout(_hashWriteTimer);
  _hashWriteTimer = setTimeout(() => {
    try { history.replaceState(null, "", "#" + serializeMapState()); } catch (e) { /* ignore */ }
  }, 400);
}

async function applyMapState(hashStr) {
  const params = new URLSearchParams(hashStr || "");
  if (![...params.keys()].length) return;
  try {
    const base = params.get("base");
    if (base) {
      const rb = document.querySelector(`input[name="basemap"][value="${base}"]`);
      if (rb) { rb.checked = true; setBasemap(base); }
    }
    // sub-radios first (DOM only) so grouped layers read the right value when enabled
    (params.get("rad") || "").split("~").filter(Boolean).forEach((pair) => {
      const i = pair.indexOf(":");
      const rb = document.querySelector(`input[name="${pair.slice(0, i)}"][value="${pair.slice(i + 1)}"]`);
      if (rb) rb.checked = true;
    });
    if (params.has("cap")) {
      valueCapEnabled = params.get("cap") === "1";
      document.querySelectorAll('input[data-value-cap]').forEach((c) => { c.checked = valueCapEnabled; });
    }
    (params.get("s") || "").split("~").filter(Boolean).forEach((pair) => {
      const i = pair.indexOf(":");
      const el = document.getElementById(pair.slice(0, i));
      if (el) el.value = pair.slice(i + 1);
    });
    // enable/disable every layer toggle to match the on-list
    if (params.has("on")) {
      const want = new Set((params.get("on") || "").split("~").filter(Boolean));
      document.querySelectorAll('input[data-layer], input[data-layer-group]').forEach((cb) => {
        const key = cb.dataset.layer || cb.dataset.layerGroup;
        const shouldBe = want.has(key);
        if (cb.checked !== shouldBe) { cb.checked = shouldBe; cb.dispatchEvent(new Event("change", { bubbles: true })); }
      });
      const anyStreet = ["streets_grid", "streets_deadend", "alleys", "street_labels"].some((k) => want.has(k));
      const master = document.getElementById("street-grid-master");
      const sub = document.getElementById("street-subrow");
      if (master) master.checked = anyStreet;
      if (sub) sub.style.display = anyStreet ? "" : "none";
    }
    // refresh sliders now that their layers are live (updates labels + expression)
    (params.get("s") || "").split("~").filter(Boolean).forEach((pair) => {
      const el = document.getElementById(pair.slice(0, pair.indexOf(":")));
      if (el) el.dispatchEvent(new Event("input", { bubbles: true }));
    });
    // zoning district selection (wait for the async menu to build)
    const zon = params.get("zon");
    if (zon != null && zoningMenuReady) {
      await zoningMenuReady;
      const want = new Set(zon.split("~").filter(Boolean));
      document.querySelectorAll("#zoning-zone-menu .zone-cb").forEach((cb) => { cb.checked = want.has(cb.dataset.zd); });
      document.querySelectorAll("#zoning-zone-menu .zone-cat").forEach((c) => syncZoningCatAll(c));
      recomputeZoningSelection();
    }
    const m = params.get("m");
    if (m) {
      const [lng, lat, z, pitch, bearing] = m.split(",").map(Number);
      map.jumpTo({ center: [lng, lat], zoom: z, pitch: pitch || 0, bearing: bearing || 0 });
    }
  } catch (e) {
    console.warn("View restore failed:", e);
  }
}


// ---- Building permits layer ------------------------------------------------
//
// Integrated into the main layer list as a regular toggle. When checked,
// loads data/permits.geojson and renders SF (single-family) and MF
// (combined multifamily + commercial) circle layers, each filtered by the
// shared year-range slider. Circle radius scales as sqrt(units) so area
// ≈ unit count.

const PERMITS_COLORS = {
  sf: "#E8A838",  // mustard — single-family
  mf: "#C44E52",  // red — multifamily (includes commercial)
};
// SF gets data type "sf"; the MF layer covers both "mf" and "com".
const PERMITS_LAYER_TYPES = {
  sf: ["sf"],
  mf: ["mf", "com"],
};

let permitsState = {
  master: false,
  visible: { sf: true, mf: true },
  yearStart: 2000,
  yearEnd: 2024,
};

function permitsRadiusExpr() {
  return [
    "interpolate", ["linear"], ["zoom"],
    9, [
      "interpolate", ["linear"], ["sqrt", ["get", "units"]],
      1, 2, 5, 4, 10, 6, 25, 10,
    ],
    14, [
      "interpolate", ["linear"], ["sqrt", ["get", "units"]],
      1, 4, 5, 8, 10, 14, 25, 24,
    ],
  ];
}

function buildPermitFilter(layerCode) {
  const dataTypes = PERMITS_LAYER_TYPES[layerCode];
  return [
    "all",
    ["in", ["get", "type"], ["literal", dataTypes]],
    [">=", ["get", "year"], permitsState.yearStart],
    ["<=", ["get", "year"], permitsState.yearEnd],
  ];
}

function permitsPopupHTML(p) {
  const dateLabel = p.date
    ? new Date(p.date + "T00:00:00").toLocaleDateString("en-US",
        { year: "numeric", month: "short", day: "numeric" })
    : (p.year || "");
  const typeLabel = (p.type === "sf") ? "Single-family" : "Multifamily";
  const actLabel = {
    new: "New Construction", recon: "Reconstruction", add: "Addition",
    finish: "Finish Out", reno: "Renovation", alter: "Alteration",
  }[p.act] || p.act;
  const value = p.value ? `<div class="popup-row"><span class="label">Value</span><span class="value">$${Number(p.value).toLocaleString()}</span></div>` : "";
  const area = p.area ? `<div class="popup-row"><span class="label">Area</span><span class="value">${Number(p.area).toLocaleString()} sq ft</span></div>` : "";
  return `
    <div class="popup-title">${p.addr || "Building permit"}</div>
    <div class="popup-row"><span class="label">Issue date</span><span class="value">${dateLabel}</span></div>
    <div class="popup-row"><span class="label">Units</span><span class="value">${p.units}</span></div>
    <div class="popup-row"><span class="label">Type</span><span class="value">${typeLabel}</span></div>
    <div class="popup-row"><span class="label">Activity</span><span class="value">${actLabel}</span></div>
    ${value}${area}
  `;
}

// Layer-registry entry. Uses customLoad to fetch the GeoJSON once on first
// enable, addLayers to register the two circle layers + click popups, and
// the standard enable/disable flow from the layer list checkbox.
LAYERS.permits = {
  label: "Building permits",
  sourceId: "permits-src",
  sourceFile: null,
  layerIds: ["permits-sf", "permits-mf"],
  customLoad: async () => {
    if (map.getSource("permits-src")) return;
    const r = await fetch("data/permits.geojson");
    map.addSource("permits-src", { type: "geojson", data: await r.json() });
  },
  addLayers: () => {
    for (const code of ["sf", "mf"]) {
      const layerId = `permits-${code}`;
      map.addLayer({
        id: layerId,
        type: "circle",
        source: "permits-src",
        filter: buildPermitFilter(code),
        paint: {
          "circle-radius": permitsRadiusExpr(),
          "circle-color": PERMITS_COLORS[code],
          "circle-stroke-color": "#FFFFFF",
          "circle-stroke-width": 0.8,
          "circle-opacity": 0.85,
        },
      });
      map.on("click", layerId, (e) => {
        const f = e.features?.[0];
        if (!f) return;
        new maplibregl.Popup({ closeButton: true })
          .setLngLat(e.lngLat)
          .setHTML(permitsPopupHTML(f.properties))
          .addTo(map);
      });
      map.on("mouseenter", layerId, () => map.getCanvas().style.cursor = "pointer");
      map.on("mouseleave", layerId, () => map.getCanvas().style.cursor = "");
    }
    permitsState.master = true;
    applyPermitsFilters();
  },
  popup: () => "", clickLayer: null,
  legend: () => `
    <div class="legend-block">
      <h3>Building Permits</h3>
      <div class="swatch-row"><span class="swatch" style="background:#E8A838;border-radius:50%"></span>Single-family</div>
      <div class="swatch-row"><span class="swatch" style="background:#C44E52;border-radius:50%"></span>Multifamily</div>
      <div class="muted" style="margin-top:4px">Circle area ≈ unit count. ${permitsState.yearStart}–${permitsState.yearEnd}.</div>
    </div>
  `,
};

function applyPermitsFilters() {
  for (const code of ["sf", "mf"]) {
    const id = `permits-${code}`;
    if (!map.getLayer(id)) continue;
    const visible = permitsState.master && permitsState.visible[code];
    map.setLayoutProperty(id, "visibility", visible ? "visible" : "none");
    map.setFilter(id, buildPermitFilter(code));
  }
  refreshLegend();
}

function initPermits() {
  // Sub-toggles (only meaningful while the layer is enabled, but the listeners
  // can be wired up unconditionally — the visibility logic checks master).
  document.querySelectorAll('input[data-permits-type]').forEach((cb) => {
    cb.addEventListener("change", () => {
      permitsState.visible[cb.dataset.permitsType] = cb.checked;
      applyPermitsFilters();
    });
  });

  // Mirror the master layer-list checkbox into permitsState so the sub-toggle
  // visibility logic respects it on both check and un-check. (The standard
  // layer flow in enableLayer forces visibility="visible" on both circle
  // layers when re-enabling, so we re-apply the sub-toggle filter here.)
  const layerCb = document.querySelector('input[data-layer="permits"]');
  if (layerCb) {
    layerCb.addEventListener("change", () => {
      permitsState.master = layerCb.checked;
      applyPermitsFilters();
    });
  }

  // Dual-thumb year slider
  const yrStart = document.getElementById("permits-year-start");
  const yrEnd   = document.getElementById("permits-year-end");
  const startLbl = document.getElementById("permits-year-start-label");
  const endLbl   = document.getElementById("permits-year-end-label");
  const rangeBar = document.getElementById("permits-year-range");
  if (!yrStart || !yrEnd) return;

  const MIN = parseInt(yrStart.min, 10);
  const MAX = parseInt(yrStart.max, 10);

  function updateRangeBar() {
    const span = MAX - MIN;
    const leftPct = ((permitsState.yearStart - MIN) / span) * 100;
    const rightPct = ((permitsState.yearEnd - MIN) / span) * 100;
    rangeBar.style.left = leftPct + "%";
    rangeBar.style.width = (rightPct - leftPct) + "%";
    startLbl.textContent = permitsState.yearStart;
    endLbl.textContent = permitsState.yearEnd;
  }

  yrStart.addEventListener("input", () => {
    let v = parseInt(yrStart.value, 10);
    if (v > permitsState.yearEnd) { v = permitsState.yearEnd; yrStart.value = String(v); }
    permitsState.yearStart = v;
    updateRangeBar();
    applyPermitsFilters();
  });
  yrEnd.addEventListener("input", () => {
    let v = parseInt(yrEnd.value, 10);
    if (v < permitsState.yearStart) { v = permitsState.yearStart; yrEnd.value = String(v); }
    permitsState.yearEnd = v;
    updateRangeBar();
    applyPermitsFilters();
  });
  updateRangeBar();
}


// ---- Reports panel (TOD + Council District) -------------------------------
//
// One side panel shared between two report kinds:
//   - "tod":      reads station_reports.json + rail_stops.geojson
//   - "district": reads district_reports.json
// The panel header, dropdown label, and renderer change based on the
// currently active mode.

let stationReports = null;
let stationCoords = null;  // Map<stop_id, [lng, lat]>
let districtReports = null;
let reportMode = null;     // "tod" | "district"

async function loadStationReports() {
  if (stationReports) return stationReports;
  const [reportsResp, stopsResp] = await Promise.all([
    fetch("data/station_reports.json"),
    fetch("data/rail_stops.geojson"),
  ]);
  stationReports = (await reportsResp.json()).stations;
  stationReports.sort((a, b) => (a.stop_name || "").localeCompare(b.stop_name || ""));

  const stopsJson = await stopsResp.json();
  stationCoords = new Map();
  for (const f of stopsJson.features || []) {
    const id = f.properties?.stop_id;
    if (id != null && f.geometry?.coordinates) {
      stationCoords.set(String(id), f.geometry.coordinates);
    }
  }
  return stationReports;
}


// ---- Active-station radius circles (1/4 mi + 1/2 mi) -----------------------

function circlePolygon(lng, lat, radiusMeters, n = 96) {
  // Equirectangular approximation — perfectly fine at half-mile distances in
  // Dallas latitudes. n = 96 produces a smooth circle at any zoom.
  const earthR = 6378137;
  const dDeg = (radiusMeters / earthR) * (180 / Math.PI);
  const dLng = dDeg / Math.cos((lat * Math.PI) / 180);
  const dLat = dDeg;
  const coords = [];
  for (let i = 0; i <= n; i++) {
    const a = (i / n) * 2 * Math.PI;
    coords.push([lng + dLng * Math.cos(a), lat + dLat * Math.sin(a)]);
  }
  return { type: "Polygon", coordinates: [coords] };
}

function ensureActiveStationLayer() {
  if (map.getSource("active-station-src")) return;
  map.addSource("active-station-src", {
    type: "geojson",
    data: { type: "FeatureCollection", features: [] },
  });
  // Filled black tint over the entire 1/2-mile area (90% transparent so
  // underlying data still reads). Drawn first so both circumference lines
  // sit on top of it.
  map.addLayer({
    id: "active-half-fill",
    type: "fill",
    source: "active-station-src",
    filter: ["==", ["get", "radius"], "half"],
    paint: { "fill-color": "#000000", "fill-opacity": 0.15 },
  });
  // 1/2 mile circumference (outer) — solid line
  map.addLayer({
    id: "active-half-line",
    type: "line",
    source: "active-station-src",
    filter: ["==", ["get", "radius"], "half"],
    paint: {
      "line-color": "#222222",
      "line-width": 3.0,
      "line-opacity": 0.95,
    },
  });
  // 1/4 mile circumference (inner) — dashed line to distinguish it from
  // the solid outer ring; same color so they read as a single station's
  // radii pair.
  map.addLayer({
    id: "active-quarter-line",
    type: "line",
    source: "active-station-src",
    filter: ["==", ["get", "radius"], "quarter"],
    paint: {
      "line-color": "#222222",
      "line-width": 3.0,
      "line-opacity": 0.95,
      "line-dasharray": [3, 2],
    },
  });
}

const HALF_MILE_M    = 804.672;
const QUARTER_MILE_M = 402.336;

function setActiveStation(stopId) {
  ensureActiveStationLayer();
  const src = map.getSource("active-station-src");
  if (!stopId || !stationCoords) {
    src.setData({ type: "FeatureCollection", features: [] });
    return;
  }
  const coords = stationCoords.get(String(stopId));
  if (!coords) {
    src.setData({ type: "FeatureCollection", features: [] });
    return;
  }
  const [lng, lat] = coords;
  src.setData({
    type: "FeatureCollection",
    features: [
      { type: "Feature", properties: { radius: "half" },
        geometry: circlePolygon(lng, lat, HALF_MILE_M) },
      { type: "Feature", properties: { radius: "quarter" },
        geometry: circlePolygon(lng, lat, QUARTER_MILE_M) },
    ],
  });
  // Make sure the rings + fill overlay are the topmost layers.
  applyLayerOrder();
}

function clearActiveStation() { setActiveStation(null); }


// ---- Active district highlight --------------------------------------------
// Mirrors the TOD station's transparent-black overlay, but on the polygon
// of the currently-selected council district. No outline (the existing
// council-line layer already draws district boundaries).

let _districtGeometries = null;  // Map<district_num, geometry>

async function loadDistrictGeometries() {
  if (_districtGeometries) return _districtGeometries;
  const r = await fetch("data/council.geojson");
  const data = await r.json();
  _districtGeometries = new Map();
  for (const feat of (data.features || [])) {
    const num = feat.properties?.district;
    if (num != null) _districtGeometries.set(String(num), feat.geometry);
  }
  return _districtGeometries;
}

function ensureActiveDistrictLayer() {
  if (map.getSource("active-district-src")) return;
  map.addSource("active-district-src", {
    type: "geojson",
    data: { type: "FeatureCollection", features: [] },
  });
  map.addLayer({
    id: "active-district-fill",
    type: "fill",
    source: "active-district-src",
    paint: { "fill-color": "#000000", "fill-opacity": 0.15 },
  });
}

async function setActiveDistrict(districtNum) {
  ensureActiveDistrictLayer();
  const src = map.getSource("active-district-src");
  if (!districtNum) {
    src.setData({ type: "FeatureCollection", features: [] });
    return;
  }
  const geoms = await loadDistrictGeometries();
  const geom = geoms.get(String(districtNum));
  if (!geom) {
    src.setData({ type: "FeatureCollection", features: [] });
    return;
  }
  src.setData({
    type: "FeatureCollection",
    features: [{ type: "Feature", properties: {}, geometry: geom }],
  });
  applyLayerOrder();
}

function clearActiveDistrict() { setActiveDistrict(null); }

function initReports() {
  const todBtn = document.getElementById("open-tod-report");
  const distBtn = document.getElementById("open-district-report");
  const luBtn  = document.getElementById("open-land-use-report");
  const closeBtn = document.getElementById("close-report");
  const panel = document.getElementById("report-panel");
  const select = document.getElementById("report-select");
  if (!todBtn || !distBtn || !closeBtn || !panel || !select) return;

  todBtn.addEventListener("click", () => openReportPanel("tod"));
  distBtn.addEventListener("click", () => openReportPanel("district"));
  if (luBtn) luBtn.addEventListener("click", () => openReportPanel("land_use"));
  closeBtn.addEventListener("click", () => {
    panel.classList.add("hidden");
    panel.setAttribute("aria-hidden", "true");
    clearActiveStation();
    clearActiveDistrict();
  });
  select.addEventListener("change", () => renderReport(select.value));
}

async function loadDistrictReports() {
  if (districtReports) return districtReports;
  const r = await fetch("data/district_reports.json");
  districtReports = (await r.json()).districts;
  districtReports.sort((a, b) => parseInt(a.district, 10) - parseInt(b.district, 10));
  return districtReports;
}

async function populateSelect(mode) {
  const select = document.getElementById("report-select");
  if (mode === "tod") {
    const data = await loadStationReports();
    select.innerHTML =
      `<option value="">— select a station —</option>` +
      data.map((s, i) => `<option value="${i}">${s.stop_name}</option>`).join("");
  } else {
    const data = await loadDistrictReports();
    select.innerHTML =
      `<option value="">— select a district —</option>` +
      data.map((d, i) => `<option value="${i}">District ${d.district} — ${d.council_member}</option>`).join("");
  }
}

async function openReportPanel(mode, preselectKey) {
  reportMode = mode;
  const panel = document.getElementById("report-panel");
  const title = document.getElementById("report-title");
  const label = document.getElementById("report-select-label");
  const select = document.getElementById("report-select");
  const controls = document.querySelector(".report-controls");

  if (mode === "tod") {
    title.textContent = "TOD Opportunity Areas";
    label.textContent = "Station";
    clearActiveDistrict();
    if (controls) controls.style.display = "";
  } else if (mode === "district") {
    title.textContent = "Council Districts";
    label.textContent = "District";
    clearActiveStation();
    if (controls) controls.style.display = "";
  } else if (mode === "land_use") {
    title.textContent = "Value by Land Use";
    clearActiveStation();
    clearActiveDistrict();
    // Hide the single-select dropdown; this mode uses inline multi-select checkboxes.
    if (controls) controls.style.display = "none";
  }

  if (mode === "land_use") {
    await renderLandUseReport();
    panel.classList.remove("hidden");
    panel.setAttribute("aria-hidden", "false");
    return;
  }

  await populateSelect(mode);

  if (preselectKey != null) {
    let i = -1;
    if (mode === "tod") {
      i = stationReports.findIndex((s) => s.stop_name === preselectKey);
    } else {
      i = districtReports.findIndex((d) => String(d.district) === String(preselectKey));
    }
    if (i >= 0) {
      select.value = String(i);
      renderReport(String(i));
    } else {
      select.value = "";
      renderReport("");
    }
  } else {
    select.value = "";
    renderReport("");
  }

  panel.classList.remove("hidden");
  panel.setAttribute("aria-hidden", "false");
}

// Backwards-compat shim — the rail-stops popup calls openReportFor(stationName)
function openReportFor(stationName) {
  openReportPanel("tod", stationName);
}

function renderReport(idxStr) {
  if (reportMode === "district") return renderDistrictReport(idxStr);
  if (reportMode === "land_use") return renderLandUseReport();
  return renderTodReport(idxStr);
}

// --- Value by Land Use --------------------------------------------------

let landUseSummary = null;
const luSelected = new Set();   // currently-checked land-use categories
let luInitialized = false;       // true once we've seeded the default selection
let luMetric = "tot_val";        // "tot_val" | "impr_val" | "land_val"

const LU_METRIC_LABELS = {
  tot_val:  "Total value",
  impr_val: "Improvement value",
  land_val: "Taxable land value",
};

async function loadLandUseSummary() {
  if (landUseSummary) return landUseSummary;
  const r = await fetch("data/land_use_value_summary.json");
  landUseSummary = await r.json();
  return landUseSummary;
}

async function renderLandUseReport() {
  const content = document.getElementById("report-content");
  const data = await loadLandUseSummary();
  const totals = data.totals;
  const cats   = data.by_land_use;

  // Seed default = everything checked, but only on the very first render.
  // (Otherwise "Clear" would race against this fallback.)
  if (!luInitialized) {
    cats.forEach(c => luSelected.add(c.land_use));
    luInitialized = true;
  }

  const metricTotal = totals[luMetric] || 0;
  const metricLabel = LU_METRIC_LABELS[luMetric];

  const rowsHtml = cats.map(c => {
    const v = c[luMetric] || 0;
    const pct = metricTotal > 0 ? (v / metricTotal * 100) : 0;
    const checked = luSelected.has(c.land_use) ? "checked" : "";
    return `
      <label class="lu-row">
        <input type="checkbox" data-lu="${escapeAttr(c.land_use)}" ${checked} />
        <span class="lu-name">${c.land_use}</span>
        <span class="lu-share">${pct.toFixed(1)}%</span>
        <span class="lu-money">${fmtMoney(v)}</span>
      </label>`;
  }).join("");

  content.innerHTML = `
    <p class="muted" style="margin:0 0 8px 0">
      Toggle land uses to see their combined share of the city's appraised property value.
      Citywide totals are from DCAD 2025 certified plus the latest Collin and Denton CAD rolls,
      across all ${fmt(totals.parcels)} parcels.
    </p>

    <div class="lu-metric-bar">
      <label class="lu-metric-opt"><input type="radio" name="lu-metric" value="tot_val"  ${luMetric==="tot_val"?"checked":""}/> Total</label>
      <label class="lu-metric-opt"><input type="radio" name="lu-metric" value="impr_val" ${luMetric==="impr_val"?"checked":""}/> Improvement</label>
      <label class="lu-metric-opt"><input type="radio" name="lu-metric" value="land_val" ${luMetric==="land_val"?"checked":""}/> Taxable land</label>
    </div>

    <div class="lu-selector-actions">
      <button type="button" id="lu-select-all" class="lu-mini-btn">Select all</button>
      <button type="button" id="lu-select-none" class="lu-mini-btn">Clear</button>
    </div>

    <div class="lu-header">
      <span class="lu-name">Land use</span>
      <span class="lu-share">% of ${luMetric === "tot_val" ? "value" : luMetric === "impr_val" ? "imp" : "land"}</span>
      <span class="lu-money">${metricLabel}</span>
    </div>
    <div id="lu-list">${rowsHtml}</div>

    <div id="lu-summary" class="lu-summary"></div>
  `;

  // Wire up
  content.querySelectorAll('input[data-lu]').forEach(cb => {
    cb.addEventListener("change", () => {
      const k = cb.dataset.lu;
      if (cb.checked) luSelected.add(k); else luSelected.delete(k);
      updateLandUseSummary();
    });
  });
  content.querySelectorAll('input[name="lu-metric"]').forEach(rb => {
    rb.addEventListener("change", () => {
      if (rb.checked) {
        luMetric = rb.value;
        renderLandUseReport();   // re-render to refresh share column + summary
      }
    });
  });
  document.getElementById("lu-select-all").addEventListener("click", () => {
    cats.forEach(c => luSelected.add(c.land_use));
    renderLandUseReport();
  });
  document.getElementById("lu-select-none").addEventListener("click", () => {
    luSelected.clear();
    renderLandUseReport();
  });

  updateLandUseSummary();
}

function updateLandUseSummary() {
  if (!landUseSummary) return;
  const totals = landUseSummary.totals;
  let p = 0, a = 0, t = 0, i = 0, l = 0;
  // Selected categories, sorted by their value/acre for the chosen metric, descending
  const selectedRows = [];
  for (const c of landUseSummary.by_land_use) {
    if (luSelected.has(c.land_use)) {
      p += c.parcels;  a += c.acres;
      t += c.tot_val;  i += c.impr_val;  l += c.land_val;
      const v = c[luMetric] || 0;
      const ppa = c.acres > 0 ? v / c.acres : 0;
      selectedRows.push({ name: c.land_use, ppa });
    }
  }
  selectedRows.sort((x, y) => y.ppa - x.ppa);

  const pPct = totals.parcels  > 0 ? p / totals.parcels  * 100 : 0;
  const aPct = totals.acres    > 0 ? a / totals.acres    * 100 : 0;
  const tPct = totals.tot_val  > 0 ? t / totals.tot_val  * 100 : 0;
  const iPct = totals.impr_val > 0 ? i / totals.impr_val * 100 : 0;
  const lPct = totals.land_val > 0 ? l / totals.land_val * 100 : 0;

  const n = luSelected.size;
  const summary = document.getElementById("lu-summary");
  if (!summary) return;

  const ppaSection = selectedRows.length
    ? `
      <div class="lu-stat-spacer"></div>
      <h3 class="lu-summary-title">Avg ${LU_METRIC_LABELS[luMetric].toLowerCase()} / acre, by use</h3>
      ${selectedRows.map(r => `
        <div class="lu-ppa-row">
          <span class="lu-ppa-name">${r.name}</span>
          <span class="lu-ppa-val">${fmtMoney(Math.round(r.ppa))} / acre</span>
        </div>
      `).join("")}
    `
    : "";

  summary.innerHTML = `
    <h3 class="lu-summary-title">${n === 0 ? "No land uses selected" : `${n} land use${n === 1 ? "" : "s"} selected`}</h3>
    <div class="lu-stat"><span class="lu-stat-label">Parcels</span><span class="lu-stat-val">${fmt(p)}</span><span class="lu-stat-pct">${pPct.toFixed(1)}%</span></div>
    <div class="lu-stat"><span class="lu-stat-label">Acres</span><span class="lu-stat-val">${fmt(Math.round(a))}</span><span class="lu-stat-pct">${aPct.toFixed(1)}%</span></div>
    <div class="lu-stat-spacer"></div>
    <div class="lu-stat"><span class="lu-stat-label">Total value</span><span class="lu-stat-val">${fmtMoney(t)}</span><span class="lu-stat-pct">${tPct.toFixed(1)}%</span></div>
    <div class="lu-stat"><span class="lu-stat-label">Improvement value</span><span class="lu-stat-val">${fmtMoney(i)}</span><span class="lu-stat-pct">${iPct.toFixed(1)}%</span></div>
    <div class="lu-stat"><span class="lu-stat-label">Taxable land value</span><span class="lu-stat-val">${fmtMoney(l)}</span><span class="lu-stat-pct">${lPct.toFixed(1)}%</span></div>
    ${ppaSection}
  `;
}

function escapeAttr(s) {
  return String(s).replace(/&/g, "&amp;").replace(/"/g, "&quot;");
}

function renderTodReport(idxStr) {
  const content = document.getElementById("report-content");
  if (idxStr === "" || idxStr == null) {
    content.innerHTML = '<p class="muted">Pick a station to see its TOD profile.</p>';
    clearActiveStation();
    return;
  }
  const i = parseInt(idxStr, 10);
  const s = stationReports[i];
  if (!s) return;
  setActiveStation(s.stop_id);

  const fmtIncome = (v) => v == null ? "—" : "$" + Number(v).toLocaleString();
  const fmtNum = (v) => v == null ? "—" : Number(v).toLocaleString();
  const fmtYear = (v) => v == null ? "—" : String(v);

  // Average FAR: total apportioned building sq ft ÷ total apportioned parcel
  // area (acres * 43,560 to convert to sq ft). Shown to 2 decimals.
  const avgFar = (() => {
    const sf = s.half_mile.total_building_sf;
    const acres = s.half_mile.land_acres;
    if (!sf || !acres) return null;
    return sf / (acres * 43560);
  })();
  const fmtFar = (v) => v == null ? "—" : v.toFixed(2);

  // Match the District-report styling: label/value rows in popup-row format
  function rows(arr) {
    return arr.map(([label, value]) =>
      `<div class="popup-row"><span class="label">${label}</span><span class="value">${value}</span></div>`
    ).join("");
  }

  const headerStats = rows([
    ["Dwelling units (1/2-mile radius)",            fmtNum(s.half_mile.dwelling_units)],
    ["Dwelling units (1/4-mile radius)",            fmtNum(s.quarter_mile.dwelling_units)],
    ["Avg floor-area ratio (1/2-mile radius)",      fmtFar(avgFar)],
    ["Avg year built (1/2-mile radius)",            fmtYear(s.half_mile.avg_year_built)],
    ["Median household income (2024, census tract)", fmtIncome(s.tract_mhi_2024)],
    ["Median family income (2024, census tract)",    fmtIncome(s.tract_mfi_2024)],
  ]);

  // Fixed legend orders so stations are visually comparable
  const ZONING_ORDER = Object.keys(ZONING_COLORS);
  const FAR_ORDER = FAR_BINS;
  const LU_ORDER = LAND_USE_DEFS.map((d) => d.dataValue)
    .filter((v) => !VACANT_DATA_VALUES.includes(v))
    .concat(["Vacant"]);
  const DECADE_ORDER = DECADE_BINS.map((b) => b.label);

  const ZONING_COLOR_FN = (k) => ZONING_COLORS[k] || "#CCCCCC";
  const LU_COLOR_FN = (k) => {
    if (k === "Vacant") return "#A89F94";
    const def = LAND_USE_DEFS.find((d) => d.dataValue === k);
    return def ? def.color : "#CCCCCC";
  };
  const FAR_COLOR_FN = (k) => FAR_COLORS[k] || "#CCCCCC";
  const DECADE_COLOR_FN = (k) => {
    const b = DECADE_BINS.find((b) => b.label === k);
    return b ? b.color : "#CCCCCC";
  };

  // Two-column pct block (1/4 mi vs 1/2 mi). Title omitted from the
  // section-head's first column since the h3 above already names the
  // section — only the column headers remain in the section-head row.
  function renderPctBlock(qPcts, hPcts, order, colorFn) {
    let html = `<div class="report-section-head">
      <span></span>
      <span class="pct-num">1/4 mi</span>
      <span class="pct-num">1/2 mi</span>
    </div>`;
    for (const k of order) {
      const q = qPcts ? qPcts[k] : null;
      const h = hPcts ? hPcts[k] : null;
      if (q == null && h == null) continue;
      html += `<div class="pct-row">
        <span class="pct-label">
          <span class="pct-swatch" style="background:${colorFn(k)}"></span>${k}
        </span>
        <span class="pct-num">${q != null ? q.toFixed(1) + "%" : "—"}</span>
        <span class="pct-num">${h != null ? h.toFixed(1) + "%" : "—"}</span>
      </div>`;
    }
    return `<div class="pct-block">${html}</div>`;
  }

  content.innerHTML = `
    <h3>${s.stop_name}</h3>
    <p class="muted" style="margin:4px 0 12px 0;font-size:11px">
      <span style="display:inline-block;width:10px;height:10px;border:2px dashed #222222;border-radius:50%;vertical-align:middle;margin-right:4px"></span>1/4 mile
      &nbsp;
      <span style="display:inline-block;width:10px;height:10px;border:2px solid #222222;border-radius:50%;vertical-align:middle;margin-right:4px"></span>1/2 mile
      &nbsp;shown on map
    </p>
    ${headerStats}

    <h3>Base zoning</h3>
    ${renderPctBlock(s.quarter_mile.zoning_pct, s.half_mile.zoning_pct, ZONING_ORDER, ZONING_COLOR_FN)}

    <h3>Land use</h3>
    ${renderPctBlock(s.quarter_mile.land_use_pct, s.half_mile.land_use_pct, LU_ORDER, LU_COLOR_FN)}

    <h3>Building floor-area ratio (FAR)</h3>
    ${renderPctBlock(s.quarter_mile.far_pct, s.half_mile.far_pct, FAR_ORDER, FAR_COLOR_FN)}

    <h3>Decade structure built</h3>
    ${renderPctBlock(s.quarter_mile.decade_pct, s.half_mile.decade_pct, DECADE_ORDER, DECADE_COLOR_FN)}
  `;
}


// ---- District report renderer ----------------------------------------------

function renderDistrictReport(idxStr) {
  const content = document.getElementById("report-content");
  if (idxStr === "" || idxStr == null) {
    content.innerHTML = '<p class="muted">Pick a district to see its profile.</p>';
    clearActiveDistrict();
    return;
  }
  const i = parseInt(idxStr, 10);
  const d = districtReports[i];
  if (!d) return;
  setActiveDistrict(d.district);

  const fmtNum   = (v) => v == null ? "—" : Number(v).toLocaleString();
  const fmtMoney = (v) => v == null ? "—" : "$" + Number(v).toLocaleString();
  const fmtPct   = (v) => v == null ? "—" : v.toFixed(1) + "%";
  const fmtSize  = (v) => v == null ? "—" : Number(v).toFixed(2);
  const fmtChg   = (v) => v == null ? "—" : (v > 0 ? "+" : "") + Number(v).toLocaleString();

  // Small inline-styled swatch usable inside any context (popup-row label etc.)
  function swatch(color) {
    return `<span style="display:inline-block;width:11px;height:11px;border-radius:2px;border:1px solid rgba(0,0,0,0.15);background:${color};margin-right:6px;vertical-align:-1px"></span>`;
  }

  // Label/value rows in the consistent popup-row style used everywhere in the report
  function rows(arr) {
    return arr.map(([label, value]) =>
      `<div class="popup-row"><span class="label">${label}</span><span class="value">${value}</span></div>`
    ).join("");
  }

  // Single-column % block (used in Built environment subsections)
  function singlePctBlock(title, pcts, order, colorFn) {
    let html = `<div class="report-section-head">
      <span>${title}</span>
      <span class="pct-num">% of land</span>
    </div>`;
    for (const k of order) {
      const v = pcts ? pcts[k] : null;
      if (v == null) continue;
      html += `<div class="pct-row pct-row-single">
        <span class="pct-label">
          <span class="pct-swatch" style="background:${colorFn(k)}"></span>${k}
        </span>
        <span class="pct-num">${v.toFixed(1)}%</span>
      </div>`;
    }
    return `<div class="pct-block">${html}</div>`;
  }

  // Race / ethnicity colors (used inline inside the People section now)
  const RC = {
    hispanic: "#E37339",
    nh_white: "#7B47B8",
    nh_black: "#2877B0",
    nh_asian: "#2A9F8F",
    other:    "#B8B0A0",
  };

  // Built-environment color functions
  const ZONING_ORDER = Object.keys(ZONING_COLORS);
  const FAR_ORDER = FAR_BINS;
  const LU_ORDER = LAND_USE_DEFS.map((x) => x.dataValue)
    .filter((v) => !VACANT_DATA_VALUES.includes(v))
    .concat(["Vacant"]);
  const DECADE_ORDER = DECADE_BINS.map((b) => b.label);
  const ZONING_COLOR_FN = (k) => ZONING_COLORS[k] || "#CCCCCC";
  const LU_COLOR_FN = (k) => {
    if (k === "Vacant") return "#A89F94";
    const def = LAND_USE_DEFS.find((x) => x.dataValue === k);
    return def ? def.color : "#CCCCCC";
  };
  const FAR_COLOR_FN = (k) => FAR_COLORS[k] || "#CCCCCC";
  const DECADE_COLOR_FN = (k) => {
    const b = DECADE_BINS.find((b) => b.label === k);
    return b ? b.color : "#CCCCCC";
  };

  const popPct = (d.pop_2010 && d.pop_2010 > 0)
    ? (d.pop_change / d.pop_2010 * 100).toFixed(1) + "%" : "—";
  const huPct  = (d.hu_2010 && d.hu_2010 > 0)
    ? (d.hu_change / d.hu_2010 * 100).toFixed(1) + "%" : "—";

  content.innerHTML = `
    <h3>District ${d.district} — ${d.council_member}</h3>
    <p class="muted" style="margin:4px 0 12px 0;font-size:11px">
      ${d.area_sqmi} sq mi
    </p>

    ${rows([
      ["Population",                fmtNum(d.pop)],
      ["Density (people / sq mi)",  fmtNum(d.density)],
      ["Median household income",   fmtMoney(d.mhi)],
      ["Median family income",      fmtMoney(d.mfi)],
      ["Median age",                d.med_age ?? "—"],
    ])}

    <h3>Housing stock</h3>
    ${rows([
      ["Dwelling units (DCAD)",         fmtNum(d.dcad_units)],
      ["Dwelling units (ACS)",          fmtNum(d.hu_acs)],
      ["Median year built",             d.med_yr_built ?? "—"],
      ["Avg household size",            fmtSize(d.avg_hh_size)],
      ["% overcrowded (>1 per room)",   fmtPct(d.pct_overcrowded)],
      ["Homeownership rate",            fmtPct(d.pct_owner)],
      ["Vacancy rate",                  fmtPct(d.vacancy_rate)],
    ])}

    <h3>Housing costs &amp; affordability</h3>
    ${rows([
      ["Median home value",                       fmtMoney(d.med_home_value)],
      ["Median rent",                             fmtMoney(d.med_rent)],
      ["Renters cost-burdened (&gt;30% of income)",   fmtPct(d.pct_renter_cb)],
      ["Renters severely cost-burdened (&gt;50%)",    fmtPct(d.pct_renter_scb)],
      ["Owners cost-burdened (&gt;30%)",              fmtPct(d.pct_owner_cb)],
      ["Owners severely cost-burdened (&gt;50%)",     fmtPct(d.pct_owner_scb)],
    ])}

    <h3>People</h3>
    ${rows([
      ["% under 18",                              fmtPct(d.pct_under_18)],
      ["% 65 or older",                           fmtPct(d.pct_65plus)],
      ["% foreign-born",                          fmtPct(d.pct_foreign_born)],
      ["% bachelor's degree or higher (25+)",     fmtPct(d.pct_bach_or_higher)],
      [`${swatch(RC.hispanic)}Hispanic`,          fmtPct(d.pct_hispanic)],
      [`${swatch(RC.nh_white)}White (non-Hispanic)`, fmtPct(d.pct_nh_white)],
      [`${swatch(RC.nh_black)}Black (non-Hispanic)`, fmtPct(d.pct_nh_black)],
      [`${swatch(RC.nh_asian)}Asian (non-Hispanic)`, fmtPct(d.pct_nh_asian)],
      [`${swatch(RC.other)}Other (non-Hispanic)`,    fmtPct(d.pct_other)],
    ])}

    <h3>Mobility</h3>
    ${rows([
      ["Rail stations in district",                fmtNum(d.rail_stations)],
      ["% of district within 1/2 mi of rail",      fmtPct(d.pct_within_half_mi_rail)],
      ["% households with no vehicle",             fmtPct(d.pct_no_vehicle)],
      ["% non-auto commute (walk, bike, transit, WFH)", fmtPct(d.pct_non_auto_commute)],
    ])}

    <h3>Recent change (2010 → 2020 Census)</h3>
    ${rows([
      ["Population 2010",    fmtNum(d.pop_2010)],
      ["Population 2020",    fmtNum(d.pop_2020)],
      ["Change",             `${fmtChg(d.pop_change)} (${popPct})`],
      ["Housing units 2010", fmtNum(d.hu_2010)],
      ["Housing units 2020", fmtNum(d.hu_2020)],
      ["Change",             `${fmtChg(d.hu_change)} (${huPct})`],
    ])}

    <h3>Permitted housing (2010–2024)</h3>
    ${rows([
      ["Single-family units",             fmtNum(d.permit_units_sf)],
      ["Multifamily units",               fmtNum(d.permit_units_mf)],
      ["Commercial (incl. mixed-use)",    fmtNum(d.permit_units_com)],
      ["Total new units permitted",       fmtNum(d.permit_units_total)],
    ])}

    <h3>Built environment</h3>
    ${singlePctBlock("Base zoning",     d.zoning_pct,    ZONING_ORDER, ZONING_COLOR_FN)}
    ${singlePctBlock("Land use",        d.land_use_pct,  LU_ORDER,     LU_COLOR_FN)}
    ${singlePctBlock("Building floor-area ratio (FAR)", d.far_pct, FAR_ORDER, FAR_COLOR_FN)}
    ${singlePctBlock("Decade structure built", d.decade_pct, DECADE_ORDER, DECADE_COLOR_FN)}
  `;
}


// ============================================================================
// County boundaries + Rent / Home-value change layers
// ============================================================================

// ---- County boundaries (dissolved 7-county outlines) -----------------------
LAYERS.counties = {
  label: "County boundaries",
  sourceId: "counties-src",
  sourceFile: "data/counties.geojson",
  layerIds: ["counties-line", "counties-label"],
  addLayers: () => {
    map.addLayer({
      id: "counties-line",
      type: "line",
      source: "counties-src",
      paint: {
        "line-color": "#3A3A3A",
        "line-width": 1.6,
        "line-dasharray": [3, 1.5],
        "line-opacity": 0.85,
      },
    });
    map.addLayer({
      id: "counties-label",
      type: "symbol",
      source: "counties-src",
      layout: {
        "text-field": ["get", "name"],
        "text-font": ["Noto Sans Regular"],
        "text-size": 13,
        "text-transform": "uppercase",
        "text-letter-spacing": 0.12,
      },
      paint: {
        "text-color": "#555555",
        "text-halo-color": "#FFFFFF",
        "text-halo-width": 1.6,
      },
    });
  },
  popup: () => "",
  clickLayer: null,
  legendGroup: "Jurisdiction boundaries",
  legendOrder: 2,
  legendRow: () => `<div class="swatch-row"><span class="line-swatch" style="border-top-style:dashed;border-top-color:#3A3A3A"></span>Counties</div>`,
};


// ---- Rent / Home-value change (ACS tract + Zillow ZIP) ---------------------
// Each metric ("rent", "value") is one grouped toggle that switches between an
// ACS tract source and a Zillow ZIP source, offers $-change / %-change, and a
// dual-thumb year slider. All values are constant 2024 dollars (deflated in the
// Python build), so % change is real (inflation-stripped) growth.

const RV_NODATA = "rgba(0,0,0,0)";   // metric absent for a feature -> background
const RV_MAX_MOE = 0.30;             // ACS: gray a tract-year if MOE/est exceeds this (keep in sync with MAX_MOE_RATIO in build_acs_rent_value.py)

// Diverging palettes: reds = real loss, cream = stable, blues = real gain.
// Asymmetric (real housing costs mostly rose), so the gain side is finer.
const RV_PAL6 = ["#D64550", "#F4A6A6", "#FAF5C5", "#A6CDE3", "#4A90A4", "#1D4F66"];            // 2 loss + stable + 3 gain
const RV_PAL7 = ["#D64550", "#F4A6A6", "#FAF5C5", "#A6CDE3", "#4A90A4", "#2E6F86", "#1D4F66"]; // 2 loss + stable + 4 gain

// Per (metric, mode): bin edges, the matching bin labels, and colors. Shared
// across sources so ACS and Zillow read comparably. colors.length === edges
// length + 1. Constant 2024$ / real %.
const RV_SCHEME = {
  rent: {
    dollar: {
      edges:  [-300, -100, 100, 300, 500],
      labels: ["Loss > $300", "Loss $100–$300", "Stable (±$100)",
               "Gain $100–$300", "Gain $300–$500", "Gain > $500"],
      colors: RV_PAL6,
    },
    pct: {
      edges:  [-15, -5, 5, 15, 30, 50],
      labels: ["Loss > 15%", "Loss 5–15%", "Stable (±5%)",
               "Gain 5–15%", "Gain 15–30%", "Gain 30–50%", "Gain > 50%"],
      colors: RV_PAL7,
    },
  },
  value: {
    dollar: {
      edges:  [-50000, -15000, 15000, 100000, 250000, 450000],
      labels: ["Loss > $50k", "Loss $15k–$50k", "Stable (±$15k)",
               "Gain $15k–$100k", "Gain $100k–$250k", "Gain $250k–$450k", "Gain > $450k"],
      colors: RV_PAL7,
    },
    pct: {
      edges:  [-15, -5, 5, 25, 60, 100],
      labels: ["Loss > 15%", "Loss 5–15%", "Stable (±5%)",
               "Gain 5–25%", "Gain 25–60%", "Gain 60–100%", "Gain > 100%"],
      colors: RV_PAL7,
    },
  },
};

// metric -> source -> GeoJSON property-key prefix
const RV_KEY = {
  rent:  { acs: "rent", zillow: "zori" },
  value: { acs: "val",  zillow: "zhvi" },
};

const RV_SOURCES = {
  acs:    { srcId: "acs-rv-src",     file: "data/acs_rent_value_tracts.geojson" },
  zillow: { srcId: "zillow-zip-src", file: "data/zillow_zip.geojson" },
};

// Slider range per (metric, source). ACS = 2012-2024. Zillow home value (ZHVI)
// goes back to 2010; Zillow rent (ZORI) only exists from 2015, so its floor is
// 2015 (no earlier data exists at all).
function rvRange(metric, source) {
  if (source === "acs") return { min: 2012, max: 2024 };
  if (metric === "rent") return { min: 2015, max: 2025 };
  return { min: 2010, max: 2025 };
}

const rvState = {
  rent:  { master: false, source: "acs", mode: "dollar", yearStart: 2012, yearEnd: 2024, added: false },
  value: { master: false, source: "acs", mode: "dollar", yearStart: 2012, yearEnd: 2024, added: false },
};

// Null-safe presence test. Properties are present-with-null in the GeoJSON, so
// `has` can't distinguish them — coalesce to a sentinel and compare.
const RV_SENTINEL = -1e15;
function rvMissing(key) {
  return ["==", ["coalesce", ["get", key], RV_SENTINEL], RV_SENTINEL];
}
function rvPresent(key) { return ["!", rvMissing(key)]; }

// ACS reliability (matches the build): a tract-year is reliable if it has both an
// estimate and a MOE, and MOE/estimate <= RV_MAX_MOE. Unreliable cells render
// gray, like low-density tracts in the pop/HU change layers.
function rvAcsReliable(metric, year) {
  const pfx = RV_KEY[metric].acs;
  const estKey = `${pfx}_${year}`, moeKey = `${pfx}_moe_${year}`;
  return ["all",
    rvPresent(estKey), rvPresent(moeKey),
    ["<=", ["to-number", ["get", moeKey]], ["*", RV_MAX_MOE, ["to-number", ["get", estKey]]]]];
}

function rvChangeExpr(metric, source) {
  const st = rvState[metric];
  const pfx = RV_KEY[metric][source];
  const s = ["to-number", ["get", `${pfx}_${st.yearStart}`]];
  const e = ["to-number", ["get", `${pfx}_${st.yearEnd}`]];
  return st.mode === "pct"
    ? ["/", ["*", 100, ["-", e, s]], s]
    : ["-", e, s];
}

function rvStepExpr(metric, source) {
  const sc = RV_SCHEME[metric][rvState[metric].mode];
  const step = ["step", rvChangeExpr(metric, source), sc.colors[0]];
  for (let i = 0; i < sc.edges.length; i++) step.push(sc.edges[i], sc.colors[i + 1]);
  return step;
}

function rvFillColor(metric, source) {
  const st = rvState[metric];
  const pfx = RV_KEY[metric][source];
  if (source === "zillow") {
    const missingEither = ["any",
      rvMissing(`${pfx}_${st.yearStart}`), rvMissing(`${pfx}_${st.yearEnd}`)];
    const hasKey = metric === "rent" ? "has_zori" : "has_zhvi";
    return ["case",
      ["!", ["coalesce", ["get", hasKey], false]], RV_NODATA,  // no data ever -> background
      missingEither, RV_NODATA,                                 // covered, but not this range (hatch draws over)
      rvStepExpr(metric, "zillow")];
  }
  // ACS: gray where either endpoint is unreliable (MOE > 30% of the estimate, or missing).
  const unreliable = ["any",
    ["!", rvAcsReliable(metric, st.yearStart)],
    ["!", rvAcsReliable(metric, st.yearEnd)]];
  return ["case", unreliable, LOW_DENS_COLOR, rvStepExpr(metric, "acs")];
}

// Zillow cross-hatch: ZIPs that HAVE the metric but lack a value at the chosen
// start or end year (their series begins after the chosen start).
function rvHatchFilter(metric) {
  const st = rvState[metric];
  const pfx = RV_KEY[metric].zillow;
  const hasKey = metric === "rent" ? "has_zori" : "has_zhvi";
  return ["all",
    ["coalesce", ["get", hasKey], false],
    ["any", rvMissing(`${pfx}_${st.yearStart}`), rvMissing(`${pfx}_${st.yearEnd}`)]];
}
function rvZipHasFilter(metric) {
  return ["coalesce", ["get", metric === "rent" ? "has_zori" : "has_zhvi"], false];
}

// Crossing-diagonal hatch image (distinct from the vacant single-stripe), used
// for Zillow ZIPs whose series starts after the chosen start year.
function ensureCrossHatchImage() {
  if (map.hasImage("cross-hatch")) return;
  const size = 8;
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = size;
  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, size, size);
  ctx.strokeStyle = "#555555";
  ctx.lineWidth = 0.8;
  ctx.beginPath();
  ctx.moveTo(-1, size + 1);        ctx.lineTo(size + 1, -1);
  ctx.moveTo(-1 - size, size + 1); ctx.lineTo(1, -1);
  ctx.moveTo(size - 1, size + 1);  ctx.lineTo(2 * size + 1, -1);
  ctx.moveTo(-1, -1);              ctx.lineTo(size + 1, size + 1);
  ctx.moveTo(size - 1, -1);        ctx.lineTo(2 * size + 1, size + 1);
  ctx.moveTo(-1 - size, -1);       ctx.lineTo(1, size + 1);
  ctx.stroke();
  map.addImage("cross-hatch", ctx.getImageData(0, 0, size, size), { pixelRatio: 1 });
}

const rvSourcesAdded = new Set();
async function ensureRVSource(source) {
  const def = RV_SOURCES[source];
  if (rvSourcesAdded.has(def.srcId) || map.getSource(def.srcId)) {
    rvSourcesAdded.add(def.srcId);
    return;
  }
  const r = await fetch(def.file);
  map.addSource(def.srcId, { type: "geojson", data: await r.json() });
  rvSourcesAdded.add(def.srcId);
}

function addRVLayers(metric) {
  const st = rvState[metric];
  if (st.added) return;
  ensureCrossHatchImage();
  map.addLayer({ id: `${metric}-acs-fill`, type: "fill", source: "acs-rv-src",
    layout: { visibility: "none" },
    paint: { "fill-color": rvFillColor(metric, "acs"), "fill-opacity": 0.78 } },
    beneathTopLayers());
  map.addLayer({ id: `${metric}-acs-outline`, type: "line", source: "acs-rv-src",
    layout: { visibility: "none" },
    paint: { "line-color": "#FFFFFF", "line-width": 0.4, "line-opacity": 0.6 } },
    beneathTopLayers());
  map.addLayer({ id: `${metric}-zip-fill`, type: "fill", source: "zillow-zip-src",
    layout: { visibility: "none" },
    paint: { "fill-color": rvFillColor(metric, "zillow"), "fill-opacity": 0.78 } },
    beneathTopLayers());
  map.addLayer({ id: `${metric}-zip-hatch`, type: "fill", source: "zillow-zip-src",
    layout: { visibility: "none" }, filter: rvHatchFilter(metric),
    paint: { "fill-pattern": "cross-hatch", "fill-opacity": 0.9 } },
    beneathTopLayers());
  map.addLayer({ id: `${metric}-zip-outline`, type: "line", source: "zillow-zip-src",
    layout: { visibility: "none" }, filter: rvZipHasFilter(metric),
    paint: { "line-color": "#FFFFFF", "line-width": 0.5, "line-opacity": 0.6 } },
    beneathTopLayers());

  for (const t of [`${metric}-acs-fill`, `${metric}-zip-fill`]) {
    map.on("click", t, (e) => {
      const f = e.features?.[0];
      if (!f) return;
      new maplibregl.Popup({ closeButton: true })
        .setLngLat(e.lngLat).setHTML(rvPopup(metric, f.properties)).addTo(map);
    });
    map.on("mouseenter", t, () => map.getCanvas().style.cursor = "pointer");
    map.on("mouseleave", t, () => map.getCanvas().style.cursor = "");
  }
  st.added = true;
  LAYERS[`${metric}_change`].layerIds.forEach((id) => layersAdded.add(id));
}

function applyRV(metric) {
  const st = rvState[metric];
  const show = (id, vis) => { if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", vis ? "visible" : "none"); };
  const acsVis = st.master && st.source === "acs";
  const zipVis = st.master && st.source === "zillow";
  show(`${metric}-acs-fill`, acsVis);
  show(`${metric}-acs-outline`, acsVis);
  show(`${metric}-zip-fill`, zipVis);
  show(`${metric}-zip-hatch`, zipVis);
  show(`${metric}-zip-outline`, zipVis);
  if (st.added) {
    if (acsVis) {
      map.setPaintProperty(`${metric}-acs-fill`, "fill-color", rvFillColor(metric, "acs"));
    }
    if (zipVis) {
      map.setPaintProperty(`${metric}-zip-fill`, "fill-color", rvFillColor(metric, "zillow"));
      map.setFilter(`${metric}-zip-hatch`, rvHatchFilter(metric));
    }
  }
  LAYERS[`${metric}_change`].enabled = st.master;
  refreshLegend();
}

async function enableRV(metric) {
  // Both sources are referenced by addRVLayers, so both must exist first.
  await Promise.all([ensureRVSource("acs"), ensureRVSource("zillow")]);
  addRVLayers(metric);
  applyRV(metric);
  applyLayerOrder();
}

// ---- Change-layer popup + legend -------------------------------------------
function rvFmtMoney(v) { return v == null ? "—" : "$" + Number(v).toLocaleString(); }

function rvChangeRow(sVal, eVal) {
  const ch = eVal - sVal;
  const pct = sVal > 0 ? (ch / sVal) * 100 : null;
  const cls = ch > 0 ? "positive" : ch < 0 ? "negative" : "";
  const sign = ch > 0 ? "+" : ch < 0 ? "−" : "";
  const pctStr = pct == null ? ""
    : ` (${pct > 0 ? "+" : pct < 0 ? "−" : ""}${Math.abs(pct).toFixed(1)}%)`;
  return `<div class="popup-row popup-change ${cls}">
    <span class="label">Change (real)</span>
    <span class="value">${sign}$${Math.abs(ch).toLocaleString()}${pctStr}</span>
  </div>`;
}

// One ACS year row: estimate ± MOE (both 2024$), flagged "excluded" when the
// MOE exceeds 30% of the estimate; "no estimate" when ACS has none.
function rvAcsYearRow(year, est, moe, reliable) {
  if (est == null) {
    return `<div class="popup-row"><span class="label">${year}</span><span class="value" style="color:#999">no estimate</span></div>`;
  }
  const moeStr = moe != null ? ` ± ${rvFmtMoney(moe)}` : "";
  const flag = reliable ? "" : ` <span style="color:#B5651D;font-size:11px">excluded</span>`;
  return `<div class="popup-row"><span class="label">${year}</span><span class="value">${rvFmtMoney(est)}${moeStr}${flag}</span></div>`;
}

function rvPopup(metric, props) {
  const st = rvState[metric];
  const pfx = RV_KEY[metric][st.source];
  const title = st.source === "acs"
    ? `Tract ${props.geoid}`
    : `ZIP ${props.zip}${props.city ? " · " + props.city : ""}`;
  const metricLabel = metric === "rent"
    ? (st.source === "acs" ? "Median gross rent · ACS 5-yr" : "Median rent · Zillow ZORI")
    : (st.source === "acs" ? "Median home value · ACS 5-yr" : "Typical home value · Zillow ZHVI");
  const header = `<div class="popup-title">${title}</div>` +
    `<div class="popup-row" style="color:#666;font-size:11px;margin-bottom:4px">${metricLabel} · constant 2024$</div>`;

  if (st.source === "acs") {
    const sEst = props[`${pfx}_${st.yearStart}`] ?? null, sMoe = props[`${pfx}_moe_${st.yearStart}`] ?? null;
    const eEst = props[`${pfx}_${st.yearEnd}`] ?? null,   eMoe = props[`${pfx}_moe_${st.yearEnd}`] ?? null;
    const rel = (est, moe) => est != null && moe != null && moe <= RV_MAX_MOE * est;
    const sRel = rel(sEst, sMoe), eRel = rel(eEst, eMoe);
    const change = (sRel && eRel)
      ? rvChangeRow(sEst, eEst)
      : `<div class="popup-row popup-change"><span class="label">Change (real)</span><span class="value" style="color:#999">unavailable</span></div>`;
    const note = ((sEst != null && !sRel) || (eEst != null && !eRel))
      ? `<div class="popup-row" style="margin-top:4px;color:#888;font-size:11px">Estimate excluded because its margin of error exceeds 30% of the estimate.</div>`
      : "";
    return header
      + rvAcsYearRow(st.yearStart, sEst, sMoe, sRel)
      + rvAcsYearRow(st.yearEnd, eEst, eMoe, eRel)
      + change + note;
  }

  // Zillow (no published MOE)
  const sVal = props[`${pfx}_${st.yearStart}`] ?? null, eVal = props[`${pfx}_${st.yearEnd}`] ?? null;
  let body;
  if (sVal == null || eVal == null) {
    const which = sVal == null ? st.yearStart : st.yearEnd;
    body = `<div class="popup-row" style="margin-top:4px;color:#888;font-size:11px">No data for ${which} — series starts later (cross-hatched).</div>`;
  } else {
    body = rvChangeRow(sVal, eVal);
  }
  return header
    + `<div class="popup-row"><span class="label">${st.yearStart}</span><span class="value">${rvFmtMoney(sVal)}</span></div>`
    + `<div class="popup-row"><span class="label">${st.yearEnd}</span><span class="value">${rvFmtMoney(eVal)}</span></div>`
    + body;
}

const RV_HATCH_SWATCH = "repeating-linear-gradient(45deg,#555 0 0.8px,transparent 0.8px 5px)," +
                        "repeating-linear-gradient(-45deg,#555 0 0.8px,transparent 0.8px 5px)";

function buildRVLegend(metric) {
  const st = rvState[metric];
  const sc = RV_SCHEME[metric][st.mode];
  const rows = sc.colors
    .map((c, i) => `<div class="swatch-row"><span class="swatch" style="background:${c}"></span>${sc.labels[i]}</div>`)
    .join("");
  const srcLabel = st.source === "acs" ? "ACS 5-yr · tract" : "Zillow · ZIP";
  const metricName = metric === "rent" ? "Median rent" : "Home value";
  const modeLabel = st.mode === "pct" ? "% change" : "$ change";
  const noData = st.source === "zillow"
    ? `<div class="swatch-row"><span class="swatch" style="background:${RV_HATCH_SWATCH}"></span>No data before ${st.yearStart}</div>`
    : `<div class="swatch-row"><span class="swatch" style="background:${LOW_DENS_COLOR}"></span>No reliable estimate</div>`;
  return `<div class="legend-block">
    <h3>${metricName} change</h3>
    <div class="muted" style="margin:-2px 0 5px 0">${srcLabel} · ${st.yearStart}→${st.yearEnd} · ${modeLabel} · real 2024$</div>
    ${rows}
    ${noData}
  </div>`;
}

LAYERS.rent_change = {
  label: "Median rent change",
  layerIds: ["rent-acs-fill", "rent-acs-outline", "rent-zip-fill", "rent-zip-hatch", "rent-zip-outline"],
  enabled: false,
  legend: () => buildRVLegend("rent"),
};
LAYERS.value_change = {
  label: "Median home value change",
  layerIds: ["value-acs-fill", "value-acs-outline", "value-zip-fill", "value-zip-hatch", "value-zip-outline"],
  enabled: false,
  legend: () => buildRVLegend("value"),
};

// ---- Change-layer UI wiring (sliders + radios + master toggle) -------------
function updateRVRangeBar(metric) {
  const st = rvState[metric];
  const s = document.getElementById(`${metric}-yr-start`);
  const MIN = parseInt(s.min, 10), MAX = parseInt(s.max, 10);
  const span = (MAX - MIN) || 1;
  const left = ((st.yearStart - MIN) / span) * 100;
  const right = ((st.yearEnd - MIN) / span) * 100;
  const range = document.getElementById(`${metric}-yr-range`);
  range.style.left = left + "%";
  range.style.width = (right - left) + "%";
  document.getElementById(`${metric}-yr-start-label`).textContent = st.yearStart;
  document.getElementById(`${metric}-yr-end-label`).textContent = st.yearEnd;
}

function syncRVSlider(metric) {
  const st = rvState[metric];
  const { min, max } = rvRange(metric, st.source);
  const s = document.getElementById(`${metric}-yr-start`);
  const e = document.getElementById(`${metric}-yr-end`);
  s.min = e.min = String(min);
  s.max = e.max = String(max);
  st.yearStart = min; st.yearEnd = max;       // snap to full range of the new source
  s.value = String(min); e.value = String(max);
  updateRVRangeBar(metric);
}

function initRVSlider(metric) {
  const st = rvState[metric];
  const s = document.getElementById(`${metric}-yr-start`);
  const e = document.getElementById(`${metric}-yr-end`);
  if (!s || !e) return;
  s.addEventListener("input", () => {
    let v = parseInt(s.value, 10);
    if (v > st.yearEnd) { v = st.yearEnd; s.value = String(v); }
    st.yearStart = v;
    updateRVRangeBar(metric);
    applyRV(metric);
  });
  e.addEventListener("input", () => {
    let v = parseInt(e.value, 10);
    if (v < st.yearStart) { v = st.yearStart; e.value = String(v); }
    st.yearEnd = v;
    updateRVRangeBar(metric);
    applyRV(metric);
  });
  updateRVRangeBar(metric);
}

function initChangeLayers() {
  for (const metric of ["rent", "value"]) {
    const group = `${metric}_change`;
    const cb = document.querySelector(`input[data-layer-group="${group}"]`);
    if (!cb) continue;
    cb.addEventListener("change", async () => {
      rvState[metric].master = cb.checked;
      if (cb.checked) {
        cb.parentElement.classList.add("loading");
        try { await enableRV(metric); }
        finally { cb.parentElement.classList.remove("loading"); }
      } else {
        applyRV(metric);
      }
    });
    document.querySelectorAll(`input[name="${group}_source"]`).forEach((rb) => {
      rb.addEventListener("change", async () => {
        if (!rb.checked) return;
        rvState[metric].source = rb.value;
        syncRVSlider(metric);
        if (rvState[metric].master && !rvState[metric].added) {
          cb.parentElement.classList.add("loading");
          try { await enableRV(metric); }
          finally { cb.parentElement.classList.remove("loading"); }
        } else {
          applyRV(metric);
        }
      });
    });
    document.querySelectorAll(`input[name="${group}_mode"]`).forEach((rb) => {
      rb.addEventListener("change", () => {
        if (!rb.checked) return;
        rvState[metric].mode = rb.value;
        applyRV(metric);
      });
    });
    initRVSlider(metric);
  }
}

// 3D property-value-per-acre layers: one grouped toggle (Total / Improvement /
// Land radio) in place of three separate ones. The three underlying LAYERS
// entries are mutually exclusive — switching the radio swaps which extrusion
// shows; the shared "cap heights" checkbox is wired separately (data-value-cap).
const VALUE3D_MAP = { total: "value_per_acre", improvement: "impr_per_acre", land: "land_per_acre" };
function initValue3d() {
  const cb = document.querySelector('input[data-layer-group="value3d"]');
  if (!cb) return;
  const selected = () => (document.querySelector('input[name="value3d_level"]:checked') || {}).value || "total";
  async function apply() {
    const sel = selected();
    for (const [k, key] of Object.entries(VALUE3D_MAP)) {
      const want = cb.checked && k === sel;
      if (want && LAYERS[key] && !LAYERS[key].enabled) await enableLayer(key);
      else if (!want && LAYERS[key] && LAYERS[key].enabled) disableLayer(key);
    }
  }
  const run = async () => {
    cb.parentElement.classList.add("loading");
    try { await apply(); } finally { cb.parentElement.classList.remove("loading"); }
  };
  cb.addEventListener("change", run);
  document.querySelectorAll('input[name="value3d_level"]').forEach((rb) => {
    rb.addEventListener("change", () => { if (rb.checked && cb.checked) run(); });
  });
}

// 2D flat-fill property-value-per-acre group: same Total / Improvement / Land
// radio pattern as value3d, no height/cap. Independent of the 3D toggle.
const VALUE2D_MAP = { total: "value_per_acre_2d", improvement: "impr_per_acre_2d", land: "land_per_acre_2d" };
function initValue2d() {
  const cb = document.querySelector('input[data-layer-group="value2d"]');
  if (!cb) return;
  const selected = () => (document.querySelector('input[name="value2d_level"]:checked') || {}).value || "total";
  async function apply() {
    const sel = selected();
    for (const [k, key] of Object.entries(VALUE2D_MAP)) {
      const want = cb.checked && k === sel;
      if (want && LAYERS[key] && !LAYERS[key].enabled) await enableLayer(key);
      else if (!want && LAYERS[key] && LAYERS[key].enabled) disableLayer(key);
    }
  }
  const run = async () => {
    cb.parentElement.classList.add("loading");
    try { await apply(); } finally { cb.parentElement.classList.remove("loading"); }
  };
  cb.addEventListener("change", run);
  document.querySelectorAll('input[name="value2d_level"]').forEach((rb) => {
    rb.addEventListener("change", () => { if (rb.checked && cb.checked) run(); });
  });
}


// ---- Street pattern: dendricity / dead-ends / intersection density ---------
// One grouped toggle with a metric radio, all from build_street_dendricity.py
// (OSM via OSMnx). Palette runs teal (grid / well-connected) -> cream -> red
// (cul-de-sac / dendritic). Dead-end share and intersection density spread DFW
// far better than length-weighted dendricity (whose short stubs compress it),
// so all three are offered. Bin edges are tuned to the 7-county distribution.
const STREET_PAL = ["#1D4F66", "#4A90A4", "#A6CDE3", "#FAF5C5", "#FEA665", "#C44E52"];  // grid -> sprawl
const STREET_NODATA = "#B8B0A0";
const STREET_METRICS = {
  dendricity:   { prop: "dendricity",           label: "Dendricity",
                  edges: [0.02, 0.04, 0.07, 0.12, 0.22], colors: STREET_PAL,
                  note: "tree-like share of street length · low = grid, high = cul-de-sac",
                  fmt: (v) => (+v).toFixed(2) },
  deadend:      { prop: "pct_deadend",          label: "Dead-end share",
                  edges: [4, 8, 12, 18, 25], colors: STREET_PAL,
                  note: "% of nodes that are culs-de-sac · low = grid",
                  fmt: (v) => v + "%" },
  intersection: { prop: "intersection_density", label: "Intersection density",
                  edges: [50, 80, 105, 135, 165], colors: [...STREET_PAL].reverse(),
                  note: "intersections per sq mi · high = grid",
                  fmt: (v) => v + "/mi²" },
};
const streetState = { master: false, metric: "dendricity", added: false };

function streetColor() {
  const m = STREET_METRICS[streetState.metric];
  const step = ["step", ["get", m.prop], m.colors[0]];
  m.edges.forEach((e, i) => step.push(e, m.colors[i + 1]));
  return ["case", ["==", ["coalesce", ["get", m.prop], -1], -1], STREET_NODATA, step];
}

function buildStreetLegend() {
  const m = STREET_METRICS[streetState.metric];
  const labels = [`&lt; ${m.fmt(m.edges[0])}`];
  for (let i = 0; i < m.edges.length - 1; i++) labels.push(`${m.fmt(m.edges[i])} – ${m.fmt(m.edges[i + 1])}`);
  labels.push(`&gt; ${m.fmt(m.edges[m.edges.length - 1])}`);
  const rows = m.colors
    .map((c, i) => `<div class="swatch-row"><span class="swatch" style="background:${c}"></span>${labels[i]}</div>`)
    .join("");
  const nd = `<div class="swatch-row"><span class="swatch" style="background:${STREET_NODATA}"></span>No street data</div>`;
  return `<div class="legend-block">
    <h3>Street pattern · ${m.label}</h3>
    <div class="muted" style="margin:-2px 0 5px 0">${m.note}</div>
    ${rows}${nd}
  </div>`;
}

function streetPopup(p) {
  if (p.dendricity == null) {
    return `<div class="popup-title">Tract ${p.geoid}</div>` +
      `<div class="popup-row" style="color:#888;font-size:11px">No street-network data.</div>`;
  }
  const grid = p.pct_deadend != null && p.pct_deadend < 6 && p.intersection_density > 110;
  const pod = p.pct_deadend != null && p.pct_deadend > 20;
  const interp = grid ? "grid-like (well connected)" : pod ? "dendritic (cul-de-sac / suburban)" : "mixed";
  return `
    <div class="popup-title">Tract ${p.geoid}</div>
    <div class="popup-row" style="color:#666;font-size:11px;margin-bottom:4px">Street pattern — ${interp}</div>
    <div class="popup-row"><span class="label">Dendricity</span><span class="value">${(+p.dendricity).toFixed(2)}</span></div>
    <div class="popup-row"><span class="label">Dead-end share</span><span class="value">${p.pct_deadend == null ? "—" : p.pct_deadend + "%"}</span></div>
    <div class="popup-row"><span class="label">Intersection density</span><span class="value">${fmt(p.intersection_density)} / sq mi</span></div>
    <div class="popup-row"><span class="label">Street length</span><span class="value">${fmt(p.street_mi)} mi</span></div>
  `;
}

LAYERS.street_pattern = {
  label: "Street pattern",
  layerIds: ["street-fill", "street-outline"],
  enabled: false,
  legend: () => buildStreetLegend(),
};

function initStreetPattern() {
  const cb = document.querySelector('input[data-layer-group="street_pattern"]');
  if (!cb) return;
  function apply() {
    const vis = streetState.master ? "visible" : "none";
    ["street-fill", "street-outline"].forEach((id) => {
      if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", vis);
    });
    if (streetState.added && streetState.master) {
      map.setPaintProperty("street-fill", "fill-color", streetColor());
    }
    LAYERS.street_pattern.enabled = streetState.master;
    refreshLegend();
  }
  async function enable() {
    if (!map.getSource("street-src")) {
      const r = await fetch("data/street_dendricity_tracts.geojson");
      map.addSource("street-src", { type: "geojson", data: await r.json() });
    }
    if (!streetState.added) {
      map.addLayer({ id: "street-fill", type: "fill", source: "street-src",
        paint: { "fill-color": streetColor(), "fill-opacity": 0.78 } }, beneathTopLayers());
      map.addLayer({ id: "street-outline", type: "line", source: "street-src",
        paint: { "line-color": "#FFFFFF", "line-width": 0.4, "line-opacity": 0.5 } }, beneathTopLayers());
      map.on("click", "street-fill", (e) => {
        const f = e.features?.[0];
        if (!f) return;
        new maplibregl.Popup({ closeButton: true })
          .setLngLat(e.lngLat).setHTML(streetPopup(f.properties)).addTo(map);
      });
      map.on("mouseenter", "street-fill", () => map.getCanvas().style.cursor = "pointer");
      map.on("mouseleave", "street-fill", () => map.getCanvas().style.cursor = "");
      streetState.added = true;
      LAYERS.street_pattern.layerIds.forEach((id) => layersAdded.add(id));
    }
    apply();
  }
  cb.addEventListener("change", async () => {
    streetState.master = cb.checked;
    if (cb.checked) {
      cb.parentElement.classList.add("loading");
      try { await enable(); applyLayerOrder(); }
      finally { cb.parentElement.classList.remove("loading"); }
    } else {
      apply();
    }
  });
  document.querySelectorAll('input[name="street_pattern_metric"]').forEach((rb) => {
    rb.addEventListener("change", () => { if (rb.checked) { streetState.metric = rb.value; apply(); } });
  });
}


// ---- Street grid (OSM line network, classified grid vs. cul-de-sac) --------
// The actual streets within the City of Dallas, colored by the same bridge/cycle
// test as dendricity: teal = grid / looped (connected), red = cul-de-sac /
// dead-end. Single file (~9 MB), zoom-gated (minzoom 9).
// "Street grid" is a master checkbox over four independent sub-layers: Streets,
// Dead-ends, Alleys, Street names. The drive network (data/streets_dallas.geojson,
// property `kind`) is split into Streets (grid / connected) and Dead-ends
// (cul-de-sac / network-bridge) so each can be toggled separately. All four share
// one collapsed "Street grid" legend block via legendGroup.
LAYERS.streets_grid = {
  label: "Streets",
  minzoom: 9,
  legendGroup: "Street grid",
  legendOrder: 1,
  legendRow: () => `<div class="swatch-row"><span class="line-swatch" style="border-top-color:#1D4F66;border-top-width:2px"></span>Streets (grid / connected)</div>`,
  sourceId: "street-grid-src",
  sourceFile: "data/streets_dallas.geojson",
  layerIds: ["streets-grid-line"],
  addLayers: () => {
    map.addLayer({
      id: "streets-grid-line",
      type: "line",
      source: "street-grid-src",
      minzoom: 9,
      filter: ["!=", ["get", "kind"], "stub"],
      paint: {
        "line-color": "#1D4F66",
        "line-width": ["interpolate", ["linear"], ["zoom"], 9, 0.3, 11, 0.5, 14, 1.1, 17, 2.2],
        "line-opacity": ["interpolate", ["linear"], ["zoom"], 9, 0.5, 13, 0.85],
      },
    }, beneathTopLayers());
  },
  popup: () => "",
  clickLayer: null,
  legend: () => "",
};

LAYERS.streets_deadend = {
  label: "Dead-ends",
  minzoom: 9,
  legendGroup: "Street grid",
  legendOrder: 2,
  legendRow: () => `<div class="swatch-row"><span class="line-swatch" style="border-top-color:#C44E52;border-top-width:2px"></span>Dead-ends / cul-de-sac</div>`,
  sourceId: "street-grid-src",
  sourceFile: "data/streets_dallas.geojson",
  layerIds: ["streets-stub-line"],
  addLayers: () => {
    map.addLayer({
      id: "streets-stub-line",
      type: "line",
      source: "street-grid-src",
      minzoom: 9,
      filter: ["==", ["get", "kind"], "stub"],
      paint: {
        "line-color": "#C44E52",
        "line-width": ["interpolate", ["linear"], ["zoom"], 9, 0.4, 11, 0.7, 14, 1.4, 17, 2.6],
        "line-opacity": ["interpolate", ["linear"], ["zoom"], 9, 0.6, 13, 0.9],
      },
    }, beneathTopLayers());
  },
  popup: () => "",
  clickLayer: null,
  legend: () => "",
};

LAYERS.buildings = {
  label: "Building footprints",
  minzoom: 13,
  sourceId: "buildings-src",
  sourceFile: null,
  customLoad: async () => {
    if (!map.getSource("buildings-src")) {
      map.addSource("buildings-src", { type: "vector", url: "pmtiles://data/buildings.pmtiles" });
    }
  },
  layerIds: ["buildings-3d"],
  addLayers: () => {
    const h = ["coalesce", ["get", "height_m"], 6];
    map.addLayer({
      id: "buildings-3d",
      type: "fill-extrusion",
      source: "buildings-src",
      "source-layer": "buildings",
      minzoom: 13,   // 3D extrusion of ~350k buildings — render once zoomed in; tilt to see height
      paint: {
        "fill-extrusion-height": h,
        "fill-extrusion-base": 0,
        "fill-extrusion-opacity": 0.92,
        "fill-extrusion-vertical-gradient": true,
        // colored by footprint source: light gray = Microsoft ML, dark gray = OSM
        "fill-extrusion-color": ["match", ["get", "src"],
          "osm", "#6F7884",
          /* default (ms) */ "#DAD4C8"],
      },
    }, beneathTopLayers());
  },
  popup: () => "",
  clickLayer: null,
  legend: () => `
    <div class="legend-block">
      <h3>Building footprints</h3>
      <div class="swatch-row"><span class="swatch" style="background:#DAD4C8"></span>Microsoft ML building footprints</div>
      <div class="swatch-row"><span class="swatch" style="background:#6F7884"></span>OSM building footprints</div>
      <div class="muted" style="margin-top:4px;line-height:1.4">Extruded by height. Tilt the map (right-drag) and zoom in to view.</div>
    </div>`,
};

LAYERS.alleys = {
  label: "Alleys",
  minzoom: 9,
  legendGroup: "Street grid",
  legendOrder: 3,
  legendRow: () => `<div class="swatch-row"><span class="line-swatch" style="border-top-color:#E8862E;border-top-width:2px"></span>Alleys</div>`,
  sourceId: "alleys-src",
  sourceFile: "data/alleys_dallas.geojson",
  layerIds: ["alley-line"],
  addLayers: () => {
    map.addLayer({
      id: "alley-line",
      type: "line",
      source: "alleys-src",
      minzoom: 9,
      paint: {
        "line-color": "#E8862E",
        "line-width": ["interpolate", ["linear"], ["zoom"], 9, 0.6, 11, 1.0, 14, 2.0, 17, 4.0],
        "line-opacity": ["interpolate", ["linear"], ["zoom"], 9, 0.55, 13, 0.9],
      },
    }, beneathTopLayers());
  },
  popup: () => "",
  clickLayer: null,
  legend: () => "",
};

// "Street grid" master checkbox (#street-grid-master) governs four independent
// sub-layers: Streets, Dead-ends, Alleys, Street names. Checking the master reveals
// the sub-row and turns on the two street layers by default; unchecking turns the
// whole group off. Toggling any sub keeps the master + row in sync.
(function initStreetGroup() {
  const master = document.getElementById("street-grid-master");
  const row = document.getElementById("street-subrow");
  if (!master || !row) return;
  const subs = ["streets_grid", "streets_deadend", "alleys", "street_labels"]
    .map((k) => document.querySelector(`input[data-layer="${k}"]`));
  const defaults = new Set(["streets_grid", "streets_deadend"]);
  const anyOn = () => subs.some((cb) => cb && cb.checked);
  const showRow = () => { row.style.display = (master.checked || anyOn()) ? "flex" : "none"; };
  const fire = (cb, on) => {
    if (!cb || cb.checked === on) return;
    cb.checked = on;
    cb.dispatchEvent(new Event("change", { bubbles: true }));
  };

  master.addEventListener("change", () => {
    if (master.checked) {
      if (!anyOn()) subs.forEach((cb) => { if (cb && defaults.has(cb.dataset.layer)) fire(cb, true); });
    } else {
      subs.forEach((cb) => fire(cb, false));
    }
    showRow();
  });
  subs.forEach((cb) => {
    if (!cb) return;
    cb.addEventListener("change", () => { master.checked = anyOn(); showRow(); });
  });
  showRow();
})();

LAYERS.parking = {
  label: "Surface parking",
  minzoom: 9,
  sourceId: "parking-src",
  sourceFile: "data/parking_dallas.geojson",
  layerIds: ["parking-fill", "parking-outline"],
  addLayers: () => {
    map.addLayer({
      id: "parking-fill",
      type: "fill",
      source: "parking-src",
      minzoom: 9,
      paint: { "fill-color": "#8E6FB0", "fill-opacity": 0.55 },
    }, beneathTopLayers());
    map.addLayer({
      id: "parking-outline",
      type: "line",
      source: "parking-src",
      minzoom: 12,
      paint: { "line-color": "#5E4B8B", "line-width": 0.5, "line-opacity": 0.7 },
    }, beneathTopLayers());
  },
  popup: (props) => `
    <div class="popup-title">Surface parking lot</div>
    <div class="popup-row"><span class="label">Area</span><span class="value">${props.area_acres ?? "?"} acres</span></div>
    <div class="popup-row"><span class="label">Source</span><span class="value">OSM amenity=parking</span></div>`,
  clickLayer: "parking-fill",
  legend: () => `
    <div class="legend-block">
      <h3>Surface parking</h3>
      <div class="swatch-row"><span class="swatch" style="background:#8E6FB0"></span>Surface parking lot</div>
    </div>`,
};

// Optional street-name labels — a sub-checkbox under "Street grid". Shares the
// street-grid source (label segments are the same OSM line features, now carrying
// `name`), so it works whether or not the street lines themselves are shown.
LAYERS.street_labels = {
  label: "Street names",
  minzoom: 14,
  sourceId: "street-grid-src",
  sourceFile: null,
  layerIds: ["street-labels-symbol"],
  customLoad: async () => {
    if (!map.getSource("street-grid-src")) {
      const data = await (await fetch("data/streets_dallas.geojson")).json();
      map.addSource("street-grid-src", { type: "geojson", data });
      sourcesAdded.add("street-grid-src");
    }
  },
  addLayers: () => {
    map.addLayer({
      id: "street-labels-symbol",
      type: "symbol",
      source: "street-grid-src",
      minzoom: 14,
      layout: {
        "symbol-placement": "line",
        "text-field": ["coalesce", ["get", "name"], ""],
        "text-font": ["Noto Sans Regular"],
        "text-size": 11,
        "symbol-spacing": 300,
        "text-max-angle": 30,
      },
      paint: {
        "text-color": "#3A3733",
        "text-halo-color": "#FFFFFF",
        "text-halo-width": 1.4,
      },
    }, beneathTopLayers());
  },
  popup: () => "",
  clickLayer: null,
  legend: () => "",
};


// ============================================================================
// New layers (2026): Subsidized housing, Floodplain, Transit + place search
// ============================================================================

// ---- Subsidized (LIHTC) housing (points) -----------------------------------
LAYERS.subsidized = {
  label: "Subsidized (LIHTC) housing",
  sourceId: "subsidized-src",
  sourceFile: "data/subsidized_housing.geojson",
  layerIds: ["subsidized"],
  addLayers: () => {
    map.addLayer({
      id: "subsidized", type: "circle", source: "subsidized-src",
      paint: {
        "circle-radius": ["interpolate", ["linear"], ["zoom"],
          10, ["*", 0.45, ["sqrt", ["max", ["coalesce", ["get", "total_units"], 1], 1]]],
          15, ["*", 1.1, ["sqrt", ["max", ["coalesce", ["get", "total_units"], 1], 1]]]],
        "circle-color": "#2E8B6B", "circle-opacity": 0.82,
        "circle-stroke-color": "#FFFFFF", "circle-stroke-width": 1,
      },
    }, beneathTopLayers());
  },
  popup: (p) => `
    <div class="popup-title">${p.name || "LIHTC property"}</div>
    ${p.address ? `<div class="popup-row"><span class="label">Address</span><span class="value">${p.address}</span></div>` : ""}
    <div class="popup-row"><span class="label">Total units</span><span class="value">${p.total_units ?? "?"}</span></div>
    <div class="popup-row"><span class="label">Income-restricted</span><span class="value">${p.lihtc_units ?? "?"}</span></div>
    ${p.year ? `<div class="popup-row"><span class="label">Awarded</span><span class="value">${p.year}</span></div>` : ""}
    ${p.pop_served ? `<div class="popup-row"><span class="label">Serves</span><span class="value">${p.pop_served}</span></div>` : ""}`,
  clickLayer: "subsidized",
  legend: () => `<div class="legend-block"><h3>Subsidized (LIHTC) housing</h3>
    <div class="swatch-row"><span class="swatch" style="background:#2E8B6B;border-radius:50%"></span>LIHTC property (sized by units)</div>
    <div class="muted" style="margin-top:3px">TDHCA inventory (May 2026)</div></div>`,
};

// ---- Floodplain (FEMA NFHL) — 100-yr / 500-yr / both -----------------------
const floodState = { master: false, mode: "both", added: false };
function floodHatchImage(color, lw, dir) {   // seamless diagonal hatch tile; dir "fwd" (/), "back" (\), else cross
  const s = 8, cv = document.createElement("canvas");
  cv.width = cv.height = s;
  const ctx = cv.getContext("2d");
  ctx.strokeStyle = color; ctx.lineWidth = lw; ctx.lineCap = "square";
  ctx.beginPath();
  if (dir !== "back") { ctx.moveTo(-1, s + 1); ctx.lineTo(s + 1, -1); }   // "/"
  if (dir !== "fwd") { ctx.moveTo(-1, -1); ctx.lineTo(s + 1, s + 1); }    // "\"
  for (let i = 0; i < 3; i++) ctx.stroke();   // overstroke so the antialiased thin lines read ~opaque, not see-through
  return ctx.getImageData(0, 0, s, s);
}
function floodApply() {
  const on100 = floodState.master && floodState.mode !== "500";
  const on500 = floodState.master && floodState.mode !== "100";
  [["flood-500-fill", on500], ["flood-500", on500], ["flood-100-fill", on100], ["flood-100", on100]]
    .forEach(([id, on]) => { if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", on ? "visible" : "none"); });
  LAYERS.floodplain.enabled = floodState.master;
  refreshLegend();
}
async function floodEnable() {
  if (!map.getSource("flood-src")) {
    const r = await fetch("data/floodplain.geojson");
    map.addSource("flood-src", { type: "geojson", data: await r.json() });
  }
  if (!floodState.added) {
    if (!map.hasImage("flood-hatch-500")) map.addImage("flood-hatch-500", floodHatchImage("#000000", 0.8, "back"));
    if (!map.hasImage("flood-hatch-100")) map.addImage("flood-hatch-100", floodHatchImage("#E0E0E0", 1.0, "fwd"));
    // 500-yr: light–medium blue fill with the darker-gray cross-hatch on top
    map.addLayer({ id: "flood-500-fill", type: "fill", source: "flood-src",
      filter: ["==", ["get", "category"], "500yr"],
      paint: { "fill-color": "#7BAAD6", "fill-opacity": 0.45 } }, beneathTopLayers());
    map.addLayer({ id: "flood-500", type: "fill", source: "flood-src",
      filter: ["==", ["get", "category"], "500yr"],
      paint: { "fill-pattern": "flood-hatch-500" } }, beneathTopLayers());
    // 100-yr: dark blue fill with the gray cross-hatch on top
    map.addLayer({ id: "flood-100-fill", type: "fill", source: "flood-src",
      filter: ["==", ["get", "category"], "100yr"],
      paint: { "fill-color": "#164A87", "fill-opacity": 0.5 } }, beneathTopLayers());
    map.addLayer({ id: "flood-100", type: "fill", source: "flood-src",
      filter: ["==", ["get", "category"], "100yr"],
      paint: { "fill-pattern": "flood-hatch-100" } }, beneathTopLayers());
    floodState.added = true;
    LAYERS.floodplain.layerIds.forEach((id) => layersAdded.add(id));
  }
  floodApply();
}
function initFloodplain() {
  const cb = document.querySelector('input[data-layer-group="floodplain"]');
  if (!cb) return;
  cb.addEventListener("change", async () => {
    floodState.master = cb.checked;
    if (cb.checked) {
      cb.parentElement.classList.add("loading");
      try { await floodEnable(); applyLayerOrder(); } finally { cb.parentElement.classList.remove("loading"); }
    } else { floodApply(); }
  });
  document.querySelectorAll('input[name="floodplain_mode"]').forEach((rb) => {
    rb.addEventListener("change", () => { if (rb.checked) { floodState.mode = rb.value; floodApply(); } });
  });
}
LAYERS.floodplain = {
  label: "Floodplain (FEMA)", enabled: false, layerIds: ["flood-500-fill", "flood-500", "flood-100-fill", "flood-100"],
  legend: () => {
    const rows = [];
    if (floodState.mode !== "500") rows.push(`<div class="swatch-row"><span class="swatch" style="background:repeating-linear-gradient(135deg,#E0E0E0 0 1px,transparent 1px 5px),#164A87"></span>1% annual (100-yr)</div>`);
    if (floodState.mode !== "100") rows.push(`<div class="swatch-row"><span class="swatch" style="background:repeating-linear-gradient(45deg,#000000 0 0.8px,transparent 0.8px 5px),#7BAAD6"></span>0.2% annual (500-yr)</div>`);
    return `<div class="legend-block"><h3>Floodplain</h3>${rows.join("")}<div class="muted" style="margin-top:3px">FEMA NFHL</div></div>`;
  },
};

// ---- Transit network (DART) — All routes / Frequent only -------------------
const transitState = { master: false, mode: "frequent", added: false };
const RAIL_LIGHT = "#A56FCE", RAIL_DARK = "#5E2A87";
const BUS_FREQ = "#1E7B4A", BUS_MED = "#2D5AA8";
function railTieImage(color) {   // vertical bar; along a line symbol it renders as a perpendicular cross-tie
  const w = 7, h = 18, cv = document.createElement("canvas");
  cv.width = w; cv.height = h;
  const ctx = cv.getContext("2d");
  ctx.fillStyle = color;
  const bw = 2.6;
  ctx.fillRect((w - bw) / 2, 0, bw, h);
  return ctx.getImageData(0, 0, w, h);
}
function transitFilter(kind) {
  const base = ["==", ["get", "kind"], kind];
  return transitState.mode === "frequent" ? ["all", base, ["==", ["get", "frequent"], true]] : base;
}
function transitApply() {
  const vis = transitState.master ? "visible" : "none";
  ["transit-bus", "transit-rail-base", "transit-rail-ties"].forEach((id) => {
    if (map.getLayer(id)) {
      map.setLayoutProperty(id, "visibility", vis);
      map.setFilter(id, transitFilter(id === "transit-bus" ? "bus" : "rail"));
    }
  });
  LAYERS.transit.enabled = transitState.master;
  refreshLegend();
}
function transitPopup(p) {
  return `<div class="popup-title">${p.route ? "Route " + p.route : "Route"}${p.name ? " — " + p.name : ""}</div>
    <div class="popup-row"><span class="label">Type</span><span class="value">${p.kind === "rail" ? "Rail" : "Bus"}</span></div>
    <div class="popup-row"><span class="label">Frequent</span><span class="value">${p.frequent ? "Yes (&le;20 min peak)" : "No"}</span></div>
    ${p.hw_am ? `<div class="popup-row"><span class="label">AM headway</span><span class="value">~${p.hw_am} min</span></div>` : ""}
    ${p.hw_pm ? `<div class="popup-row"><span class="label">PM headway</span><span class="value">~${p.hw_pm} min</span></div>` : ""}`;
}
async function transitEnable() {
  if (!map.getSource("transit-src")) {
    const r = await fetch("data/transit_routes.geojson");
    map.addSource("transit-src", { type: "geojson", data: await r.json() });
  }
  if (!transitState.added) {
    const railColor = ["case", ["get", "frequent"], RAIL_DARK, RAIL_LIGHT];   // frequent = dark purple
    if (!map.hasImage("rail-tie-freq")) map.addImage("rail-tie-freq", railTieImage(RAIL_DARK));
    if (!map.hasImage("rail-tie-infq")) map.addImage("rail-tie-infq", railTieImage(RAIL_LIGHT));
    // Bus: 2 tiers by worst-peak headway — frequent green (25% thicker) vs >20 min dark blue
    map.addLayer({ id: "transit-bus", type: "line", source: "transit-src",
      filter: transitFilter("bus"), layout: { "line-cap": "round", "line-join": "round" },
      paint: {
        "line-color": ["step", ["get", "hw"], BUS_FREQ, 21, BUS_MED],
        "line-width": ["interpolate", ["linear"], ["zoom"],
          9, ["step", ["get", "hw"], 1.25, 21, 0.8],
          15, ["step", ["get", "hw"], 3.25, 21, 2.1]],
        "line-opacity": 0.9,
      } }, beneathTopLayers());
    // Rail: single purple line (dark if frequent) with perpendicular cross-ties as a SYMBOL layer —
    // symbol-spacing places ties at even pixel intervals at any zoom, unlike a dasharray (which
    // bunches near the line's vertices when zoomed out).
    map.addLayer({ id: "transit-rail-base", type: "line", source: "transit-src",
      filter: transitFilter("rail"), layout: { "line-cap": "round", "line-join": "round" },
      paint: { "line-color": railColor,
        "line-width": ["interpolate", ["linear"], ["zoom"], 9, 3, 15, 6.5], "line-opacity": 0.95 } }, beneathTopLayers());
    map.addLayer({ id: "transit-rail-ties", type: "symbol", source: "transit-src",
      filter: transitFilter("rail"),
      layout: {
        "symbol-placement": "line",
        "symbol-spacing": 10,
        "icon-image": ["case", ["get", "frequent"], "rail-tie-freq", "rail-tie-infq"],
        "icon-size": ["interpolate", ["linear"], ["zoom"], 9, 0.5, 15, 1.0],
        "icon-allow-overlap": true,
        "icon-ignore-placement": true,
        "icon-rotation-alignment": "map",
        "icon-pitch-alignment": "map",
        "icon-keep-upright": false,
      },
      paint: { "icon-opacity": 0.95 } }, beneathTopLayers());
    ["transit-bus", "transit-rail-base"].forEach((id) => {
      map.on("click", id, (e) => {
        const f = e.features?.[0]; if (!f) return;
        new maplibregl.Popup({ closeButton: true }).setLngLat(e.lngLat).setHTML(transitPopup(f.properties)).addTo(map);
      });
      map.on("mouseenter", id, () => map.getCanvas().style.cursor = "pointer");
      map.on("mouseleave", id, () => map.getCanvas().style.cursor = "");
    });
    transitState.added = true;
    LAYERS.transit.layerIds.forEach((id) => layersAdded.add(id));
  }
  transitApply();
}
function initTransit() {
  const cb = document.querySelector('input[data-layer-group="transit"]');
  if (!cb) return;
  cb.addEventListener("change", async () => {
    transitState.master = cb.checked;
    if (cb.checked) {
      cb.parentElement.classList.add("loading");
      try { await transitEnable(); applyLayerOrder(); } finally { cb.parentElement.classList.remove("loading"); }
    } else { transitApply(); }
  });
  document.querySelectorAll('input[name="transit_mode"]').forEach((rb) => {
    rb.addEventListener("change", () => { if (rb.checked) { transitState.mode = rb.value; transitApply(); } });
  });
}
LAYERS.transit = {
  label: "Transit network", enabled: false,
  layerIds: ["transit-bus", "transit-rail-base", "transit-rail-ties"],
  legend: () => {
    const all = transitState.mode === "all";
    const rows = [
      `<div class="swatch-row"><span class="line-swatch" style="border-top-color:${RAIL_DARK};border-top-width:4px"></span>Frequent rail</div>`,
      all ? `<div class="swatch-row"><span class="line-swatch" style="border-top-color:${RAIL_LIGHT};border-top-width:4px"></span>Other rail</div>` : "",
      `<div class="swatch-row"><span class="line-swatch" style="border-top-color:${BUS_FREQ};border-top-width:3.5px"></span>Frequent bus (&le;20 min)</div>`,
      all ? `<div class="swatch-row"><span class="line-swatch" style="border-top-color:${BUS_MED};border-top-width:2px"></span>Bus (&gt;20 min)</div>` : "",
    ].filter(Boolean).join("");
    return `<div class="legend-block"><h3>Transit network (DART)</h3>${rows}<div class="muted" style="margin-top:3px">DART GTFS · frequent = &le;20 min in 7-9am &amp; 4-6pm</div></div>`;
  },
};

// ---- Place search (Photon geocoder, free/no-key, biased to Dallas) ---------
function initGeocoder() {
  const input = document.getElementById("geocoder-input");
  const results = document.getElementById("geocoder-results");
  if (!input || !results) return;
  let timer = null, items = [], active = -1, marker = null;
  const hide = () => { results.style.display = "none"; results.innerHTML = ""; items = []; active = -1; };
  const label = (p) => [p.name, p.housenumber && p.street ? `${p.housenumber} ${p.street}` : p.street,
    p.city || p.district || p.county, p.state].filter(Boolean).join(", ");
  async function search(q) {
    if (q.trim().length < 3) { hide(); return; }
    try {
      const url = `https://photon.komoot.io/api?q=${encodeURIComponent(q)}&lat=32.78&lon=-96.80&limit=6&lang=en`;
      const d = await (await fetch(url)).json();
      items = (d.features || []).filter((f) => f.geometry && f.geometry.type === "Point");
      if (!items.length) { hide(); return; }
      results.innerHTML = items.map((f, i) => `<div class="geocoder-item" data-i="${i}">${label(f.properties || {}) || "?"}</div>`).join("");
      results.style.display = "block"; active = -1;
    } catch (e) { hide(); }
  }
  function pick(i) {
    const f = items[i]; if (!f) return;
    const [lon, lat] = f.geometry.coordinates;
    map.flyTo({ center: [lon, lat], zoom: 15 });
    if (marker) marker.setLngLat([lon, lat]);
    else marker = new maplibregl.Marker({ color: "#d95660" }).setLngLat([lon, lat]).addTo(map);
    input.value = results.querySelector(`[data-i="${i}"]`)?.textContent || input.value;
    hide();
  }
  input.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(() => search(input.value), 300); });
  results.addEventListener("mousedown", (e) => { const el = e.target.closest(".geocoder-item"); if (el) { e.preventDefault(); pick(+el.dataset.i); } });
  input.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown") active = Math.min(active + 1, items.length - 1);
    else if (e.key === "ArrowUp") active = Math.max(active - 1, 0);
    else if (e.key === "Enter") { pick(active >= 0 ? active : 0); return; }
    else if (e.key === "Escape") { hide(); return; }
    else return;
    e.preventDefault();
    results.querySelectorAll(".geocoder-item").forEach((el, i) => el.classList.toggle("active", i === active));
  });
  document.addEventListener("click", (e) => { if (!input.parentElement.contains(e.target)) hide(); });
}

// ---- Demographics (grouped, ACS 5-yr; metric radio) ------------------------
const DEMO_PAL = ["#F1EEF6", "#BDC9E1", "#74A9CF", "#2B8CBE", "#045A8D"];
const DEMO_NULL = "#D9D4CC";
const DEMO_METRICS = {
  income:          { label: "Median household income", prop: "income", edges: [40000, 60000, 85000, 120000], money: true },
  renter_pct:      { label: "Renter share", prop: "renter_pct", edges: [15, 30, 45, 60] },
  rent_burden_pct: { label: "Rent burden (≥30% of income)", prop: "rent_burden_pct", edges: [35, 45, 55, 65] },
  poverty_pct:     { label: "Poverty rate", prop: "poverty_pct", edges: [8, 15, 25, 35] },
  hisp_pct:        { label: "% Hispanic", prop: "hisp_pct", edges: [10, 25, 45, 70] },
  white_pct:       { label: "% Non-Hispanic White", prop: "white_pct", edges: [10, 25, 45, 70] },
  black_pct:       { label: "% Non-Hispanic Black", prop: "black_pct", edges: [10, 25, 45, 70] },
  asian_pct:       { label: "% Non-Hispanic Asian", prop: "asian_pct", edges: [5, 10, 20, 35] },
};
const demoState = { master: false, metric: "income", added: false };
function demoColor() {
  const m = DEMO_METRICS[demoState.metric];
  const step = ["step", ["get", m.prop], DEMO_PAL[0]];
  m.edges.forEach((ed, i) => step.push(ed, DEMO_PAL[i + 1]));
  return ["case", ["==", ["get", m.prop], null], DEMO_NULL, step];
}
function demoFmtVal(m, v) {
  if (v == null) return "—";
  return m.money ? "$" + Number(v).toLocaleString() : v + "%";
}
function demoPopup(p) {
  const rows = Object.values(DEMO_METRICS).map((m) =>
    `<div class="popup-row"><span class="label">${m.label}</span><span class="value">${demoFmtVal(m, p[m.prop])}</span></div>`).join("");
  return `<div class="popup-title">Census tract ${p.geoid || ""}</div>${rows}`;
}
function demoLegend() {
  const m = DEMO_METRICS[demoState.metric];
  const f = (v) => m.money ? "$" + (v / 1000) + "k" : v + "%";
  const e = m.edges;
  const rows = [`<div class="swatch-row"><span class="swatch" style="background:${DEMO_PAL[0]}"></span>&lt; ${f(e[0])}</div>`];
  for (let i = 0; i < e.length - 1; i++) rows.push(`<div class="swatch-row"><span class="swatch" style="background:${DEMO_PAL[i + 1]}"></span>${f(e[i])}–${f(e[i + 1])}</div>`);
  rows.push(`<div class="swatch-row"><span class="swatch" style="background:${DEMO_PAL[e.length]}"></span>&ge; ${f(e[e.length - 1])}</div>`);
  rows.push(`<div class="swatch-row"><span class="swatch" style="background:${DEMO_NULL}"></span>No data</div>`);
  return `<div class="legend-block"><h3>${m.label}</h3>${rows.join("")}<div class="muted" style="margin-top:3px">ACS 2020–24 · by tract</div></div>`;
}
function demoApply() {
  const vis = demoState.master ? "visible" : "none";
  ["demo-fill", "demo-outline"].forEach((id) => { if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", vis); });
  if (demoState.added && demoState.master) map.setPaintProperty("demo-fill", "fill-color", demoColor());
  LAYERS.demographics.enabled = demoState.master;
  refreshLegend();
}
async function demoEnable() {
  if (!map.getSource("demo-src")) {
    const r = await fetch("data/acs_demographics_tracts.geojson");
    map.addSource("demo-src", { type: "geojson", data: await r.json() });
  }
  if (!demoState.added) {
    map.addLayer({ id: "demo-fill", type: "fill", source: "demo-src",
      paint: { "fill-color": demoColor(), "fill-opacity": 0.72 } }, beneathTopLayers());
    map.addLayer({ id: "demo-outline", type: "line", source: "demo-src",
      paint: { "line-color": "#FFFFFF", "line-width": 0.3, "line-opacity": 0.4 } }, beneathTopLayers());
    map.on("click", "demo-fill", (e) => {
      const f = e.features?.[0]; if (!f) return;
      new maplibregl.Popup({ closeButton: true }).setLngLat(e.lngLat).setHTML(demoPopup(f.properties)).addTo(map);
    });
    map.on("mouseenter", "demo-fill", () => map.getCanvas().style.cursor = "pointer");
    map.on("mouseleave", "demo-fill", () => map.getCanvas().style.cursor = "");
    demoState.added = true;
    LAYERS.demographics.layerIds.forEach((id) => layersAdded.add(id));
  }
  demoApply();
}
function initDemographics() {
  const cb = document.querySelector('input[data-layer-group="demographics"]');
  if (!cb) return;
  cb.addEventListener("change", async () => {
    demoState.master = cb.checked;
    if (cb.checked) {
      cb.parentElement.classList.add("loading");
      try { await demoEnable(); applyLayerOrder(); } finally { cb.parentElement.classList.remove("loading"); }
    } else { demoApply(); }
  });
  document.querySelectorAll('input[name="demographics_metric"]').forEach((rb) => {
    rb.addEventListener("change", () => { if (rb.checked) { demoState.metric = rb.value; demoApply(); } });
  });
}
LAYERS.demographics = {
  label: "Demographics", enabled: false, layerIds: ["demo-fill", "demo-outline"],
  legend: () => demoLegend(),
};

// ---- Info tooltips on layer controls (native title, never clipped) ---------
const TOOLTIPS = {
  value3d: "Appraised value ÷ acreage, as 3-D towers. Height caps at $100M/acre by default (toggle to uncap); parcels under $100k/acre render flat/transparent. About 1 m per $25k/acre.",
  value2d: "Flat-map version of value per acre — total, improvement, or land value ÷ acres.",
  imp_land_ratio: "Structure (improvement) value ÷ land value. Low ratios flag under-built or teardown-prone land. Institutional and <$100k/acre parcels excluded.",
  far_footprint: "Estimated floor-area ratio: CAD building floor area spread across building footprints ÷ lot area.",
  decade_built: "Decade the main structure was built (CAD year built).",
  land_use: "What is BUILT on each parcel (CAD land use). Some apartments are CAD-coded 'Commercial'. Differs from Base zoning, which is what's ALLOWED.",
  zoning: "What each parcel ALLOWS (base zoning district). Planned Development (PD) is a catch-all where much of Dallas's density is actually entitled — it is not a base district.",
  demographics: "Census ACS 2020–24 5-year estimates by tract. Small-sample tract values carry wide margins of error — treat as approximate.",
  subsidized: "LIHTC (tax-credit) properties from the TDHCA inventory. Not public housing, project-based Section 8, or vouchers. Older awards may be leaving affordability.",
  transit: "DART routes. 'Frequent' = 20-minute-or-better headway in BOTH the 7–9am and 4–6pm weekday peaks. Rail drawn with cross-ties; bus shaded by headway.",
  floodplain: "FEMA National Flood Hazard Layer. 100-yr = 1% annual-chance (Special Flood Hazard Area); 500-yr = 0.2% annual-chance.",
  street_pattern: "OSM street-network connectivity per tract: dendricity (tree-likeness), dead-end share, and intersection density — grid vs. cul-de-sac suburbia.",
  jobs_density: "Workplace jobs per acre (Census LODES 2022). Wage tiers are MODEL-BASED (BLS sector-weighted), not measured earnings.",
  oi_earnings: "Opportunity Atlas: predicted adult household income for children raised in low-income families here. A place-based MOBILITY measure, not current residents' income.",
  rent_change: "Median gross-rent change in REAL (CPI-adjusted 2024$) dollars. Gray tracts = margin of error too high to trust; Zillow cross-hatch = series begins after the start year.",
  value_change: "Median home-value change in REAL (CPI-adjusted 2024$) dollars. Same caveats as rent. ACS home value is top-coded, so a few high-end tracts can overstate gains.",
  pop_change: "Population change 2010→2020 via a BLOCK-level crosswalk (more accurate than block-group). Toggle block-group vs. tract.",
  hu_change: "Housing-unit change 2010→2020, same block-level crosswalk as population.",
  permits: "New-construction building permits. MF counts include apartments in CAD 'Commercial' buildings but exclude hotels/retail. Slider sets the permit-year range.",
};
function injectTooltips() {
  document.querySelectorAll("[data-layer],[data-layer-group]").forEach((cb) => {
    const key = cb.dataset.layer || cb.dataset.layerGroup;
    const tip = TOOLTIPS[key];
    if (!tip) return;
    const span = cb.closest("label")?.querySelector("span");
    if (!span || span.querySelector(".info-tip")) return;
    const b = document.createElement("span");
    b.className = "info-tip"; b.textContent = "?";
    b.title = tip; b.setAttribute("aria-label", tip);
    span.appendChild(b);
  });
}

// ---- Data-vintage line appended to each legend block ------------------------
const VINTAGE = {
  zoning: "City of Dallas zoning",
  parcels: "DCAD 2025 + Collin / Denton CAD",
  land_use: "DCAD 2025 / Collin / Denton CAD",
  far_footprint: "DCAD 2025 + MS / OSM footprints",
  decade_built: "DCAD 2025",
  imp_land_ratio: "DCAD 2025",
  jobs_density: "Census LODES 2022",
  oi_earnings: "Opportunity Insights (Chetty et al.)",
  block_groups: "Census 2010 & 2020",
  tracts: "Census 2010 & 2020",
  bg_hu: "Census 2010 & 2020",
  tract_hu: "Census 2010 & 2020",
  rent_change: "ACS 2012–24 & Zillow · real 2024$",
  value_change: "ACS 2012–24 & Zillow · real 2024$",
  street_pattern: "OpenStreetMap",
  permits: "City of Dallas · 2000–2024",
  buildings: "MS ML footprints + OSM",
  parking: "OpenStreetMap",
};
const VINTAGE_GROUP = {
  "Jurisdiction boundaries": "Census TIGER / City of Dallas",
  "Street grid": "OpenStreetMap",
};
function withVintage(html, v) {
  if (!v || !html) return html;
  const i = html.lastIndexOf("</div>");
  if (i < 0) return html;
  return html.slice(0, i) + `<div class="muted legend-vintage">${v}</div>` + html.slice(i);
}
