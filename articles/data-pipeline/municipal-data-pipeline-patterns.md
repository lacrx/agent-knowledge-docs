---
title: Municipal Data Pipeline Patterns
topics:
  - python
  - data-pipeline
  - municipal-data
  - geospatial
  - civic-tech
  - jsonl
skills:
  - build-municipal-data-pipeline
summary: >
  Patterns for building reliable data pipelines that ingest municipal source data
  (permits, housing reports, meeting records, fiscal documents), cross-reference
  across sources, enrich with geographic boundaries, and output static JSON for
  frontend consumption. Covers source validation, regression guards, geocoding,
  point-in-polygon assignment, content hashing for incremental updates, and
  anti-hallucination constraints when LLMs participate in extraction.
aliases:
  - municipal data pipeline
  - civic data pipeline
  - permit data import
  - housing data pipeline
  - etrakit pipeline
  - apr data pipeline
  - jsonl to json pipeline
related:
  - cms-driven-data-visualization-gatsby
  - interactive-choropleth-dashboard
last-updated: 2026-10-23
---

# Municipal Data Pipeline Patterns

## Overview

Municipal data comes from many sources in many formats: permit systems (JSONL from web scrapers), state housing reports (CSV from HCD), meeting records (structured JSON from transcription pipelines), fiscal documents (PDF to JSON via LLM extraction), and geographic boundaries (GeoJSON from planning departments). A dashboard or analysis tool needs these cross-referenced, enriched, and unified into static JSON that a frontend can consume without a runtime API.

This article describes patterns that have proven reliable across multiple municipal data projects. The core principle: the pipeline should be deterministic, auditable, and defensive. Deterministic means the same inputs produce the same outputs. Auditable means every claim traces to a source record. Defensive means the pipeline refuses to produce bad output rather than silently degrading.

> **Skill:** For step-by-step scaffolding, use the `build-municipal-data-pipeline` skill.

---

## Pipeline Architecture

### The Shape

```
Source A (JSONL)  ─┐
Source B (CSV)    ─┤──→  Python importer  ──→  static JSON  ──→  Frontend / Analysis
Source C (GeoJSON)─┤      (cross-reference,     (committed to     (Gatsby, Vite,
Source D (JSON)   ─┘       enrich, validate)      repo or S3)      or Python scripts)
```

Importers are standalone Python scripts, not framework-dependent modules. Each reads its sources, transforms and cross-references, validates output, and writes static JSON. They run locally, in CI, or on a schedule. The output JSON is either committed to the frontend repo or deployed to static hosting.

### File Conventions

Source data:
```
data/
  permits/etrakit-projects-{year}.jsonl    # one JSON object per line
  permits/etrakit-permits-{year}.jsonl
  hcd-apr-tablea.csv                        # state housing report
  reference/hcd-apr-{jurisdiction}.json     # enriched reference extract
  structured/all-records.jsonl              # meeting records
  d-district-zoning.geojson                 # geographic boundaries
```

Output data:
```
dashboard/data/
  production.json       # unit counts by geography and year
  officials.json        # vote scores and grades
  pipeline.json         # pending applications
  metadata.json         # data vintage, record counts, methodology notes
```

---

## Source Validation

### Schema Checks on Ingest

Every source record should be validated at read time. Don't trust upstream data to be stable.

```python
REQUIRED_FIELDS = {"project_no", "type", "applied", "address"}

def validate_etrakit_record(record: dict, file_path: str, line_num: int) -> bool:
    missing = REQUIRED_FIELDS - record.keys()
    if missing:
        log.warning(f"{file_path}:{line_num} missing fields: {missing}")
        return False
    return True
```

Log warnings with file and line number so problems trace back to source. Never silently drop records; count them and report the drop rate.

### Regression Guard

Before overwriting output, compare against the existing file. If the new output is substantially smaller, refuse to write and exit with a nonzero code:

```python
def regression_check(new_data: dict, existing_path: Path, floor: float = 0.9):
    if not existing_path.exists():
        return True
    existing = json.loads(existing_path.read_text())
    new_count = count_records(new_data)
    old_count = count_records(existing)
    if old_count > 0 and new_count / old_count < floor:
        raise RuntimeError(
            f"Regression: {new_count} records vs {old_count} previously "
            f"({new_count/old_count:.0%}). Refusing to overwrite. "
            f"Delete {existing_path} manually to force."
        )
```

This catches: upstream API changes that silently drop data, filter bugs that exclude valid records, schema changes that break parsing. The 90% floor is a starting point; adjust per source based on expected volatility.

### Data Vintage Metadata

Every output file should include metadata about when it was built and from what:

```python
meta = {
    "source": "Oceanside etrakit + HCD APR Table A",
    "built": datetime.now(UTC).isoformat(),
    "records": len(records),
    "year_range": [min_year, max_year],
    "source_files": [str(p) for p in source_paths],
    "drop_rate": dropped / total if total > 0 else 0,
    "methodology": "Discretionary projects from etrakit; unit counts from APR"
}
```

Frontends should display data vintage prominently. Users need to know how fresh the data is.

---

## Cross-Referencing Sources

