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
const LOW_DENS_COLOR = "#B8B0A0";
const LOW_DENS_LABEL = "Low density (<1,000 / sq mi)";

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

// Value-per-acre bins (used for 3D fill-extrusion layers). Color thresholds
// chosen to match the ordinal feel of the FAR palette. Extrusion height is
// linear: 1 metre per $100,000 of value per acre.
const VALUE_PER_ACRE_BINS = [
  { upper: 250_000,    label: "< $250k",       color: "#22ecf0" },
  { upper: 1_000_000,  label: "$250k – $1M",   color: "#14b1fd" },
  { upper: 2_000_000,  label: "$1M – $2M",     color: "#2c7fdb" },
  { upper: 5_000_000,  label: "$2M – $5M",     color: "#6539b3" },
  { upper: 10_000_000, label: "$5M – $10M",    color: "#a032b2" },
  { upper: 25_000_000, label: "$10M – $25M",   color: "#d124a9" },
  { upper: 50_000_000, label: "$25M – $50M",   color: "#ff7911" },
  { upper: Infinity,   label: "$50M+",         color: "#ffdd00" },
];
const NO_VALUE_COLOR = "#B8B0A0";
const VALUE_HEIGHT_MULTIPLIER = 0.00001;  // 1 m extrusion per $100k value/acre

function valuePerAcreColorExpr(propName) {
  // Step expression: ≤ 0 returns the "no data" gray; positive values step
  // through the binned color palette.
  const expr = [
    "step", ["coalesce", ["get", propName], 0],
    NO_VALUE_COLOR,            // value ≤ 0 → no data
    1, VALUE_PER_ACRE_BINS[0].color,  // 1–upper[0]
  ];
  for (let i = 0; i < VALUE_PER_ACRE_BINS.length - 1; i++) {
    expr.push(VALUE_PER_ACRE_BINS[i].upper, VALUE_PER_ACRE_BINS[i + 1].color);
  }
  return expr;
}

function valuePerAcreHeightExpr(propName) {
  return ["*", ["coalesce", ["get", propName], 0], VALUE_HEIGHT_MULTIPLIER];
}

function makeValuePerAcreLayer(layerKey, propName, label) {
  const fillLayerId = `${layerKey}-3d`;
  return {
    label,
    sourceId: "parcels-src",
    sourceFile: null,
    layerIds: [fillLayerId],
    customLoad: async () => {
      const data = await loadParcelsCombined();
      if (!map.getSource("parcels-src")) {
        map.addSource("parcels-src", { type: "geojson", data });
      }
    },
    addLayers: () => {
      map.addLayer({
        id: fillLayerId,
        type: "fill-extrusion",
        source: "parcels-src",
        minzoom: 11,
        paint: {
          "fill-extrusion-color": valuePerAcreColorExpr(propName),
          "fill-extrusion-height": valuePerAcreHeightExpr(propName),
          "fill-extrusion-base": 0,
          "fill-extrusion-opacity": 0.9,
        },
      }, beneathTopLayers());
    },
    popup: (props) => parcelPopup(props),
    clickLayer: fillLayerId,
    legend: () => {
      const rows = VALUE_PER_ACRE_BINS.map((b) =>
        `<div class="swatch-row"><span class="swatch" style="background:${b.color}"></span>${b.label}</div>`).join("");
      return `<div class="legend-block">
        <h3>${label}</h3>
        <div class="swatch-row"><span class="swatch" style="background:${NO_VALUE_COLOR}"></span>No data</div>
        ${rows}
        <div class="muted" style="margin-top:4px">Height ≈ 1 m per $100k/acre. Right-drag or shift-drag to tilt the map for 3D.</div>
      </div>`;
    },
  };
}


