# AGENTS.md

Foighne — a classic Klondike Solitaire game in a single HTML file.

## Quickstart
- **Play**: open `foighne.html` in any browser
- **Publish**: run `./publish.sh` (bumps version, tags, pushes to GitHub Pages via `public` branch)
- **No build step, no dependencies**

## File map
| File | Purpose |
|------|---------|
| `foighne.html` | The entire game — HTML, CSS, and JS in one file |
| `publish.sh` | Copies `foighne.html` → `public/index.html`, injects version & commit hash, bumps semver tag, pushes to `public` branch for GitHub Pages |
| `README.md` | Human-facing readme |

## Code structure inside `foighne.html`
- **CSS** (`<style>` near top) — custom properties for theming, card/pile styles, overlays, animations
- **HTML** (`<body>`) — game layout: title, stats bar, top-row (stock, waste, foundations, buttons), tableau, debug panel, win overlay, settings overlay
- **JS** (`<script>` near bottom) — all game logic in global scope

### Key globals
- `stock[]`, `waste[]`, `tableau[7][]`, `foundations[4][]` — game state (cards: `{suit, rank, faceUp}`)
- `SUITS = ['♠','♥','♦','♣']`, `RANKS = ['A'..'K']` — suit 0=♠(black), 1=♥(red), 2=♦(red), 3=♣(black); rank 0=A .. 12=K
- `selectedCards`, `debugMode`, `autoCompleting`
- `SETTINGS_KEY`, `SAVE_KEY`, `STATS_KEY` — localStorage keys
- `activeEgg`, `eggParticles[]`, `eggAnimId`, `eggCanvas`, `eggCtx` — easter egg canvas system
- `audioCtx` — Web Audio API context for sound engine

### Key functions
- `dealBoard()` / `newGame()` — shuffle and deal
- `render()` — full DOM redraw of all piles, debug panel, auto-complete/New Game swap, stalemate check
- `runAutoComplete()` — animated card-by-card move to foundations; replaces New Game button when available
- `setupNearlyComplete()` — debug panel preset (random nearly-won state)
- `validateGameState()` / `ensureValidState()` — duplicate detection and auto-fix
- `saveGame()` / `loadGame()` / `clearSavedGame()` / `clearSavedData()` — localStorage persistence and reset
- `createCardElement()` — DOM card rendering with face-card SVGs; on mobile centre suit moves to bottom-right
- `playSound(type)` — Web Audio API sound engine with 6 types (deal, draw, place, foundation, win, invalid)
- `trackEvent(path)` — GoatCounter custom event tracking (new-game, game-won, auto-complete, etc.)

### Easter egg system
- `EASTER_EGGS` — object keyed by `MM-DD` or `MM-DD--MM-DD` (date ranges). Each entry has `name` and `particles` config (shape, count, colors, size range, speed range, opacity range, optional `fall: true`)
- `checkEasterEgg()` — called at startup, iterates eggs and activates if today matches (handles year-boundary wrap for ranges like `12-24--01-06`)
- `activateEgg(key)` / `deactivateEgg()` — shows/hides `<canvas id="egg-canvas">`, starts/stops `requestAnimationFrame` particle loop
- `animateEgg()` — clears canvas, updates particle positions with sinusoidal drift, wraps edges, draws each particle via `DRAW_FNS`
- `DRAW_FNS` — lookup of 16 shape functions: `drawCircle`, `drawSparkle`, `drawStar`, `drawBurst`, `drawSun`, `drawBalloon`, `drawPumpkin`, `drawSkull`, `drawWitch`, `drawBanana`, `drawJester`, `drawCross`, `drawSanta`, `drawTree`, `drawHeart`, `drawShamrock`, `drawSnowflake`
- Shapes support multi-shape arrays per egg (particle picks randomly), and use internal hardcoded colors for complex shapes (santa, tree, skull, witch, pumpkin, jester, cross) while simpler shapes use the particle's color
- Debug panel lists all eggs with date and active status; click to manually toggle any egg for testing

### Card object shape
```js
{ suit: 0–3, rank: 0–12, faceUp: Boolean }
```
- `cardColor(suit)` → `'red'` (♥♦) or `'black'` (♠♣)
- `canPlaceOnTableau(card, pile)` — descending rank, alternating colour
- `canPlaceOnFoundation(card, pile)` — ascending rank, same suit

## Versioning
- Source meta tag: `<meta name="version" content="VERSION">` — replaced by `publish.sh` with the semver tag
- Source meta tag: `<meta name="commit" content="COMMIT">` — replaced by `publish.sh` with `git rev-parse --short HEAD`
- Both shown in the debug panel (long-press top-right corner to open)

## Debug panel
Long-press (hold ~1.5s) the invisible button in the **top-right corner** of the page — a gold ring expands as visual feedback. Shows stock/waste/foundations state, version/commit, easter eggs, a **🧪 Nearly Complete** button, and a **🗑 Clear Saved Data** button for testing.

## Publishing
```bash
./publish.sh              # bump version, copy, commit, tag, push
./publish.sh --no-push    # copy only (preview locally)
PUBLISH_BRANCH=gh-pages ./publish.sh  # override target branch (default: public)
```
GitHub Pages must be set to deploy from the target branch (`public` or `gh-pages`), root directory.
