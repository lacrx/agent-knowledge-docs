---
name: blazor-ui-verification
title: Blazor UI Visual Verification Loop
type: skill
topics:
  - visual-verification
  - blazor
  - dotnet
  - ui-testing
  - playwright
  - design-tokens
  - css-debugging
summary: >
  Edit-verify-iterate loop for Blazor/.NET UI changes using a Playwright-based
  UiVerify CLI tool. Bootstraps the screenshot tool on first use per project.
  Handles Blazor-specific concerns: hot reload limits, CSS isolation scoping,
  component library theme overrides, and render mode detection.
references:
  - articles/frontend/ui-visual-verification-workflow.md
last-updated: 2026-11-03
---

# Blazor UI Visual Verification Loop

Agent-driven edit-verify-iterate loop for Blazor/.NET UI changes. Uses a Playwright-based UiVerify console app for headless screenshots, pixel diffs, and viewport testing. Bootstraps the tool on first use per project. No UI task is done without visual proof.

---

## Prerequisites

- .NET SDK (6.0+)
- A Blazor project (Server, WASM, or hybrid/auto)
- The `UiVerify` console app in the solution (bootstrapped in Step 1 if missing)

## Steps

### Step 1: Bootstrap UiVerify (One-Time Per Project)

Check if UiVerify already exists:
```bash
find . -maxdepth 2 -name "UiVerify.csproj" -o -name "*.UiVerify.csproj" 2>/dev/null
```

If missing, create it:
```bash
dotnet new console -n UiVerify
dotnet sln add UiVerify/UiVerify.csproj
cd UiVerify
dotnet add package Microsoft.Playwright
dotnet build
```

Install the browser:
```bash
# Windows
pwsh bin/Debug/net*/playwright.ps1 install chromium
# Linux/macOS
dotnet tool run playwright install chromium --with-deps
```

Write a single `Program.cs` (under 300 lines) implementing three commands:

**`screenshot <url> <output.png> [--width 1280] [--height 800] [--full-page] [--wait-for-blazor]`**
- Headless Chromium, navigates to URL
- `--wait-for-blazor` (default true): polls for `window.Blazor` (15s timeout), waits for `#blazor-error-ui` hidden, `[aria-busy]` cleared, network idle, then 500ms settle
- Sets viewport, captures screenshot, saves to path
- Stdout: file path and dimensions. Exit 0 success, 1 failure.

**`diff <baseline.png> <current.png> <diff.png> [--threshold 0.01]`**
- Pixel comparison using SkiaSharp or System.Drawing
- Generates red-highlighted diff image
- Stdout: "PASS: 0.00% changed" or "FAIL: X.XX% changed". Exit 0 under threshold, 1 over.

**`baseline <url> <output-dir> [--viewports desktop,tablet,mobile] [--dark]`**
- desktop: 1280x800, tablet: 768x1024, mobile: 375x812
- Saves as `<dir>/desktop.png`, `<dir>/tablet.png`, `<dir>/mobile.png`
- `--dark`: also captures with `prefers-color-scheme: dark` as `*-dark.png`

All output machine-parseable. No interactive prompts. No color codes.

After writing Program.cs, build and test:
```bash
dotnet build UiVerify/UiVerify.csproj
dotnet run --project UiVerify -- screenshot <app-url> /tmp/test.png
```

Add `.ui-baselines/` to `.gitignore`.

### Step 2: Environment Setup

Detect the project:
```bash
find . -maxdepth 3 -name "*.sln" -o -name "*.csproj" | head -20
grep -r "BlazorWebAssembly\|Sdk=\"Microsoft.NET.Sdk.Web\"\|Blazor" --include="*.csproj" 2>/dev/null | head -5
grep -r "InteractiveServer\|InteractiveWebAssembly\|InteractiveAuto" --include="*.razor" --include="*.cs" -l 2>/dev/null | head -5
grep -r "MudBlazor\|Radzen\|FluentUI\|Syncfusion\|Telerik" --include="*.csproj" 2>/dev/null
```

Find or start the dev server:
```bash
for port in 5000 5001 5002 5173 7000 7001 7100 7200 8080; do
  code=$(curl -sk -o /dev/null -w "%{http_code}" "https://localhost:$port" 2>/dev/null)
  [ "$code" != "000" ] && echo "https://localhost:$port -> $code"
  code=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:$port" 2>/dev/null)
  [ "$code" != "000" ] && echo "http://localhost:$port -> $code"
done
```

If not running:
```bash
find . -name "launchSettings.json" -path "*/Properties/*" | head -5
# Read it for the port, then:
dotnet watch --project <main-project> run
```

### Step 3: Load Design Context

Detect token/design system infrastructure:
```bash
grep -roh -- '--[a-zA-Z][a-zA-Z0-9-]*' --include="*.css" 2>/dev/null | sort -u | wc -l
find . -maxdepth 4 -name "tokens.json" -o -name "design-tokens.*" -o -name "theme.css" \
  -o -name "variables.css" -o -name "_variables.scss" 2>/dev/null | head -5
```

