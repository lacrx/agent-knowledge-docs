---
title: Interactive Data Explorer Patterns
topics:
  - data-visualization
  - react
  - d3
  - interactive-charts
  - civic-tech
  - typescript
  - observable-plot
  - mobx
skills:
  - add-dashboard-view
summary: >
  Reusable architecture patterns for building user-driven interactive data
  explorers (not scrollytelling), distilled from the OWID Grapher and adapted
  for civic data projects. Covers chart configuration schemas, the three-layer
  component pattern, state-driven rendering, color scale strategies, responsive
  sizing, tooltip design, URL-driven state, and the linked-views interaction
  model.
aliases:
  - data explorer
  - interactive charts
  - owid grapher patterns
  - chart component architecture
  - user-driven visualization
  - data dashboard patterns
  - grapher patterns
related:
  - interactive-choropleth-dashboard
  - cms-driven-data-visualization-gatsby
last-updated: 2026-10-24
---

# Interactive Data Explorer Patterns

## Overview

An interactive data explorer puts the user in control. No scroll-locked narrative, no predetermined path. The user picks indicators, selects entities, toggles chart types, adjusts time ranges, and explores. Every chart works the same way: hover for details, click to select, toggle to compare. The interaction grammar is consistent; the learning curve is one chart deep.

This article captures reusable patterns from the Our World in Data (OWID) Grapher, an open-source charting platform powering thousands of interactive visualizations. The Grapher is the best reference implementation for this style of data explorer: user-driven, lightweight, consistent. These patterns are adapted for general reuse in civic data projects using React, D3, Observable Plot, or similar stacks.