function popChangeFillColor(propertyName, scheme) {
  return [
    "case",
    ["==", ["get", "low_density"], true],
    LOW_DENS_COLOR,
    ["step", ["get", propertyName],
      scheme.palette[0],
      scheme.edges[0], scheme.palette[1],
      scheme.edges[1], scheme.palette[2],
      scheme.edges[2], scheme.palette[3],
      scheme.edges[3], scheme.palette[4],
      scheme.edges[4], scheme.palette[5],
      scheme.edges[5], scheme.palette[6],
    ],
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
  let total = 0;
  const features = [];
  for (const p of parts) {
    features.push(...p.features);
    total += p.features.length;
  }
  parcelsCombined = { type: "FeatureCollection", features };
  console.log(`Loaded ${total.toLocaleString()} parcels.`);
  return parcelsCombined;
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
    clickLayer: "council-fill",
    legend: () => `
      <div class="legend-block">
        <h3>Council Districts</h3>
        <div class="swatch-row"><span class="line-swatch"></span> District boundary</div>
      </div>
    `,
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
    legend: () => `
      <div class="legend-block">
        <h3>City of Dallas</h3>
        <div class="swatch-row">
          <span class="line-swatch" style="border-top-width:2px;border-top-color:#222222"></span>
          City boundary
        </div>
      </div>
    `,
  },

  zoning: {
    label: "Base zoning",
    sourceId: "zoning-src",
    sourceFile: "data/zoning.geojson",
    layerIds: ["zoning-fill", "zoning-outline"],
    addLayers: () => {
      const colorExpr = ["match", ["get", "category"]];
      Object.entries(ZONING_COLORS).forEach(([cat, color]) => {
        colorExpr.push(cat, color);
      });
      colorExpr.push("#C4BDB3");

      map.addLayer({
        id: "zoning-fill",
        type: "fill",
        source: "zoning-src",
        paint: { "fill-color": colorExpr, "fill-opacity": 0.65 },
      }, beneathTopLayers());
      map.addLayer({
        id: "zoning-outline",
        type: "line",
        source: "zoning-src",
        paint: { "line-color": "#FFFFFF", "line-width": 0.3, "line-opacity": 0.5 },
      }, beneathTopLayers());
    },
    popup: (props) => `
      <div class="popup-title">Zoning: ${props.zone_dist ?? ""}</div>
      <div class="popup-row"><span class="label">Category</span><span class="value">${props.category ?? ""}</span></div>
      ${props.common_name ? `<div class="popup-row"><span class="label">Name</span><span class="value">${props.common_name}</span></div>` : ""}
      ${props.pd_num ? `<div class="popup-row"><span class="label">PD #</span><span class="value">${props.pd_num}</span></div>` : ""}
      ${props.cd_num ? `<div class="popup-row"><span class="label">CD #</span><span class="value">${props.cd_num}</span></div>` : ""}
    `,
    clickLayer: "zoning-fill",
    legend: () => {
      const rows = Object.entries(ZONING_COLORS)
        .map(([cat, color]) =>
          `<div class="swatch-row"><span class="swatch" style="background:${color}"></span>${cat}</div>`).join("");
      return `<div class="legend-block"><h3>Base Zoning</h3>${rows}</div>`;
    },
  },

  parcels: {
    label: "Parcels (neutral)",
    sourceId: "parcels-src",
    sourceFile: null, // loaded separately via loadParcelsCombined()
    layerIds: ["parcels-fill", "parcels-outline"],
    customLoad: async () => {
      const data = await loadParcelsCombined();
      if (!map.getSource("parcels-src")) {
        map.addSource("parcels-src", { type: "geojson", data });
      }
    },
    addLayers: () => {
      // Invisible fill — preserved so clicks still register on parcels
      map.addLayer({
        id: "parcels-fill",
        type: "fill",
        source: "parcels-src",
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
    sourceId: "parcels-src",
    sourceFile: null,
    layerIds: ["land-use-fill", "land-use-vacant-pattern", "land-use-outline"],
    customLoad: async () => {
      const data = await loadParcelsCombined();
      if (!map.getSource("parcels-src")) {
        map.addSource("parcels-src", { type: "geojson", data });
      }
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

      // Base fill — every parcel colored by category (vacant uses the same
      // base color as its non-vacant counterpart).
      map.addLayer({
        id: "land-use-fill",
        type: "fill",
        source: "parcels-src",
        minzoom: 11,
        paint: {
          "fill-color": colorExpr,
          "fill-opacity": [
            "interpolate", ["linear"], ["zoom"],
            11, 0.6, 14, 0.85,
          ],
        },
      }, beneathTopLayers());

      // Diagonal-stripe pattern overlay applied ONLY to vacant categories.
      // The image has a transparent background, so the underlying base
      // color shows through — no outer border, just the diagonals.
      map.addLayer({
        id: "land-use-vacant-pattern",
        type: "fill",
        source: "parcels-src",
        minzoom: 11,
        filter: ["in", ["get", "land_use_cat"],
                 ["literal", VACANT_DATA_VALUES]],
        paint: {
          "fill-pattern": "diag-stripes",
          "fill-opacity": [
            "interpolate", ["linear"], ["zoom"],
            11, 0.85, 14, 1.0,
          ],
        },
      }, beneathTopLayers());

      map.addLayer({
        id: "land-use-outline",
        type: "line",
        source: "parcels-src",
        minzoom: 14,
        paint: { "line-color": "#FFFFFF", "line-width": 0.2, "line-opacity": 0.4 },
      }, beneathTopLayers());
    },
    popup: (props) => parcelPopup(props),
    clickLayer: "land-use-fill",
    legend: () => {
      const rows = LAND_USE_DEFS.map((d) => {
        if (d.vacant) {
          // Swatch: base color + diagonal-stripe overlay (matches the map pattern)
          return `<div class="swatch-row">
            <span class="swatch" style="background:
              repeating-linear-gradient(45deg, #1A1A1A 0 0.7px, transparent 0.7px 5px),
              ${d.color}"></span>${d.label}</div>`;
        }
        return `<div class="swatch-row"><span class="swatch" style="background:${d.color}"></span>${d.label}</div>`;
      }).join("");
      return `<div class="legend-block"><h3>Land Use</h3>${rows}</div>`;
    },
  },

  far: {
    label: "Building FAR",
    sourceId: "parcels-src",
    sourceFile: null,
    layerIds: ["far-fill", "far-outline"],
    customLoad: async () => {
      const data = await loadParcelsCombined();
      if (!map.getSource("parcels-src")) {
        map.addSource("parcels-src", { type: "geojson", data });
      }
    },
    addLayers: () => {
      const colorExpr = ["match", ["get", "far_cat"]];
      FAR_BINS.forEach((bin) => colorExpr.push(bin, FAR_COLORS[bin]));
      colorExpr.push("#888888");

      map.addLayer({
        id: "far-fill",
        type: "fill",
        source: "parcels-src",
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
        id: "far-outline",
        type: "line",
        source: "parcels-src",
        minzoom: 14,
        paint: { "line-color": "#FFFFFF", "line-width": 0.2, "line-opacity": 0.4 },
      }, beneathTopLayers());
    },
    popup: (props) => parcelPopup(props),
    clickLayer: "far-fill",
    legend: () => {
      const rows = FAR_BINS.map((bin) =>
        `<div class="swatch-row"><span class="swatch" style="background:${FAR_COLORS[bin]}"></span>FAR ${bin}</div>`).join("");
      return `<div class="legend-block"><h3>Building FAR</h3>${rows}</div>`;
    },
  },

  decade_built: {
    label: "Decade built",
    sourceId: "parcels-src",
    sourceFile: null,
    layerIds: ["decade-built-fill", "decade-built-outline"],
    customLoad: async () => {
      const data = await loadParcelsCombined();
      if (!map.getSource("parcels-src")) {
        map.addSource("parcels-src", { type: "geojson", data });
      }
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
        minzoom: 14,
        paint: { "line-color": "#FFFFFF", "line-width": 0.2, "line-opacity": 0.4 },
      }, beneathTopLayers());
    },
    popup: (props) => parcelPopup(props),
    clickLayer: "decade-built-fill",
    legend: () => {
      const rows = DECADE_BINS.map((d) =>
        `<div class="swatch-row"><span class="swatch" style="background:${d.color}"></span>${d.label}</div>`).join("");
      return `<div class="legend-block"><h3>Decade Built</h3>${rows}</div>`;
    },
  },

  // 3D value-per-acre layers (Urban3-style). Each renders parcels as
  // `fill-extrusion` polygons with height proportional to the chosen
  // value-per-acre property and color binned by value.
  value_per_acre: makeValuePerAcreLayer("value-per-acre", "value_per_acre", "Total value per acre"),
  impr_per_acre:  makeValuePerAcreLayer("impr-per-acre",  "impr_per_acre",  "Improvement value per acre"),
  land_per_acre:  makeValuePerAcreLayer("land-per-acre",  "land_per_acre",  "Taxable land value per acre"),

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
          "fill-color": popChangeFillColor("hu_change", POP_CHANGE_COLORS.bg),
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
    legend: () => buildChangeLegend("Housing Unit Change, BG", POP_CHANGE_COLORS.bg),
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
          "fill-color": popChangeFillColor("hu_change", POP_CHANGE_COLORS.tract),
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
    legend: () => buildChangeLegend("Housing Unit Change, Tract", POP_CHANGE_COLORS.tract),
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

