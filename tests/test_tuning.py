import json
import tempfile
import unittest
from pathlib import Path

import tuning
from build_sim import effects
from causal_analysis import analysis_version, archetypes


class TuningTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.original_file = tuning.TUNING_FILE
        tuning.TUNING_FILE = Path(self.tmp.name) / "tuning.json"
        self.addCleanup(self._restore)

    def _restore(self):
        tuning.reset()
        tuning.TUNING_FILE = self.original_file

    def test_update_applies_and_saves_only_overrides(self):
        before = analysis_version()
        tuning.update({"causal_analysis.stomp_lead": "3000", "build_sim.ELECTROCUTE": "80, 250, 0.1, 0.05, 20"})
        self.assertEqual(archetypes.DEFAULT_THRESHOLDS.stomp_lead, 3000)
        self.assertEqual(effects.ELECTROCUTE, (80, 250, 0.1, 0.05, 20))
        self.assertNotEqual(analysis_version(), before)
        saved = json.loads(tuning.TUNING_FILE.read_text())
        self.assertEqual(set(saved), {"causal_analysis.stomp_lead", "build_sim.ELECTROCUTE"})

    def test_bad_values_are_rejected_without_applying(self):
        with self.assertRaises(ValueError):
            tuning.update({"causal_analysis.stomp_lead": "3000", "build_sim.ELECTROCUTE": "1, 2"})
        self.assertEqual(archetypes.DEFAULT_THRESHOLDS.stomp_lead, 3500)
        with self.assertRaises(ValueError):
            tuning.update({"live_advisor.MIN_WINS_TO_FLAG": "2.5"})
        with self.assertRaises(ValueError):
            tuning.update({"nope": 1})

    def test_reset_restores_defaults_and_removes_file(self):
        tuning.update({"live_advisor.MIN_WINS_TO_FLAG": 4})
        tuning.reset()
        self.assertFalse(tuning.TUNING_FILE.exists())
        self.assertEqual(tuning.BY_KEY["live_advisor.MIN_WINS_TO_FLAG"].get(), 3)


if __name__ == "__main__":
    unittest.main()
