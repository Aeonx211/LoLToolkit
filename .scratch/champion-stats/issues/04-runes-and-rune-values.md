# 04: Runes and rune values

**What to build:** The Runes section: keystone, primary and secondary tree, every individual rune, full rune pages used 5+ times, and rune values (var1–var3 averaged for wins vs losses) with best-guess labels marked "unverified". Every row except rune values is clickable into the filter stack.

**Blocked by:** 01

**Status:** done

- [x] Game row includes keystone, trees, each selected rune with var1–var3, and stat shards (tested)
- [x] Rune value label table with best guesses for common keystones and minor runes; unlabeled runes show raw var1–var3
- [x] Rune values framed as diagnostic, not a recommendation

## Comments

- Done. `python -m champion_stats.dump_runes "Name#TAG" Champion` added for ticket 08. Labels are in `champion_stats/rune_labels.py`, all unverified.
- The full rune page table hides pages under the min-games setting (default 5), rather than a fixed 5.
