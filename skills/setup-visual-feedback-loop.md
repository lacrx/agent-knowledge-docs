---
name: setup-visual-feedback-loop
topics:
  - frontend
  - playwright
  - browser-automation
  - mcp
  - visual-testing
  - ai-development
summary: >
  Set up Playwright MCP and Playwriter for visual browser feedback in a frontend
  project, including MCP server config, Claude Code skill, and permission settings.
references:
  - articles/frontend/visual-feedback-loop-for-agents.md
last-updated: 2026-10-23
---

# Set Up Visual Browser Feedback Loop

Executable steps for adding browser-based visual verification to a Claude Code project. Follow in order.

---

## Prerequisites

- Google Chrome installed
- Node.js / npm / npx available
- Claude Code project with a `.claude/` directory
- A frontend dev server (Gatsby, Next.js, Vite, or any framework with `localhost` dev mode)

## Steps

### Step 1: Create MCP server configuration

Create `.claude/mcp.json` at the project root (or merge into existing):

```json
{
  "mcpServers": {
    "playwright": {
      "command": "npx",
      "args": [
        "@playwright/mcp@latest",
        "--headless",
        "--browser", "chrome",
        "--caps", "vision",
        "--block-service-workers",
        "--viewport-size", "1280x720"
      ]
    },
    "playwriter": {
      "command": "npx",
      "args": ["playwriter@latest"],
      "env": {
        "PLAYWRITER_DIRECT": "1"
      }
    }
  }
}
```

If `.claude/mcp.json` already exists, merge the `playwright` and `playwriter` keys into the existing `mcpServers` object.

### Step 2: Create the visual verification skill

Create the directory and skill file:

```bash
mkdir -p .claude/skills/visual-verify
```

Write `.claude/skills/visual-verify/SKILL.md`:

````markdown
---
description: >
  Verify frontend changes visually using browser MCP tools. Use this workflow
  after modifying JSX, CSS, layout components, or responsive behavior.
alwaysApply: false
---

# Visual Verification Workflow

## When to use

Invoke this workflow after any change to:
- JSX/TSX component markup or structure
- CSS, SCSS, or styled-components
- Layout components, grid, or flexbox
- Responsive breakpoints or media queries
- Image, icon, or SVG assets
- Animation or transition properties

Skip for: pure data transforms, API routes, utility functions, type-only changes, test files.

## Dev server

Before navigating, confirm the dev server is running:

```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000
```

If not running, start it:

```bash
# Gatsby
npx gatsby develop &

# Next.js
npx next dev &

# Vite
npx vite &
```

Wait for the server to respond before proceeding.

## Verification steps

1. **Navigate** to the affected page using `browser_navigate`. Target the specific route.
2. **DOM snapshot** first using `browser_snapshot`. Confirm elements exist, text is correct, structure matches expectations. This is cheap (200-500 tokens).
3. **Screenshot** only if visual properties matter (spacing, color, alignment, animation). Use `browser_screenshot`. This costs 1000-1500 tokens per image.
4. **Evaluate** the result. If issues are found, fix the code, wait for HMR, and re-check.
5. **Responsive test** only when the change involves breakpoint-sensitive code. Resize to 375px, 768px, and 1280px using `browser_resize`.

## Token budget

- Maximum 4-5 screenshots per task
- Prefer snapshots over screenshots for structural checks
- Batch 2-3 CSS changes before re-screenshotting
- Never screenshot pages unrelated to your change

## Framework timing

Wait after file save before screenshotting:
- **Gatsby:** 5 seconds (slow HMR, webpack recompilation)
- **Next.js:** 1-3 seconds (Fast Refresh)
- **Vite:** under 1 second for components, 2-3 seconds for config changes

If a snapshot shows "compiling" or stale content, wait and retry. If the change still does not appear after 10 seconds, navigate to the URL again for a full reload.

## WebGL and maps

Pages with MapLibre, deck.gl, or other WebGL content need extra time in headless mode. Wait 5-10 seconds after page load for GPU layers to composite. Poster frames will appear if you screenshot too early.
````

### Step 3: Update permission settings

Add MCP tool permissions to `.claude/settings.local.json` so the agent can use browser tools without interactive approval:

```json
{
  "permissions": {
    "allow": [
      "mcp__playwright__browser_navigate",
      "mcp__playwright__browser_snapshot",
      "mcp__playwright__browser_screenshot",
      "mcp__playwright__browser_click",
      "mcp__playwright__browser_type",
      "mcp__playwright__browser_resize",
      "mcp__playwright__browser_wait",
      "mcp__playwright__browser_close",
      "mcp__playwriter__execute"
    ]
  }
}
```

If `.claude/settings.local.json` already exists, merge the permission entries into the existing `allow` array.

### Step 4: Add reference to project CLAUDE.md

Append to your project's `CLAUDE.md`:

```markdown
## Visual Verification

Use the `visual-verify` skill after frontend changes. Browser MCP tools (Playwright MCP and Playwriter) are configured in `.claude/mcp.json`. See the skill at `.claude/skills/visual-verify/SKILL.md` for the full workflow.
```

### Step 5: Validate the setup

Start a new Claude Code session in the project directory. Confirm:

1. MCP server discovery message appears on startup (both `playwright` and `playwriter` listed).
2. Run a test navigation and screenshot:

```
Navigate to http://localhost:8000 (or your dev server URL) and take a screenshot.
```

3. Verify the screenshot appears in the conversation and shows the expected page.

If MCP tools do not appear, check that `.claude/mcp.json` is valid JSON and that `npx` can resolve the packages (`npx @playwright/mcp@latest --help`).

## Constraints

- Playwright MCP is fetched via npx on first use. No global install step is needed, but the first invocation takes 10-20 seconds to download.
- Screenshots cost approximately 1000-1500 tokens each. The skill must enforce budget discipline; unconstrained screenshotting can consume a significant portion of the context window.
- Headless WebGL rendering is slower than headed rendering. Agents must wait for async visualizations (maps, 3D, canvas-based charts) to finish compositing before screenshotting.
- Service worker blocking (`--block-service-workers`) is critical for frameworks with offline plugins (Gatsby, Next.js with PWA). Without it, the agent sees cached stale content.
- Playwriter in `PLAYWRITER_DIRECT=1` mode requires Chrome to be running. It will fail if no Chrome instance is available.
- The skill file uses `alwaysApply: false` so it only activates when relevant. Agents should invoke it explicitly for frontend changes, not on every task.

## Outputs

- `.claude/mcp.json` with `playwright` and `playwriter` server configurations
- `.claude/skills/visual-verify/SKILL.md` teaching the agent the visual verification workflow
- Updated `.claude/settings.local.json` with MCP tool permissions for both servers
- Updated `CLAUDE.md` with a pointer to the visual verification skill