If CSS custom properties exist, note them. Style changes should use them. If a design doc exists (DESIGN.md, style guide), read it as hard constraints. If nothing exists, skip token verification later.

### Step 4: Capture Baseline

Before editing:
```bash
dotnet run --project UiVerify -- baseline <app-url>/<path> .ui-baselines/<task-name>
```

Read the desktop.png to see current state.

### Step 5: Define Acceptance Criteria

Measurable checklist. Each verifiable by screenshot diff or UiVerify output:
```
CRITERIA:
- [ ] Button visible at mobile (375px)
- [ ] No horizontal overflow at any viewport
- [ ] Background color matches CSS custom property
- [ ] Layout: 3 columns desktop, 1 column mobile
```

If design tokens exist, add token criteria:
```
TOKEN CRITERIA:
- [ ] T2-token: body background-color matches --bg-primary
- [ ] T2-contrast: text on background >= 4.5:1
- [ ] T2-drift: no new hardcoded color values
```

### Step 6: Make the Edit

Write code. Then wait for hot reload:
```bash
sleep 5
```

**Blazor hot reload limits:**
- Razor markup: usually works (5-20s)
- Scoped CSS (.razor.css): usually works, can be flaky
- C# code-behind: sometimes works, sometimes needs restart
- New files / Program.cs changes: needs restart
- Silent failure (UI unchanged after edit): full browser reload needed

If hot reload fails twice, restart `dotnet watch`.

### Step 7: Verify

Screenshot and diff:
```bash
dotnet run --project UiVerify -- screenshot <app-url>/<path> .ui-baselines/<task-name>/current.png
dotnet run --project UiVerify -- diff .ui-baselines/<task-name>/desktop.png .ui-baselines/<task-name>/current.png .ui-baselines/<task-name>/diff.png
```

Read the diff output. PASS = under threshold. FAIL = check diff percentage and read the diff image.

For responsive check:
```bash
dotnet run --project UiVerify -- screenshot <app-url>/<path> .ui-baselines/<task-name>/current-mobile.png --width 375 --height 812
```

### Step 8: Classify and Diagnose

Diagnose before fixing:

| Classification | Symptom | Fix Approach |
|---|---|---|
| absent | Missing from DOM | Render logic, data binding, `@if` |
| hidden | In DOM, not visible | CSS display/visibility, overflow |
| misplaced | Wrong position/size | CSS layout, flex, grid |
| mis-styled | Wrong appearance | CSS properties, theme |
| selector-collision | Rule loses | Specificity, `::deep`, isolation |
| hot-reload-stale | Code correct, UI old | Reload/restart dotnet watch |
| render-mode-mismatch | One mode only | SSR vs interactive |

**Blazor-specific diagnostics:**
- CSS isolation: `.razor.css` scopes via `b-<hash>` attribute. Check rendered HTML for the attribute.
- `::deep`: penetrates one level only.
- Component library themes override your styles (MudBlazor `.mud-*`, Radzen `.rz-*`, Fluent `::part()`).
- Blazor re-renders reset JS-interop DOM state.
- Prerender can flash before interactive mode activates.

### Step 9: Iterate or Complete

- All criteria pass: proceed to Step 10
- Some fail: classify, fix, return to Step 6
- Same issue twice: **stop and report T2 diagnostics, ask user**
- Max 5 total iterations

### Step 10: Final Verification

```bash
dotnet run --project UiVerify -- baseline <app-url>/<path> .ui-baselines/<task-name>/final --viewports desktop,tablet,mobile
dotnet run --project UiVerify -- diff .ui-baselines/<task-name>/desktop.png .ui-baselines/<task-name>/final/desktop.png .ui-baselines/<task-name>/diff-desktop.png
dotnet run --project UiVerify -- diff .ui-baselines/<task-name>/mobile.png .ui-baselines/<task-name>/final/mobile.png .ui-baselines/<task-name>/diff-mobile.png
```

Report: what changed, diff percentage per viewport, any regressions.

### Step 11: Clean Up

```bash
rm -rf .ui-baselines/<task-name>
```

## Constraints

| Constraint | Rationale |
|---|---|
| Never declare done without a passing screenshot | Visual proof is the acceptance criterion |
| Baseline before edit, always | Cannot measure change without a reference |
| Diagnose before fixing (classify first) | Wrong classification wastes iterations |
| Fewer, larger edits | Hot reload is expensive in Blazor; minimize round trips |
| Max 5 iterations, stuck twice = ask user | Prevents infinite loops on hard problems |
| All screenshots at explicit viewport sizes | Unknown viewport makes results unreproducible |
| If dotnet watch fails twice, restart it | Silent hot-reload failure is common in Blazor |
| Adapt to project | Detect tokens, component libs, hosting model. Use what exists, skip what doesn't |
| Video is for temporal bugs only | Flicker, animation. Screenshots for everything else |

## Outputs

- Verified UI change passing all acceptance criteria at specified viewports
- Screenshot proof at desktop and mobile (minimum)
- Diff images showing before/after changes with percentage
- Token compliance confirmation (if design tokens exist)
- UiVerify console app bootstrapped in the solution (first use only)
- Clean `.ui-baselines/` with no leftover task artifacts
