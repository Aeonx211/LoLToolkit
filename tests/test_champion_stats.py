import unittest

from champion_stats import backfill, game_row
from data_layer import DataLayer, Store

from .fixtures import build_match

ME = "puuid-2"  # participant 2: blue jungle in the fixtures


def lillia_match(match_id="NA1_1", duration_min=30, winner=100, queue_id=420, champion="Lillia", **kw):
    match, timeline = build_match(duration_min=duration_min, winner=winner, match_id=match_id, queue_id=queue_id, **kw)
    info = match["info"]
    info["gameVersion"] = "15.19.712.1234"
    for p in info["participants"]:
        p["totalMinionsKilled"] = 10 * p["participantId"]
        p["neutralMinionsKilled"] = 100 if p["participantId"] in (2, 7) else 0
    info["participants"][1]["championName"] = champion
    return match, timeline


class GameRowTests(unittest.TestCase):
    def test_basic_facts(self):
        row = game_row(*lillia_match(), ME)
        self.assertEqual(row["match_id"], "NA1_1")
        self.assertEqual(row["patch"], "15.19")
        self.assertEqual(row["queue"], 420)
        self.assertEqual(row["duration_s"], 1800)
        self.assertTrue(row["win"])
        self.assertEqual(row["role"], "JUNGLE")
        self.assertEqual(row["cs"], 120)

    def test_allies_and_enemies_by_role(self):
        row = game_row(*lillia_match(), ME)
        self.assertEqual(row["enemies"], {"TOP": "Champ6", "JUNGLE": "Champ7", "MIDDLE": "Champ8",
                                          "BOTTOM": "Champ9", "UTILITY": "Champ10"})
        self.assertEqual(row["allies"], {"TOP": "Champ1", "MIDDLE": "Champ3", "BOTTOM": "Champ4", "UTILITY": "Champ5"})

    def test_missing_role_is_left_out(self):
        match, timeline = lillia_match()
        match["info"]["participants"][7]["teamPosition"] = ""
        row = game_row(match, timeline, ME)
        self.assertNotIn("MIDDLE", row["enemies"])
        self.assertEqual(len(row["enemies"]), 4)

    def test_loss(self):
        self.assertFalse(game_row(*lillia_match(winner=200), ME)["win"])

    def test_remake_gives_no_row(self):
        self.assertIsNone(game_row(*lillia_match(duration_min=3), ME))

    def test_early_surrender_gives_no_row(self):
        match, timeline = lillia_match()
        for p in match["info"]["participants"]:
            p["gameEndedInEarlySurrender"] = True
        self.assertIsNone(game_row(match, timeline, ME))

    def test_player_not_in_match(self):
        self.assertIsNone(game_row(*lillia_match(), "someone-else"))


class FakeClient:
    """Serves a fixed match history; counts what was fetched."""

    def __init__(self, games):
        self.games = {m["metadata"]["matchId"]: (m, t) for m, t in games}
        self.order = sorted(self.games, key=lambda i: int(i.split("_")[1]), reverse=True)
        self.match_calls, self.timeline_calls = [], []

    def match_ids(self, puuid, count=20, start=0, queue=None, priority=None, **kw):
        ids = [i for i in self.order if queue is None or self.games[i][0]["info"]["queueId"] == queue]
        return ids[start:start + count]

    def match(self, match_id, priority=None):
        self.match_calls.append(match_id)
        return self.games[match_id][0]

    def timeline(self, match_id, priority=None):
        self.timeline_calls.append(match_id)
        return self.games[match_id][1]


def history(n, lillia_every=2):
    """n solo games, newest first by id; every `lillia_every`th one on Lillia."""
    return [lillia_match(f"NA1_{i}", champion="Lillia" if i % lillia_every == 0 else "Graves") for i in range(1, n + 1)]


