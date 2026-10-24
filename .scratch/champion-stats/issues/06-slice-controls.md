# 06: Slice controls

**What to build:** Solo / Flex / Both queue toggle (default Solo), patch range filter, a minimum-games setting, and the tab remembering the last slice and filter stack in browser storage.

**Blocked by:** 01

**Status:** done

- [x] Backfill and rows work for flex and both queues
- [x] Patch range narrows the slice in the browser
- [x] Minimum games setting replaces the fixed 5
- [x] Reopening the page shows the last view instantly

## Comments

- Done. Changing the queue needs a Load click (it is a different backfill); patch range and min games apply instantly. Min games applies as you type: a change-on-blur re-render swallowed the next row click.
