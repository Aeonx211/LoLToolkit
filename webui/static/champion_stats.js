"use strict";

// Champion Stats tab. The server returns one row per game (champion_stats/rows.py); every cut and the filter stack
// are computed here from those rows, so a click recalculates instantly (ADR 0002). Loaded after app.js and uses its
// helpers ($, h, fill, runJob, setStatus, withButton, saved, cache, timeAgo, champName, pct, META).

const CS_ROLES = ["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"];
const CS_ROLE_NAMES = { TOP: "Top", JUNGLE: "Jungle", MIDDLE: "Mid", BOTTOM: "ADC", UTILITY: "Support" };
const csRole = (role) => CS_ROLE_NAMES[role] || "no role";
const CS = { data: null, stack: [], sort: {}, minGames: 5, patchFrom: "", patchTo: "" };

// ---------- cuts -------------------------------------------------------------------------------------------
// A cut groups games by `keys(row)` (a list, usually of one). `multi` cuts can hold several keys per game (e.g.
// "any item"), so selecting two of them means "both"; single-valued cuts swap their selection instead.
function csMainRole(rows) {
  const counts = {};
  for (const r of rows) counts[r.role] = (counts[r.role] || 0) + 1;
  return Object.entries(counts).sort((a, b) => b[1] - a[1])[0]?.[0] || "";
}

const csName = (table, id) => (CS.data.names?.[table]?.[id]) || `#${id}`;
const csItem = (id) => csName("items", id);
const csRune = (id) => csName("runes", id);
const csTree = (id) => csName("trees", id);
const CS_SIDE = { us: "We took it", them: "They took it", none: "Nobody" };
const csGap = (r, mark) => (r.pace?.[mark] ? r.pace[mark][0] - r.pace[mark][1] : null);
const csPaceKey = (mark) => (r) => {
  const gap = csGap(r, mark);
  return gap == null ? [] : [gap > 0 ? "Ahead" : gap < 0 ? "Behind" : "Even"];
};
const one = (v) => (v == null || v === "" ? [] : [v]);
const CS_LENGTH_ORDER = ["<25", "25–30", "30–35", "35+"];

function csCuts(rows) {
  const mine = csMainRole(rows);
  const cut = (id, section, title, keys, label = String, extra = {}) => ({ id, section, title, short: title, keys, label, ...extra });
  const cuts = [cut("matchup", "matchups", `Matchup (vs enemy ${csRole(mine)})`, (r) => one(r.enemies[r.role]), champName,
                    { short: "Matchup" })];
  for (const role of CS_ROLES) {
    if (role !== mine) cuts.push(cut(`enemy:${role}`, "matchups", `Enemy ${csRole(role)}`, (r) => one(r.enemies[role]), champName));
  }
  for (const role of CS_ROLES) {
    if (role !== mine) cuts.push(cut(`ally:${role}`, "allies", `Ally ${csRole(role)}`, (r) => one(r.allies[role]), champName));
  }
  cuts.push(
    cut("path3", "builds", "3-item paths", (r) => (r.items.length >= 3 ? [r.items.slice(0, 3).join(",")] : []),
        (k) => k.split(",").map(csItem).join(" → "), { short: "Path", wide: true }),
    ...[0, 1, 2, 3, 4].map((i) => cut(`slot${i + 1}`, "builds", `Item ${i + 1}`, (r) => one(r.items[i]), csItem)),
    cut("item", "builds", "Any slot", (r) => r.items, csItem, { multi: true, short: "Has item" }),
    cut("boots", "builds", "Boots", (r) => one(r.boots), csItem),
    cut("pet", "builds", "Jungle pet", (r) => one(r.pet), csItem),
    cut("keystone", "runes", "Keystone", (r) => one(r.keystone), csRune),
    cut("primary", "runes", "Primary tree", (r) => one(r.primary_tree), csTree),
    cut("secondary", "runes", "Secondary tree", (r) => one(r.secondary_tree), csTree),
    cut("rune", "runes", "Individual runes", (r) => r.runes, csRune, { multi: true, short: "Rune" }),
    cut("page", "runes", "Full rune pages (used ≥ min games)", (r) => one(r.page),
        (k) => k.split("-").map((id) => CS.data.names?.shards?.[id] || csRune(id)).join(", "),
        { short: "Page", hideThin: true, wide: true }),
    cut("pace5", "pace", "Camp pace at 5:00", csPaceKey("5"), String, { short: "Pace 5:00" }),
    cut("pace10", "pace", "Camp pace at 10:00", csPaceKey("10"), String, { short: "Pace 10:00" }),
    cut("dragon", "pace", "First dragon", (r) => [r.first_dragon || "none"], (k) => CS_SIDE[k], { short: "First dragon" }),
    cut("herald", "pace", "First herald", (r) => [r.first_herald || "none"], (k) => CS_SIDE[k], { short: "First herald" }),
    cut("length", "length", "Game length (minutes)", (r) => one(r.length), String,
        { short: "Length", order: (a, b) => CS_LENGTH_ORDER.indexOf(a.key) - CS_LENGTH_ORDER.indexOf(b.key) }),
  );
  return cuts;
}