function changeRow(label, change) {
  const cls = change > 0 ? "positive" : change < 0 ? "negative" : "";
  const sign = change > 0 ? "+" : "";
  return `<div class="popup-row popup-change ${cls}">
    <span class="label">${label}</span>
    <span class="value">${sign}${fmt(change)}</span>
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
    props.total_units ? `<div class="popup-row"><span class="label">Units</span><span class="value">${props.total_units}</span></div>` : "",
    props.year_built ? `<div class="popup-row"><span class="label">Year built</span><span class="value">${props.year_built}</span></div>` : "",
    totVal  ? `<div class="popup-row"><span class="label">Total appraised value (2025)</span><span class="value">${fmtMoney(totVal)}</span></div>` : "",
    imprVal ? `<div class="popup-row"><span class="label">Improvement value</span><span class="value">${fmtMoney(imprVal)}</span></div>` : "",
    landVal ? `<div class="popup-row"><span class="label">Land value</span><span class="value">${fmtMoney(landVal)}</span></div>` : "",
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
    ${changeRow("Change", props.pop_change)}

    <div class="popup-row" style="margin-top:6px;font-weight:600;color:#444;font-size:11px;text-transform:uppercase;letter-spacing:0.4px">Housing Units</div>
    <div class="popup-row"><span class="label">2010</span><span class="value">${fmt(props.hu_2010)}</span></div>
    <div class="popup-row"><span class="label">2020</span><span class="value">${fmt(props.hu_2020)}</span></div>
    ${changeRow("Change", props.hu_change)}

    ${props.low_density ? '<div class="popup-row" style="margin-top:6px;color:#888;font-size:11px">⚠ Low density — interpret with caution</div>' : ""}
  `;
}

