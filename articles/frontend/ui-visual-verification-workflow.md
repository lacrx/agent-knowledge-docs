---
title: UI Visual Verification Workflow
topics:
  - visual-verification
  - frontend
  - ui-testing
  - design-tokens
  - accessibility
  - screenshots
  - css-debugging
skills:
  - ui-visual-verification
summary: >
  Methodology for agent-driven visual UI verification using a tiered
  cheapest-first approach: a11y tree, computed styles, screenshots, pixel
  diffs, and video frame analysis. Covers the edit-verify-iterate loop,
  token-aware verification, bug classification taxonomy, and two-stage
  (localhost + production) verification.
aliases:
  - ui surgeon
  - visual testing
  - screenshot verification
  - css visual regression
  - ui verification loop
related:
  - cms-driven-data-visualization-gatsby
  - interactive-data-explorer-patterns
last-updated: 2026-11-03
---

# UI Visual Verification Workflow

## Overview

Agent-driven visual verification closes the feedback loop that GUI-less coding assistants normally lack. Instead of declaring a UI task done after editing CSS, the agent captures screenshots, measures computed styles, diffs against baselines, and iterates until measurable acceptance criteria pass. The result: UI bugs get caught before commit, not after deploy.

The core insight is that verification should be **tiered by cost**. An a11y tree query costs ~200 tokens. A computed style check costs ~100. A full-page screenshot costs ~3000. Video frame extraction can cost 15000+. By starting cheap and escalating only when needed, the agent stays fast on easy fixes and thorough on hard ones.

This methodology is framework-agnostic. The verification loop, bug taxonomy, and tiered approach work with any frontend stack (React, Vue, Svelte, Blazor, static HTML). Only the screenshot tooling and hot-reload behavior change between stacks.

## Verification Tiers

The tier model governs how the agent checks its work. Always start at the cheapest tier that can answer the question.

| Tier | Method | Token Cost | Use When |
|---|---|---|---|
| **T1** | A11y tree snapshot | ~200 | Element presence, text content, roles, enabled/disabled state |
| **T2** | Computed styles / bounding box / JS eval | ~100-500 | Colors, spacing, dimensions, flex/grid values, CSS custom properties |
| **T3** | Screenshot | ~2000-5000 | Layout, visual appearance, overflow, alignment |
| **T3+** | Pixel diff against baseline | ~500 | Before/after comparison, regression detection |
| **T4** | Video frame analysis | ~5000-15000 | Animations, transitions, flicker, page-load flash, scroll jank |

**T2 is the diagnostic workhorse.** Screenshots show _what_ is wrong. T2 tells you _why_. When a screenshot reveals a problem, always follow up with T2 (computed styles, bounding box, JS eval) to get the actual values before attempting a fix.

**T4 (video) is for temporal bugs only.** Flicker, animation timing, page-load flash, scroll jank. For layout, color, spacing, and responsive issues, screenshots are faster and cheaper. Every video recording must be followed by frame extraction (ffmpeg) since agents cannot play video files directly.

## Token-Aware Verification

When a project uses CSS custom properties (design tokens), verification should confirm that computed values trace back to tokens, not hardcoded values.

### Why It Matters

A `background-color: #1e293b` in a stylesheet might look correct today but breaks when the design system updates its dark surface color. The same background set as `var(--bg-surface)` stays correct through token changes. Token verification catches this drift at edit time.

### Three Token Checks

**T2-token (computed value match):** After an edit, query `getComputedStyle` on affected elements. Convert the returned `rgb()` to hex. Compare against the expected token's resolved value from the project's token manifest or CSS custom property definitions. Mismatch means a hardcoded value or wrong token.

**T2-contrast (WCAG compliance):** For any foreground/background token pair, compute the contrast ratio in the browser using the relative luminance formula. WCAG AA requires >= 4.5:1 for normal text, >= 3.0:1 for large text (>= 18px or >= 14px bold).

**T2-drift (sweep for hardcoded values):** Scan visible elements on the page, collect their computed background-color and color values, and compare each against the set of known token resolved values. Any hex that doesn't match any token is a potential hardcoded value. Exceptions: transparent, `color-mix()` tints, and browser defaults on unstyled elements.

### Adaptive Token Discovery

Not every project has a formal token manifest. The agent should detect what exists:

1. CSS custom properties in `theme.css`, `variables.css`, `_variables.scss`, or similar
2. Token definition files (`tokens.json`, `design-tokens.*`, `token-manifest.json`)
3. Tailwind config files (`tailwind.config.*`)
4. Design documentation (`DESIGN.md`, style guides, brand guidelines)

If custom properties exist, enforce them. If they don't, skip token verification and use screenshots only.

## Bug Classification Taxonomy

Before fixing a failing criterion, classify the bug. The classification determines the fix approach and prevents wasted iterations.

