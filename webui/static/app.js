"use strict";

// ---------- helpers ----------------------------------------------------------------------------------------
const $ = (sel, el = document) => el.querySelector(sel);
const $$ = (sel, el = document) => [...el.querySelectorAll(sel)];
const SVG_NS = "http://www.w3.org/2000/svg";

function h(tag, attrs, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "value") el.value = v;
    else if (k === "checked") el.checked = !!v;
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat(Infinity)) {
    if (c == null || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}

function s(tag, attrs, ...children) {
  const el = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs || {})) if (v != null) el.setAttribute(k, v);
  for (const c of children.flat(Infinity)) {
    if (c == null) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}

// replaceChildren() would render null/false as text, so drop them first.
const fill = (el, ...children) => el.replaceChildren(...children.flat(Infinity).filter((c) => c != null && c !== false));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const TEAM = { 100: "Blue", 200: "Red" };
const mmss = (sec) => `${Math.floor(sec / 60)}:${String(Math.floor(sec % 60)).padStart(2, "0")}`;
const kfmt = (v) => (Math.abs(v) >= 1000 ? `${(Math.abs(v) / 1000).toFixed(1)}k` : `${Math.round(Math.abs(v))}`);
const pct = (x) => `${Math.round(x * 100)}%`;
const signed = (v) => (v > 0 ? "+" : "") + Math.round(v);
const champName = (id) => (META && META.champions[id]) || id;
const queueName = (id) => (META && META.queues[id]) || `Queue ${id}`;
const ROLE_LABELS = { utility: "support" };
const roleLabel = (position) => ROLE_LABELS[position.toLowerCase()] || position.toLowerCase() || "no role";
let META = null;

// op.gg's region slugs where they differ from Riot's platform ids.
const OPGG_REGIONS = { na1: "na", br1: "br", la1: "lan", la2: "las", euw1: "euw", eun1: "eune", tr1: "tr", me1: "me",
  jp1: "jp", oc1: "oc", sg2: "sg", tw2: "tw", vn2: "vn" };
// A player's name as a link to their op.gg profile.
function playerLink(riotId, attrs) {
  const i = riotId.lastIndexOf("#");
  if (i < 1) return h("span", attrs, riotId);
  const platform = (META && META.platform) || "na1";
  const region = OPGG_REGIONS[platform] || platform;
  const href = `https://www.op.gg/lol/summoners/${region}/${encodeURIComponent(riotId.slice(0, i))}-${encodeURIComponent(riotId.slice(i + 1))}`;
  return h("a", { ...attrs, class: `player-link ${(attrs && attrs.class) || ""}`.trim(), href, target: "_blank", rel: "noopener noreferrer",
    title: "Open on op.gg" }, riotId);
}
let clipSeq = 0;

const DEFAULT_RIOT_ID = "Aeoen#NA1";

const saved = {
  get(k, d) { try { return localStorage.getItem(k) ?? d; } catch { return d; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch { /* storage unavailable */ } },
};

// Caches the last query's full result per tool, so reopening the page or switching tabs shows it instantly
// with no server round-trip. The server/DB cache (data/toolkit.db) is what avoids re-hitting the Riot API;
// this is just about not re-running that lookup at all when nothing's changed.
const cache = {
  get(k) { try { return JSON.parse(localStorage.getItem(`cache:${k}`)); } catch { return null; } },
  set(k, v) { try { localStorage.setItem(`cache:${k}`, JSON.stringify({ ...v, savedAt: Date.now() })); } catch { /* full or unavailable */ } },
};
const timeAgo = (ms) => {
  const mins = Math.round((Date.now() - ms) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  return `${Math.round(mins / 60)}h ago`;
};

async function api(path, body) {
  const opts = body === undefined ? {} : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  };
  const r = await fetch(path, opts);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || r.statusText);
  return data;
}

// Jobs run server-side in a daemon thread, independent of whether anything is still polling them — but a plain
// page reload or tab close drops the JS loop below that was watching one. `persistKey` remembers the job id in
// localStorage so `resumeJob` can reattach and keep showing progress instead of the run looking like it "stopped".
function saveRunningJob(key, id, meta) {
  try { localStorage.setItem(`job:${key}`, JSON.stringify({ id, meta })); } catch { /* storage unavailable */ }
}
function clearRunningJob(key) {
  try { localStorage.removeItem(`job:${key}`); } catch { /* storage unavailable */ }
}
function getRunningJob(key) {
  try { return JSON.parse(localStorage.getItem(`job:${key}`)); } catch { return null; }
}

async function pollJob(id, { statusEl, onPartial, interval = 600, seen = 0 } = {}) {
  for (;;) {
    await sleep(interval);
    const job = await api(`/api/jobs/${id}`);
    if (statusEl && job.progress.length) setStatus(statusEl, job.progress[job.progress.length - 1], { busy: true });
    if (onPartial && job.partial.length > seen) {
      onPartial(job.partial.slice(seen));
      seen = job.partial.length;
    }
    if (job.status === "done") return job.result;
    if (job.status === "error") throw new Error(job.error);
  }
}

async function runJob(tool, params, { persistKey, ...opts } = {}) {
  const { id } = await api("/api/jobs", { tool, params });
  if (persistKey) saveRunningJob(persistKey, id, params);
  try {
    const result = await pollJob(id, opts);
    if (persistKey) clearRunningJob(persistKey);
    return result;
  } catch (e) {
    if (persistKey) clearRunningJob(persistKey);
    throw e;
  }
}

