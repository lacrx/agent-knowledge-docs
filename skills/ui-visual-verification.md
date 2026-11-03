---
name: ui-visual-verification
title: UI Visual Verification Loop
type: skill
topics:
  - visual-verification
  - frontend
  - ui-testing
  - design-tokens
  - accessibility
  - screenshots
  - css-debugging
summary: >
  Edit-verify-iterate loop for frontend UI changes using agent-browser.
  Tiered verification (a11y tree, computed styles, screenshots, pixel diffs,
  video) with adaptive design-token enforcement and two-stage verification
  (localhost + production).
references:
  - articles/frontend/ui-visual-verification-workflow.md
last-updated: 2026-11-03
---

# UI Visual Verification Loop

Agent-driven edit-verify-iterate loop for frontend UI changes. Uses agent-browser for headless screenshots, computed style queries, pixel diffs, and viewport testing. No UI task is done without visual proof.

---

## Prerequisites

- **agent-browser** installed globally:
  ```bash
  npm install -g agent-browser
  agent-browser install --with-deps
  ```
- Headless Linux environments need `--no-sandbox`:
  ```bash
  mkdir -p ~/.agent-browser
  echo '{"args": "--no-sandbox"}' > ~/.agent-browser/config.json
  ```
- A running dev server with realistic data (not mock/empty data)
- ffmpeg (only if video diagnostics are needed for temporal bugs)

## Steps

Every UI change follows this protocol. Steps are sequential. Do not write code until Step 3.

### Step 1: Environment Setup

Find or start the dev server:
```bash
for port in 3000 3001 4173 5173 5174 5175 8000 8001 8080 8888; do
  code=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:$port" 2>/dev/null)
  [ "$code" != "000" ] && echo "localhost:$port -> $code"
done
```

If not running, read `package.json` scripts for the dev command. Check for port conflicts (`ss -tlnp src :<port>`).

Match production data conditions. Check for env vars the project needs (`*_URL`, `*_API_KEY` in `.env*`, CI config, or `gh variable list`). Start the dev server with those vars set.

Set viewport immediately after opening:
```bash
agent-browser open http://localhost:<port>/<path>
agent-browser set viewport 1280 800
```

### Step 2: Load Design Context

Detect what design system infrastructure exists:
```bash
find . -maxdepth 4 -name "DESIGN.md" -o -name "design-tokens.*" -o -name "tokens.json" \
  -o -name "theme.css" -o -name "variables.css" -o -name "_variables.scss" \
  -o -name "tailwind.config.*" -o -name "token-manifest.json" 2>/dev/null | head -10
grep -roh -- '--[a-zA-Z][a-zA-Z0-9-]*' --include="*.css" 2>/dev/null | sort -u | wc -l
```

If a design doc exists (DESIGN.md, style guide, README with visual direction), read it. These are hard constraints.

If CSS custom properties or token files exist, note the token names and their resolved values. Style changes must use them. If a token manifest exists, load it for computed-value verification later.

If no design system exists, skip token verification in later steps.

### Step 3: Capture Baseline

Before defining criteria or writing code, capture the current state:
```bash
agent-browser screenshot --full /tmp/ui-surgeon-baseline-desktop.png
agent-browser snapshot -i > /tmp/ui-surgeon-baseline-snapshot.txt
```

For responsive work, also capture mobile:
```bash
agent-browser set viewport 375 812
agent-browser screenshot --full /tmp/ui-surgeon-baseline-mobile.png
```

For dark mode (if the project supports it):
```bash
agent-browser set media dark
agent-browser screenshot --full /tmp/ui-surgeon-baseline-dark.png
agent-browser set media light
```

Capture a production reference too, if the site is deployed:
```bash
agent-browser open https://<prod-url>/<path>
agent-browser screenshot --full /tmp/ui-surgeon-prod-reference.png
```

### Step 4: Define Acceptance Criteria

Decompose the task into measurable criteria. Each must be verifiable by a specific tier:

```
CRITERIA:
- [ ] T1: Nav contains "Dashboard" link with role=link
- [ ] T2: .hero background-color matches --bg-primary token
- [ ] T2: .card-grid has 3-column grid at 1280px
- [ ] T3: No horizontal overflow at 375px viewport
- [ ] T3: Dark mode shows no white-on-white text
```