| Classification | Symptom | Fix Approach |
|---|---|---|
| **absent** | Element missing from a11y tree and DOM | Render logic / data issue, not CSS |
| **hidden** | In DOM but not visible (display:none, visibility, overflow, z-index) | CSS visibility |
| **misplaced** | Visible but wrong position or size | CSS layout (flex, grid, positioning) |
| **mis-styled** | Correct position, wrong appearance | CSS colors, fonts, borders, shadows |
| **selector-collision** | Correct rule exists but another rule wins | CSS specificity |
| **broken-responsive** | Passes one viewport, fails another | Media queries, container queries |
| **interaction-bug** | Static looks fine, interaction fails | Event handlers, state, transitions |
| **hardcoded-value** | Computed color doesn't match any token | Replace raw value with `var(--token)` |
| **wrong-layer** | Uses primitive token instead of semantic | Replace `var(--color-blue-500)` with `var(--accent-primary)` |
| **contrast-fail** | fg/bg pair doesn't meet WCAG AA ratio | Adjust token value or choose different semantic token |

Common CSS gotchas worth checking with T2:
- `:first-child` / `:last-child` collisions when an element is an only child (matches both)
- `flex` shorthand overriding `flex-grow` due to source order
- `overflow: hidden` on a parent clipping a child unexpectedly
- Computed `width` being constrained by a parent's `max-width` or flex basis

## Design Document Enforcement

If a project has a design document (DESIGN.md, style guide, brand guidelines), treat it as a hard constraint. A token can be technically correct but semantically wrong for the project's visual direction.

For example: a monochrome design system allows chromatic color only in data visualization. Using `var(--accent-primary)` on a card border is a valid token but violates the design direction. The agent should internalize the design doc before defining acceptance criteria.

## Two-Stage Verification

Localhost verification (the edit-verify-iterate loop) catches code bugs. Production verification catches deployment bugs. Both must pass.

**Localhost catches:** wrong CSS values, broken layout, missing elements, responsive failures, token drift, contrast violations.

**Production catches:** CDN cache staleness, CSS order differences between dev and prod builds, SSR hydration mismatches, real-data edge cases (text overflow with production-length content, empty states, pagination).

After CI deploys, verify on production by running the same T2 checks and taking screenshots at the same viewports. Any discrepancy between localhost and production is a deployment bug worth investigating before closing the task.

## Trade-offs: Tooling Choices

### Screenshot Tools

**agent-browser:** CLI tool for headless Chrome via CDP. Supports screenshots, a11y tree snapshots, computed style queries, JS eval, pixel diffs, viewport control, dark mode emulation, and video recording. Installed globally via npm. Best for: agent-driven workflows where the agent needs to see and measure the UI interactively.

**Playwright:** Browser automation library available in JS/TS, Python, Java, .NET. Built-in screenshot comparison with `toHaveScreenshot()`. Best for: CI pipelines, test suites, and .NET/Blazor projects where agent-browser isn't available.

**Puppeteer:** Lower-level Chrome DevTools Protocol library. Similar capabilities to agent-browser but requires more scaffolding. Best for: custom tooling and environments where agent-browser can't be installed.

The verification methodology works with any of these. Only the CLI syntax changes.

### Framework Considerations

**JS frameworks (React, Vue, Svelte, Astro):** Hot module replacement (HMR) is fast (sub-second). The agent can make frequent small edits and verify each. `sleep 2 && reload` is usually sufficient after an edit.

**Blazor/.NET:** Hot reload is slower (5-20s for Razor markup, sometimes requires full restart for C# changes). The agent should make fewer, more deliberate edits. CSS isolation via `.razor.css` scopes through `b-<hash>` attributes, which complicates specificity debugging. Component libraries (MudBlazor, Radzen, Fluent UI) inject their own themes that can override custom styles. The agent needs to detect the hosting model (Server, WASM, hybrid) and wait for framework readiness (SignalR circuit, WASM bootstrap) before capturing screenshots.

**Static site generators (Gatsby, Next.js, Astro static):** Full rebuilds may be required for some changes. Watch for compilation errors in the dev server output before taking screenshots.

## When Video Adds Value

Video (T4) is justified only for temporal bugs: behavior that exists across multiple frames and cannot be captured in a single screenshot. The cost is high (recording time + ffmpeg extraction + frame viewing), so never use it for static issues.

**Worth recording:** page navigation flash/flicker, CSS transition timing, skeleton loader behavior, scroll-triggered animations, lazy-load jank.

**Not worth recording:** margin change, color fix, responsive breakpoint, component presence/absence, font swap.

After recording, always extract frames with ffmpeg at an appropriate rate (60fps for flash detection, 10-15fps for scroll behavior, 5-10fps for general review). Use ImageMagick `compare` to find high-difference frames automatically, then view those frames to pinpoint the transition.

> **Skill:** For the step-by-step edit-verify-iterate loop using agent-browser, use the `ui-visual-verification` skill.

## References

- WCAG 2.1 Success Criterion 1.4.3 (Contrast Minimum): normal text >= 4.5:1, large text >= 3.0:1
- CSS Custom Properties (MDN): runtime theming via `var()` and `getComputedStyle`
- agent-browser: headless Chrome CLI for agent workflows (`npm install -g agent-browser`)