const CS_SECTIONS = [["matchups", "Matchups"], ["allies", "Allies"], ["builds", "Builds"], ["runes", "Runes"],
                     ["pace", "Camp Pace"], ["length", "Game Length"]];

const csCut = (id) => csCuts(CS.data.rows).find((c) => c.id === id);
const csMatches = (row, entry) => csCut(entry.cut).keys(row).includes(entry.key);

// Patches compare numerically ("15.9" < "15.10").
const csPatchNum = (p) => p.split(".").reduce((a, n) => a * 1000 + Number(n), 0);
const csPatches = () => [...new Set(CS.data.rows.map((r) => r.patch))].sort((a, b) => csPatchNum(a) - csPatchNum(b));

// The focus slice before the filter stack: the loaded games within the patch range.
function csSlice() {
  const from = CS.patchFrom ? csPatchNum(CS.patchFrom) : -Infinity, to = CS.patchTo ? csPatchNum(CS.patchTo) : Infinity;
  return CS.data.rows.filter((r) => csPatchNum(r.patch) >= from && csPatchNum(r.patch) <= to);
}

// Rows matching every stack entry, ignoring the entries of `skipCut` so a single-valued cut can still show (and
// swap to) its alternatives.
function csFiltered(skipCut = null) {
  const entries = CS.stack.filter((e) => e.cut !== skipCut);
  return csSlice().filter((r) => entries.every((e) => csMatches(r, e)));
}

// Lower bound of the 95% Wilson interval: a sample-size-aware win rate, so 2-0 doesn't outrank 30-15.
function csWilson(wins, games, z = 1.96) {
  if (!games) return 0;
  const p = wins / games, z2 = z * z;
  return (p + z2 / (2 * games) - z * Math.sqrt((p * (1 - p) + z2 / (4 * games)) / games)) / (1 + z2 / games);
}

function csComputeCut(cut) {
  const base = csFiltered(cut.multi ? null : cut.id);
  const baseWins = base.filter((r) => r.win).length;
  const baseWr = base.length ? baseWins / base.length : 0;
  const groups = new Map();
  for (const r of base) {
    for (const key of new Set(cut.keys(r))) {
      const g = groups.get(key) || { key, games: 0, wins: 0 };
      g.games += 1;
      if (r.win) g.wins += 1;
      groups.set(key, g);
    }
  }
  return [...groups.values()].map((g) => ({
    ...g, wr: g.wins / g.games, delta: g.wins / g.games - baseWr, pick: g.games / base.length,
    score: csWilson(g.wins, g.games),
  }));
}

// ---------- filter stack -------------------------------------------------------------------------------------
function csToggle(cut, key) {
  const i = CS.stack.findIndex((e) => e.cut === cut.id && e.key === key);
  if (i >= 0) CS.stack.splice(i, 1);
  else {
    if (!cut.multi) CS.stack = CS.stack.filter((e) => e.cut !== cut.id);
    CS.stack.push({ cut: cut.id, key });
  }
  csRender();
  csSaveView();
}

function csChips() {
  if (!CS.stack.length) return null;
  return h("div", { class: "cs-chips" },
    CS.stack.map((e) => {
      const cut = csCut(e.cut);
      return h("span", { class: "chip" }, `${cut.short}: ${cut.label(e.key)}`,
        h("button", { class: "chip-x", title: "Remove", onclick: () => csToggle(cut, e.key) }, "×"));
    }),
    h("button", { class: "small", onclick: () => { CS.stack = []; csRender(); csSaveView(); } }, "Clear all"));
}