**For any style change, add token criteria (if design tokens exist):**
```
TOKEN CRITERIA:
- [ ] T2-token: body background-color matches --bg-primary
- [ ] T2-contrast: --text-primary on --bg-primary >= 4.5:1
- [ ] T2-drift: no new hardcoded color values introduced
```

### Step 5: Make the Edit

Only now write code. After editing, wait for hot reload:
```bash
sleep 2
agent-browser reload
sleep 1
```

Static site generators may need a full rebuild. Watch for compilation errors in dev server output.

### Step 6: Verify (Cheapest Tier First)

**T2 first for layout/style changes** (screenshots might look "close enough" but hide broken values):
```bash
agent-browser eval "
  const el = document.querySelector('.target');
  const cs = getComputedStyle(el);
  JSON.stringify({
    display: cs.display, flex: cs.flex, width: cs.width,
    children: el.children.length,
    childWidths: Array.from(el.children).map(c => Math.round(c.getBoundingClientRect().width))
  });
"
```

**T2-token (if design tokens exist):**
```bash
agent-browser eval "
  function rgbToHex(rgb) {
    const m = rgb.match(/\\d+/g);
    if (!m) return rgb;
    return '#' + m.slice(0,3).map(n => (+n).toString(16).padStart(2,'0')).join('');
  }
  const el = document.querySelector('.target');
  const cs = getComputedStyle(el);
  JSON.stringify({
    backgroundColor: rgbToHex(cs.backgroundColor),
    color: rgbToHex(cs.color),
    padding: cs.padding
  });
"
```
Compare returned hex values against known token resolved values.

**T2-contrast:**
```bash
agent-browser eval "
  function luminance(r,g,b) {
    const [R,G,B] = [r,g,b].map(c => { c /= 255; return c <= 0.03928 ? c/12.92 : Math.pow((c+0.055)/1.055, 2.4); });
    return 0.2126*R + 0.7152*G + 0.0722*B;
  }
  function cr(fg,bg) {
    const l1 = luminance(...fg), l2 = luminance(...bg);
    return ((Math.max(l1,l2)+0.05) / (Math.min(l1,l2)+0.05)).toFixed(2);
  }
  const body = getComputedStyle(document.body);
  const bgRgb = body.backgroundColor.match(/\\d+/g).map(Number);
  const fgRgb = body.color.match(/\\d+/g).map(Number);
  JSON.stringify({ contrast: cr(fgRgb, bgRgb), fg: body.color, bg: body.backgroundColor });
"
```
AA pass: >= 4.5 normal text, >= 3.0 large text (>= 18px or >= 14px bold).

**T1 structural check:**
```bash
agent-browser snapshot -i
```

**T3 visual check (after T2 confirms values):**
```bash
agent-browser screenshot --full /tmp/ui-surgeon-current.png
```

**T3+ diff against baseline:**
```bash
agent-browser diff screenshot --baseline /tmp/ui-surgeon-baseline-desktop.png --threshold 0.1
```

**T2-drift sweep (if design tokens exist):**
```bash
agent-browser eval "
  function rgbToHex(rgb) {
    const m = rgb.match(/\\d+/g);
    if (!m) return rgb;
    return '#' + m.slice(0,3).map(n => (+n).toString(16).padStart(2,'0')).join('');
  }
  const els = document.querySelectorAll('body *:not(script):not(style):not(svg):not(path)');
  const seen = new Set(); const issues = [];
  for (const el of Array.from(els).slice(0, 200)) {
    const cs = getComputedStyle(el);
    const bg = cs.backgroundColor;
    if (bg !== 'rgba(0, 0, 0, 0)' && bg !== 'transparent') {
      const hex = rgbToHex(bg);
      const key = el.tagName + ':bg:' + hex;
      if (!seen.has(key)) { seen.add(key); issues.push({ tag: el.tagName, prop: 'background-color', hex }); }
    }
  }
  JSON.stringify(issues.slice(0, 30));
"
```
Compare each hex against known token values. Unmatched hex = potential hardcoded value.

### Step 7: Classify and Diagnose

For any failing criterion, diagnose with T2 before fixing:
```bash
agent-browser get styles ".element"
agent-browser get box ".element"
agent-browser eval "document.querySelectorAll('.element').length"
```

