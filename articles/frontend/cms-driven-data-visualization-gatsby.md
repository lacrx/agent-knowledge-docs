---
title: CMS-Driven Data Visualization in Gatsby
topics:
  - gatsby
  - data-visualization
  - maplibre
  - deck-gl
  - d3
  - strapi
  - react
  - pmtiles
  - observable-plot
skills:
  - add-gatsby-visualization
summary: >
  Architecture for embedding interactive data visualizations in a Gatsby site
  via CMS content blocks. Covers the artifact.json config pattern, renderer
  registry with staging differentiation (heavy vs. lightweight), CMS-sourced
  data/config for lightweight renderers, MapLibre + deck.gl composition,
  PMTiles self-hosted basemaps, poster frame fallbacks, and service worker
  caching strategy.
aliases:
  - gatsby visualization
  - gatsby maplibre
  - cms data viz
  - gatsby deck.gl
  - strapi visualization block
  - gatsby choropleth
  - pmtiles gatsby
related:
  - interactive-choropleth-dashboard
  - interactive-data-explorer-patterns
last-updated: 2026-10-24
---

# CMS-Driven Data Visualization in Gatsby

## Overview

A recurring need in civic data publishing: editors write articles in a CMS, and some articles embed interactive visualizations (choropleths, scatter plots, dashboards) that require custom React components and large datasets. The challenge is bridging CMS content management with code-driven interactivity without requiring editors to touch code, and without requiring developers to redeploy for every new article.

This article describes an architecture that solves this by treating visualizations as named artifacts: each visualization has a `vizId`, a renderer type, and a configuration object. The CMS references the vizId in a content block; the frontend looks it up, lazy-loads the appropriate renderer, and passes the config. New visualization instances require only a JSON file and (sometimes) a GeoJSON dataset. New visualization types require a new renderer component.

> **Skill:** For step-by-step scaffolding of a new visualization, use the `add-gatsby-visualization` skill.

---

## Architecture

### The Three Layers

```
Strapi CMS                    Gatsby Build                    Browser
─────────────                 ───────────                     ───────
Article with                  gatsby-node.ts                  VisualizationBlock
  ComponentSharedVisualization  → sourceNodes()                 → lookup by vizId
  block (vizId, caption,        → creates GatsbyVisualization   → resolve renderer by type
  height, align)                  nodes from artifact.json       → lazy load with Suspense
                                                                → pass artifact config as props
```

**CMS layer:** Strapi defines a `ComponentSharedVisualization` block type with fields: `vizId` (string), `caption` (optional text), `height` (integer, px), `align` (enum: inline/wide/full-bleed). Editors drop this block into an article and enter the vizId. That's all they touch.

**Build layer:** `gatsby-node.ts` reads `artifact.json` files from `src/assets/visualizations/{vizId}/` and creates `GatsbyVisualization` nodes. Each node carries the full config: camera position, color scale, elevation mapping, data file references. Gatsby's file system nodes automatically resolve linked GeoJSON and PMTiles files so they get content-hashed URLs.

**Runtime layer:** `VisualizationBlock` receives a vizId from the article's block data, looks up the matching `GatsbyVisualization` node via a static query, resolves the renderer component from a type registry, and renders it inside a Suspense boundary with a poster frame fallback.

### artifact.json Schema

Each visualization lives in its own directory:

```
src/assets/visualizations/
  oceanside-wealth/
    artifact.json
    parcels.pmtiles          # or parcels.geojson
    poster-desktop.jpg
    poster-mobile.jpg
```

The artifact.json defines everything the renderer needs:

```json
{
  "vizId": "oceanside-wealth",
  "type": "choropleth-3d-maplibre",
  "title": "Our Wealth Is Downtown",
  "source": "San Diego County Assessor, 2024",
  "features": "parcels",
  "featuresTiles": "parcels",
  "posterFrame": "poster-desktop",
  "posterFrameMobile": "poster-mobile",
  "basemap": "oceanside.pmtiles",
  "tilesLayer": "features",
  "camera": {
    "center": [-117.3795, 33.1965],
    "zoom": 12.5,
    "pitch": 45,
    "bearing": 0
  },
  "color": {
    "field": "assessed_value_sqft",
    "domain": [50, 100, 200, 400, 800],
    "range": ["#f0f4f7", "#b3d4e8", "#6baed6", "#2171b5", "#08519c", "#042f6b"]
  },
  "elevation": {
    "field": "assessed_value_sqft",
    "divisor": 2
  },
  "fallback2d": {
    "maxViewportWidth": 360
  }
}
```

Key design decisions:
- **`features` and `featuresTiles` reference filenames** (no extension), resolved by Gatsby's file system linking. This means the actual URLs are content-hashed and cache-safe.
- **`type` maps to a renderer component.** Adding a new visualization type means writing a new renderer and registering it. Adding a new instance of an existing type means only adding an artifact.json.
- **`color` uses d3-scale conventions** (domain = break values, range = color stops). The renderer builds the scale from these arrays. Editors or data analysts can tune colors in JSON without touching component code.
- **`fallback2d`** declares a viewport threshold below which the interactive map is skipped entirely and only the poster image is shown. This avoids WebGL context limits on low-end mobile.