// Reattaches to a "games" job left running from before the page was reloaded/closed, if the server still has it
// (jobs are kept for an hour; see JOB_TTL_S in webui/server.py). Returns true if it handled the games tab's
// initial state (either by resuming or by clearing a stale/expired entry), false if there was nothing to resume.
async function resumeGamesJob() {
  const running = getRunningJob("games");
  if (!running) return false;
  const status = $("#games-status");
  const list = $("#games-list");
  const { riot_id: riotId, count, queue } = running.meta;
  $("#games-form").riot_id.value = riotId;
  $("#games-form").count.value = count;
  $("#games-form").queue.value = queue || "";
  list.replaceChildren();
  $("#games-summary").replaceChildren();
  let puuid = null;
  const addResults = (items) => {
    for (const r of items) {
      puuid = puuid || findPuuid(r, riotId);
      list.append(gameCard(r, puuid));
    }
  };
  const finish = (res) => {
    clearRunningJob("games");
    $("#games-summary").replaceChildren(gamesSummary(res.results, res.puuid, res.rollup));
    setStatus(status, `${res.results.length} games analyzed.`);
    cache.set("games", { riotId, count, queue, puuid: res.puuid, results: res.results, rollup: res.rollup });
  };
  setStatus(status, "Resuming analysis...", { busy: true });
  try {
    const job = await api(`/api/jobs/${running.id}`);
    addResults(job.partial);
    if (job.status === "done") { finish(job.result); return true; }
    if (job.status === "error") { clearRunningJob("games"); setStatus(status, job.error, { error: true }); return true; }
    finish(await pollJob(running.id, { statusEl: status, onPartial: addResults, seen: job.partial.length }));
  } catch (e) {
    // Job expired or the server restarted since — nothing left to resume, fall back to the cached view.
    clearRunningJob("games");
    return false;
  }
  return true;
}

function setStatus(el, text, { busy = false, error = false } = {}) {
  el.className = "status" + (error ? " error" : "");
  el.replaceChildren(busy ? h("span", { class: "spin" }) : "", text || "");
}

async function withButton(button, fn) {
  button.disabled = true;
  try { await fn(); } finally { button.disabled = false; }
}

// ---------- tabs -------------------------------------------------------------------------------------------
function showTab(name) {
  $$("#tabs button").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
  $$(".tab").forEach((t) => t.classList.toggle("active", t.id === `tab-${name}`));
  saved.set("tab", name);
  if (name === "tuning") loadTuning();
}

// ---------- charts -----------------------------------------------------------------------------------------
function areaChart(t, values, { width, height, pad = 0, upColor, downColor, markers = [], axes = false }) {
  const maxAbs = Math.max(500, ...values.map((v) => Math.abs(v)));
  const x0 = axes ? 44 : pad, x1 = width - pad, y0 = pad, y1 = height - (axes ? 22 : pad);
  const tMax = t[t.length - 1] || 1;
  const X = (tt) => x0 + ((x1 - x0) * tt) / tMax;
  const Y = (v) => y0 + ((y1 - y0) * (maxAbs - v)) / (2 * maxAbs);
  const zero = Y(0);
  const line = values.map((v, i) => `${X(t[i]).toFixed(1)},${Y(v).toFixed(1)}`).join(" ");
  const area = `${X(t[0])},${zero} ${line} ${X(t[t.length - 1])},${zero}`;
  const id = `clip${++clipSeq}`;
  const svg = s("svg", { viewBox: `0 0 ${width} ${height}`, class: "chart", role: "img" },
    s("defs", null,
      s("clipPath", { id: `${id}u` }, s("rect", { x: 0, y: 0, width, height: zero })),
      s("clipPath", { id: `${id}d` }, s("rect", { x: 0, y: zero, width, height: height - zero }))),
    s("polygon", { points: area, fill: upColor, "fill-opacity": 0.28, "clip-path": `url(#${id}u)` }),
    s("polygon", { points: area, fill: downColor, "fill-opacity": 0.28, "clip-path": `url(#${id}d)` }),
    s("polyline", { points: line, fill: "none", stroke: upColor, "stroke-width": 1.6, "clip-path": `url(#${id}u)` }),
    s("polyline", { points: line, fill: "none", stroke: downColor, "stroke-width": 1.6, "clip-path": `url(#${id}d)` }),
    s("line", { x1: x0, x2: x1, y1: zero, y2: zero, stroke: "currentColor", "stroke-opacity": 0.3 }));
  if (axes) {
    for (let m = 0; m * 60 <= tMax; m += 5) {
      svg.append(s("text", { x: X(m * 60), y: height - 6, "text-anchor": "middle" }, `${m}m`));
    }
    svg.append(s("text", { x: x0 - 6, y: y0 + 10, "text-anchor": "end" }, `+${kfmt(maxAbs)}`));
    svg.append(s("text", { x: x0 - 6, y: y1, "text-anchor": "end" }, `-${kfmt(maxAbs)}`));
    svg.append(s("text", { x: x0 - 6, y: zero + 4, "text-anchor": "end" }, "0"));
  }
  for (const m of markers) {
    const x = X(m.t);
    svg.append(s("g", null,
      s("line", { x1: x, x2: x, y1: y0, y2: y1, stroke: m.color, "stroke-dasharray": "3 3", "stroke-opacity": 0.8 }),
      s("circle", { cx: x, cy: y0 + 6, r: 5, fill: m.color }, s("title", null, m.label))));
  }
  return svg;
}

const cssVar = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

// ---------- Tool 1: game analysis --------------------------------------------------------------------------
function perspective(tag, me) {
  const mine = tag.team === me.team_id;
  const d = tag.detail;
  switch (tag.archetype) {
    case "Stomp": return mine ? ["We stomped", "good"] : ["Got stomped", "bad"];
    case "Comeback": return mine ? ["Came back", "good"] : ["Enemy came back", "bad"];
    case "Thrown": return mine ? ["We threw", "bad"] : ["Enemy threw", "good"];
    case "Snowballed-on": return mine ? [`Snowballed on by ${champName(d.champion)}`, "bad"] : [`${champName(d.champion)} snowballed`, "good"];
    case "Carried":
      if (d.participant_id === me.participant_id) return ["You carried", "gold"];
      return mine ? [`${champName(d.champion)} carried us`, "good"] : [`${champName(d.champion)} carried them`, "bad"];
    case "Even-then-decided": return ["Even, then decided", ""];
    default: return [tag.archetype, ""];
  }
}

function neutralTag(tag) {
  const d = tag.detail;
  if (d.champion) return `${tag.archetype}: ${champName(d.champion)}`;
  return tag.team ? `${tag.archetype} (${TEAM[tag.team]})` : tag.archetype;
}

function describeMoment(m) {
  const team = m.beneficiary, other = team === 100 ? 200 : 100;
  const ours = m.kills[team], theirs = m.kills[other];
  const parts = [];
  if (ours + theirs >= 2) parts.push(ours > theirs ? `won a ${ours}-${theirs} fight` : `traded kills ${ours}-${theirs}`);
  else if (ours === 1) parts.push("got a pick");
  const taken = {};
  m.objectives.filter((o) => o.team === team).forEach((o) => { taken[o.kind] = (taken[o.kind] || 0) + 1; });
  const names = Object.entries(taken).map(([k, n]) => (n > 1 ? `${n} ${k}s` : k));
  if (names.length) parts.push(`took ${names.join(", ")}`);
  return `${TEAM[team]} ${parts.join(" and ") || "swung the gold"} at ${mmss(m.start)} (${kfmt(m.gold_swing)} swing)`;
}