class BackfillTests(unittest.TestCase):
    def layer(self, games):
        client = FakeClient(games)
        store = Store(":memory:")
        self.addCleanup(store.close)
        return DataLayer(client, store), client

    def test_keeps_only_focus_champion_and_fetches_only_their_timelines(self):
        layer, client = self.layer(history(10))
        ids = backfill(layer, ME, "Lillia", (420,), target=100)
        self.assertEqual(sorted(ids), sorted(f"NA1_{i}" for i in (2, 4, 6, 8, 10)))
        self.assertEqual(sorted(client.timeline_calls), sorted(ids))

    def test_champion_name_is_case_insensitive(self):
        layer, _ = self.layer(history(4))
        self.assertEqual(len(backfill(layer, ME, "lillia", (420,), target=100)), 2)

    def test_stops_at_target_newest_first(self):
        layer, client = self.layer(history(300))
        ids = backfill(layer, ME, "Lillia", (420,), target=3)
        self.assertEqual(ids, ["NA1_300", "NA1_298", "NA1_296"])
        self.assertLess(len(client.match_calls), 20)

    def test_never_refetches_stored_matches(self):
        layer, client = self.layer(history(10))
        backfill(layer, ME, "Lillia", (420,), target=100)
        client.match_calls.clear()
        client.timeline_calls.clear()
        ids = backfill(layer, ME, "Lillia", (420,), target=100)
        self.assertEqual(len(ids), 5)
        self.assertEqual(client.match_calls, [])
        self.assertEqual(client.timeline_calls, [])

    def test_remakes_dont_count_toward_target(self):
        games = [lillia_match("NA1_3"), lillia_match("NA1_2", duration_min=3), lillia_match("NA1_1")]
        layer, _ = self.layer(games)
        self.assertEqual(backfill(layer, ME, "Lillia", (420,), target=2), ["NA1_3", "NA1_1"])

    def test_merges_queues_newest_first(self):
        games = [lillia_match("NA1_1", queue_id=420), lillia_match("NA1_2", queue_id=440),
                 lillia_match("NA1_3", queue_id=420)]
        layer, _ = self.layer(games)
        self.assertEqual(backfill(layer, ME, "Lillia", (420, 440), target=100), ["NA1_3", "NA1_2", "NA1_1"])
        self.assertEqual(backfill(layer, ME, "Lillia", (440,), target=100), ["NA1_2"])

    def test_progress_reports(self):
        layer, _ = self.layer(history(4))
        seen = []
        backfill(layer, ME, "Lillia", (420,), target=100, progress=seen.append)
        self.assertTrue(seen)
        self.assertIn("2 kept", seen[-1])


# Minimal Data Dragon item data: just the fields item classification reads, shaped like patch 16.20's item.json
# (tier-2 boots upgrade into tier-3 boots; a missing `into`/`from` means none).
ITEMS = {
    "1001": {"name": "Boots", "tags": ["Boots"], "into": ["3020", "3111", "3008"], "gold": {"total": 300}},
    "3020": {"name": "Sorcerer's Shoes", "tags": ["Boots", "MagicPenetration"], "from": ["1001"], "into": ["3175"],
             "gold": {"total": 1100}},
    "3175": {"name": "Spellslinger's Shoes", "tags": ["Boots"], "from": ["3020"], "gold": {"total": 1100}},
    "3111": {"name": "Mercury's Treads", "tags": ["Boots", "SpellBlock", "Tenacity"], "from": ["1001", "1033"],
             "into": ["3173"], "gold": {"total": 1250}},
    "3006": {"name": "Berserker's Greaves", "tags": ["AttackSpeed", "Boots"], "from": ["1001", "1042", "1042"],
             "into": ["3172"], "gold": {"total": 1100}},
    "3172": {"name": "Gunmetal Greaves", "tags": ["AttackSpeed", "LifeSteal", "NonbootsMovement"], "from": ["3006"],
             "gold": {"total": 1100}},  # really ships without the Boots tag
    "3008": {"name": "Gluttonous Greaves", "tags": ["LifeSteal", "SpellVamp", "Boots"], "from": ["1001"],
             "into": ["3168"], "gold": {"total": 1000}},
    "1052": {"name": "Amplifying Tome", "tags": [], "into": ["3916"], "gold": {"total": 400}},
    "3916": {"name": "Oblivion Orb", "tags": [], "into": ["3165"], "gold": {"total": 800}},
    "6653": {"name": "Liandry's Torment", "tags": [], "into": [], "gold": {"total": 3000}},
    "3116": {"name": "Rylai's Crystal Scepter", "tags": [], "into": [], "gold": {"total": 2600}},
    "4633": {"name": "Riftmaker", "tags": [], "into": [], "gold": {"total": 3100}},
    "3157": {"name": "Zhonya's Hourglass", "tags": [], "into": [], "gold": {"total": 3250}},
    "2003": {"name": "Health Potion", "tags": ["Consumable"], "into": [], "gold": {"total": 50}},
    "1103": {"name": "Mosstomper Seedling", "tags": ["Jungle"], "gold": {"total": 450}},
    "3364": {"name": "Oracle Lens", "tags": ["Active", "Trinket", "Vision"], "gold": {"total": 0}},
}


