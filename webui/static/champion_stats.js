"use strict";

// Champion Stats tab. The server returns one row per game (champion_stats/rows.py); every cut and the filter stack
// are computed here from those rows, so a click recalculates instantly (ADR 0002). Loaded after app.js and uses its
// helpers ($, h, fill, runJob, setStatus, withButton, saved, cache, timeAgo, champName, pct, META).

const CS_MIN_GAMES = 5;
const CS_ROLES = ["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"];
const CS_ROLE_NAMES = { TOP: "Top", JUNGLE: "Jungle", MIDDLE: "Mid", BOTTOM: "ADC", UTILITY: "Support" };
const csRole = (role) => CS_ROLE_NAMES[role] || "no role";
const CS = { data: null, stack: [], sort: {} };

// ---------- cuts -------------------------------------------------------------------------------------------
// A cut groups games by `keys(row)` (a list, usually of one). `multi` cuts can hold several keys per game (e.g.
// "any item"), so selecting two of them means "both"; single-valued cuts swap their selection instead.
function csMainRole(rows) {
  const counts = {};
  for (const r of rows) counts[r.role] = (counts[r.role] || 0) + 1;
  return Object.entries(counts).sort((a, b) => b[1] - a[1])[0]?.[0] || "";
}

function csCuts(rows) {
  const mine = csMainRole(rows);
  const cuts = [{
    id: "matchup", section: "matchups", title: `Matchup (vs enemy ${csRole(mine)})`, short: "Matchup",
    keys: (r) => (r.enemies[r.role] ? [r.enemies[r.role]] : []), label: champName,
  }];
  for (const role of CS_ROLES) {
    if (role === mine) continue;
    cuts.push({ id: `enemy:${role}`, section: "matchups", title: `Enemy ${csRole(role)}`,
                short: `Enemy ${csRole(role)}`, keys: (r) => (r.enemies[role] ? [r.enemies[role]] : []),
                label: champName });
  }
  return cuts;
}

const CS_SECTIONS = [["matchups", "Matchups"]];

const csCut = (id) => csCuts(CS.data.rows).find((c) => c.id === id);
const csMatches = (row, entry) => csCut(entry.cut).keys(row).includes(entry.key);

// Rows matching every stack entry, ignoring the entries of `skipCut` so a single-valued cut can still show (and
// swap to) its alternatives.
function csFiltered(skipCut = null) {
  const entries = CS.stack.filter((e) => e.cut !== skipCut);
  return CS.data.rows.filter((r) => entries.every((e) => csMatches(r, e)));
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
}

function csChips() {
  if (!CS.stack.length) return null;
  return h("div", { class: "cs-chips" },
    CS.stack.map((e) => {
      const cut = csCut(e.cut);
      return h("span", { class: "chip" }, `${cut.short}: ${cut.label(e.key)}`,
        h("button", { class: "chip-x", title: "Remove", onclick: () => csToggle(cut, e.key) }, "×"));
    }),
    h("button", { class: "small", onclick: () => { CS.stack = []; csRender(); } }, "Clear all"));
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
  const stats = csComputeCut(cut);
  if (!stats.length) return null;
  const sort = CS.sort[cut.id] || { col: "score", dir: -1 };
  const value = (s, col) => (col === "label" ? cut.label(s.key) : col === "wl" ? s.wins : s[col]);
  stats.sort((a, b) => {
    const va = value(a, sort.col), vb = value(b, sort.col);
    return (typeof va === "string" ? va.localeCompare(vb) : va - vb) * sort.dir || b.games - a.games;
  });
  const setSort = (col) => {
    CS.sort[cut.id] = { col, dir: sort.col === col ? -sort.dir : col === "label" ? 1 : -1 };
    csRender();
  };
  const selected = (key) => CS.stack.some((e) => e.cut === cut.id && e.key === key);
  return h("div", { class: "card cs-cut" },
    h("h3", null, cut.title),
    h("table", { class: "cs-table" },
      h("thead", null, h("tr", null, CS_COLUMNS.map(([col, label]) =>
        h("th", { class: sort.col === col ? "sorted" : null, onclick: () => setSort(col) },
          label, sort.col === col ? (sort.dir < 0 ? " ▾" : " ▴") : "")))),
      h("tbody", null, stats.map((s) => h("tr", {
        class: [s.games < CS_MIN_GAMES ? "thin" : "", selected(s.key) ? "selected" : ""].join(" ").trim() || null,
        onclick: () => csToggle(cut, s.key),
      },
        h("td", null, cut.label(s.key)), h("td", null, s.games), h("td", null, `${s.wins}–${s.games - s.wins}`),
        h("td", null, pct(s.wr)),
        h("td", { class: s.delta > 0 ? "win-text" : s.delta < 0 ? "loss-text" : "muted" }, csSigned(s.delta)),
        h("td", null, pct(s.pick)), h("td", { class: "muted" }, Math.round(s.score * 100)))))));
}

function csRender() {
  const out = $("#cs-out");
  if (!CS.data) return out.replaceChildren();
  const rows = csFiltered();
  const total = CS.data.rows.length;
  const cuts = csCuts(CS.data.rows);
  fill(out,
    csChips(),
    h("div", { class: "cs-banner muted" }, CS.stack.length ? `${rows.length} of ${total} games match` : `${total} games`,
      ` · ${CS.data.riot_id} on ${champName(CS.data.champion)}`),
    csSummary(rows),
    CS_SECTIONS.map(([id, title]) => {
      const tables = cuts.filter((c) => c.section === id).map(csTable).filter(Boolean);
      return tables.length ? h("section", { class: "cs-section" }, h("h2", null, title), h("div", { class: "cs-grid" }, tables)) : null;
    }));
}

// ---------- loading -----------------------------------------------------------------------------------------
async function csLoad(form) {
  const status = $("#cs-status");
  const params = { riot_id: form.riot_id.value.trim(), champion: form.champion.value.trim(), queue: "solo" };
  saved.set("riot_id", params.riot_id);
  setStatus(status, "Starting...", { busy: true });
  try {
    const data = await runJob("champion_stats", params, { statusEl: status });
    CS.data = data;
    CS.stack = [];
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
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    withButton(form.querySelector("button.primary"), () => csLoad(form));
  });
  if (cached?.rows) {
    CS.data = cached;
    setStatus($("#cs-status"), `Showing ${cached.rows.length} cached games from ${timeAgo(cached.savedAt)}. Click Load to refresh.`);
    csRender();
  }
}