function gameCard(r, puuid) {
  const me = r.players.find((p) => p.puuid === puuid);
  const sign = me.team_id === 100 ? 1 : -1;
  const chart = areaChart(r.timeline.t, r.timeline.gold_diff.map((v) => v * sign),
    { width: 220, height: 50, pad: 2, upColor: cssVar("--win"), downColor: cssVar("--loss") });
  chart.style.width = "220px";
  const tags = r.tags.map((t) => { const [label, cls] = perspective(t, me); return h("span", { class: `chip ${cls}` }, label); });
  return h("div", { class: `game${me.win ? " win" : ""}` },
    h("div", { class: "stripe" }),
    h("div", { class: "body" },
      h("div", { class: "title" },
        h("span", { class: "result" }, me.win ? "Victory" : "Defeat"),
        h("span", { class: "champ" }, champName(me.champion)),
        h("span", { class: "muted" },
          `${roleLabel(me.position)} · ${me.kda.join("/")} · ${queueName(r.queue_id)} · `
          + `${mmss(r.duration_s)} · ${new Date(r.game_start).toLocaleDateString()}`),
        h("span", { class: "muted", title: "Weighted average of KP/damage/gold share and objective damage share, divided by a typical mix for this role. 1x = typical." }, `impact ${me.impact_ratio.toFixed(2)}x`)),
      h("div", { class: "chips" }, tags.length ? tags : h("span", { class: "chip" }, "No archetype")),
      h("p", { class: "verdict" }, r.verdict)),
    h("div", { class: "side" },
      h("div", { title: "Your team's gold lead over time" }, chart),
      h("div", { class: "row" },
        h("button", { class: "small", onclick: () => openMatch(r.match_id, puuid) }, "Details"),
        h("button", { class: "small", onclick: () => replayAdvisor(r.match_id) }, "Replay advisor"))));
}

function gamesSummary(results, puuid, rollup) {
  const mine = results.map((r) => ({ r, me: r.players.find((p) => p.puuid === puuid) }));
  const wins = mine.filter((x) => x.me.win);
  const counts = {};
  for (const { r, me } of mine) {
    for (const t of r.tags) {
      const [label] = perspective(t, me);
      const key = t.archetype === "Carried" && label !== "You carried" ? null
        : t.archetype === "Snowballed-on" ? (t.team === me.team_id ? "Got snowballed on" : "We snowballed") : label;
      if (key) counts[key] = (counts[key] || 0) + 1;
    }
  }
  const stat = (v, l) => h("div", { class: "stat" }, h("div", { class: "v" }, v), h("div", { class: "l" }, l));
  return h("div", { class: "stats" },
    stat(`${wins.length}-${mine.length - wins.length}`, "Record"),
    stat(`${wins.filter((x) => x.me.carried).length}/${wins.length}`, "Wins you carried"),
    ...Object.entries(counts).sort((a, b) => b[1] - a[1]).map(([k, n]) => stat(n, k)),
    rollup ? stat(`${rollup.carried_wins}/${rollup.wins}`, `Carried (all ${rollup.games} stored games)`) : null);
}

function renderGames(results, puuid, rollup) {
  $("#games-list").replaceChildren(...results.map((r) => gameCard(r, puuid)));
  $("#games-summary").replaceChildren(gamesSummary(results, puuid, rollup));
}

function loadCachedGames() {
  const c = cache.get("games");
  if (!c) return false;
  $("#games-form").riot_id.value = c.riotId;
  $("#games-form").count.value = c.count;
  $("#games-form").queue.value = c.queue || "";
  renderGames(c.results, c.puuid, c.rollup);
  setStatus($("#games-status"), `Showing ${c.results.length} cached games for ${c.riotId} from ${timeAgo(c.savedAt)}. Click Analyze to refresh.`);
  return true;
}

async function analyzeGames(form) {
  const status = $("#games-status");
  const list = $("#games-list");
  const riotId = form.riot_id.value.trim();
  const count = form.count.value, queue = form.queue.value || null;
  saved.set("riot_id", riotId);
  list.replaceChildren();
  $("#games-summary").replaceChildren();
  setStatus(status, `Looking up ${riotId}...`, { busy: true });
  let puuid = null;
  try {
    const res = await runJob("player", { riot_id: riotId, count, queue }, {
      statusEl: status,
      persistKey: "games",
      onPartial: (items) => {
        for (const r of items) {
          puuid = puuid || findPuuid(r, riotId);
          list.append(gameCard(r, puuid));
        }
      },
    });
    $("#games-summary").replaceChildren(gamesSummary(res.results, res.puuid, res.rollup));
    setStatus(status, `${res.results.length} games analyzed.`);
    cache.set("games", { riotId, count, queue, puuid: res.puuid, results: res.results, rollup: res.rollup });
  } catch (e) {
    setStatus(status, e.message, { error: true });
  }
}

function findPuuid(result, riotId) {
  const want = riotId.toLowerCase();
  const p = result.players.find((x) => x.riot_id.toLowerCase() === want);
  return p ? p.puuid : result.players[0].puuid;
}

async function openMatch(matchId, puuid) {
  const dialog = $("#match-dialog");
  const box = $("#match-detail");
  const status = h("div", { class: "status" });
  box.replaceChildren(status);
  setStatus(status, `Loading ${matchId}...`, { busy: true });
  dialog.showModal();
  try {
    const r = await runJob("match", { match_id: matchId }, { interval: 300 });
    box.replaceChildren(matchDetail(r, puuid));
  } catch (e) {
    setStatus(status, e.message, { error: true });
  }
}