def with_events(timeline, events):
    """Append (seconds, event) pairs to the frame covering each time."""
    frames = timeline["info"]["frames"]
    for t, ev in events:
        frames[min(int(t // 60) + 1, len(frames) - 1)]["events"].append({"timestamp": int(t * 1000), **ev})
    return timeline


def buy(t, item, pid=2):
    return t, {"type": "ITEM_PURCHASED", "participantId": pid, "itemId": item}


class GameLengthTests(unittest.TestCase):
    def test_buckets(self):
        for minutes, bucket in ((20, "<25"), (25, "25–30"), (29, "25–30"), (30, "30–35"), (40, "35+")):
            self.assertEqual(game_row(*lillia_match(duration_min=minutes), ME)["length"], bucket)


class BuildTests(unittest.TestCase):
    def row(self, events):
        match, timeline = lillia_match()
        return game_row(match, with_events(timeline, events), ME, ITEMS)

    def test_completed_items_in_completion_order(self):
        row = self.row([buy(10, 1103), buy(20, 2003), buy(300, 1001), buy(400, 1052), buy(500, 3916),
                        buy(700, 6653), buy(900, 3020), buy(1100, 4633), buy(1300, 3116)])
        self.assertEqual(row["items"], [6653, 4633, 3116])
        self.assertEqual(row["boots"], 3020)
        self.assertEqual(row["pet"], 1103)

    def test_undo_removes_item(self):
        row = self.row([buy(700, 6653), (705, {"type": "ITEM_UNDO", "participantId": 2, "beforeId": 6653, "afterId": 0}),
                        buy(800, 3116)])
        self.assertEqual(row["items"], [3116])

    def test_sold_item_keeps_its_slot(self):
        row = self.row([buy(700, 6653), buy(900, 3116), (1500, {"type": "ITEM_SOLD", "participantId": 2, "itemId": 6653}),
                        buy(1600, 3157)])
        self.assertEqual(row["items"], [6653, 3116, 3157])

    def test_last_completed_boots_win(self):
        row = self.row([buy(300, 1001), buy(600, 3020), (601, {"type": "ITEM_SOLD", "participantId": 2, "itemId": 3020}),
                        buy(700, 3111)])
        self.assertEqual(row["boots"], 3111)

    def test_tier_two_boots_are_completed_boots(self):
        # Real games: tier-2 boots list their tier-3 upgrade under `into`, and most games never buy the upgrade.
        row = self.row([buy(300, 1001), buy(600, 3008), buy(700, 6653)])
        self.assertEqual(row["boots"], 3008)
        self.assertEqual(row["items"], [6653])

    def test_tier_three_upgrade_replaces_tier_two_boots(self):
        row = self.row([buy(300, 1001), buy(600, 3020), buy(1500, 3175)])
        self.assertEqual(row["boots"], 3175)

    def test_untagged_tier_three_boots_still_count(self):
        row = self.row([buy(600, 3006), buy(1500, 3172)])
        self.assertEqual((row["boots"], row["items"]), (3172, []))

    def test_untagged_boots_are_never_legendary(self):
        # A Boots-less tier-3 boot that ever cost legendary money must stay boots, not become an item.
        match, timeline = lillia_match()
        items = {**ITEMS, "3172": {**ITEMS["3172"], "gold": {"total": 2500}}}
        row = game_row(match, with_events(timeline, [buy(600, 3006), buy(1500, 3172)]), ME, items)
        self.assertEqual((row["boots"], row["items"]), (3172, []))

    def test_basic_boots_alone_are_not_completed(self):
        self.assertIsNone(self.row([buy(300, 1001)])["boots"])

    def test_trinket_swap_and_pet_are_not_items(self):
        # Real timelines log the pet buy and the Oracle Lens swap as ITEM_PURCHASED.
        row = self.row([buy(9, 1103), buy(975, 3364), buy(1000, 6653)])
        self.assertEqual((row["items"], row["boots"], row["pet"]), ([6653], None, 1103))

    def test_undo_of_a_sale_keeps_the_item(self):
        # Undoing a sale logs beforeId 0 / afterId item; the item was already counted when bought.
        row = self.row([buy(700, 6653), (900, {"type": "ITEM_SOLD", "participantId": 2, "itemId": 6653}),
                        (902, {"type": "ITEM_UNDO", "participantId": 2, "beforeId": 0, "afterId": 6653})])
        self.assertEqual(row["items"], [6653])

    def test_other_players_purchases_ignored(self):
        self.assertEqual(self.row([buy(700, 6653, pid=3)])["items"], [])

    def test_no_item_data_gives_empty_build(self):
        match, timeline = lillia_match()
        row = game_row(match, with_events(timeline, [buy(700, 6653)]), ME)
        self.assertEqual((row["items"], row["boots"], row["pet"]), ([], None, None))


PERKS = {
    "statPerks": {"offense": 5008, "flex": 5008, "defense": 5011},
    "styles": [
        {"description": "primaryStyle", "style": 8100, "selections": [
            {"perk": 8128, "var1": 950, "var2": 12, "var3": 0}, {"perk": 8126, "var1": 400, "var2": 0, "var3": 0},
            {"perk": 8138, "var1": 18, "var2": 0, "var3": 0}, {"perk": 8106, "var1": 5, "var2": 0, "var3": 0}]},
        {"description": "subStyle", "style": 8200, "selections": [
            {"perk": 8234, "var1": 3000, "var2": 0, "var3": 0}, {"perk": 8237, "var1": 600, "var2": 0, "var3": 0}]},
    ],
}


class RuneTests(unittest.TestCase):
    def test_verified_runes_have_labels(self):
        from champion_stats.rune_labels import RUNE_VALUE_LABELS, VERIFIED_RUNES
        self.assertLessEqual(VERIFIED_RUNES, set(RUNE_VALUE_LABELS))

    def test_rune_page(self):
        match, timeline = lillia_match()
        match["info"]["participants"][1]["perks"] = PERKS
        row = game_row(match, timeline, ME)
        self.assertEqual(row["keystone"], 8128)
        self.assertEqual((row["primary_tree"], row["secondary_tree"]), (8100, 8200))
        self.assertEqual(row["runes"], [8128, 8126, 8138, 8106, 8234, 8237])
        self.assertEqual(row["shards"], [5008, 5008, 5011])
        self.assertEqual(row["rune_values"]["8128"], [950, 12, 0])
        self.assertEqual(row["page"], "8128-8126-8138-8106-8234-8237-5008-5008-5011")

    def test_missing_perks(self):
        row = game_row(*lillia_match(), ME)
        self.assertIsNone(row["keystone"])
        self.assertEqual(row["runes"], [])


class CampPaceTests(unittest.TestCase):
    def match(self, mine, theirs, **kw):
        match, timeline = lillia_match(**kw)
        for minute, frame in enumerate(timeline["info"]["frames"]):
            frame["participantFrames"]["2"]["jungleMinionsKilled"] = mine(minute)
            frame["participantFrames"]["7"]["jungleMinionsKilled"] = theirs(minute)
        return match, timeline

    def test_pace_at_marks(self):
        row = game_row(*self.match(lambda m: 8 * m, lambda m: 6 * m), ME)
        self.assertEqual(row["pace"], {"3": [24, 18], "5": [40, 30], "8": [64, 48], "10": [80, 60]})

    def test_short_game_has_no_late_marks(self):
        match, timeline = self.match(lambda m: m, lambda m: m, duration_min=30)
        del timeline["info"]["frames"][9:]
        self.assertEqual(sorted(game_row(match, timeline, ME)["pace"]), ["3", "5", "8"])

    def test_jungle_end_of_game_stats(self):
        match, timeline = lillia_match()
        me = match["info"]["participants"][1]
        me["challenges"] = {"jungleCsBefore10Minutes": 62.0}
        me["totalEnemyJungleMinionsKilled"] = 14
        row = game_row(match, timeline, ME)
        self.assertEqual((row["jungle_cs_10"], row["enemy_jungle_kills"]), (62, 14))

    def test_enemy_jungle_ignores_challenge_monster_count(self):
        # challenges.enemyJungleMonsterKills counts something smaller than CS (20 vs 26 in a real game), so it
        # mustn't stand in for totalEnemyJungleMinionsKilled.
        match, timeline = lillia_match()
        match["info"]["participants"][1]["challenges"] = {"enemyJungleMonsterKills": 20}
        self.assertEqual(game_row(match, timeline, ME)["enemy_jungle_kills"], 0)

    def test_first_objectives(self):
        match, timeline = build_match(objectives=[(400, 200, "DRAGON"), (500, 100, "RIFTHERALD"), (900, 100, "DRAGON")])
        match["info"]["participants"][1]["championName"] = "Lillia"
        row = game_row(match, timeline, ME)
        self.assertEqual((row["first_dragon"], row["first_herald"]), ("them", "us"))

    def test_no_objectives(self):
        row = game_row(*lillia_match(), ME)
        self.assertEqual((row["first_dragon"], row["first_herald"]), (None, None))


class FakeDragon:
    def items(self):
        return ITEMS

    def runes(self):
        return [{"id": 8100, "name": "Domination", "slots": [{"runes": [{"id": 8128, "name": "Dark Harvest"}]}]}]


class LoadRowsTests(unittest.TestCase):
    def test_rows_and_names(self):
        from champion_stats import load_rows
        match, timeline = lillia_match("NA1_5")
        match["info"]["participants"][1]["perks"] = PERKS
        with_events(timeline, [buy(10, 1103), buy(700, 6653), buy(900, 3020)])
        client = FakeClient([(match, timeline)])
        store = Store(":memory:")
        self.addCleanup(store.close)
        store.save_account(ME, "Aeoen", "NA1")
        data = load_rows(DataLayer(client, store), "Aeoen#NA1", "Lillia", "solo", dd=FakeDragon())
        self.assertEqual([r["items"] for r in data["rows"]], [[6653]])
        names = data["names"]
        self.assertEqual(names["items"], {6653: "Liandry's Torment", 3020: "Sorcerer's Shoes", 1103: "Mosstomper Seedling"})
        self.assertEqual(names["runes"], {8128: "Dark Harvest"})
        self.assertEqual(names["trees"], {8100: "Domination"})
        self.assertIn(8128, names["rune_labels"])
        self.assertEqual(names["rune_labels_verified"], [])

    def test_verified_rune_labels_are_named(self):
        from champion_stats import load_rows, service
        match, timeline = lillia_match("NA1_5")
        match["info"]["participants"][1]["perks"] = PERKS
        client = FakeClient([(match, timeline)])
        store = Store(":memory:")
        self.addCleanup(store.close)
        store.save_account(ME, "Aeoen", "NA1")
        original = service.VERIFIED_RUNES
        service.VERIFIED_RUNES = frozenset({8128, 9999})  # 9999 isn't on the page, so it isn't sent
        self.addCleanup(setattr, service, "VERIFIED_RUNES", original)
        data = load_rows(DataLayer(client, store), "Aeoen#NA1", "Lillia", "solo", dd=FakeDragon())
        self.assertEqual(data["names"]["rune_labels_verified"], [8128])

    def test_unknown_queue(self):
        from champion_stats import load_rows
        with self.assertRaises(ValueError):
            load_rows(None, "a#b", "Lillia", "aram")


class ExportTests(unittest.TestCase):
    def test_page_embeds_rows_and_scripts(self):
        import json
        import re

        from champion_stats.export import build_html
        rows = [game_row(*lillia_match(f"NA1_{i}"), ME) for i in range(3)]
        data = {"puuid": ME, "riot_id": "Aeoen#NA1", "champion": "Lillia", "queue": "solo", "rows": rows,
                "names": {"items": {}, "runes": {}, "trees": {}, "shards": {}, "rune_labels": {}}}
        page = build_html(data, {"Lillia": "Lillia"}, exported_at=0)
        self.assertIn("<title>Champion Stats</title>", page)
        self.assertIn("3 Ranked Solo games", page)
        self.assertIn("function csRender", page)
        self.assertIn("const fill", page)  # app.js helpers
        self.assertNotIn("function showTab", page)  # but not the rest of app.js
        self.assertNotIn(ME, page)  # puuid stripped
        embedded = json.loads(re.search(r"const CS_EXPORT = (.*);\n", page).group(1))
        self.assertEqual([r["match_id"] for r in embedded["rows"]], ["NA1_0", "NA1_1", "NA1_2"])

    def test_script_close_tags_in_data_are_escaped(self):
        from champion_stats.export import build_html
        data = {"riot_id": "x</script>#NA1", "champion": "Lillia", "queue": "solo", "rows": [], "names": {}}
        self.assertNotIn("x</script>", build_html(data))

    def test_page_has_the_slice_controls_the_tab_wires(self):
        from champion_stats.export import build_html
        data = {"riot_id": "Aeoen#NA1", "champion": "Lillia", "queue": "solo", "rows": [], "names": {}}
        page = build_html(data)
        for name in ("patch_from", "patch_to", "all_patches", "min_games"):
            self.assertIn(f'name="{name}"', page)

    def test_snapshot_rebuilds_the_page_without_riot(self):
        import os
        import tempfile

        from champion_stats import export
        rows = [game_row(*lillia_match(f"NA1_{i}"), ME) for i in range(2)]
        data = {"puuid": ME, "riot_id": "Aeoen#NA1", "champion": "Lillia", "queue": "solo", "rows": rows,
                "names": {"items": {}, "runes": {}, "trees": {}, "shards": {}, "rune_labels": {}}}
        with tempfile.TemporaryDirectory() as tmp:
            snap, out = os.path.join(tmp, "snap.json"), os.path.join(tmp, "page.html")
            export.save_snapshot(snap, data, {"Lillia": "Lillia"}, exported_at=0)
            with open(snap, encoding="utf-8") as f:
                self.assertNotIn(ME, f.read())  # puuid stays out of the committed file
            export.main(["--from-data", snap, "-o", out])  # no Riot ID, no DataLayer, no network
            with open(out, encoding="utf-8") as f:
                page = f.read()
        self.assertIn("2 Ranked Solo games", page)
        self.assertIn('"match_id":"NA1_1"', page)

    def test_riot_id_and_champion_needed_without_snapshot(self):
        from champion_stats import export
        with self.assertRaises(SystemExit):
            export.main([])


class BrowserCompatTests(unittest.TestCase):
    """The shared web UI code also runs in the offline export on phones, which may have Chrome as old as 80."""

    @staticmethod
    def read(name):
        from pathlib import Path
        return (Path(__file__).resolve().parent.parent / "webui" / "static" / name).read_text(encoding="utf-8")

    def test_no_post_chrome_80_javascript(self):
        import re
        newer = {r"\?\?=|\|\|=|&&=": "logical assignment (Chrome 85)", r"\.replaceAll\(": "replaceAll (Chrome 85)",
                 r"\.at\(-?\d": "Array.at (Chrome 92)", r"\bstructuredClone\(": "structuredClone (Chrome 98)",
                 r"Object\.hasOwn\(": "Object.hasOwn (Chrome 93)", r"\.findLast(Index)?\(": "findLast (Chrome 97)",
                 r"Promise\.any\(": "Promise.any (Chrome 85)", r"^await ": "top-level await (Chrome 89)"}
        for name in ("app.js", "champion_stats.js"):
            text = self.read(name)
            for pattern, what in newer.items():
                self.assertIsNone(re.search(pattern, text, re.M), f"{name} uses {what}")

    def test_replace_children_has_a_fallback_before_first_use(self):
        app = self.read("app.js")
        polyfill = app.find("Element.prototype.replaceChildren =")
        self.assertNotEqual(polyfill, -1)
        self.assertLess(polyfill, app.find(".replaceChildren("))
        self.assertLess(polyfill, app.find("// ---------- tabs"))  # inside the helpers the export embeds

    def test_color_mix_always_has_a_fallback(self):
        import re
        css = self.read("style.css")
        for rule in re.findall(r"[^{}]*\{[^{}]*color-mix\([^{}]*\}", css):
            for prop in re.findall(r"([\w-]+)\s*:\s*color-mix\(", rule):
                before = rule[:rule.index(f"{prop}: color-mix(")]
                self.assertRegex(before, rf"\b{prop}\s*:", f"no {prop} fallback before color-mix in: {rule.strip()}")