// ---------- rendering ----------------------------------------------------------------------------------------
const csSigned = (x) => `${x > 0 ? "+" : ""}${(x * 100).toFixed(1)}`;
const CS_COLUMNS = [
  ["label", "Name"], ["games", "Games"], ["wl", "W–L"], ["wr", "Win %"], ["delta", "Δ"], ["pick", "Pick %"],
  ["score", "Score"],
];

function csSummary(rows) {
  const games = rows.length;
  const wins = rows.filter((r) => r.win).length;
  const sum = (f) => rows.reduce((a, r) => a + f(r), 0);
  const kda = (sum((r) => r.kills) + sum((r) => r.assists)) / Math.max(1, sum((r) => r.deaths));
  const csMin = sum((r) => r.cs) / Math.max(1, sum((r) => r.duration_s) / 60);
  const stat = (label, value) => h("div", { class: "stat" }, h("div", { class: "muted" }, label), h("b", null, value));
  return h("div", { class: "cs-summary card" },
    stat("Games", games), stat("W–L", `${wins}–${games - wins}`), stat("Win %", games ? pct(wins / games) : "–"),
    stat("KDA", games ? kda.toFixed(2) : "–"), stat("CS", games ? Math.round(sum((r) => r.cs) / games) : "–"),
    stat("CS/min", games ? csMin.toFixed(1) : "–"));
}

function csTable(cut) {
  const stats = csComputeCut(cut).filter((s) => !cut.hideThin || s.games >= CS.minGames);
  if (!stats.length) return null;
  const sort = CS.sort[cut.id] || (cut.order ? { col: "order", dir: 1 } : { col: "score", dir: -1 });
  if (sort.col === "order") stats.sort(cut.order);
  const value = (s, col) => (col === "label" ? cut.label(s.key) : col === "wl" ? s.wins : s[col]);
  if (sort.col !== "order") {
    stats.sort((a, b) => {
      const va = value(a, sort.col), vb = value(b, sort.col);
      return (typeof va === "string" ? va.localeCompare(vb) : va - vb) * sort.dir || b.games - a.games;
    });
  }
  const setSort = (col) => {
    CS.sort[cut.id] = { col, dir: sort.col === col ? -sort.dir : col === "label" ? 1 : -1 };
    csRender();
    csSaveView();
  };
  const selected = (key) => CS.stack.some((e) => e.cut === cut.id && e.key === key);
  return h("div", { class: cut.wide ? "card cs-cut cs-span" : "card cs-cut" },
    h("h3", null, cut.title),
    h("table", { class: "cs-table" },
      h("thead", null, h("tr", null, CS_COLUMNS.map(([col, label]) =>
        h("th", { class: sort.col === col ? "sorted" : null, onclick: () => setSort(col) },
          label, sort.col === col ? (sort.dir < 0 ? " ▾" : " ▴") : "")))),
      h("tbody", null, stats.map((s) => h("tr", {
        class: [s.games < CS.minGames ? "thin" : "", selected(s.key) ? "selected" : ""].join(" ").trim() || null,
        onclick: () => csToggle(cut, s.key),
      },
        h("td", null, cut.label(s.key)), h("td", null, s.games), h("td", null, `${s.wins}–${s.games - s.wins}`),
        h("td", null, pct(s.wr)),
        h("td", { class: s.delta > 0 ? "win-text" : s.delta < 0 ? "loss-text" : "muted" }, csSigned(s.delta)),
        h("td", null, pct(s.pick)), h("td", { class: "muted" }, Math.round(s.score * 100)))))));
}

// ---------- non-cut blocks -----------------------------------------------------------------------------------
const csAvg = (rows, f) => {
  const vals = rows.map(f).filter((v) => v != null);
  return vals.length ? vals.reduce((x, y) => x + y, 0) / vals.length : null;
};
const csFmt = (v, digits = 0) => (v == null ? "–" : v.toFixed(digits));
const csSplit = (rows) => [rows.filter((r) => r.win), rows.filter((r) => !r.win)];