function matchDetail(r, puuid) {
  const close = h("button", { onclick: () => $("#match-dialog").close() }, "Close");
  if (r.skipped) return h("div", null, h("div", { class: "dialog-head" }, h("h2", null, r.match_id), close),
    h("p", null, `Skipped: ${r.skipped}`));
  const markers = r.key_moments.map((m) => ({
    t: m.start, color: m.beneficiary === 100 ? cssVar("--blue") : cssVar("--red"), label: describeMoment(m),
  }));
  const chart = areaChart(r.timeline.t, r.timeline.gold_diff, {
    width: 940, height: 240, pad: 10, axes: true, upColor: cssVar("--blue"), downColor: cssVar("--red"), markers,
  });
  const peaks = r.leads.gold_peaks;
  const teamTable = (team) => {
    const rows = r.players.filter((p) => p.team_id === team).map((p) => h("tr", { class: p.puuid === puuid ? "me" : null },
      h("td", null, champName(p.champion), p.carried ? h("span", { class: "chip gold", style: "margin-left:6px" }, "carried") : null),
      h("td", { class: "muted" }, playerLink(p.riot_id)),
      h("td", null, roleLabel(p.position)),
      h("td", { class: "num" }, p.kda.join("/")),
      h("td", { class: "num", title: "Kill participation: this player's kills+assists, over the team's kills in the game" }, pct(p.shares.kp)),
      h("td", { class: "num" }, pct(p.shares.damage)),
      h("td", { class: "num" }, pct(p.shares.gold)),
      h("td", { class: "num", title: "Share of the team's tower/dragon/herald/baron damage" }, pct(p.shares.objectives)),
      h("td", { class: "num" }, `${p.impact_ratio.toFixed(2)}x`),
      h("td", { class: "num muted", title: p.predicted_impact ? `Average impact over their ${p.predicted_impact.games} earlier stored game(s)` : "No earlier stored games for this player" },
        p.predicted_impact ? `${p.predicted_impact.value.toFixed(2)}x` : "n/a"),
      (() => {
        const d = p.predicted_impact ? p.impact_ratio - p.predicted_impact.value : null;
        if (d == null) return h("td", { class: "num muted" }, "n/a");
        const big = Math.abs(d) >= 0.15;
        return h("td", { class: `num ${big ? (d > 0 ? "win-text" : "loss-text") : "muted"}`,
          title: "Actual impact minus predicted. Positive means they had more impact than their history suggested." },
          `${d > 0 ? "+" : ""}${d.toFixed(2)}`);
      })()));
    return h("div", { class: "table-wrap" }, h("table", null,
      h("thead", null, h("tr", null,
        h("th", { class: team === 100 ? "team-blue" : "team-red" },
          `${TEAM[team]} ${r.winner === team ? "(won)" : "(lost)"}`),
        h("th", null, "Player"), h("th", null, "Role"), h("th", { class: "num" }, "KDA"),
        h("th", { class: "num", title: "Kill participation (kills+assists, not exclusive — can add up to more than 100% across the team)" }, "KP"),
        h("th", { class: "num" }, "Damage"), h("th", { class: "num" }, "Gold"), h("th", { class: "num" }, "Obj"),
        h("th", { class: "num", title: "Weighted average of KP/damage/gold share (85%) and objective damage share (15%), divided by the same mix for a typical player in this role. Above 1x means they contributed more than a typical player in that role would; well above (~1.35x+) can tag them as the game's Carried player." }, "Impact"),
        h("th", { class: "num", title: "Predicted impact: the player's average impact over their earlier stored games, before this one. Compare with the actual Impact." }, "Predicted"),
        h("th", { class: "num", title: "Actual impact minus predicted: who over- or under-performed their expectation this game." }, "Δ"))),
      h("tbody", null, rows)));
  };
  return h("div", null,
    h("div", { class: "dialog-head" },
      h("div", null, h("h2", { style: "margin:0" }, `${TEAM[r.winner]} won`),
        h("div", { class: "muted" }, `${r.match_id} · ${queueName(r.queue_id)} · ${mmss(r.duration_s)}`)),
      close),
    h("div", { class: "chips" }, r.tags.map((t) => h("span", { class: "chip" }, neutralTag(t)))),
    h("p", null, r.verdict),
    h("div", { class: "card" }, h("h4", { style: "margin-top:0" }, "Gold difference (Blue up, Red down)"), chart,
      h("div", { class: "legend" },
        h("span", null, `Blue peak +${kfmt(peaks["100"].lead)} at ${mmss(peaks["100"].at)}`),
        h("span", null, `Red peak +${kfmt(peaks["200"].lead)} at ${mmss(peaks["200"].at)}`),
        r.leads.gold_flips.length ? h("span", null, `Lead changed hands at ${r.leads.gold_flips.map(mmss).join(", ")}`) : null)),
    h("div", { class: "card" }, h("h4", { style: "margin-top:0" }, "Key moments"),
      h("ul", { style: "margin:0;padding-left:18px" }, r.key_moments.map((m) => h("li", null, describeMoment(m))))),
    h("div", { class: "card" }, historyLoader(r, puuid), teamTable(100), h("div", { style: "height:10px" }), teamTable(200)));
}

// Predictions only use stored games; this fetches missing earlier games on request (slow: many API calls).
function historyLoader(r, puuid) {
  const missing = r.players.filter((p) => !p.predicted_impact || p.predicted_impact.games < r.prediction_depth);
  if (!missing.length) return null;
  const status = h("span", { class: "status" });
  const button = h("button", { class: "small" }, "Load prediction history");
  button.onclick = () => withButton(button, async () => {
    setStatus(status, "Starting...", { busy: true });
    try {
      const updated = await runJob("match", { match_id: r.match_id, load_history: true }, { statusEl: status, interval: 300 });
      $("#match-detail").replaceChildren(matchDetail(updated, puuid));
    } catch (e) {
      setStatus(status, e.message, { error: true });
    }
  });
  return h("div", { class: "row", style: "margin-bottom:10px;align-items:center;gap:10px" }, button, status,
    h("span", { class: "muted" }, `${missing.length} player(s) have fewer than ${r.prediction_depth} earlier stored games. Loading fetches them from Riot (can take a while).`));
}

// ---------- Tool 2: live advisor ---------------------------------------------------------------------------
function replayAdvisor(matchId) {
  const form = $("#advisor-form");
  form.replay.value = matchId;
  form.riot_id.value = form.riot_id.value || saved.get("riot_id", "");
  showTab("advisor");
  form.requestSubmit();
}

