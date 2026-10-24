# 03: Builds

**What to build:** The Builds section: most common and highest win 3-item paths side by side, completed legendary items by slot 1–5, all completed items, completed boots, and jungle pet. Every row is clickable into the filter stack.

**Blocked by:** 01

**Status:** done

- [x] Completed items are in completion order from timeline buy, sell and undo events; components, base boots and the pet don't count as slots; an item sold before the end still counts in its slot (tested)
- [x] Completed boots identified (base boots ignored); pet identified from the jungle pet starting item (tested)
- [x] Item names come from Data Dragon item data; completed vs component decided from it
- [x] Most common and highest win paths shown at the top of Builds

## Comments

- Done. A completed legendary is an item with no upgrade path, at least 2000 gold, not boots or a consumable (Data Dragon item data, latest patch). Completed boots = last boots item bought with no upgrade path. Pet ids 1101–1103 are hard-coded. Without Data Dragon (e.g. this cloud environment) the build fields are empty apart from the pet.
- The 3-item path and rune page tables span the full width because their names are long.
