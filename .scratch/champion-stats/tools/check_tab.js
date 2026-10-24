const { chromium } = require("playwright");
const assert = (c, m) => { if (!c) { console.error("FAIL:", m); process.exitCode = 1; } else console.log("ok:", m); };
// Deterministic synthetic rows.
let seed = 7; const rnd = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
const pick = (a) => a[Math.floor(rnd() * a.length)];
const rows = Array.from({ length: 40 }, (_, i) => ({
  match_id: `NA1_${i}`, patch: "15.19", queue: 420, start: i, duration_s: 1800, win: rnd() < 0.55, champion: "Lillia",
  role: "JUNGLE", kills: 5, deaths: 3, assists: 7, cs: 200,
  allies: { TOP: pick(["Garen", "Darius"]), MIDDLE: "Ahri", BOTTOM: "Jinx", UTILITY: "Lulu" },
  enemies: { TOP: pick(["Aatrox", "Fiora", "Jax"]), JUNGLE: pick(["Graves", "Viego", "Kindred"]),
             MIDDLE: pick(["Syndra", "Zed"]), BOTTOM: "Kaisa", UTILITY: pick(["Thresh", "Nautilus"]) },
}));
const data = { puuid: "p", riot_id: "Aeoen#NA1", champion: "Lillia", queue: "solo", rows, savedAt: Date.now() };
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1280, height: 1400 } });
  const errors = []; page.on("pageerror", (e) => errors.push(e.message));
  await page.addInitScript((d) => { localStorage.setItem("cache:champstats", JSON.stringify(d)); localStorage.setItem("tab", "champstats"); }, data);
  await page.goto("http://127.0.0.1:8799/");
  await page.waitForSelector("#cs-out .cs-table");
  const banner = () => page.textContent(".cs-banner");
  assert((await banner()).startsWith("40 games"), "banner shows 40 games");
  const wins = rows.filter((r) => r.win).length;
  assert((await page.textContent(".cs-summary")).includes(`${wins}–${40 - wins}`), "summary W–L");
  const tables = await page.$$eval(".cs-cut h3", (hs) => hs.map((x) => x.textContent));
  assert(tables[0] === "Matchup (vs enemy Jungle)" && tables.length === 5, "matchup first, 4 other enemy roles: " + tables);
  // Click Graves in matchup.
  const graves = rows.filter((r) => r.enemies.JUNGLE === "Graves");
  await page.click(".cs-cut:nth-of-type(1) tbody tr:has-text('Graves')");
  assert((await banner()).startsWith(`${graves.length} of 40 games match`), `filter to Graves (${graves.length})`);
  assert(await page.isVisible(".cs-chips .chip:has-text('Matchup: Graves')"), "chip shown");
  assert((await page.$$(".cs-cut:nth-of-type(1) tbody tr")).length === 3, "matchup still lists alternatives");
  assert(await page.isVisible(".cs-cut:nth-of-type(1) tr.selected:has-text('Graves')"), "selected row highlighted");
  // Stack: enemy top Aatrox.
  const both = graves.filter((r) => r.enemies.TOP === "Aatrox");
  await page.click(".cs-cut:has(h3:text('Enemy Top')) tbody tr:has-text('Aatrox')");
  assert((await banner()).startsWith(`${both.length} of 40 games match`), `stacked Graves+Aatrox (${both.length})`);
  // Swap matchup to Viego keeps Aatrox.
  const viego = rows.filter((r) => r.enemies.JUNGLE === "Viego" && r.enemies.TOP === "Aatrox");
  await page.click(".cs-cut:nth-of-type(1) tbody tr:has-text('Viego')");
  assert((await banner()).startsWith(`${viego.length} of 40 games match`), `swap to Viego (${viego.length})`);
  assert((await page.$$(".cs-chips .chip")).length === 2, "two chips after swap");
  await page.screenshot({ path: process.argv[2] + "/champstats.png", fullPage: true });
  await page.click(".cs-chips .chip:has-text('Viego') .chip-x");
  assert((await page.$$(".cs-chips .chip")).length === 1, "chip x removes one");
  await page.click(".cs-chips button:text('Clear all')");
  assert((await banner()).startsWith("40 games"), "clear all");
  // Sorting by Games ascending/descending.
  await page.click(".cs-cut:nth-of-type(1) th:text('Games')");
  const g = await page.$$eval(".cs-cut:nth-of-type(1) tbody tr td:nth-child(2)", (t) => t.map((x) => +x.textContent));
  assert(g.join() === [...g].sort((a, b) => b - a).join(), "sort by games desc " + g);
  assert(!errors.length, "no page errors " + errors);
  await browser.close();
})();
