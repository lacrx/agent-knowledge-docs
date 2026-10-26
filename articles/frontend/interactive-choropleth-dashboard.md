---
title: Interactive Choropleth Dashboard
topics:
  - data-visualization
  - maplibre
  - react
  - d3
  - choropleth
  - dashboard
  - civic-tech
  - typescript
skills:
  - add-dashboard-view
summary: >
  Architecture for building interactive civic data dashboards with linked
  choropleth maps, sortable tables, and scatter plots. Covers the linked
  selection model, fixed-break color scales, geographic unit abstraction,
  year-range navigation with sparklines, CSV export, methodology documentation,
  and patterns from the Chicago Housing Tracker adapted for reuse.
aliases:
  - choropleth dashboard
  - housing dashboard
  - civic dashboard
  - interactive map dashboard
  - linked selection map table
  - ward map dashboard
  - council district dashboard
related:
  - cms-driven-data-visualization-gatsby
  - municipal-data-pipeline-patterns
  - interactive-data-explorer-patterns
last-updated: 2026-10-24
---

# Interactive Choropleth Dashboard

## Overview

A civic data dashboard typically has three coordinated views: a map showing geographic patterns, a table for precise lookup and sorting, and a chart revealing relationships (income vs. production, time trends, category breakdowns). The power comes from linking these views: clicking a district on the map highlights it in the table and chart; hovering a row highlights the district on the map.

This article describes the architecture for building these dashboards, drawn from patterns in the Chicago Housing Tracker (an open-source ward-level housing dashboard) and adapted for general reuse. The geographic unit is parameterized (wards, council districts, census tracts, or any polygon layer), and the data model is flexible enough to support production counts, affordability metrics, official vote scores, or any value that varies by geography and time.

> **Skill:** For step-by-step scaffolding of a new dashboard view, use the `add-dashboard-view` skill.

---

## The Linked Selection Model

This is the core coordination pattern. All visual components share four props:

```typescript
type SelectionProps = {
  selectedUnit: number | null;   // click-locked selection
  hoveredUnit: number | null;    // mouse hover (ephemeral)
  onSelectUnit: (unit: number | null) => void;
  onHoverUnit: (unit: number | null) => void;
};
```

The parent page owns the state:

```typescript
const [selectedUnit, setSelectedUnit] = useState<number | null>(null);
const [hoveredUnit, setHoveredUnit] = useState<number | null>(null);
const active = selectedUnit ?? hoveredUnit;
```

**Selection semantics:** Click toggles (clicking the same unit deselects). Hover is ephemeral and never persists. The `active` unit (selected if set, otherwise hovered) drives detail views and highlights.

Every component receives these four props and:
- Highlights the active unit visually (border weight on map, row class on table, dot color on scatter)
- Calls `onSelectUnit` on click, `onHoverUnit` on mouseenter/mouseleave
- Draws the active unit last (z-order) so it sits on top

This pattern scales to any number of coordinated components. Add a new view and it participates automatically.

---

## Color Scales

### Fixed Breaks, Not Quantiles

Use fixed break values for choropleth colors:

```typescript
const BREAKS = [5, 15, 40, 100, 250, 600];
const RAMP = ["#e2f4fc", "#b3e2f6", "#7cccef", "#3fb2e3", "#0d96c9", "#00718f", "#004a63"];
```

Quantile breaks re-rank the data so every color bin has roughly equal membership. This hides real differences: switching between two metrics (say, 60% AMI and 100% AMI affordability) produces identical-looking maps even when the underlying values differ dramatically, because quantiles always produce even distribution.

Fixed breaks preserve the absolute meaning of color. A district that moves from one bin to another shows a real shift, not just a rank change. The tradeoff: some bins may be empty for some metrics. That's fine; the visual gap communicates something true.

### Geometric vs. Linear Breaks

Choose break spacing based on data distribution:

- **Linear breaks** (5, 10, 15, 20, 25, 30) for normally distributed data like affordability percentages
- **Geometric breaks** (5, 15, 40, 100, 250, 600) for power-law distributed data like permit counts, where the top unit may be 100x the bottom

Test by checking the ratio of max to min across geographic units. If it exceeds 20x, geometric breaks will produce better visual discrimination.

### Diverging Scale for Change

Year-over-year change needs a diverging scale. Encode direction as color and magnitude as opacity:

```typescript
function divergingColor(value: number, maxAbs: number) {
  if (Math.abs(value) < 0.05) return { fill: "#c3cbcf", opacity: 0.5 };
  const fill = value > 0 ? "#0d96c9" : "#d85a42";
  const opacity = 0.35 + 0.65 * Math.min(1, Math.abs(value) / maxAbs);
  return { fill, opacity };
}
```

Opacity encoding avoids generating intermediate hex values and keeps the color semantics clean: blue means improvement, coral means decline, gray means flat.

---

## Geographic Unit Abstraction

The dashboard should work with any polygon layer. Abstract the geographic unit:

```typescript
type GeoUnit = {
  id: number | string;
  name: string;
  geometry?: GeoJSON.Feature;
};

type DashboardConfig = {
  unitLabel: string;           // "Ward" | "District" | "Tract"
  unitLabelPlural: string;     // "Wards" | "Districts" | "Tracts"
  unitCount: number;           // 50 for Chicago, 4 for Oceanside
  boundaryFile: string;        // "chicago_wards.json" | "oceanside_districts.geojson"
  unitIdField: string;         // property name in GeoJSON features
  bounds: [[number, number], [number, number]];  // map bounding box
  defaultCenter: [number, number];
  defaultZoom: number;
};
```

Components reference `config.unitLabel` instead of hardcoding "Ward." The map reads `feature.properties[config.unitIdField]` instead of `feature.properties.ward`.

---

## Map Component (MapLibre)

### Basic Choropleth

```typescript
function ChoroplethMap({ data, colorFn, config, ...selectionProps }: Props) {
  // Fetch GeoJSON at runtime from static assets
  // For each feature, look up data by unit ID
  // Apply fill color from colorFn(value)
  // Stroke weight: selected=3, hovered=2, default=1
}
```

Key implementation details:

**GeoJSON loaded at runtime**, not imported statically. This keeps the JS bundle small (ward boundaries can be 150KB+). Fetch from `import.meta.env.BASE_URL + config.boundaryFile`.

**Validate feature count** against `config.unitCount`. If the GeoJSON has fewer features than expected, show an error rather than a silently incomplete map.

**Shared viewport for multi-map pages.** When showing the same geography in multiple time periods side by side, synchronize pan/zoom across all map instances:

```typescript
type SharedViewport = {
  center: [number, number];
  zoom: number;
};
const [viewport, setViewport] = useState<SharedViewport | null>(null);
```

**Accessibility:** Add `tabindex`, `role="button"`, and `aria-label` to each polygon path element so keyboard users can navigate and select geographic units.

---

## Table Component

Use TanStack React Table for sorting and filtering. The table shows one row per geographic unit with columns adapted to the current metric:

```typescript
const columns = useMemo(() => [
  { header: config.unitLabel, accessorKey: "id" },
  { header: "Name", accessorKey: "name" },
  { header: metricHeader(filters), accessorKey: "value" },
  { header: "Rank", accessorKey: "rank" },
  { header: "YoY", accessorKey: "rankChange" },
], [filters, config]);
```

**Search** filters by name or unit ID. **Click and hover** on rows trigger the same selection callbacks as the map. **CSS classes** `row-selected` and `row-hovered` highlight the active row.

**Formatting functions** for consistent display:

```typescript
const fmtPct = (v: number | null) => v != null ? `${v.toFixed(1)}%` : "—";
const fmtMoney = (v: number | null) => v != null ? `$${v.toLocaleString()}` : "—";
const fmtRank = (v: number | null) => v != null ? `#${v}` : "—";
const fmtSignedPct = (v: number | null) => v != null ? `${v > 0 ? "+" : ""}${v.toFixed(1)}pp` : "—";
```

---

## Scatter Plot (Hand-Rolled SVG)

For the income-vs-production or similar two-variable view, hand-rolled SVG outperforms charting libraries in bundle size and customization:

### Outlier Handling

Auto-detect outliers and use an axis break:

```typescript
const OUTLIER_RATIO = 1.6;
function needsAxisBreak(values: number[]): boolean {
  const sorted = [...values].sort((a, b) => b - a);
  return sorted.length > 1 && sorted[0] / sorted[1] > OUTLIER_RATIO;
}
```

When the top value exceeds the second by 1.6x, cap the main axis at the second value and draw the outlier in a separate band above a squiggle axis-break mark. This prevents one extreme value from compressing the rest of the chart into illegibility.

### Label Placement

Collision-avoidance for point labels:

```typescript
function placeLabels(points: Point[], maxLabels: number): PlacedLabel[] {
  // For each point, try 4 positions: right, left, above, below
  // Check against all already-placed labels AND all dot markers
  // Priority: forced labels first, then by importance ranking
  // Approximate character dimensions: CH=6, LH=11
}
```

### Trend Line

Least-squares regression as a dashed line in a muted color. Helps readers see whether the relationship is positive, negative, or flat without eye-balling scattered dots.

### Smart Label Selection

For the income-vs-production scatter, label the most interesting outliers automatically:

```typescript
function selectLabels(points: Point[]): number[] {
  // Compute least-squares regression
  // Rank points by absolute residual (distance from trend)
  // Return the top N + axis extremes (highest X, highest Y, lowest X)
}
```

---

## Year-Range Navigation

### Dual-Handle Slider

```typescript
const [from, setFrom] = useState(FIRST_YEAR);
const [to, setTo] = useState(LAST_YEAR);
```

CSS custom properties position the filled range:

```css
.slider-track {
  background: linear-gradient(
    to right,
    var(--track-bg) var(--lo),
    var(--track-fill) var(--lo),
    var(--track-fill) var(--hi),
    var(--track-bg) var(--hi)
  );
}
```

Safe setters prevent `from > to`:

```typescript
const setSafeFrom = (v: number) => setFrom(Math.min(v, to));
const setSafeTo = (v: number) => setTo(Math.max(v, from));
```

### Sparkline Below Slider

One bar per year, height proportional to the citywide total for that year. Clicking a bar sets both `from` and `to` to that year (single-year view). Bars inside the selected range are highlighted. The final year gets a "partial" label when data is incomplete.

This serves as both a trend overview and a navigation control: the user sees the overall trajectory while choosing their focus period.

---

## CSV Export

Every view should offer CSV download. Encode the current filter state in the filename:

```typescript
function downloadCsv(rows: Row[], filters: FilterState, config: DashboardConfig) {
  const headers = [config.unitLabel, "Name", metricHeader(filters), "Rank"];
  const csv = [
    headers.join(","),
    ...rows.map(r => [r.id, `"${r.name}"`, r.value, r.rank].join(","))
  ].join("\n");

  const blob = new Blob([csv], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${config.unitLabelPlural.toLowerCase()}-${filters.metric}-${filters.from}-${filters.to}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}
```

Low effort, high value. Advocates and journalists will use the CSV more than the interactive views.

---

## Methodology Notes

Every dashboard page should end with a methodology section covering:

1. **Data source** with link to the authoritative origin
2. **What's included and excluded** (only discretionary? ministerial? both?)
3. **How geographic assignment works** (point-in-polygon, centroid, stated vs. current)
4. **Known limitations** (classification rate, missing data, partial years)
5. **How to interpret the metric** (what does "affordable at 60% AMI" actually mean?)
6. **Data vintage** (when was this last updated?)

This is not optional decoration. It builds trust and preempts misinterpretation. If the methodology section would be embarrassing to write, the data isn't ready for a public dashboard.

---

## Filter Architecture

Centralize filter state in a single object:

```typescript
type FilterState = {
  year: YearKey;          // or [from, to] for range
  metric: MetricKey;       // "production" | "affordability" | "scores"
  viewMode: "level" | "change";
  geography: GeographyKey; // when multiple boundary layers are available
};
```

All metric computation functions accept `FilterState` and return the appropriate value. This means adding a new filter dimension (a new metric, a new geography level) only requires:
1. Adding the option to FilterState
2. Handling it in the metric functions
3. Adding a UI control

Components never branch on filter state directly. They call metric functions and display what comes back.

---

## Data Loading Patterns

### Static Import (Gatsby)

For Gatsby sites, import JSON at build time via GraphQL or direct import:

```typescript
import productionData from "../data/production.json";
```

Gatsby's webpack will chunk this into the page bundle. For large datasets (500KB+), consider loading at runtime from `/static/` instead.

### Runtime Fetch (Vite)

For Vite sites, load from the public directory:

```typescript
const [data, setData] = useState<ProductionData | null>(null);
useEffect(() => {
  fetch(`${import.meta.env.BASE_URL}data/production.json`)
    .then(r => r.json())
    .then(setData);
}, []);
```

### Hybrid (Gatsby page with runtime data)

For a Gatsby page that needs data too large or too dynamic for the build:

```typescript
// Small config/metadata at build time via static query
const { meta } = useStaticQuery(graphql`...`);

// Large data at runtime
const [records, setRecords] = useState(null);
useEffect(() => {
  fetch("/data/production.json").then(r => r.json()).then(setRecords);
}, []);
```

---

## Advocacy-Specific Dimensions

Civic housing dashboards serve a different audience than internal analytics. Advocates, journalists, and elected officials need metrics that connect to policy levers.

### RHNA Pace (California-Specific)

In California, every city has a state-mandated housing target (RHNA). Showing progress against this target, broken down by income tier, is the highest-impact view a housing dashboard can offer. Display as progress bars per tier:

```
Very Low Income:  ████░░░░░░░░░░░░ 24% (312 of 1,298)
Low Income:       ██████░░░░░░░░░░ 38% (285 of 750)
Moderate:         █████████░░░░░░░ 58% (435 of 750)
Above Moderate:   ████████████████ 100%+ (1,944 of 1,645)
```

The income-tier breakdown reveals the pattern: cities commonly overproduce market-rate while underproducing affordable. A single aggregate "55% of target" hides this.

### Compliance Status

Whether a jurisdiction is "in compliance" or "out of compliance" with state housing law changes the legal landscape: Builder's Remedy, SB 35 streamlining, SB 423. Display compliance status prominently and explain what it unlocks. Link to the statewide tracker (cities.fairhousingelements.org) for context.

### Policy Impact Timeline

Overlay policy change dates on production timelines: when did a density cap change? When were parking minimums eliminated? When did a new inclusionary ordinance take effect? This transforms "units per year" from a flat trend into a causal narrative. Even if the causal claim is uncertain, showing the date creates the right question.

---

## Integrating with an Existing Design System

When the dashboard lives inside an existing site (not a standalone deploy), it must inherit the site's visual language while adding data-specific components.

### Extending Existing Tokens

A typical editorial site has a minimal set of CSS custom properties (background, text, a few greys, serif/sans fonts, a rule color). A dashboard needs more:

```css
:root {
  /* Existing editorial tokens (inherit, don't duplicate) */
  --bg: #fff;
  --text: #121212;
  --grey: #333;
  --rule: #e2e2e2;
  --serif: Georgia, "Times New Roman", Times, serif;
  --sans: Helvetica, "Helvetica Neue", Arial, sans-serif;

  /* Dashboard extensions */
  --accent: #0d96c9;           /* data highlight, links in data context */
  --negative: #d85a42;         /* decline, anti-housing */
  --neutral: #c3cbcf;          /* no change, missing data */
  --positive: #2a9d8f;         /* improvement, pro-housing */

  /* Data typography */
  --mono: "SF Mono", "Fira Code", Consolas, monospace;
  --table-font-size: 0.8125rem;
  --stat-font-size: 2rem;
}
```

### Preserving Site Consistency

Borrow specific patterns from the editorial side:
- Same `0.125rem` border-radius on all interactive elements (buttons, inputs, map containers, table cells)
- Same `var(--rule)` for borders and separators
- Same sans-serif stack for UI chrome, serif for body text
- Same middot separator pattern for metadata lines (author, date, data vintage)

### What the Dashboard Adds

The dashboard introduces UI elements the editorial site doesn't have: toggle groups, range sliders, sortable table headers, map controls, chart legends, stat tiles. Define these once in a shared CSS module that all dashboard views import. Don't let each view reinvent button styles.

---

## When to Use This Pattern

**Good fit:**
- Public-facing civic data with geographic and temporal dimensions
- Data that updates on a schedule (monthly/quarterly), not real-time
- Audiences that include advocates, journalists, and elected officials (need CSV export and methodology)
- 3-50 geographic units (fewer than 3 is a table, more than 50 needs clustering or hexbins)

**Poor fit:**
- Real-time dashboards (use a database-backed API)
- Internal analytics tools (don't need the trust-building methodology layer)
- Point-level data only, no geographic aggregation (use a dot map, not a choropleth)