Municipal data about the same project often lives in multiple systems with different identifiers. Cross-referencing is the highest-value transformation in the pipeline.

### Matching Strategies (in priority order)

1. **Tracking ID match.** APR records include `jurs_tracking_id` which may match etrakit `project_no`. Direct join.

2. **APN match.** Assessor's parcel number is stable across systems. Match on APN when tracking IDs differ or are missing.

3. **Address normalization + fuzzy match.** Addresses vary wildly across systems ("3950 N RIVER RD" vs "3950 North River Road"). Normalize: uppercase, strip directional abbreviations, standardize street types. Then fuzzy match with a threshold.

4. **Spatial proximity.** When geocoded, projects within a distance threshold at the same APN or address are likely the same project. Use shapely for point distance.

Tag each match with its method so downstream consumers know confidence level:

```python
record["match_method"] = "tracking_id"  # or "apn", "address", "spatial", "manual"
```

### Deduplication

The same project appears in multiple source systems. Establish a priority order for which source's fields win:

```python
FIELD_PRIORITY = {
    "applied_date": ["etrakit", "apr"],       # etrakit has exact filing date
    "unit_count": ["apr", "etrakit"],          # APR has official unit counts
    "income_breakdown": ["apr"],               # only source for income tiers
    "project_status": ["etrakit"],             # etrakit has latest status
    "coordinates": ["apr", "geocoder"],        # APR geocoding is official
}
```

---

## Geographic Enrichment

### Point-in-Polygon Assignment

Assign each record to a geographic unit (council district, planning area, downtown zone) using shapely:

```python
from shapely.geometry import shape, Point
from shapely.strtree import STRtree
import json

def load_boundaries(geojson_path: Path) -> list[tuple]:
    with open(geojson_path) as f:
        fc = json.load(f)
    return [
        (shape(feat["geometry"]), feat["properties"])
        for feat in fc["features"]
    ]

def build_spatial_index(boundaries):
    geoms = [b[0] for b in boundaries]
    tree = STRtree(geoms)
    return tree, boundaries

def assign_geography(lat: float, lon: float, tree, boundaries) -> dict | None:
    point = Point(lon, lat)
    idx = tree.query(point, predicate="contains")
    if len(idx) > 0:
        return boundaries[idx[0]][1]
    return None
```

Use an STRtree spatial index, not a naive loop. For 1,700 records against 36 polygons it barely matters, but for 384K APR rows against census tracts it does.

### Census Tract to Political District

Census data (income, demographics) comes at the tract level. To aggregate to political districts:

1. Load tract geometries and compute centroids (reproject to a local coordinate system for accuracy; EPSG:2230 for San Diego County, feet)
2. Spatially join tract centroids to district boundaries
3. Aggregate with household-weighted averages, not simple means:

```python
def weighted_average(tracts: list[dict], value_field: str, weight_field: str) -> float:
    total_weight = sum(t[weight_field] for t in tracts if t[value_field] is not None)
    if total_weight == 0:
        return None
    return sum(
        t[value_field] * t[weight_field]
        for t in tracts
        if t[value_field] is not None
    ) / total_weight
```

Centroid-based assignment is a simplification (a tract that straddles two districts gets assigned entirely to one). This works well for small tracts. For large tracts in sparse areas, area-weighted interpolation is more accurate but rarely worth the complexity for city-level analysis.

---

## RHNA Pace Tracking

In California, every jurisdiction has a Regional Housing Needs Allocation (RHNA) target: a state-mandated number of housing units to permit during each 8-year planning cycle, broken down by income tier. Tracking pace against this target is the single most powerful advocacy metric.

### Pace Calculation

```python
def rhna_pace(permitted: int, target: int, years_elapsed: float, cycle_years: float = 8.0) -> dict:
    rate = permitted / max(years_elapsed, 0.5)
    projected = rate * cycle_years
    shortfall = max(0, target - projected)
    return {
        "permitted": permitted,
        "target": target,
        "pct_complete": permitted / target if target > 0 else None,
        "annual_rate": rate,
        "projected_at_pace": round(projected),
        "shortfall": round(shortfall),
        "on_track": projected >= target
    }
```

### Income Tier Breakdown

RHNA targets and APR data both break down by income category. Track each tier separately because cities commonly overproduce above-moderate housing while underproducing very-low and low-income. Showing this gap per tier is more actionable than a single aggregate number.

APR income fields map to RHNA tiers:
- Very low income: `acutely_low_income_*` + `extremely_low_income_*` + `vlow_income_*`
- Low income: `low_income_*`
- Moderate income: `mod_income_*`
- Above moderate: `above_mod_income`

The `_dr` (deed restricted) and `_ndr` (non-deed-restricted) suffixes distinguish permanent affordability from transient affordability. For RHNA counting, both count, but the distinction matters for policy analysis.

### Partial-Year Normalization

When the current year is incomplete, raw counts understate production. Normalize by the fraction of the year elapsed:

```python
from datetime import date

def annualize_partial_year(count: int, as_of: date) -> float:
    day_of_year = as_of.timetuple().tm_yday
    fraction = day_of_year / 365
    return count / fraction if fraction > 0.25 else count
```

