import json
import tempfile
import time
import unittest
from pathlib import Path

from beacon_skill.matchmaker import MatchmakerManager


class TestMatchmaker(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.data_dir = Path(self.tmpdir)

    def test_scan_roster_basic(self):
        mgr = MatchmakerManager(data_dir=self.data_dir)
        roster = [
            {"agent_id": "bcn_alice", "name": "Alice", "offers": ["rust"], "needs": ["python"]},
            {"agent_id": "bcn_bob", "name": "Bob", "offers": ["z3"], "needs": ["python"]},
        ]
        matches = mgr.scan_roster(roster, my_agent_id="bcn_me", my_offers=["python"], my_needs=["rust"])
        self.assertEqual(len(matches), 2)
        # Alice offers rust (I need it) + needs python (I offer it) = highest score
        self.assertEqual(matches[0]["agent_id"], "bcn_alice")

    def test_scan_roster_skips_self(self):
        mgr = MatchmakerManager(data_dir=self.data_dir)
        roster = [
            {"agent_id": "bcn_me", "offers": ["python"], "needs": ["rust"]},
            {"agent_id": "bcn_other", "offers": ["rust"], "needs": []},
        ]
        matches = mgr.scan_roster(roster, my_agent_id="bcn_me", my_needs=["rust"])
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["agent_id"], "bcn_other")

    def test_scan_roster_with_goals(self):
        mgr = MatchmakerManager(data_dir=self.data_dir)
        roster = [
            {"agent_id": "bcn_teacher", "offers": ["z3"], "needs": [], "topics": ["formal-verification"]},
        ]
        goals = [{"title": "Learn z3", "state": "active"}]
        matches = mgr.scan_roster(roster, my_agent_id="bcn_me", goals=goals)
        self.assertTrue(len(matches) >= 1)

    def test_can_contact_cooldown(self):
        mgr = MatchmakerManager(data_dir=self.data_dir)
        self.assertTrue(mgr.can_contact("bcn_alice"))
        mgr.record_contact("bcn_alice", match_id="m_001")
        self.assertFalse(mgr.can_contact("bcn_alice"))  # Just contacted
        self.assertTrue(mgr.can_contact("bcn_alice", cooldown_s=0))  # No cooldown

    def test_record_contact_persistence(self):
        mgr1 = MatchmakerManager(data_dir=self.data_dir)
        mgr1.record_contact("bcn_alice")

        mgr2 = MatchmakerManager(data_dir=self.data_dir)
        self.assertFalse(mgr2.can_contact("bcn_alice"))

    def test_record_response(self):
        mgr = MatchmakerManager(data_dir=self.data_dir)
        mgr.record_response("m_001", "interested")
        history = mgr.match_history_log()
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["response"], "interested")

    def test_match_demand(self):
        mgr = MatchmakerManager(data_dir=self.data_dir)
        roster = [
            {"agent_id": "bcn_a", "needs": ["rust"]},
            {"agent_id": "bcn_b", "needs": ["python", "rust"]},
        ]
        demand = {"rust": 5, "python": 3}
        matches = mgr.match_demand(roster, demand)
        # Should find rust needs (both agents) and python need (bcn_b)
        self.assertTrue(len(matches) >= 2)

    def test_match_curiosity(self):
        from beacon_skill.curiosity import CuriosityManager
        curiosity = CuriosityManager(data_dir=self.data_dir)
        curiosity.add("formal-verification", intensity=0.8)
        curiosity.add("z3")

        mgr = MatchmakerManager(data_dir=self.data_dir, curiosity_mgr=curiosity)
        roster = [
            {"agent_id": "bcn_a", "curiosities": ["z3", "rust"]},
            {"agent_id": "bcn_b", "curiosities": ["cooking"]},
        ]
        matches = mgr.match_curiosity(roster)
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["agent_id"], "bcn_a")
        self.assertIn("z3", matches[0]["shared_interests"])

    def test_match_curiosity_no_manager(self):
        mgr = MatchmakerManager(data_dir=self.data_dir)
        self.assertEqual(mgr.match_curiosity([]), [])

    def test_match_compatibility_hash_match(self):
        from beacon_skill.values import ValuesManager
        values = ValuesManager(data_dir=self.data_dir)
        values.set_principle("honesty", 1.0)
        my_hash = values.values_hash()

        mgr = MatchmakerManager(data_dir=self.data_dir, values_mgr=values)
        roster = [
            {"agent_id": "bcn_aligned", "values_hash": my_hash},
            {"agent_id": "bcn_different", "values_hash": "different_hash_1234"},
        ]
        matches = mgr.match_compatibility(roster)
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0]["agent_id"], "bcn_aligned")
        self.assertEqual(matches[0]["compatibility"], 1.0)

    def test_match_compatibility_no_manager(self):
        mgr = MatchmakerManager(data_dir=self.data_dir)
        self.assertEqual(mgr.match_compatibility([]), [])

    def test_suggest_introductions(self):
        mgr = MatchmakerManager(data_dir=self.data_dir)
        roster = [
            {"agent_id": "bcn_a", "offers": ["rust"], "needs": ["python"]},
            {"agent_id": "bcn_b", "offers": ["python"], "needs": ["rust"]},
            {"agent_id": "bcn_c", "offers": ["cooking"], "needs": ["cooking"]},
        ]
        intros = mgr.suggest_introductions(roster)
        # bcn_a and bcn_b are a perfect match
        self.assertTrue(len(intros) >= 1)
        top = intros[0]
        self.assertIn("bcn_a", [top["agent_a"], top["agent_b"]])
        self.assertIn("bcn_b", [top["agent_a"], top["agent_b"]])

    def test_match_history_log(self):
        mgr = MatchmakerManager(data_dir=self.data_dir)
        mgr.record_contact("bcn_a", "m_001")
        mgr.record_contact("bcn_b", "m_002")
        mgr.record_response("m_001", "accepted")

        history = mgr.match_history_log(limit=10)
        self.assertEqual(len(history), 3)
        # Most recent first
        self.assertEqual(history[0]["action"], "response")

    def test_scan_empty_roster(self):
        mgr = MatchmakerManager(data_dir=self.data_dir)
        matches = mgr.scan_roster([], my_agent_id="bcn_me")
        self.assertEqual(matches, [])

    def test_no_match_when_no_overlap(self):
        mgr = MatchmakerManager(data_dir=self.data_dir)
        roster = [{"agent_id": "bcn_other", "offers": ["cooking"], "needs": ["gardening"]}]
        matches = mgr.scan_roster(roster, my_agent_id="bcn_me", my_offers=["rust"], my_needs=["python"])
        self.assertEqual(len(matches), 0)


if __name__ == "__main__":
    unittest.main()
