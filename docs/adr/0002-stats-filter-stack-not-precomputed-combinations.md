---
status: accepted
---

# Champion stats are explored by stacking filters, not by precomputed combination tables

The Champion Stats tab loads with every cut shown unfiltered. Selecting a row (e.g. a specific first item) filters the focus slice to matching games and every other cut recalculates; each further selection narrows the slice again, until the sample runs out or a pattern shows. We chose this over fixed "set combination" tables because the number of possible item and rune sets explodes at 100 games, and the user wants to choose which dimensions to combine. The consequence is that the tab needs per-game rows in the browser (or a filtered query per click) rather than a static report.
