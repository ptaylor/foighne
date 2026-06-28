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

### Key functions
- `dealBoard()` / `newGame()` — shuffle and deal
- `render()` — full DOM redraw of all piles, debug panel, auto-complete button, stalemate check
- `runAutoComplete()` — animated card-by-card move to foundations
- `setupNearlyComplete()` — debug panel preset (random nearly-won state)
- `validateGameState()` / `ensureValidState()` — duplicate detection and auto-fix
- `saveGame()` / `loadGame()` — localStorage persistence
- `createCardElement()` — DOM card rendering with face-card SVGs

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
- Both shown in the debug panel (click top-right corner to open)

## Debug panel
Click the invisible button in the **top-right corner** of the page. Shows stock/waste/foundations state, version/commit, easter eggs, and a **🧪 Nearly Complete** button for testing.

## Publishing
```bash
./publish.sh              # bump version, copy, commit, tag, push
./publish.sh --no-push    # copy only (preview locally)
PUBLISH_BRANCH=gh-pages ./publish.sh  # override target branch (default: public)
```
GitHub Pages must be set to deploy from the target branch (`public` or `gh-pages`), root directory.
