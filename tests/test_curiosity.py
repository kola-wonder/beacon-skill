import json
import tempfile
import time
import unittest
from pathlib import Path

from beacon_skill.curiosity import CuriosityManager


class TestCuriosity(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.data_dir = Path(self.tmpdir)

    def test_add_interest(self):
        mgr = CuriosityManager(data_dir=self.data_dir)
        result = mgr.add("formal-verification", intensity=0.8, notes="saw in bounty")
        self.assertEqual(result["topic"], "formal-verification")
        self.assertEqual(result["intensity"], 0.8)
        self.assertIn("since", result)

    def test_add_clamps_intensity(self):
        mgr = CuriosityManager(data_dir=self.data_dir)
        r1 = mgr.add("too-high", intensity=5.0)
        self.assertEqual(r1["intensity"], 1.0)
        r2 = mgr.add("too-low", intensity=-1.0)
        self.assertEqual(r2["intensity"], 0.0)

    def test_add_empty_raises(self):
        mgr = CuriosityManager(data_dir=self.data_dir)
        with self.assertRaises(ValueError):
            mgr.add("")

    def test_remove_interest(self):
        mgr = CuriosityManager(data_dir=self.data_dir)
        mgr.add("rust-macros")
        self.assertTrue(mgr.remove("rust-macros"))
        self.assertFalse(mgr.remove("nonexistent"))
        self.assertEqual(len(mgr.interests()), 0)

    def test_explore_moves_to_explored(self):
        mgr = CuriosityManager(data_dir=self.data_dir)
        mgr.add("python-asyncio", notes="want to learn")
        ok = mgr.explore("python-asyncio", notes="built a task runner")
        self.assertTrue(ok)
        self.assertNotIn("python-asyncio", mgr.interests())
        self.assertIn("python-asyncio", mgr.explored())
        self.assertEqual(mgr.explored()["python-asyncio"]["notes"], "built a task runner")

    def test_explore_nonexistent_returns_false(self):
        mgr = CuriosityManager(data_dir=self.data_dir)
        self.assertFalse(mgr.explore("nonexistent"))

    def test_top_interests_by_intensity(self):
        mgr = CuriosityManager(data_dir=self.data_dir)
        mgr.add("low", intensity=0.2)
        mgr.add("high", intensity=0.9)
        mgr.add("medium", intensity=0.5)

        top = mgr.top_interests(limit=2)
        self.assertEqual(len(top), 2)
        self.assertEqual(top[0], "high")
        self.assertEqual(top[1], "medium")

    def test_find_mutual(self):
        mgr = CuriosityManager(data_dir=self.data_dir)
        mgr.add("formal-verification")
        mgr.add("rust-macros")
        mgr.add("category-theory")

        roster_entry = {
            "agent_id": "bcn_other",
            "curiosities": ["formal-verification", "game-theory"],
        }
        result = mgr.find_mutual(roster_entry)
        self.assertEqual(result["agent_id"], "bcn_other")
        self.assertIn("formal-verification", result["shared"])
        self.assertIn("rust-macros", result["i_have_exclusively"])
        self.assertIn("game-theory", result["they_have_exclusively"])
        self.assertGreater(result["overlap_score"], 0)
        self.assertLess(result["overlap_score"], 1.0)

    def test_build_curious_envelope(self):
        mgr = CuriosityManager(data_dir=self.data_dir)
        mgr.add("formal-verification", intensity=0.9)
        mgr.add("rust-macros", intensity=0.7)

        env = mgr.build_curious_envelope("bcn_me")
        self.assertEqual(env["kind"], "curious")
        self.assertEqual(env["agent_id"], "bcn_me")
        self.assertIn("formal-verification", env["interests"])
        self.assertIn("ts", env)

    def test_score_curiosity_match(self):
        mgr = CuriosityManager(data_dir=self.data_dir)
        mgr.add("formal-verification")
        mgr.add("rust-macros")

        # Envelope that matches (topic appears in topics list)
        env = {"text": "Bounty available", "topics": ["formal-verification", "math"]}
        score = mgr.score_curiosity_match(env)
        self.assertGreater(score, 0)

        # Envelope that doesn't match
        env2 = {"text": "Need help with cooking", "topics": ["food"]}
        score2 = mgr.score_curiosity_match(env2)
        self.assertEqual(score2, 0.0)

    def test_score_capped_at_30(self):
        mgr = CuriosityManager(data_dir=self.data_dir)
        mgr.add("a")
        mgr.add("b")
        mgr.add("c")
        mgr.add("d")

        env = {"text": "a b c d all matching"}
        score = mgr.score_curiosity_match(env)
        self.assertLessEqual(score, 30.0)

    def test_persistence(self):
        mgr1 = CuriosityManager(data_dir=self.data_dir)
        mgr1.add("quantum-computing", intensity=0.7)

        mgr2 = CuriosityManager(data_dir=self.data_dir)
        self.assertIn("quantum-computing", mgr2.interests())
        self.assertEqual(mgr2.interests()["quantum-computing"]["intensity"], 0.7)

    def test_update_preserves_since(self):
        mgr = CuriosityManager(data_dir=self.data_dir)
        r1 = mgr.add("topic-x", intensity=0.5)
        original_since = r1["since"]

        r2 = mgr.add("topic-x", intensity=0.9, notes="updated")
        self.assertEqual(r2["since"], original_since)
        self.assertEqual(r2["intensity"], 0.9)


if __name__ == "__main__":
    unittest.main()