> **Reference implementation:** [github.com/owid/owid-grapher](https://github.com/owid/owid-grapher). TypeScript monorepo: React 19, MobX 6, MySQL for config storage, Vite build, Cloudflare edge deployment. Note: the Grapher is no longer MIT-licensed; study the patterns but don't copy the code directly.

---

## Chart Configuration as Data

The core insight: every chart is a JSON config object, not a bespoke component. The config declares what to show; the renderer figures out how. This separates editorial decisions (which indicator, which entities, what time range) from rendering logic.

### The Config Schema

OWID's `GrapherInterface` includes:

```
title, subtitle, note          — text content
chartTypes                     — ["LineChart", "ScatterPlot", ...]
tab                            — active view (chart | map | table)
selectedEntityNames            — ["United States", "Germany"]
dimensions                     — [{variableId, property: "y"}]
hasMapTab, hasTableTab         — toggle available views
xAxis.scaleType, yAxis.scaleType  — "linear" | "log"
colorScale.baseColorScheme     — palette name
colorScale.binningStrategy     — "manual" | "equalSizeBins" | "logarithmic"
minTime, maxTime               — data range
stackMode                      — stacking behavior
```

### Adaptation for civic projects

You don't need MySQL. A static JSON file per dashboard view works:

```json
{
  "title": "Housing Permits by Ward",
  "chartType": "choropleth",
  "indicator": "permits_per_1000",
  "geoUnit": "ward",
  "colorScale": {
    "scheme": "YlOrRd",
    "breaks": [0, 2, 4, 6, 8, 10],
    "strategy": "fixed"
  },
  "defaultSelection": [],
  "timeRange": [2015, 2026]
}
```

Fixed breaks (not quantile) so the color meaning stays stable when toggling between indicators or time periods. This is the single most important color scale decision for a data explorer.

---

## The Three-Layer Component Pattern

OWID structures each chart type as three layers. This separates concerns cleanly and enables both interactive and static (export) rendering from the same code.

### Layer 1: State class (`*State.ts`)

Layout-independent. Computes derived data from raw inputs: series grouping, scale domains, color assignments, label placement. Pure computation, no DOM, no React.

### Layer 2: Observer component (`*Chart.tsx`)

MobX `@observer` React component. Reads from the state class, renders SVG structure, attaches interaction handlers (hover, click, resize). Has two render paths: `renderInteractive()` with tooltips and overlays, `renderStatic()` for SVG/PNG export.

### Layer 3: Stateless SVG renderers

Pure components that render visual marks: lines, bars, points, polygons. Receive positioned, styled data. No state, no side effects.

### The data chain

```
Raw Data → Series → SizedSeries → PlacedSeries → RenderSeries
```

Each stage adds layout information. `Series` has data values. `SizedSeries` adds computed dimensions. `PlacedSeries` adds x/y positions. `RenderSeries` adds emphasis state and final styling. This chain means the expensive layout computation only reruns when data or container size changes, not on every hover.

### Adaptation

In a non-MobX project (plain React + hooks), the three layers map to:

1. **Custom hook** (`useDashboardState`): computes derived data via `useMemo`
2. **Container component**: manages interactions, renders layout
3. **Presentational components**: pure SVG renderers

---

## Interface-Based Polymorphism

OWID chart types do NOT share a base class. Instead, every chart implements a `ChartInterface` contract. The orchestrator (`Grapher`) renders any chart type polymorphically through this interface.

Charts that use Cartesian axes also implement `AxisManager`. Map charts implement `ChoroplethMapManager`. This composition-over-inheritance approach means new chart types slot in without modifying existing ones.

For a civic data dashboard: define a `DashboardView` interface with `render()`, `getTooltipContent()`, `handleSelection()`. Each view type (choropleth, scatter, table, bar) implements it. The dashboard shell doesn't know which view it's rendering.

---

## Color Scale Strategies

### Categorical colors

OWID uses a `CategoricalColorAssigner` that maps entities to colors deterministically. The assignment is stable: adding or removing an entity doesn't shuffle colors for other entities.

For civic dashboards: assign colors by a hash of the entity name, not by array index. This ensures "Ward 12" always gets the same color regardless of which other wards are selected.

### Sequential and diverging scales

Three binning strategies based on data distribution:

- **Fixed manual breaks**: editor-defined thresholds. Best for comparability across views.
- **Equal-size bins**: 5-9 bins, linear distribution. Good for normally distributed data.
- **Logarithmic bins**: "1-2-5" pattern. For data spanning multiple orders of magnitude (population, income).

OWID's key insight: fixed breaks beat quantile breaks for explorers. When the user toggles between "2020 permits" and "2023 permits," fixed breaks let them see that Ward 27 went from orange to red. Quantile breaks would reshuffle the entire scale, destroying the comparison.

### ColorBrewer integration

OWID builds on ColorBrewer palettes (the standard for cartographic color). Custom palettes extend these. For civic projects, ColorBrewer's sequential (`YlOrRd`, `Blues`) and diverging (`RdBu`, `PiYG`) schemes are the right foundation.

---

## State Management and URL Binding

### The URL is the state

Every OWID chart encodes its state in the URL: `?tab=map&time=2020&country=USA~DEU&yScale=log`. This means:

- Charts are bookmarkable and shareable in their exact state
- Browser back/forward navigates chart state
- Embeds can be pre-configured via URL params

### Entity selection via URL

Entities separated by `~`: `?country=USA~DEU~JPN`. Special tokens like `~OWID_WRL` for aggregate entities. The selection syncs bidirectionally: clicking a country on the map updates the URL; editing the URL updates the selection.

### Adaptation

For a civic dashboard, encode: selected geography IDs, active indicator, time range, active view tab. Use `URLSearchParams` or a router's query state. Two-way sync: UI changes update URL (via `replaceState` to avoid history spam for every hover), URL changes update UI.

```
/data/permits?ward=12,27&indicator=permits_per_1000&year=2023&view=map
```

---

## Responsive Chart Sizing

OWID charts fill their container. No fixed dimensions. The `GrapherLoader.mount()` method observes container resizes and re-renders. Charts adapt by:

- Hiding/repositioning legends at narrow widths
- Reducing label density on axes
- Switching tooltip position (above vs. beside) based on available space
- Adjusting font sizes proportionally

The default aspect ratio is 850:600 (~1.42:1). For embeds, charts work at any size the container provides.

### Adaptation

Use `ResizeObserver` on the chart container. Pass width/height as props to the chart component. All internal sizing should be relative to these dimensions, never absolute px values. Breakpoints:

- **< 400px**: hide axis labels, compress legend to single row, tooltip follows touch
- **400-700px**: abbreviated labels, legend below chart
- **> 700px**: full labels, legend beside chart (if space permits)

---

## Tooltip Design

Each OWID chart type has its own tooltip component, but all share a pattern:

1. **Position**: tooltip state is an observable `{ x, y, entity, time, values }`. Updated on cursor move.
2. **Content**: chart-specific formatting. Line charts show the value at the hovered time. Maps show the entity name + value + rank. Scatter plots show both axis values + size variable.
3. **Placement**: smart positioning to avoid clipping viewport edges.
4. **Performance**: tooltip rendering is decoupled from chart rendering. Moving the cursor only updates the tooltip overlay, not the entire chart SVG.

### Key principle

Tooltips show one thing: the data under the cursor, formatted for that chart type. No mini-charts inside tooltips. No multi-paragraph explanations. Entity name, value, unit, time. That's it.

---

## Linked Views

The interaction model that defines a data explorer: multiple views (map, table, chart) share selection state. Click a ward on the map, the table scrolls to it, the scatter plot highlights it.

### Implementation

A shared selection store (MobX observable, React context, or Zustand store) holds:

```typescript
interface SelectionState {
  selectedIds: Set<string>
  hoveredId: string | null
  activeIndicator: string
  timeRange: [number, number]
  activeTab: "map" | "table" | "chart"
}
```

All views read from this store and render accordingly. All views write to it on interaction. The store is the single source of truth.

### Emphasis vs. selection

Two distinct interaction states:
- **Hover/emphasis**: temporary highlight, resets on mouse leave. Visual: brighter color, thicker stroke.
- **Selection**: persistent until explicitly deselected. Visual: full opacity vs. dimmed for unselected.

OWID uses a `focus` module for this. Hovered entities get emphasis; clicked entities get selection. Both states compose: a selected entity can also be hovered (getting both emphasis treatments).

---

## Chart Type Catalog

OWID supports these chart types, all from the same config-driven architecture:

| Type | Use case | Key feature |
|------|----------|-------------|
| Line | Time series for selected entities | Multi-entity comparison, log scale toggle |
| Scatter | Two-variable relationship | Connected scatter for time evolution, size encoding |
| Choropleth map | Geographic distribution | Globe view, region zoom, timeline scrubber |
| Stacked area | Composition over time | Absolute vs. relative toggle |
| Bar (discrete) | Single-time comparison | Sortable, horizontal or vertical |
| Stacked bar | Composition at a point | Category breakdown |
| Slope | Change between two time points | Start/end comparison |
| Marimekko | Two-dimensional composition | Width + height encoding |
| Dumbbell | Range or change display | Connector styles, trend colors |
| Table | Precise values | Sortable columns, summary stats, search |

For a civic data dashboard, the minimum viable set is: choropleth map, sortable table, and one chart type (bar or scatter). The linked selection model ties them together.

---

## Embed Pattern

OWID charts work both standalone (full page) and embedded (iframe in an article). The same component handles both; the container size determines the layout.

Embed URL structure: `https://ourworldindata.org/grapher/{slug}?{params}`. The URL is both the embed source and the shareable link.

For a civic project: if charts live inside a CMS-driven page (like a Gatsby article), render them as React components with config props. If they need to be embeddable elsewhere, add an iframe-friendly route that renders just the chart with URL-param-driven state.

---

## Key Takeaways for Civic Data Projects

1. **Config-driven charts**: define what to show in JSON; let the renderer handle how. New views require a config file, not new code.
2. **Fixed color breaks**: never quantile for explorers. The user needs stable color meaning across toggles.
3. **URL is state**: every view configuration is bookmarkable and shareable.
4. **Three-layer components**: state computation, interactive wrapper, pure SVG renderers.
5. **Linked selection store**: one shared state drives map + table + chart. Click anywhere, see everywhere.
6. **Consistent interaction grammar**: hover = details, click = select, toggle = change dimension. Same in every view.
7. **Responsive by default**: charts fill containers, adapt layout to size, never use fixed px.
8. **Tooltips are data, not decoration**: entity, value, unit, time. Nothing more.