Only annualize if at least a quarter has passed; earlier than that, the extrapolation is too noisy. Label partial-year data clearly in output metadata.

---

## Deduplication Audit Trail

When cross-referencing records across sources, maintain a persistent ledger documenting every dedup decision:

```python
def log_dedup_decision(ledger: list, record_a: dict, record_b: dict, action: str, reason: str):
    ledger.append({
        "record_a_id": record_a.get("id"),
        "record_b_id": record_b.get("id"),
        "action": action,      # "merged", "kept_both", "dropped_b"
        "reason": reason,       # "same APN within 2 years", "address mismatch"
        "match_method": record_a.get("match_method"),
        "timestamp": datetime.now(UTC).isoformat()
    })
```

Write the ledger alongside the output data. This makes the pipeline auditable by third parties (journalists, other advocacy orgs, city staff) and lets you debug false merges or missed matches without re-running the entire pipeline.

The `yimby/cfhe-data` project (Campaign for Fair Housing Elements) maintains this kind of ledger for statewide APR deduplication across 539 jurisdictions. Their pattern: block on jurisdiction + permit date + tracking ID, link across years via address and APN, document every removal rule in an audit summary JSON.

---

## Content Hashing for Incremental Updates

When the pipeline feeds LLM-based analysis (profile generation, summaries), re-running unchanged inputs wastes time and money. Hash the input data and skip processing when the hash matches:

```python
import hashlib

def content_hash(records: list[dict]) -> str:
    canonical = json.dumps(records, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]

def should_reprocess(records, cache_path: Path) -> bool:
    current_hash = content_hash(records)
    if cache_path.exists():
        cached = json.loads(cache_path.read_text())
        if cached.get("input_hash") == current_hash:
            return False
    return True
```

Store the hash alongside the output so the next run can compare.

---

## LLM Integration Constraints

When LLMs participate in the pipeline (extracting structured data from PDFs, generating summaries, scoring records), hard constraints prevent hallucination from compounding through the pipeline.

### Anti-Hallucination Rules

These go in every LLM system prompt that touches source data:

1. **Never invent names.** Only name individuals who appear by name in source data. If a vote record lacks individual names, say "individual votes not documented."
2. **Never invent events.** Every claim must trace to a source record.
3. **Never fill gaps with plausible guesses.** A thin record produces a thin profile with a caveat, not a complete-sounding profile with fabricated detail.

### Structured Output Schema

Force LLM output through a JSON schema so validation catches drift:

```python
SCORE_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string"},
        "score": {"type": "integer", "minimum": -2, "maximum": 2},
        "rationale": {"type": "string"},
        "source_record_id": {"type": "string"}
    },
    "required": ["action", "score", "rationale", "source_record_id"]
}
```

The `source_record_id` field is critical: it forces the LLM to cite which record supports the score. Downstream validation can verify the citation exists.

### Two LLM Modes

Support both subscription CLI (`claude -p`) and API (`anthropic` SDK) modes:
- CLI mode: $0 marginal cost, good for development and iteration
- API mode: costs money, better for batch runs and CI

Both modes should receive identical system context (knowledge articles, scoring rubrics, anti-hallucination constraints). The mode switch should only change the transport, not the prompt.

---

## Output JSON Design

### Nested Geography-Year Tables

For data that varies by geography and year, use the Chicago tracker's proven shape:

```json
{
  "units": {
    "district_1": { "2020": 45, "2021": 62, "2022": 38 },
    "district_2": { "2020": 12, "2021": 18, "2022": 23 }
  }
}
```

String keys (not integer) for both geography and year. This makes JavaScript property access clean (`data.units[district][year]`) and survives JSON round-trips without type confusion.

### Project-Level Detail

For individual project records (needed for dot maps, detail views, search):

```json
{
  "projects": {
    "district_1": [
      { "id": "RD22-00045", "d": "2022-03-15", "u": 120, "a": "300 N Coast Hwy", "t": "5+", "s": "approved" }
    ]
  }
}
```

Short field names (`d`, `u`, `a`, `t`, `s`) reduce JSON size when there are thousands of records. Document the mapping in metadata.

### Metadata Block

Every output file starts with a `meta` object:

```json
{
  "meta": {
    "source": "HCD APR Table A + Oceanside etrakit",
    "jurisdiction": "Oceanside",
    "built": "2026-10-23T19:00:00Z",
    "records": 1710,
    "yearRange": [2018, 2025],
    "dropRate": 0.02,
    "methodology": "Unit counts from APR; filing dates from etrakit; geographic assignment via d-district-zoning.geojson point-in-polygon"
  }
}
```

---

## When to Use This Pattern

**Good fit:**
- City-level housing, permit, fiscal, or voting data from 2+ sources
- Datasets under 500K records (above that, consider a database layer)
- Static output consumed by a frontend or analysis scripts
- Data that updates on a schedule (monthly, quarterly), not real-time

**Poor fit:**
- Real-time data streams (use a database and API)
- Single-source data that needs no cross-referencing (just load it directly)
- Data that requires interactive cleaning (use a notebook or spreadsheet first)