// Most common vs highest win 3-item path, side by side; clicking one filters to it like a path3 row.
function csPaths(rows) {
  const cut = csCut("path3");
  const stats = csComputeCut(cut);
  if (!stats.length) return null;
  const common = [...stats].sort((a, b) => b.games - a.games || b.score - a.score)[0];
  const eligible = stats.filter((s) => s.games >= CS.minGames);
  const best = [...(eligible.length ? eligible : stats)].sort((a, b) => b.score - a.score)[0];
  const card = (title, s) => h("div", { class: "card cs-path", onclick: () => csToggle(cut, s.key) },
    h("div", { class: "muted" }, title), h("b", null, cut.label(s.key)),
    h("div", null, `${s.games} games · ${s.wins}–${s.games - s.wins} · ${pct(s.wr)} `,
      h("span", { class: s.delta > 0 ? "win-text" : s.delta < 0 ? "loss-text" : "muted" }, csSigned(s.delta))));
  return h("div", { class: "cs-paths" }, card("Most common", common), card("Highest win", best));
}

// Rune values: averages of each rune's var1-var3 in wins vs losses. Diagnostic only: values are higher in games
// that went well regardless of whether the rune helped.
function csRuneValues(rows) {
  const byRune = new Map();
  for (const r of rows) {
    for (const [id, vals] of Object.entries(r.rune_values || {})) {
      if (!byRune.has(id)) byRune.set(id, []);
      byRune.get(id).push({ win: r.win, vals });
    }
  }
  if (!byRune.size) return null;
  const labels = CS.data.names?.rune_labels || {};
  const body = [];
  for (const [id, games] of byRune) {
    const known = labels[id];
    for (let i = 0; i < 3; i++) {
      if (known ? !known[i] : games.every((g) => !g.vals[i])) continue;
      const avg = (list) => csAvg(list, (g) => g.vals[i]);
      const wins = games.filter((g) => g.win), losses = games.filter((g) => !g.win);
      body.push(h("tr", null, h("td", null, csRune(id)), h("td", null, known ? known[i] : `var${i + 1}`),
        h("td", null, games.length), h("td", null, csFmt(avg(wins))), h("td", null, csFmt(avg(losses)))));
    }
  }
  return h("div", { class: "card cs-cut cs-wide" },
    h("h3", null, "Rune values ", h("span", { class: "chip" }, "labels unverified")),
    h("p", { class: "muted" }, "Average per game. Higher in wins usually means the game went well, not that the rune is better."),
    h("table", { class: "cs-table static" },
      h("thead", null, h("tr", null, ["Rune", "Value", "Games", "Avg in wins", "Avg in losses"].map((t) => h("th", null, t)))),
      h("tbody", null, body)));
}

function csPaceTable(rows) {
  const marks = ["3", "5", "8", "10"].filter((m) => rows.some((r) => r.pace?.[m]));
  if (!marks.length) return null;
  const [wins, losses] = csSplit(rows);
  const line = (label, f, digits = 1, signed = false) => h("tr", null, h("td", null, label),
    [rows, wins, losses].map((set) => {
      const v = csAvg(set, f);
      return h("td", { class: signed && v ? (v > 0 ? "win-text" : "loss-text") : null },
        v == null ? "–" : (signed && v > 0 ? "+" : "") + v.toFixed(digits));
    }));
  return h("div", { class: "card cs-cut cs-wide" },
    h("h3", null, "Camp pace vs enemy jungler"),
    h("p", { class: "muted" }, "Cumulative jungle monsters killed. Gap = yours − theirs."),
    h("table", { class: "cs-table static" },
      h("thead", null, h("tr", null, ["", "All games", "Wins", "Losses"].map((t) => h("th", null, t)))),
      h("tbody", null,
        marks.map((m) => [
          line(`${m}:00 you`, (r) => r.pace?.[m]?.[0]), line(`${m}:00 them`, (r) => r.pace?.[m]?.[1]),
          line(`${m}:00 gap`, (r) => csGap(r, m), 1, true)]),
        line("Jungle CS before 10:00", (r) => r.jungle_cs_10),
        line("Enemy jungle camps taken", (r) => r.enemy_jungle_kills))));
}

const CS_EXTRAS = { builds: [csPaths], runes: [], pace: [csPaceTable] };
const CS_EXTRAS_AFTER = { runes: [csRuneValues] };