### Renderer Registry

```typescript
const RENDERERS: Record<string, React.LazyExoticComponent<React.ComponentType<any>>> = {
  "choropleth-3d-maplibre": Choropleth3DMaplibre,
  "stat-tiles": StatTiles,
  "timeline": Timeline,
  "bar-chart": BarChart,
  "vote-visualization": VoteVisualization,
  "data-table": DataTable,
};
```

Each renderer receives `{ artifact }` as props. The artifact object is the full `GatsbyVisualization` node with resolved file URLs. Renderers are lazy-loaded so pages without visualizations pay zero JS cost.

Normalize type strings on lookup (underscores to hyphens) so CMS entries with `stat_tiles` still resolve to the `stat-tiles` renderer key:

```typescript
const normalizedType = artifact.type.replace(/_/g, "-");
const Renderer = RENDERERS[normalizedType];
```

### Staging: Heavy vs. Lightweight Renderers

Not every renderer needs the poster frame and loader overlay. A `NEEDS_STAGE` map declares which types require the full staging treatment (poster crossfade, loading indicator, `data-viz-ready` gate):

```typescript
const NEEDS_STAGE: Record<string, boolean> = {
  "choropleth-3d-maplibre": true,
};
```

Types not in this map (stat-tiles, timeline, bar-chart, vote-visualization, data-table) render immediately without a poster or loader. They mount directly inside the figure container. This avoids unnecessary layout complexity for components that render in under 50ms.

The staging wrapper (absolute-positioned poster, Suspense boundary, loading dots, `data-viz-ready` opacity transition) only wraps renderers where `NEEDS_STAGE[type]` is truthy.

### CMS-Sourced Data and Config

For lightweight visualizations, data can live in the CMS itself rather than in `artifact.json` files on disk. The `GatsbyVisualization` type extends with two optional fields:

```typescript
type GatsbyVisualization = {
  vizId: string;
  type: string;
  // ... standard fields (camera, color, elevation) ...
  data?: unknown;    // structured data from CMS
  config?: unknown;  // renderer-specific config from CMS
};
```

In Strapi, the visualization content type includes `data` (JSON) and `config` (JSON) fields that editors can populate directly. `gatsby-node.ts` sources these alongside `vizId` and `type`:

```graphql
query GetAllStrapiVisualizations {
  visualizations(pagination: { pageSize: 100 }) {
    documentId
    vizId
    title
    type
    source
    data
    config
  }
}
```

This is the right path for data that updates with editorial workflow (vote tallies, stat tile values, timeline entries). Heavy geospatial datasets still belong in artifact.json with file system linking.

---

## MapLibre + deck.gl Composition

The `choropleth-3d-maplibre` renderer demonstrates how to composite MapLibre basemaps with deck.gl data layers.

### Basemap Strategy: Self-Hosted PMTiles

PMTiles bundles an entire vector tileset into a single file, served from static hosting (S3, CloudFront, Netlify) with HTTP range requests. No tile server needed.

```typescript
import { Protocol } from "pmtiles";
import maplibregl from "maplibre-gl";

const protocol = new Protocol();
maplibregl.addProtocol("pmtiles", protocol.tile);
```

The basemap style is defined inline (not loaded from a URL), using the OpenMapTiles schema. This means no external style JSON fetch, no Mapbox API key, no third-party tile servers. Layers included: background, park fill, water, minor roads, major roads, buildings. No text labels (avoids glyph font dependency).

### Data Layer: Two Paths

**PMTiles path (preferred for large datasets):** Vector tiles loaded as a MapLibre source, rendered with `fill-extrusion` layer. Color is a MapLibre step expression built from the artifact's domain/range arrays:

```typescript
function buildStepColorExpression(field, domain, range) {
  const expr = ["step", ["get", field], range[0]];
  for (let i = 1; i < range.length && i - 1 < domain.length; i++) {
    expr.push(domain[i - 1], range[i]);
  }
  return expr;
}
```