function loadCachedAdvisor() {
  const c = cache.get("advisor");
  if (!c || !c.report.counters.grievous_wounds.sources) return false;
  const form = $("#advisor-form");
  form.riot_id.value = c.riotId;
  form.depth.value = c.depth;
  form.replay.value = c.replay || "";
  renderAdvisor(c.report);
  setStatus($("#advisor-status"), `Showing cached report (${c.report.source}) from ${timeAgo(c.savedAt)}. Click Run advisor to refresh.`);
  return true;
}

async function runAdvisor(form) {
  const status = $("#advisor-status");
  const out = $("#advisor-out");
  const riotId = form.riot_id.value.trim(), depth = form.depth.value;
  const replay = form.replay.value.trim() || null;
  saved.set("riot_id", riotId);
  setStatus(status, "Finding the game...", { busy: true });
  // Render each player's card the moment the server reports it, instead of waiting on the whole roster.
  const enemyGrid = h("div", { class: "grid3" });
  const allyGrid = h("div", { class: "grid3" });
  fill(out,
    h("div", { class: "card muted" }, "Enemy team — loading players as they finish..."), enemyGrid,
    h("h3", null, "Your team"), allyGrid);
  const addPlayers = (cards) => {
    for (const card of cards) {
      if (card.side === "enemy") enemyGrid.append(enemyCard(card));
      else allyGrid.append(allyCard(card));
    }
  };
  try {
    const rep = await runJob("advisor", { riot_id: riotId, depth, replay },
      { statusEl: status, interval: 600, onPartial: addPlayers });
    renderAdvisor(rep);
    setStatus(status, `Done (${rep.source}).`);
    cache.set("advisor", { riotId, depth, replay, report: rep });
  } catch (e) {
    setStatus(status, e.message, { error: true });
  }
}

function threatTable(rows, title) {
  return h("div", { class: "card" }, h("h3", null, title), h("div", { class: "table-wrap" }, h("table", null,
    h("thead", null, h("tr", null, h("th", null, "Champion"), h("th", null, "Player"),
      h("th", { class: "num" }, "Carried wins"), h("th", { class: "num" }, "Avg impact"), h("th", { class: "num" }, "Games"),
      h("th", null, ""))),
    h("tbody", null, rows.map((t) => h("tr", null,
      h("td", null, champName(t.champion)), h("td", { class: "muted" }, playerLink(t.riot_id)),
      h("td", { class: "num" }, `${t.carried_wins}/${t.wins}`),
      h("td", { class: "num" }, t.avg_impact == null ? "n/a" : `${t.avg_impact.toFixed(2)}x`),
      h("td", { class: "num" }, t.games),
      h("td", null, t.flagged ? h("span", { class: "chip bad" }, "threat") : null)))))));
}

function damageBar(split) {
  return h("div", null,
    h("div", { class: "bar", style: "height:14px" },
      h("span", { style: `width:${split.physical * 100}%;background:var(--physical)` }),
      h("span", { style: `width:${split.magic * 100}%;background:var(--magic)` }),
      h("span", { style: `width:${split.true * 100}%;background:var(--true)` })),
    h("div", { class: "legend" },
      h("span", null, h("i", { style: "background:var(--physical)" }), `Physical ${pct(split.physical)}`),
      h("span", null, h("i", { style: "background:var(--magic)" }), `Magic ${pct(split.magic)}`),
      h("span", null, h("i", { style: "background:var(--true)" }), `True ${pct(split.true)}`)));
}

function impactChip(imp) {
  if (!imp) return null;
  return h("span", { class: `chip ${imp.flagged ? "bad" : ""}`, title: `Carried ${imp.carried_wins}/${imp.wins} recent wins over ${imp.games} games` },
    `${imp.flagged ? "Threat" : "Impact"}: ${imp.carried_wins}/${imp.wins} carried wins`,
    imp.avg_impact != null ? ` · ${imp.avg_impact.toFixed(2)}x` : "");
}

function enemyCard(e) {
  const p = e.profile;
  return h("div", { class: "card" },
    h("h3", null, champName(e.champion), " ", h("span", { class: "muted", style: "font-weight:400" }, playerLink(e.riot_id))),
    h("div", { class: "chips" },
      impactChip(e.impact),
      (p.tempo.length ? p.tempo : ["no clear tempo"]).map((t) => h("span", { class: "chip" }, t)),
      e.pool && e.pool.one_trick ? h("span", { class: "chip gold", title: e.pool.on_it ? "Playing their main" : `Not playing it this game` },
        `One-trick: ${champName(e.pool.champion)} (${e.pool.games}/${e.pool.total} games)`) : null,
      e.pool ? h("span", { class: `chip ${e.pool.off_champion ? "bad" : ""}`, title: `Their last ${e.pool.total} games in this queue` },
        `${e.pool.off_champion ? "Off-pick" : "On-pick"}: ${e.pool.on_champion_games}/${e.pool.total} on ${champName(e.champion)}`) : null,
      e.pool && e.pool.role ? h("span", { class: `chip ${e.pool.role.off_role ? "bad" : ""}`,
        title: e.pool.role.playing ? `Playing ${roleLabel(e.pool.role.playing)} this game` : "Their role this game isn't known from the live feed" },
        `${e.pool.role.off_role ? "Off-role" : "Usually"} ${roleLabel(e.pool.role.role)} (${e.pool.role.games}/${e.pool.role.total})`) : null,
      p.lane_gold_diff_14 != null ? h("span", { class: "chip" }, `lane gold @14 ${signed(p.lane_gold_diff_14)}`) : null,
      e.healing.score > 0 ? h("span", { class: "chip", title: e.healing.reasons.join("; ") },
        e.healing.reasons.every((r) => r.startsWith("builds")) ? "healing items" : "heals") : null),
    h("div", { class: "muted", style: "margin-top:6px;font-size:12px" }, `Based on ${p.games} ${p.source}`));
}

function allyCard(a) {
  return h("div", { class: "card" },
    h("h3", null, champName(a.champion), " ", h("span", { class: "muted", style: "font-weight:400" }, playerLink(a.riot_id))),
    h("div", { class: "chips" }, impactChip(a.impact) || h("span", { class: "chip muted" }, "no recent history")));
}

