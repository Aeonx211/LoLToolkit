// Drives the Champion Stats tab against seeded rows: node check_tab.js <screenshot dir> [port]
const { chromium } = require("playwright");
const assert = (c, m) => { if (!c) { console.error("FAIL:", m); process.exitCode = 1; } else console.log("ok:", m); };
const PORT = process.argv[3] || 8799;
let seed = 7; const rnd = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
const pick = (a) => a[Math.floor(rnd() * a.length)];
const ITEMS = { 6653: "Liandry's Torment", 4633: "Riftmaker", 3116: "Rylai's Crystal Scepter", 3157: "Zhonya's Hourglass",
                3020: "Sorcerer's Shoes", 3111: "Mercury's Treads", 1103: "Mosstomper Seedling", 1102: "Gustwalker Hatchling" };
const rows = Array.from({ length: 40 }, (_, i) => {
  const items = [pick([6653, 4633]), pick([3116, 3157])];
  if (rnd() < 0.8) items.push(items[0] === 6653 ? 4633 : 6653);
  const keystone = pick([8128, 8010]);
  const runes = [keystone, 8126, 8138, 8106, 8234, 8237];
  const mine5 = 30 + Math.floor(rnd() * 10), theirs5 = 30 + Math.floor(rnd() * 10);
  return {
    match_id: `NA1_${i}`, patch: i < 15 ? "15.18" : "15.19", queue: 420, start: i, duration_s: 1200 + i * 45,
    win: rnd() < 0.55, champion: "Lillia", role: "JUNGLE", kills: 5, deaths: 3, assists: 7, cs: 200,
    allies: { TOP: pick(["Garen", "Darius"]), MIDDLE: "Ahri", BOTTOM: "Jinx", UTILITY: "Lulu" },
    enemies: { TOP: pick(["Aatrox", "Fiora", "Jax"]), JUNGLE: pick(["Graves", "Viego", "Kindred"]),
               MIDDLE: pick(["Syndra", "Zed"]), BOTTOM: "Kaisa", UTILITY: pick(["Thresh", "Nautilus"]) },
    length: ["<25", "25–30", "30–35", "35+"][Math.max(0, Math.min(3, Math.floor((1200 + i * 45) / 300) - 4))],
    items, boots: pick([3020, 3111]), pet: pick([1103, 1102]),
    keystone, primary_tree: 8100, secondary_tree: 8200, runes, shards: [5008, 5008, 5011],
    page: [...runes, 5008, 5008, 5011].join("-"),
    rune_values: { [keystone]: [800 + Math.floor(rnd() * 400), 10, 0], 8126: [300, 0, 0] },  // Conqueror's var2 has no label
    pace: { 3: [18, 18], 5: [mine5, theirs5], 8: [60, 55], 10: [80, 75] },
    jungle_cs_10: 60, enemy_jungle_kills: 4, first_dragon: pick(["us", "them", null]), first_herald: pick(["us", "them"]),
  };
});
const names = { items: ITEMS, runes: { 8128: "Dark Harvest", 8010: "Conqueror", 8126: "Cheap Shot", 8138: "Eyeball Collection",
  8106: "Ultimate Hunter", 8234: "Celerity", 8237: "Scorch" }, trees: { 8100: "Domination", 8200: "Sorcery" },
  shards: { 5008: "Adaptive Force", 5011: "Health" }, rune_labels: { 8128: ["Total damage", "Souls collected", null], 8010: ["Total healing", null, null] },
  rune_labels_verified: [8010] };
