import json
import tempfile
import time
import unittest
from pathlib import Path

from beacon_skill.values import ValuesManager, AgentScanner, MORAL_PRESETS


class TestValues(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.data_dir = Path(self.tmpdir)

    def test_set_and_get_principle(self):
        mgr = ValuesManager(data_dir=self.data_dir)
        mgr.set_principle("open-source", 1.0, text="Software should be free")
        principles = mgr.principles()
        self.assertIn("open-source", principles)
        self.assertEqual(principles["open-source"]["weight"], 1.0)
        self.assertEqual(principles["open-source"]["text"], "Software should be free")

    def test_remove_principle(self):
        mgr = ValuesManager(data_dir=self.data_dir)
        mgr.set_principle("test", 0.5)
        self.assertTrue(mgr.remove_principle("test"))
        self.assertFalse(mgr.remove_principle("nonexistent"))
        self.assertEqual(len(mgr.principles()), 0)

    def test_principle_weight_clamped(self):
        mgr = ValuesManager(data_dir=self.data_dir)
        mgr.set_principle("too-high", 5.0)
        mgr.set_principle("too-low", -1.0)
        self.assertEqual(mgr.principles()["too-high"]["weight"], 1.0)
        self.assertEqual(mgr.principles()["too-low"]["weight"], 0.0)

    def test_empty_principle_name_raises(self):
        mgr = ValuesManager(data_dir=self.data_dir)
        with self.assertRaises(ValueError):
            mgr.set_principle("", 0.5)

    def test_add_and_get_boundary(self):
        mgr = ValuesManager(data_dir=self.data_dir)
        idx = mgr.add_boundary("No surveillance bounties")
        self.assertEqual(idx, 0)
        boundaries = mgr.boundaries()
        self.assertEqual(len(boundaries), 1)
        self.assertEqual(boundaries[0], "No surveillance bounties")

    def test_remove_boundary(self):
        mgr = ValuesManager(data_dir=self.data_dir)
        mgr.add_boundary("First")
        mgr.add_boundary("Second")
        self.assertTrue(mgr.remove_boundary(0))
        self.assertEqual(mgr.boundaries(), ["Second"])
        self.assertFalse(mgr.remove_boundary(99))

    def test_empty_boundary_raises(self):
        mgr = ValuesManager(data_dir=self.data_dir)
        with self.assertRaises(ValueError):
            mgr.add_boundary("")

    def test_set_and_get_aesthetic(self):
        mgr = ValuesManager(data_dir=self.data_dir)
        mgr.set_aesthetic("style", "functional")
        aesthetics = mgr.aesthetics()
        self.assertEqual(aesthetics["style"], "functional")

    def test_remove_aesthetic(self):
        mgr = ValuesManager(data_dir=self.data_dir)
        mgr.set_aesthetic("style", "functional")
        self.assertTrue(mgr.remove_aesthetic("style"))
        self.assertFalse(mgr.remove_aesthetic("nonexistent"))

    def test_values_hash_changes(self):
        mgr = ValuesManager(data_dir=self.data_dir)
        hash1 = mgr.values_hash()
        mgr.set_principle("new-thing", 0.5)
        hash2 = mgr.values_hash()
        self.assertNotEqual(hash1, hash2)
        self.assertEqual(len(hash2), 16)

    def test_values_hash_consistent(self):
        mgr = ValuesManager(data_dir=self.data_dir)
        mgr.set_principle("test", 0.5)
        h1 = mgr.values_hash()
        h2 = mgr.values_hash()
        self.assertEqual(h1, h2)

    def test_compatibility_same_values(self):
        mgr = ValuesManager(data_dir=self.data_dir)
        mgr.set_principle("open-source", 1.0)
        mgr.set_principle("transparency", 0.8)

        other = {
            "principles": {
                "open-source": {"weight": 1.0},
                "transparency": {"weight": 0.8},
            }
        }
        score = mgr.compatibility(other)
        self.assertEqual(score, 1.0)

    def test_compatibility_different_values(self):
        mgr = ValuesManager(data_dir=self.data_dir)
        mgr.set_principle("open-source", 1.0)

        other = {
            "principles": {
                "proprietary": {"weight": 1.0},
            }
        }
        score = mgr.compatibility(other)
        self.assertLess(score, 0.5)

    def test_compatibility_no_values(self):
        mgr = ValuesManager(data_dir=self.data_dir)
        score = mgr.compatibility({})
        self.assertEqual(score, 0.5)

    def test_to_card_dict(self):
        mgr = ValuesManager(data_dir=self.data_dir)
        mgr.set_principle("test-driven", 0.8)
        mgr.add_boundary("No surveillance")
        card = mgr.to_card_dict()
        self.assertIn("test-driven", card["principles"])
        self.assertEqual(card["boundary_count"], 1)
        self.assertEqual(len(card["values_hash"]), 16)

    def test_check_boundaries_violated(self):
        mgr = ValuesManager(data_dir=self.data_dir)
        mgr.add_boundary("No surveillance bounties")

        envelope = {"text": "Build a surveillance tool for monitoring", "topics": ["bounties"]}
        result = mgr.check_boundaries(envelope)
        self.assertIsNotNone(result)
        self.assertIn("surveillance", result.lower())

    def test_check_boundaries_passed(self):
        mgr = ValuesManager(data_dir=self.data_dir)
        mgr.add_boundary("No surveillance bounties")

        envelope = {"text": "Build a REST API for weather data", "topics": ["api"]}
        result = mgr.check_boundaries(envelope)
        self.assertIsNone(result)

    def test_check_boundaries_empty(self):
        mgr = ValuesManager(data_dir=self.data_dir)
        result = mgr.check_boundaries({"text": "Anything"})
        self.assertIsNone(result)

    def test_apply_preset_biblical(self):
        mgr = ValuesManager(data_dir=self.data_dir)
        count = mgr.apply_preset("biblical-honesty")
        self.assertGreater(count, 0)
        principles = mgr.principles()
        self.assertIn("honest-weights", principles)
        self.assertIn("by-their-fruits", principles)
        self.assertGreater(len(mgr.boundaries()), 0)

    def test_apply_preset_unknown_raises(self):
        mgr = ValuesManager(data_dir=self.data_dir)
        with self.assertRaises(ValueError):
            mgr.apply_preset("nonexistent-preset")

    def test_persistence(self):
        mgr1 = ValuesManager(data_dir=self.data_dir)
        mgr1.set_principle("honesty", 1.0, text="Be honest")
        mgr1.add_boundary("No scams")

        mgr2 = ValuesManager(data_dir=self.data_dir)
        self.assertIn("honesty", mgr2.principles())
        self.assertEqual(mgr2.boundaries(), ["No scams"])

    def test_version_increments(self):
        mgr = ValuesManager(data_dir=self.data_dir)
        mgr.set_principle("a", 0.5)
        v1 = mgr.full_values()["version"]
        mgr.set_principle("b", 0.5)
        v2 = mgr.full_values()["version"]
        self.assertGreater(v2, v1)


class TestAgentScanner(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.data_dir = Path(self.tmpdir)

    def _write_jsonl(self, name, entries):
        path = self.data_dir / name
        with path.open("w", encoding="utf-8") as f:
            for entry in entries:
                f.write(json.dumps(entry) + "\n")

    def test_scan_clean_agent(self):
        self._write_jsonl("interactions.jsonl", [
            {"agent_id": "bcn_good", "outcome": "ok", "rtc": 10, "dir": "in"},
            {"agent_id": "bcn_good", "outcome": "delivered", "rtc": 50, "dir": "out"},
        ])
        self._write_jsonl("tasks.jsonl", [
            {"agent_id": "bcn_good", "task_id": "t1", "state": "paid"},
        ])
        scanner = AgentScanner(data_dir=self.data_dir)
        result = scanner.scan_agent("bcn_good")
        self.assertGreaterEqual(result["integrity_score"], 0.8)
        self.assertEqual(result["recommendation"], "trustworthy")
        self.assertEqual(result["violation_count"], 0)

    def test_scan_promise_breaker(self):
        self._write_jsonl("interactions.jsonl", [
            {"agent_id": "bcn_bad", "outcome": "ok", "rtc": 1, "dir": "in"},
        ])
        self._write_jsonl("tasks.jsonl", [
            {"agent_id": "bcn_bad", "task_id": "t1", "state": "accepted"},
            {"agent_id": "bcn_bad", "task_id": "t2", "state": "accepted"},
            {"agent_id": "bcn_bad", "task_id": "t3", "state": "accepted"},
        ])
        scanner = AgentScanner(data_dir=self.data_dir)
        result = scanner.scan_agent("bcn_bad")
        self.assertLess(result["integrity_score"], 0.8)
        violations = [v["type"] for v in result["violations"]]
        self.assertIn("promise_breaker", violations)

    def test_scan_all(self):
        self._write_jsonl("interactions.jsonl", [
            {"agent_id": "bcn_a", "outcome": "ok", "rtc": 10, "dir": "in"},
            {"agent_id": "bcn_a", "outcome": "ok", "rtc": 10, "dir": "out"},
            {"agent_id": "bcn_b", "outcome": "ok", "rtc": 10, "dir": "in"},
            {"agent_id": "bcn_b", "outcome": "spam", "rtc": 0, "dir": "in"},
        ])
        self._write_jsonl("tasks.jsonl", [])
        scanner = AgentScanner(data_dir=self.data_dir)
        results = scanner.scan_all()
        self.assertEqual(len(results), 2)

    def test_scan_trust_gamer(self):
        # 15 tiny positive interactions, 0 negative — suspicious
        interactions = [
            {"agent_id": "bcn_gamer", "outcome": "ok", "rtc": 0.001, "dir": "in"}
            for _ in range(15)
        ]
        self._write_jsonl("interactions.jsonl", interactions)
        self._write_jsonl("tasks.jsonl", [])
        scanner = AgentScanner(data_dir=self.data_dir)
        result = scanner.scan_agent("bcn_gamer")
        violations = [v["type"] for v in result["violations"]]
        self.assertIn("trust_gamer", violations)


if __name__ == "__main__":
    unittest.main()