function renderAdvisor(rep) {
  const out = $("#advisor-out");
  const f = rep.focus_target;
  const c = rep.counters, gw = c.grievous_wounds;
  fill(out,
    f ? h("div", { class: "banner" }, h("div", { class: "muted" }, "Focus target"),
      h("div", { class: "big" }, champName(f.champion)),
      h("div", null, playerLink(f.riot_id), `: tagged as the carry in ${f.carried_wins}/${f.wins} recent wins (${pct(f.carry_rate)})`))
      : h("div", { class: "card muted" }, "No enemy has a consistent carry record in their recent wins."),
    h("div", { class: "grid2" },
      threatTable(rep.carry_threats, "Enemy carry threats"),
      h("div", { class: "card" }, h("h3", null, "Counter-itemization"),
        damageBar(c.damage_split),
        h("p", null, c.resist_advice),
        h("p", null, h("strong", null, `Grievous Wounds: ${gw.urgency} priority`), gw.timing ? `, ${gw.timing}` : "",
          gw.sources.length ? "" : ". No enemy healing found."),
        gw.sources.length ? h("ul", { style: "margin:0;padding-left:18px" }, gw.sources.map((x) =>
          h("li", null, h("strong", null, champName(x.champion)), `: ${x.reasons.join("; ") || "some healing"}`))) : null)),
    h("h3", null, "Enemy team"),
    h("div", { class: "grid3" }, rep.enemies.map(enemyCard)),
    rep.ally_carries && rep.ally_carries.length ? h("h3", null, "Your team") : null,
    rep.ally_carries && rep.ally_carries.length
      ? h("div", { class: "grid3" }, rep.ally_carries.map((t) => allyCard({ champion: t.champion, riot_id: t.riot_id, impact: t })))
      : null);
}

// ---------- Tool 3: build sim ------------------------------------------------------------------------------
const ORDERS = ["QWE", "QEW", "WQE", "WEQ", "EQW", "EWQ"];

function select(options, value, attrs = {}) {
  return h("select", attrs, options.map(([v, label]) => h("option", { value: v, selected: v === value ? true : null }, label)));
}

function makeBuilder(root, title, { allowDummy }) {
  const sim = META.sim;
  const champs = Object.keys(sim.champions);
  const f = {
    champion: select(champs.map((c) => [c, c]), champs[0], { class: "wide" }),
    level: h("input", { type: "number", min: 1, max: 18, value: 11, class: "narrow" }),
    order: select(ORDERS.map((o) => [o, o.split("").join(" > ")]), "QEW"),
    items: Array.from({ length: 6 }, (_, i) => h("input", { list: "items-list", placeholder: `Item ${i + 1}` })),
    keystone: select([["", "(none)"], ...sim.keystones.map((k) => [k, k])], ""),
    minor: sim.minor_runes.map((m) => h("input", { type: "checkbox", value: m })),
    shards: Array.from({ length: 3 }, () => select([["", "(none)"], ...sim.shards.map((x) => [x, x.replace("_", " ")])], "")),
    rotation: h("input", { class: "wide", placeholder: "e.g. E W Q AA R" }),
    dummy: { hp: h("input", { type: "number", value: 2500 }), armor: h("input", { type: "number", value: 60 }),
      mr: h("input", { type: "number", value: 50 }) },
  };
  const hint = h("span", { class: "muted", style: "font-size:12px" });
  const updateHint = () => { hint.textContent = `Keys: ${sim.champions[f.champion.value].join(" ")} AA`; };
  f.champion.addEventListener("change", updateHint);
  updateHint();
  const field = (label, ...el) => h("div", { class: "field" }, h("span", null, label), h("div", null, el));
  const champPanel = h("div", null,
    field("Champion", f.champion),
    field("Level / order", h("div", { class: "row" }, f.level, f.order)),
    field("Items", h("div", { class: "items" }, f.items)),
    field("Keystone", f.keystone),
    field("Minor runes", h("div", { class: "checks" }, f.minor.map((c) => h("label", { class: "check" }, c, c.value)))),
    field("Shards", h("div", { class: "row" }, f.shards)),
    field("Rotation", f.rotation, hint));
  const dummyPanel = h("div", null,
    field("Health", f.dummy.hp), field("Armor", f.dummy.armor), field("Magic resist", f.dummy.mr));
  let isDummy = false;
  const modeChamp = h("input", { type: "radio", name: `${title}-mode`, checked: true });
  const modeDummy = h("input", { type: "radio", name: `${title}-mode` });
  const setMode = (dummy) => {
    isDummy = dummy;
    modeDummy.checked = dummy;
    modeChamp.checked = !dummy;
    champPanel.classList.toggle("hidden", dummy);
    dummyPanel.classList.toggle("hidden", !dummy);
  };
  modeChamp.addEventListener("change", () => setMode(false));
  modeDummy.addEventListener("change", () => setMode(true));
  root.replaceChildren(h("div", { class: "builder" }, h("h3", null, title),
    allowDummy ? h("div", { class: "mode" }, h("label", { class: "check" }, modeChamp, "Champion"),
      h("label", { class: "check" }, modeDummy, "Training dummy")) : null,
    champPanel, allowDummy ? dummyPanel : null));
  setMode(false);

  return {
    read() {
      if (isDummy) return { dummy: { hp: +f.dummy.hp.value, armor: +f.dummy.armor.value, mr: +f.dummy.mr.value } };
      return {
        champion: f.champion.value,
        level: +f.level.value,
        skill_order: f.order.value,
        items: f.items.map((i) => i.value.trim()).filter(Boolean),
        runes: {
          keystone: f.keystone.value || null,
          minor: f.minor.filter((c) => c.checked).map((c) => c.value),
          shards: f.shards.map((x) => x.value).filter(Boolean),
        },
        rotation: f.rotation.value.split(/[\s,]+/).filter(Boolean),
      };
    },
    fill(spec) {
      if (spec.dummy) {
        setMode(true);
        f.dummy.hp.value = spec.dummy.hp ?? 2500;
        f.dummy.armor.value = spec.dummy.armor ?? 60;
        f.dummy.mr.value = spec.dummy.mr ?? 50;
        return;
      }
      setMode(false);
      f.champion.value = spec.champion;
      updateHint();
      f.level.value = spec.level ?? 11;
      f.order.value = spec.skill_order ?? "QEW";
      f.items.forEach((input, i) => { input.value = (spec.items || [])[i] || ""; });
      const runes = spec.runes || {};
      f.keystone.value = runes.keystone || "";
      f.minor.forEach((c) => { c.checked = (runes.minor || []).includes(c.value); });
      f.shards.forEach((x, i) => { x.value = (runes.shards || [])[i] || ""; });
      f.rotation.value = (spec.rotation || []).join(" ");
    },
  };
}

