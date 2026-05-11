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

map.addControl(new maplibregl.NavigationControl({ visualizePitch: false }), "top-right");
map.addControl(new maplibregl.ScaleControl({ unit: "imperial" }), "bottom-left");


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
  const value = props.land_value || props.mkt_value;
  const luLabel = props.land_use_cat
    ? (LAND_USE_LABEL_BY_VALUE[props.land_use_cat] || props.land_use_cat)
    : null;

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
    value ? `<div class="popup-row"><span class="label">Value</span><span class="value">$${fmt(value)}</span></div>` : "",
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
  if (enabled.length === 0) {
    document.getElementById("legend-content").innerHTML =
      '<p class="muted">Toggle a layer to see its legend.</p>';
    return;
  }
  document.getElementById("legend-content").innerHTML =
    enabled.map(([k, v]) => v.legend()).join("");
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
});


// ---- TOD Opportunity Areas report panel ------------------------------------
//
// Loads the precomputed station_reports.json on demand. Renders a side-panel
// with bar-chart-style breakdowns for 1/4-mile and 1/2-mile buffers around the
// selected station.

let stationReports = null;
let stationCoords = null;  // Map<stop_id, [lng, lat]>

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
  // 1/2 mile circumference (outer)
  map.addLayer({
    id: "active-half-line",
    type: "line",
    source: "active-station-src",
    filter: ["==", ["get", "radius"], "half"],
    paint: {
      "line-color": "#222222",
      "line-width": 3.0,
      "line-opacity": 0.95,
      "line-dasharray": [3, 2],
    },
  });
  // 1/4 mile circumference (inner) — solid line to distinguish it from
  // the dashed outer ring; same color so they read as a single station's
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

function initReports() {
  const openBtn = document.getElementById("open-tod-report");
  const closeBtn = document.getElementById("close-report");
  const panel = document.getElementById("report-panel");
  const select = document.getElementById("station-select");
  if (!openBtn || !closeBtn || !panel || !select) return;

  openBtn.addEventListener("click", async () => {
    await ensureReportSelectorPopulated();
    panel.classList.remove("hidden");
    panel.setAttribute("aria-hidden", "false");
  });
  closeBtn.addEventListener("click", () => {
    panel.classList.add("hidden");
    panel.setAttribute("aria-hidden", "true");
    clearActiveStation();
  });
  select.addEventListener("change", () => renderReport(select.value));
}

async function ensureReportSelectorPopulated() {
  const select = document.getElementById("station-select");
  if (select.options.length > 0) return;
  const data = await loadStationReports();
  select.innerHTML =
    `<option value="">— select a station —</option>` +
    data.map((s, i) => `<option value="${i}">${s.stop_name}</option>`).join("");
}

async function openReportFor(stopName) {
  const panel = document.getElementById("report-panel");
  const select = document.getElementById("station-select");
  await ensureReportSelectorPopulated();
  const idx = stationReports.findIndex((s) => s.stop_name === stopName);
  if (idx < 0) return;
  select.value = String(idx);
  renderReport(String(idx));
  panel.classList.remove("hidden");
  panel.setAttribute("aria-hidden", "false");
}

function renderReport(idxStr) {
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

  const headerStats = `
    <div class="report-stat-grid">
      <div class="report-stat">
        <span class="report-stat-label">Dwelling units (1/2-mile radius)</span>
        <span class="report-stat-value">${fmtNum(s.half_mile.dwelling_units)}</span>
      </div>
      <div class="report-stat">
        <span class="report-stat-label">Dwelling units (1/4-mile radius)</span>
        <span class="report-stat-value">${fmtNum(s.quarter_mile.dwelling_units)}</span>
      </div>
      <div class="report-stat">
        <span class="report-stat-label">Avg floor-area ratio (1/2-mile radius)</span>
        <span class="report-stat-value">${fmtFar(avgFar)}</span>
      </div>
      <div class="report-stat">
        <span class="report-stat-label">Avg year built (1/2-mile radius)</span>
        <span class="report-stat-value">${fmtYear(s.half_mile.avg_year_built)}</span>
      </div>
      <div class="report-stat">
        <span class="report-stat-label">Median household income (2024, census tract)</span>
        <span class="report-stat-value">${fmtIncome(s.tract_mhi_2024)}</span>
      </div>
      <div class="report-stat">
        <span class="report-stat-label">Median family income (2024, census tract)</span>
        <span class="report-stat-value">${fmtIncome(s.tract_mfi_2024)}</span>
      </div>
    </div>
  `;

  // For each breakdown, render bars in a fixed legend order so different
  // stations can be compared at a glance.
  const ZONING_ORDER = Object.keys(ZONING_COLORS);
  const FAR_ORDER = FAR_BINS;
  const LU_ORDER = LAND_USE_DEFS.map((d) => d.dataValue)
    .filter((v) => !VACANT_DATA_VALUES.includes(v))
    .concat(["Vacant"]);

  const ZONING_COLOR_FN = (k) => ZONING_COLORS[k] || "#CCCCCC";
  const LU_COLOR_FN = (k) => {
    if (k === "Vacant") return "#A89F94";
    const def = LAND_USE_DEFS.find((d) => d.dataValue === k);
    return def ? def.color : "#CCCCCC";
  };
  const FAR_COLOR_FN = (k) => FAR_COLORS[k] || "#CCCCCC";

  function renderPctBlock(title, qPcts, hPcts, order, colorFn) {
    let rows = "";
    rows += `<div class="report-section-head">
      <span>${title}</span>
      <span class="pct-num">1/4 mi</span>
      <span class="pct-num">1/2 mi</span>
    </div>`;
    for (const k of order) {
      const q = qPcts[k];
      const h = hPcts[k];
      if (q == null && h == null) continue;
      // Bar widths scaled to the larger of the two so they're comparable
      const denom = Math.max(q || 0, h || 0, 1);
      const wH = Math.round(((h || 0) / denom) * 100);
      rows += `<div class="pct-row">
        <span class="pct-label">
          <span class="pct-swatch" style="background:${colorFn(k)}"></span>${k}
        </span>
        <span class="pct-num">${q != null ? q.toFixed(1) + "%" : "—"}</span>
        <span class="pct-num">${h != null ? h.toFixed(1) + "%" : "—"}</span>
      </div>`;
    }
    return rows;
  }

  content.innerHTML = `
    <h3>${s.stop_name}</h3>
    <p class="muted" style="margin:4px 0 12px 0;font-size:11px">
      <span style="display:inline-block;width:10px;height:10px;border:2px solid #222222;border-radius:50%;vertical-align:middle;margin-right:4px"></span>1/4 mile
      &nbsp;
      <span style="display:inline-block;width:10px;height:10px;border:2px dashed #222222;border-radius:50%;vertical-align:middle;margin-right:4px"></span>1/2 mile
      &nbsp;shown on map
    </p>
    ${headerStats}

    <h3 style="margin-top:18px">Base zoning mix</h3>
    ${renderPctBlock("Category", s.quarter_mile.zoning_pct, s.half_mile.zoning_pct, ZONING_ORDER, ZONING_COLOR_FN)}

    <h3>Land use mix</h3>
    ${renderPctBlock("Category", s.quarter_mile.land_use_pct, s.half_mile.land_use_pct, LU_ORDER, LU_COLOR_FN)}

    <h3>Building FAR distribution</h3>
    ${renderPctBlock("FAR bin", s.quarter_mile.far_pct, s.half_mile.far_pct, FAR_ORDER, FAR_COLOR_FN)}
  `;
}