function bgPopup(props) {
  return `<div class="popup-title">Block Group ${props.geoid}</div>${bgOrTractBody(props)}`;
}

function tractPopup(props) {
  return `<div class="popup-title">Tract ${props.geoid}</div>${bgOrTractBody(props)}`;
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
  content.innerHTML = enabled.map(([k, v]) => v.legend()).join("");
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
      map.on("click", layer.clickLayer, (e) => {
        const f = e.features?.[0];
        if (!f) return;
        new maplibregl.Popup({ closeButton: true })
          .setLngLat(e.lngLat)
          .setHTML(layer.popup(f.properties))
          .addTo(map);
      });
      map.on("mouseenter", layer.clickLayer, () => map.getCanvas().style.cursor = "pointer");
      map.on("mouseleave", layer.clickLayer, () => map.getCanvas().style.cursor = "");
    }
  }
  layer.layerIds.forEach((id) => map.setLayoutProperty(id, "visibility", "visible"));
  layer.enabled = true;
  refreshLegend();
  applyLayerOrder();   // place this layer in the user's preferred stack position
}

function disableLayer(key) {
  const layer = LAYERS[key];
  if (!layer || !layer.enabled) return;
  layer.layerIds.forEach((id) => {
    if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", "none");
  });
  layer.enabled = false;
  refreshLegend();
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
    const key = cb && cb.dataset.layer;
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
}


// ---- UI wiring -------------------------------------------------------------

map.on("load", async () => {
  // Basemap selector
  document.querySelectorAll('input[name="basemap"]').forEach((rb) => {
    rb.addEventListener("change", () => {
      if (rb.checked) setBasemap(rb.value);
    });
  });

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

  initReports();
  initPermits();

  // Legend collapse / expand
  const legendEl = document.getElementById("legend");
  const collapseBtn = document.getElementById("legend-collapse");
  if (legendEl && collapseBtn) {
    collapseBtn.addEventListener("click", () => {
      legendEl.classList.toggle("collapsed");
      collapseBtn.textContent = legendEl.classList.contains("collapsed") ? "+" : "−";
    });
  }
});


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
  const closeBtn = document.getElementById("close-report");
  const panel = document.getElementById("report-panel");
  const select = document.getElementById("report-select");
  if (!todBtn || !distBtn || !closeBtn || !panel || !select) return;

  todBtn.addEventListener("click", () => openReportPanel("tod"));
  distBtn.addEventListener("click", () => openReportPanel("district"));
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

  if (mode === "tod") {
    title.textContent = "TOD Opportunity Areas";
    label.textContent = "Station";
    clearActiveDistrict();   // hide district highlight if switching from district mode
  } else {
    title.textContent = "Council Districts";
    label.textContent = "District";
    clearActiveStation();    // hide TOD rings if switching from TOD mode
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
  return renderTodReport(idxStr);
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

    <h3>Decade built</h3>
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
      ["Total dwelling units",            fmtNum(d.permit_units_total)],
    ])}

    <h3>Built environment</h3>
    ${singlePctBlock("Base zoning",     d.zoning_pct,    ZONING_ORDER, ZONING_COLOR_FN)}
    ${singlePctBlock("Land use",        d.land_use_pct,  LU_ORDER,     LU_COLOR_FN)}
    ${singlePctBlock("Building floor-area ratio (FAR)", d.far_pct, FAR_ORDER, FAR_COLOR_FN)}
    ${singlePctBlock("Decade built",    d.decade_pct,    DECADE_ORDER, DECADE_COLOR_FN)}
  `;
}