function csRender() {
  const out = $("#cs-out");
  if (!CS.data) return out.replaceChildren();
  const rows = csFiltered();
  const total = csSlice().length;
  const cuts = csCuts(CS.data.rows);
  fill(out,
    csChips(),
    h("div", { class: "cs-banner muted" }, CS.stack.length ? `${rows.length} of ${total} games match` : `${total} games`,
      ` · ${CS.data.riot_id} on ${champName(CS.data.champion)}`),
    csSummary(rows),
    CS_SECTIONS.map(([id, title]) => {
      const before = (CS_EXTRAS[id] || []).map((f) => f(rows)).filter(Boolean);
      const tables = cuts.filter((c) => c.section === id).map(csTable).filter(Boolean);
      const after = (CS_EXTRAS_AFTER[id] || []).map((f) => f(rows)).filter(Boolean);
      if (!before.length && !tables.length && !after.length) return null;
      return h("section", { class: "cs-section" }, h("h2", null, title), before, h("div", { class: "cs-grid" }, tables), after);
    }));
}

// ---------- slice controls & persistence ------------------------------------------------------------------
function csSaveView() {
  saved.set("champstats:view", JSON.stringify({ stack: CS.stack, sort: CS.sort, minGames: CS.minGames,
                                                patchFrom: CS.patchFrom, patchTo: CS.patchTo }));
}

function csRestoreView() {
  try {
    const v = JSON.parse(saved.get("champstats:view", "{}"));
    Object.assign(CS, { stack: v.stack || [], sort: v.sort || {}, minGames: v.minGames || 5,
                        patchFrom: v.patchFrom || "", patchTo: v.patchTo || "" });
  } catch { /* corrupt entry: keep defaults */ }
  const known = new Set(csCuts(CS.data.rows).map((c) => c.id));
  CS.stack = CS.stack.filter((e) => known.has(e.cut));
}

function csFillPatches() {
  const form = $("#cs-form");
  const patches = csPatches();
  for (const [sel, value, blank] of [[form.patch_from, CS.patchFrom, "Oldest"], [form.patch_to, CS.patchTo, "Newest"]]) {
    sel.replaceChildren(h("option", { value: "" }, blank), ...patches.map((p) => h("option", { value: p }, p)));
    sel.value = patches.includes(value) ? value : "";
  }
  CS.patchFrom = form.patch_from.value;
  CS.patchTo = form.patch_to.value;
  form.min_games.value = CS.minGames;
}

// ---------- loading -----------------------------------------------------------------------------------------
async function csLoad(form) {
  const status = $("#cs-status");
  const params = { riot_id: form.riot_id.value.trim(), champion: form.champion.value.trim(), queue: form.queue.value };
  saved.set("riot_id", params.riot_id);
  setStatus(status, "Starting...", { busy: true });
  try {
    const data = await runJob("champion_stats", params, { statusEl: status });
    CS.data = data;
    CS.stack = [];
    csFillPatches();
    csSaveView();
    cache.set("champstats", data);
    setStatus(status, data.rows.length ? `${data.rows.length} games loaded.` : `No ${params.champion} games found.`);
    csRender();
  } catch (e) {
    setStatus(status, e.message, { error: true });
  }
}

function csInit() {
  const form = $("#cs-form");
  const cached = cache.get("champstats");
  const tracked = (META && META.tracked_players && META.tracked_players[0]) || { riot_id: DEFAULT_RIOT_ID, champion: "Lillia" };
  form.riot_id.value = cached?.riot_id || tracked.riot_id;
  form.champion.value = cached?.champion || tracked.champion;
  form.queue.value = cached?.queue || "solo";
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    withButton(form.querySelector("button.primary"), () => csLoad(form));
  });
  const onSlice = () => {
    CS.patchFrom = form.patch_from.value;
    CS.patchTo = form.patch_to.value;
    CS.minGames = Math.max(1, Number(form.min_games.value) || 5);
    csSaveView();
    if (CS.data) csRender();
  };
  form.patch_from.addEventListener("change", onSlice);
  form.patch_to.addEventListener("change", onSlice);
  // "input", not "change": a change event fires on blur, and re-rendering then would swallow the click that blurred it.
  form.min_games.addEventListener("input", onSlice);
  if (cached?.rows && cached.names) {  // rows cached before the build/rune fields existed can't render
    CS.data = cached;
    csRestoreView();
    csFillPatches();
    setStatus($("#cs-status"), `Showing ${cached.rows.length} cached games from ${timeAgo(cached.savedAt)}. Click Load to refresh.`);
    csRender();
  }
}
