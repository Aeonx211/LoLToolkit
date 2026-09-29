import unittest

from causal_analysis import analyze

from .fixtures import build_match, gold_from_diff


def review_for(result, pid):
    return next(p for p in result["players"] if p["participant_id"] == pid)["review"]


class ReviewPlayerTests(unittest.TestCase):
    def test_early_solo_death_and_lead_thrown_away(self):
        def diff(m):
            return 0 if m < 10 else max(0, 3000 - (m - 10) * 2000)

        kills = [(200, 6, 1), (650, 6, 1)]
        result = analyze(*build_match(25, winner=200, gold=gold_from_diff(diff), kills=kills))
        review = review_for(result, 1)

        self.assertEqual(review["deaths"], 2)
        early = next(f for f in review["findings"] if f["t"] == 200)
        self.assertIn("early_solo", early["tags"])
        self.assertIn("no_trade", early["tags"])

        thrown = next(f for f in review["findings"] if f["t"] == 650)
        self.assertIn("gave_up_lead", thrown["tags"])
        self.assertGreaterEqual(thrown["lead_before"], 300)
        self.assertLessEqual(thrown["swing"], -300)
        self.assertGreaterEqual(review["flagged_count"], 2)

    def test_lost_fight_flagged(self):
        kills = [(500, 6, 1), (505, 7, 2)]
        result = analyze(*build_match(20, winner=200, kills=kills))
        review = review_for(result, 1)
        finding = next(f for f in review["findings"] if f["t"] == 500)
        self.assertIn("lost_fight", finding["tags"])

    def test_clean_game_has_no_flags(self):
        result = analyze(*build_match(20))
        review = review_for(result, 1)
        self.assertEqual(review["deaths"], 0)
        self.assertEqual(review["flagged_count"], 0)
        self.assertIn("No standout", review["summary"])


if __name__ == "__main__":
    unittest.main()
