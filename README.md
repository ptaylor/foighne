# foighne

A classic **Klondike Solitaire** card game — playable right in the browser, no dependencies.

*Foighne* means "patience" in Irish.

## How to Play

Open `foighne.html` in any modern browser. The goal is to build all four foundation piles up from Ace to King, one per suit.

- **Tableau**: Build descending sequences in alternating colors. Drag cards or click to select, then click the destination.
- **Stock & Waste**: Click the stock (top-left) to flip cards into the waste pile. Drag cards from the waste onto the tableau or foundations.
- **Foundations**: Start with an Ace, then stack same-suit cards in ascending order.
- **Auto-complete**: Cards that can safely go to the foundations are automatically sent there.

## Features

- Drag-and-drop and click-to-move
- Undo, hint, and auto-complete
- Game state persists across page reloads via `localStorage`
- Win stats tracking (streak, best time, total wins)
- Customizable card backs and face styles via settings
- Keyboard shortcuts (e.g., `Ctrl+Z` to undo, `Ctrl+H` for hint)
- Debug panel (click the top-right corner to reveal)
- Responsive layout that scales to the viewport

## License

MIT