const data = { puuid: "p", riot_id: "Aeoen#NA1", champion: "Lillia", queue: "solo", rows, names, savedAt: Date.now() };
const count = (f) => rows.filter(f).length;
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1280, height: 1400 } });
  const errors = []; page.on("pageerror", (e) => errors.push(e.message));
  await page.addInitScript((d) => {
    if (!sessionStorage.getItem("seeded")) {
      localStorage.clear();
      localStorage.setItem("cache:champstats", JSON.stringify(d)); localStorage.setItem("tab", "champstats");
      sessionStorage.setItem("seeded", "1");
    }
  }, data);
  await page.goto(`http://127.0.0.1:${PORT}/`);
  await page.waitForSelector("#cs-out .cs-table");
  const banner = () => page.textContent(".cs-banner");
  const table = (title) => `.cs-cut:has(h3:text-is("${title}"))`;
  const sections = await page.$$eval(".cs-section h2", (hs) => hs.map((x) => x.textContent));
  assert(sections.join() === "Matchups,Allies,Builds,Runes,Camp Pace,Game Length", "sections " + sections);
  assert((await page.$$(".cs-cut h3:text-matches('^Ally ')")).length === 4, "4 ally tables");
  // Matchup filter (ticket 01 behaviour).
  await page.click(`${table("Matchup (vs enemy Jungle)")} tbody tr:has-text('Graves')`);
  assert((await banner()).startsWith(`${count((r) => r.enemies.JUNGLE === "Graves")} of 40`), "matchup filter");
  await page.click(".cs-chips button:text('Clear all')");
  // Item slot + multi "any slot" AND.
  await page.click(`${table("Item 1")} tbody tr:has-text('Riftmaker')`);
  assert((await banner()).startsWith(`${count((r) => r.items[0] === 4633)} of 40`), "slot 1 = Riftmaker");
  await page.click(".cs-chips button:text('Clear all')");
  await page.click(`${table("Any slot")} tbody tr:has-text('Riftmaker')`);
  await page.click(`${table("Any slot")} tbody tr:has-text('Rylai')`);
  const both = count((r) => r.items.includes(4633) && r.items.includes(3116));
  assert((await banner()).startsWith(`${both} of 40`), `any-slot Riftmaker AND Rylai (${both})`);
  assert((await page.$$(".cs-chips .chip")).length === 2, "two any-slot chips");
  await page.click(".cs-chips button:text('Clear all')");
  // Paths.
  const paths = {};
  for (const r of rows) if (r.items.length >= 3) paths[r.items.slice(0, 3).join(",")] = (paths[r.items.slice(0, 3).join(",")] || 0) + 1;
  const top = Object.entries(paths).sort((a, b) => b[1] - a[1])[0];
  assert((await page.textContent(".cs-path:first-child")).includes(`${top[1]} games`), "most common path count");
  await page.click(".cs-path:first-child");
  assert((await banner()).startsWith(`${top[1]} of 40`), "clicking path filters");
  await page.click(".cs-chips button:text('Clear all')");
  // Runes.
  await page.click(`${table("Keystone")} tbody tr:has-text('Conqueror')`);
  assert((await banner()).startsWith(`${count((r) => r.keystone === 8010)} of 40`), "keystone filter");
  await page.click(".cs-chips button:text('Clear all')");
  const runeValues = ".cs-cut:has(h3:has-text('Rune values'))";
  assert(await page.isVisible(`${runeValues} tr:has-text('Dark Harvest') .chip:text('unverified')`), "unverified rune marked");
  assert(!(await page.isVisible(`${runeValues} tr:has-text('Conqueror') .chip`)), "verified rune not marked");
  assert(await page.isVisible(`${runeValues} td:text('var1')`), "unlabeled rune shows raw var");
  assert(await page.isVisible(`${runeValues} tr:has-text('Conqueror') td:text('var2')`), "unlabeled non-zero slot shows raw var");
  // Camp pace.
  await page.click(`${table("Camp pace at 5:00")} tbody tr:has-text('Ahead')`);
  assert((await banner()).startsWith(`${count((r) => r.pace[5][0] > r.pace[5][1])} of 40`), "pace ahead at 5");
  assert(await page.isVisible(".cs-cut h3:text('Camp pace vs enemy jungler')"), "pace table");
  await page.click(`${table("First dragon")} tbody tr:has-text('Nobody')`);
  assert((await banner()).startsWith(`${count((r) => r.pace[5][0] > r.pace[5][1] && !r.first_dragon)} of 40`), "first dragon nobody");
  // Game length keeps bucket order by default.
  await page.click(".cs-chips button:text('Clear all')");
  const lengths = await page.$$eval(`${table("Game length (minutes)")} tbody td:first-child`, (t) => t.map((x) => x.textContent));
  assert(lengths.join() === "<25,25–30,30–35,35+", "length order " + lengths);
  // Slice controls: patch range and min games.
  await page.selectOption("select[name=patch_from]", "15.19");
  assert((await banner()).startsWith("25 games"), "patch from 15.19");
  await page.fill("input[name=min_games]", "1");
  assert((await page.$$(".cs-table tr.thin")).length === 0, "min games 1 → nothing greyed");
  await page.click(`${table("Boots")} tbody tr:has-text('Mercury')`);
  // Reload: view restored.
  await page.reload();
  await page.waitForSelector("#cs-out .cs-table");
  assert((await banner()).startsWith(`${count((r) => r.patch === "15.19" && r.boots === 3111)} of 25`), "stack + patch restored after reload");
  assert(await page.inputValue("#cs-form select[name=queue]") === "solo", "queue toggle defaults to solo");
  // All patches: one click clears the patch range (the filter stack stays).
  assert(!(await page.isDisabled("#cs-form button[name=all_patches]")), "all patches enabled while a range is set");
  await page.click("#cs-form button[name=all_patches]");
  assert((await banner()).startsWith(`${count((r) => r.boots === 3111)} of 40`), "all patches widens back to every game");
  assert(await page.inputValue("select[name=patch_from]") === "" && await page.inputValue("select[name=patch_to]") === "",
    "all patches resets both ends");
  assert(await page.isDisabled("#cs-form button[name=all_patches]"), "all patches disabled when already all");
  // Layout: no table is wider than its card, at desktop and phone widths.
  for (const width of [1280, 390]) {
    await page.setViewportSize({ width, height: 1000 });
    const over = await page.$$eval("#cs-out .cs-cut", (cs) => cs.filter((c) => c.scrollWidth > c.clientWidth + 1)
      .map((c) => c.querySelector("h3")?.textContent));
    assert(!over.length, `tables fit their cards at ${width}px ${over}`);
  }
  await page.setViewportSize({ width: 1280, height: 1400 });
  await page.screenshot({ path: process.argv[2] + "/champstats.png", fullPage: true });
  assert(!errors.length, "no page errors " + errors);
  await browser.close();
})();