Classify the bug:

| Classification | Symptom | Fix Approach |
|---|---|---|
| absent | Missing from DOM | Render logic, not CSS |
| hidden | In DOM, not visible | CSS display/visibility/overflow |
| misplaced | Wrong position/size | CSS layout (flex, grid) |
| mis-styled | Wrong appearance | CSS colors, fonts, borders |
| selector-collision | Another rule wins | CSS specificity |
| broken-responsive | Fails at other viewport | Media queries |
| hardcoded-value | Computed color unmatched | Replace with `var(--token)` |
| contrast-fail | Ratio below WCAG AA | Adjust token or choose different one |

### Step 8: Iterate or Complete

- All criteria pass: proceed to Step 9
- Some fail: diagnose (Step 7), fix, return to Step 5
- Same issue twice on same criterion: **stop and ask the user**, including T2 diagnostics
- Max 5 total iterations

Track state:
```
ITERATION 2/5:
- [x] T1: Nav element present
- [x] T2: background-color correct
- [ ] T2: grid columns -- FAIL (flex: 0 0 150px, expected flex: 1)
      Classification: selector-collision
      Fix: scope selector with :not(:first-child)
- [x] T3: No horizontal overflow
```

### Step 9: Final Verification

Run full verification across viewports:
```bash
agent-browser set viewport 1280 800
agent-browser screenshot --full /tmp/ui-surgeon-final-desktop.png
agent-browser diff screenshot --baseline /tmp/ui-surgeon-baseline-desktop.png

agent-browser set viewport 375 812
agent-browser screenshot --full /tmp/ui-surgeon-final-mobile.png

agent-browser diff snapshot --baseline /tmp/ui-surgeon-baseline-snapshot.txt
```

If the project has multiple themes/sites using shared components, verify token resolution for each theme. The same semantic tokens should resolve to different values per theme.

### Step 10: Ship and Verify Production

Commit and push. Watch CI:
```bash
gh run list --limit 1
gh run watch <run-id> --exit-status
```

After deploy, verify on production (catches CDN cache, SSR mismatches, real-data edge cases):
```bash
agent-browser open https://<prod-url>/<path>
agent-browser set viewport 1280 800
```

Run the same T2 checks from Step 6 against production. Any discrepancy vs localhost is a deployment bug. Common causes: stale CDN cache, CSS order difference in prod build, SSR hydration mismatch.

### Step 11: Clean Up

Only after production verification passes:
```bash
agent-browser close
rm -f /tmp/ui-surgeon-*.png /tmp/ui-surgeon-*.webm
rm -rf /tmp/ui-surgeon-frames-*
```

Leave nothing behind in `/tmp/`.

## Constraints

| Constraint | Rationale |
|---|---|
| Never declare done without visual proof | "I changed the CSS" is not done; a passing screenshot at a known viewport is done |
| Baseline before edit, always | Cannot measure change without a reference point |
| T2 diagnose before fixing | Screenshots show symptoms; computed styles show causes |
| Classify before fixing | A missing element is not a CSS problem; a specificity collision is not a layout problem |
| Explicit viewports on every screenshot | Unknown viewport size makes screenshots unreproducible |
| Stuck twice = stop and ask | Same issue twice means ask the user, not try a third variation |
| Responsive by default for layout changes | Minimum: desktop (1280x800) and mobile (375x812) |
| Video only for temporal bugs | Flicker, animation, scroll jank. Screenshots for everything else |
| Token enforcement if tokens exist | If the project has design tokens, computed values must trace back to them |
| Design doc is law if one exists | Token can be technically correct but semantically wrong for the project's visual direction |
| Two-stage verification | Localhost catches code bugs; production catches deployment bugs |
| Clean up after confirmed deploy | Remove all `/tmp/ui-surgeon-*` artifacts after production verification passes |

## Outputs

- Verified UI change passing all acceptance criteria at specified viewports
- Screenshot proof at desktop and mobile (minimum)
- Token compliance confirmation (if design tokens exist)
- WCAG contrast verification for affected fg/bg pairs
- Production verification confirming deployment matches localhost
- Clean `/tmp/` with no leftover artifacts