**GeoJSON path (for smaller datasets or when tiles aren't pre-built):** deck.gl `GeoJsonLayer` with `extruded: true`. Color via d3 `scaleThreshold`. GeoJSON is fetched with `AbortSignal` so navigation away cancels the download. Buffer construction is deferred via `requestIdleCallback` to keep the UI responsive during the 1-2 second attribute build.

### Camera and Interaction

Camera config (center, zoom, pitch, bearing) comes from artifact.json. During development, `moveend` logs the current camera state as JSON so you can paste it back into the artifact:

```typescript
if (process.env.NODE_ENV === "development") {
  map.on("moveend", () => {
    console.log(`[viz:${artifact.vizId}] camera`, JSON.stringify(cam));
  });
}
```

Interaction is deliberately constrained: scroll zoom, double-click zoom, and box zoom are disabled. Pinch-zoom is enabled only after the map finishes loading (prevents scroll-hijacking while the user is reading). Custom camera controls (rotate CW/CCW, tilt up/down) are added as a horizontal button group.

### Responsive Behavior

Zoom is adjusted by viewport width at mount time (narrower viewports get a lower zoom to keep the full dataset in frame). Below a configurable breakpoint (`fallback2d.maxViewportWidth`), the interactive map is not mounted at all and only the poster image is shown. This is binary (interactive or poster), not a degraded flat-polygon middle state.

---

## Poster Frames and Loading

Every visualization should have poster frames: static images that display instantly while the interactive version loads. This matters because:

- GeoJSON/PMTiles data can be 60+ MB
- WebGL context creation takes time
- deck.gl buffer construction blocks the main thread briefly
- Mobile devices may never get the interactive version

The poster is a `<picture>` element with desktop and mobile sources:

```html
<picture>
  <source media="(max-width: 768px)" srcSet={posterUrlMobile} />
  <img src={posterUrl} alt={title} loading="lazy" />
</picture>
```

The interactive renderer mounts on top of the poster inside a Suspense boundary. A CSS transition fades the poster out when `data-viz-ready="true"` is set. A 30-second safety timer sets ready even if data never loads, so the user is never stuck on a poster indefinitely.

---

## Service Worker Caching

PMTiles basemaps and feature tiles are large, immutable-ish files. The service worker config uses `CacheFirst` for `/tiles/*.pmtiles` and `/static/*` (Gatsby's content-hashed assets). HTML and page-data JSON use `NetworkFirst` because their URLs are stable but content changes per deploy.

The key tradeoff: only pages the user has actually visited are cached. There is no precache of the full site. This keeps the initial service worker install from competing with the page render for bandwidth.

On service worker update, runtime caches are flushed to prevent stale JS chunks from referencing deleted asset URLs. This is handled by an `appendScript` that calls `caches.keys()` and deletes non-precache caches.

---

## Gatsby Node Integration

Visualization nodes are created in `sourceNodes`:

```typescript
for (const vizDir of fs.readdirSync(visualizationsDir)) {
  const artifactPath = path.join(visualizationsDir, vizDir, "artifact.json");
  if (!fs.existsSync(artifactPath)) continue;
  const artifact = JSON.parse(fs.readFileSync(artifactPath, "utf-8"));
  createNode({
    ...artifact,
    id: createNodeId(`viz-${artifact.vizId}`),
    internal: {
      type: "GatsbyVisualization",
      contentDigest: createContentDigest(artifact)
    }
  });
}
```

Schema customization links file references:

```graphql
type GatsbyVisualization implements Node {
  vizId: String!
  type: String!
  featuresFile: File @link(by: "name", from: "features")
  featuresTilesFile: File @link(by: "name", from: "featuresTiles")
  posterFile: File @link(by: "name", from: "posterFrame")
  camera: GatsbyVizCamera
  color: GatsbyVizColor
  elevation: GatsbyVizElevation
}
```

The `@link(by: "name", from: "features")` directive means the `features` field in artifact.json is a filename (without extension), and Gatsby resolves it against `File` nodes created by `gatsby-source-filesystem` pointing at the visualizations directory. This gives you content-hashed public URLs automatically.

---

## When to Use This Pattern

**Good fit:**
- CMS-authored articles that embed interactive maps or charts
- Multiple visualization instances sharing the same renderer type
- Large geospatial datasets that need PMTiles or lazy loading
- Sites where editors should not need to redeploy for new content

**Poor fit:**
- Dashboards with complex interlinked views (filters, linked selection across components). Those need dedicated page components, not CMS blocks. See the Interactive Choropleth Dashboard article.
- One-off visualizations that will never be reused. Just build a page component.
- Real-time data. This pattern is build-time; data updates require a rebuild.

---

## CMS Content Styling Patterns

When CMS-authored rich text surrounds visualizations, a few CSS patterns keep the editorial flow consistent without requiring editors to use special markup.

### Image Captions via `:has()`

Editors write captions as italic text on its own line after an image. CSS detects this automatically:

```css
.richText p:has(> em:only-child) {
  text-align: center;
  max-width: 600px;
  margin: 0 auto 2em;
  font-size: 0.9rem;
  font-style: italic;
  color: var(--grey);
}
```

No special caption block type in the CMS. The author just writes `*Photo credit: Source*` and it styles itself.

### Visualization Breakout Widths

Article body text sits inside a `max-width` container, but visualizations often need more room. Three alignment modes handle this without breaking the article flow:

```css
.vizFigure.inline { max-width: 100%; }
.vizFigure.wide { margin-inline: calc((100vw - min(100vw, 960px)) / -2); max-width: 100vw; }
.vizFigure.fullBleed { margin-inline: calc(50% - 50vw); max-width: 100vw; }
```

The editor chooses the mode per block in the CMS. The negative margin trick lets visualizations extend past the text column without a layout wrapper.