let ATTACKER = null, TARGET = null, BUILD_B = null;

function makeBuildB(root) {
  const items = Array.from({ length: 6 }, (_, i) => h("input", { list: "items-list", placeholder: `Item ${i + 1}` }));
  const keystone = select([["", "(same as attacker)"], ...META.sim.keystones.map((k) => [k, k])], "");
  const copy = h("button", { class: "small", type: "button", onclick: () => {
    const a = ATTACKER.read();
    items.forEach((input, i) => { input.value = (a.items || [])[i] || ""; });
  } }, "Copy attacker's items");
  root.replaceChildren(h("div", { class: "builder", style: "margin-top:10px" },
    h("div", { class: "field" }, h("span", null, "Items"), h("div", { class: "items" }, items)),
    h("div", { class: "field" }, h("span", null, "Keystone"), keystone),
    copy));
  return {
    read() {
      const a = ATTACKER.read();
      const out = { items: items.map((i) => i.value.trim()).filter(Boolean) };
      if (keystone.value) out.runes = { ...a.runes, keystone: keystone.value };
      return out;
    },
  };
}

function scenario() {
  const win = $("#sim-window").value;
  return { attacker: ATTACKER.read(), target: TARGET.read(), ...(win ? { window: +win } : {}) };
}

function sideCard(side, stats) {
  const t = side.by_type, total = Math.max(side.damage_dealt, 1);
  return h("div", { class: "card side-result" },
    h("h3", null, side.name),
    stats ? h("div", { class: "muted", style: "font-size:12px;margin:-6px 0 8px" },
      `lvl ${stats.level} · ${stats.hp} HP · ${stats.ad} AD · ${stats.ap} AP · ${stats.attack_speed} AS · `
      + Object.entries(stats.ranks).map(([k, v]) => `${k}${v}`).join(" ")) : null,
    h("div", { class: "big" }, side.damage_dealt, h("span", { class: "muted", style: "font-size:13px;font-weight:400" }, " damage dealt")),
    h("div", { class: "bar", style: "margin:6px 0" },
      h("span", { style: `width:${(t.physical / total) * 100}%;background:var(--physical)` }),
      h("span", { style: `width:${(t.magic / total) * 100}%;background:var(--magic)` }),
      h("span", { style: `width:${(t.true / total) * 100}%;background:var(--true)` })),
    h("div", { class: "legend" },
      h("span", null, h("i", { style: "background:var(--physical)" }), `${t.physical} phys`),
      h("span", null, h("i", { style: "background:var(--magic)" }), `${t.magic} magic`),
      h("span", null, h("i", { style: "background:var(--true)" }), `${t.true} true`)),
    h("p", { style: "margin:10px 0 4px" },
      `HP ${side.hp_end} / ${side.hp_start}`,
      side.healing ? ` · healed ${side.healing}` : "", side.shielding ? ` · shielded ${side.shielding}` : "",
      side.died_at != null ? h("strong", { class: "pos" }, ` · died at ${side.died_at}s`) : ""),
    h("div", { class: "bar" }, h("span", { style: `width:${(side.hp_end / side.hp_start) * 100}%;background:var(--win)` })));
}

function simResult(r, title) {
  return h("div", null,
    title ? h("h3", null, title) : null,
    h("div", { class: "grid2" }, sideCard(r.attacker, r.attacker.stats), sideCard(r.target)),
    h("p", { class: "trade" }, h("span", { class: `pos${r.net_trade >= 0 ? " up" : ""}` }, `${signed(r.net_trade)} HP`),
      h("span", { class: "muted", style: "font-weight:400;font-size:14px" }, ` trade in your favor over ${r.duration}s`)),
    r.assumptions.length ? h("div", { class: "muted", style: "font-size:12px" }, "Assumes: ", r.assumptions.join("; ")) : null,
    r.unmodeled_passives.length ? h("div", { class: "muted", style: "font-size:12px" },
      "Stats only (passive not modeled): ", r.unmodeled_passives.join(", ")) : null,
    h("details", { class: "card", style: "margin-top:10px" }, h("summary", null, `Event log (${r.log.length})`),
      h("div", { class: "table-wrap" }, h("table", { class: "log" }, h("tbody", null, r.log.map((e) => h("tr", null,
        h("td", { class: "num" }, `${e.t.toFixed(2)}s`), h("td", null, e.source), h("td", null, e.what),
        h("td", { class: "num" }, e.type ? e.amount.toFixed(0) : ""), h("td", { class: "muted" }, e.type || ""))))))));
}

async function simAction(kind) {
  const status = $("#sim-status");
  const out = $("#sim-out");
  out.replaceChildren();
  setStatus(status, kind === "breakpoints" ? "Trying every swap..." : "Simulating...", { busy: true });
  try {
    const sc = scenario();
    if (kind === "run") {
      out.replaceChildren(simResult(await runJob("sim_run", { scenario: sc }, { interval: 200 })));
    } else if (kind === "compare") {
      const buildB = BUILD_B.read();
      if (!buildB.items.length) throw new Error("Fill in Build B's items first (open the Build B panel).");
      const { a, b } = await runJob("sim_compare", { scenario: sc, build_b: buildB }, { interval: 250 });
      const dmg = b.attacker.damage_dealt - a.attacker.damage_dealt;
      out.replaceChildren(
        h("div", { class: "banner" }, h("div", { class: "big" },
          `Build B: ${signed(dmg)} damage, ${signed(b.net_trade - a.net_trade)} trade vs A`)),
        simResult(a, "A: current build"), simResult(b, "B: alternative build"));
    } else {
      const { base, rows } = await runJob("sim_breakpoints", { scenario: sc }, { interval: 400 });
      const row = (r) => h("tr", null,
        h("td", { class: `num pos${r.damage >= 0 ? " up" : ""}` }, signed(r.damage)),
        h("td", { class: `num pos${r.net_trade >= 0 ? " up" : ""}` }, signed(r.net_trade)),
        h("td", { class: "num muted" }, `${signed(r.gold)}g`),
        h("td", null, r.change),
        h("td", { class: "muted" }, r.kills_at != null ? `kills at ${r.kills_at}s` : ""));
      const table = (title, list) => h("div", { class: "card" }, h("h3", null, title), h("div", { class: "table-wrap" },
        h("table", null, h("thead", null, h("tr", null, h("th", { class: "num" }, "Damage"), h("th", { class: "num" }, "Trade"),
          h("th", { class: "num" }, "Gold"), h("th", null, "Swap"), h("th", null, ""))), h("tbody", null, list.map(row)))));
      const by = base.target.died_at != null ? "fastest kill" : "damage";
      out.replaceChildren(table(`Best swaps by ${by} (boots are left alone)`, rows.slice(0, 20)), table("Worst swaps", rows.slice(-5)),
        simResult(base, "Baseline"));
    }
    setStatus(status, "");
  } catch (e) {
    setStatus(status, e.message, { error: true });
  }
}

