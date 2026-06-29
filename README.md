# foighne

A classic **Klondike Solitaire** card game — playable right in the browser, no dependencies.

*Foighne* means "patience" in Irish.

## How to Play

Open `foighne.html` in any modern browser. The goal is to build all four foundation piles up from Ace to King, one per suit.

- **Tableau**: Build descending sequences in alternating colors. Drag cards or click to select, then click the destination.
- **Stock & Waste**: Click the stock (top-left) to flip cards into the waste pile. Drag cards from the waste onto the tableau or foundations.
- **Foundations**: Start with an Ace, then stack same-suit cards in ascending order.
- **Auto-complete**: When all cards are face-up, the New Game button becomes an auto-complete button to finish the game automatically.

## Features

- Drag-and-drop and click-to-move with touch support
- Game state persists across page reloads via `localStorage`
- Win stats tracking (games played, won, current streak, best streak)
- 8 color themes (Azure, Paper, Ocean, Sunset, Classic Green, Midnight, Cedar, Clover)
- 6 card back styles + custom image upload
- 5 face card styles (Cool, Funky, Cute, Funny, Stupid)
- 8 sound themes (Crystal, Felt, Zen, Arcade, Clover, Paper, Ocean, Sunset) — Web Audio API, no files needed
- Single or triple draw from stock
- Responsive layout with mobile-optimised card design (simplified, larger rank+suit, tighter spacing)
- PWA-ready with favicon, apple-touch-icon, and theme colour for home screen install
- Privacy-friendly GoatCounter analytics (no cookies, no personal data)
- Debug panel (long-press top-right corner) with game state inspector, easter egg toggles, nearly-complete preset, and clear-saved-data option

### 🥚 Easter Eggs

The game has **11 date-based easter eggs** that trigger subtle themed background particles on specific days:

| Date | Egg |
|------|-----|
| Jan 1 | 🎉 New Year's — stars & bursts |
| Feb 1 | 🕯️ St Brigid's Day — woven reed crosses |
| Feb 14 | 💕 Valentine's — floating hearts |
| Mar 17 | ☘️ St Patrick's — shamrocks |
| Apr 1 | 🤡 April Fools — jesters & bananas |
| May 10 | 💍 Wedding Anniversary — hearts & stars |
| Jun 21 | ☀️ Mid Summer — suns |
| Jul 7 | 🎂 Birthday — balloons & sparkles |
| Oct 31 | 🎃 Halloween — skulls & witches |
| Dec 21–22 | ❄️ Mid Winter — falling snowflakes |
| Dec 24 – Jan 6 | 🎄 Christmas — santas, trees & stars |

Particles are rendered on a lightweight `<canvas>` layer behind the game with zero performance impact.

## License

MIT