function setupSim() {
  ATTACKER = makeBuilder($("#sim-attacker"), "You (attacker)", { allowDummy: false });
  TARGET = makeBuilder($("#sim-target"), "Target", { allowDummy: true });
  BUILD_B = makeBuildB($("#sim-b"));
  const examples = META.sim.examples;
  const pick = $("#sim-example");
  for (const name of Object.keys(examples)) pick.append(h("option", { value: name }, name.replaceAll("_", " ")));
  pick.addEventListener("change", () => {
    const ex = examples[pick.value];
    if (!ex) return;
    ATTACKER.fill(ex.attacker);
    TARGET.fill(ex.target || { dummy: {} });
    $("#sim-window").value = ex.window ?? "";
  });
  const first = Object.keys(examples)[0];
  if (first) { pick.value = first; pick.dispatchEvent(new Event("change")); }
  $("#sim-run").addEventListener("click", (e) => withButton(e.currentTarget, () => simAction("run")));
  $("#sim-cmp").addEventListener("click", (e) => withButton(e.currentTarget, () => simAction("compare")));
  $("#sim-bp").addEventListener("click", (e) => withButton(e.currentTarget, () => simAction("breakpoints")));
}

// ---------- tuning ------------------------------------------------------------------------------------------
let TUNING = null;
const fmtValue = (v) => (Array.isArray(v) ? v.join(", ") : String(v));

async function loadTuning() {
  try {
    TUNING = await api("/api/tuning");
    renderTuning();
  } catch (e) {
    setStatus($("#tuning-status"), e.message, { error: true });
  }
}

function renderTuning() {
  const out = $("#tuning-out");
  out.replaceChildren(...TUNING.map((g) => h("div", { class: "card tuning-group" }, h("h3", null, g.group),
    h("div", { class: "table-wrap" }, h("table", null,
      h("thead", null, h("tr", null, h("th", null, "Setting"), h("th", null, "Value"), h("th", null, "Default"), h("th", null, ""), h("th", null, ""))),
      h("tbody", null, g.settings.map((st) => {
        const input = h("input", { value: fmtValue(st.value), "data-key": st.key, "data-current": fmtValue(st.value),
          class: Array.isArray(st.default) ? "tuple" : null });
        const tr = h("tr", { class: fmtValue(st.value) !== fmtValue(st.default) ? "changed" : null });
        const mark = () => tr.classList.toggle("changed", input.value.replace(/\s/g, "") !== fmtValue(st.default).replace(/\s/g, ""));
        input.addEventListener("input", mark);
        tr.append(
          h("td", null, st.label),
          h("td", null, input),
          h("td", { class: "muted" }, fmtValue(st.default)),
          h("td", null, h("button", { class: "small", onclick: () => { input.value = fmtValue(st.default); mark(); } }, "Default")),
          h("td", { class: "help" }, st.help));
        return tr;
      })))))));
}

async function saveTuning() {
  const status = $("#tuning-status");
  const values = {};
  for (const input of $$("#tuning-out input[data-key]")) {
    if (input.value.replace(/\s/g, "") !== input.dataset.current.replace(/\s/g, "")) values[input.dataset.key] = input.value;
  }
  if (!Object.keys(values).length) return setStatus(status, "Nothing changed.");
  try {
    TUNING = await api("/api/tuning", { values });
    renderTuning();
    setStatus(status, `Saved ${Object.keys(values).length} change(s).`);
  } catch (e) {
    setStatus(status, e.message, { error: true });
  }
}

async function resetTuning() {
  if (!confirm("Reset every tuning value to its default?")) return;
  TUNING = await api("/api/tuning/reset", {});
  renderTuning();
  setStatus($("#tuning-status"), "All values reset to defaults.");
}

// ---------- init --------------------------------------------------------------------------------------------
async function init() {
  $$("#tabs button").forEach((b) => b.addEventListener("click", () => showTab(b.dataset.tab)));
  const riotId = saved.get("riot_id", DEFAULT_RIOT_ID);
  $("#games-form").riot_id.value = riotId;
  $("#advisor-form").riot_id.value = riotId;

  $("#games-form").addEventListener("submit", (e) => {
    e.preventDefault();
    withButton(e.submitter || $("#games-form button.primary"), () => analyzeGames(e.target));
  });
  $("#match-open").addEventListener("click", () => {
    const form = $("#games-form");
    const id = form.match_id.value.trim();
    if (id) openMatch(id, null);
  });
  $("#advisor-form").addEventListener("submit", (e) => {
    e.preventDefault();
    withButton($("#advisor-form button.primary"), () => runAdvisor(e.target));
  });
  $("#match-dialog").addEventListener("click", (e) => { if (e.target.id === "match-dialog") e.target.close(); });
  $("#tuning-save").addEventListener("click", saveTuning);
  $("#tuning-reset").addEventListener("click", resetTuning);

  const status = $("#sim-status");
  setStatus(status, "Loading champion and item data...", { busy: true });
  try {
    META = await api("/api/meta");
    const queue = $("#games-form").queue;
    for (const [id, name] of Object.entries(META.queues)) queue.append(h("option", { value: id }, name));
    $("#items-list").replaceChildren(...META.sim.items.map((name) => h("option", { value: name })));
    if (!(await resumeGamesJob())) loadCachedGames();
    loadCachedAdvisor();
    setupSim();
    setStatus(status, "");
  } catch (e) {
    setStatus(status, `Couldn't load game data: ${e.message}`, { error: true });
  }
  showTab(saved.get("tab", "games"));
}

init();
