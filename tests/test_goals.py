import json
import tempfile
import time
import unittest
from pathlib import Path

from beacon_skill.goals import GoalManager, VALID_CATEGORIES, VALID_STATES


class TestGoals(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.data_dir = Path(self.tmpdir)

    def test_dream_creates_goal(self):
        mgr = GoalManager(data_dir=self.data_dir)
        gid = mgr.dream("Learn Z3", description="SMT solver", category="skill")
        self.assertTrue(gid.startswith("g_"))
        goal = mgr.get(gid)
        self.assertIsNotNone(goal)
        self.assertEqual(goal["title"], "Learn Z3")
        self.assertEqual(goal["state"], "dreaming")
        self.assertEqual(goal["category"], "skill")

    def test_dream_empty_title_raises(self):
        mgr = GoalManager(data_dir=self.data_dir)
        with self.assertRaises(ValueError):
            mgr.dream("")

    def test_dream_invalid_category_raises(self):
        mgr = GoalManager(data_dir=self.data_dir)
        with self.assertRaises(ValueError):
            mgr.dream("Test", category="invalid")

    def test_activate_goal(self):
        mgr = GoalManager(data_dir=self.data_dir)
        gid = mgr.dream("Learn Rust")
        self.assertTrue(mgr.activate(gid))
        goal = mgr.get(gid)
        self.assertEqual(goal["state"], "active")

    def test_activate_already_active_fails(self):
        mgr = GoalManager(data_dir=self.data_dir)
        gid = mgr.dream("Learn Rust")
        mgr.activate(gid)
        self.assertFalse(mgr.activate(gid))

    def test_activate_nonexistent_fails(self):
        mgr = GoalManager(data_dir=self.data_dir)
        self.assertFalse(mgr.activate("g_nonexistent"))

    def test_progress_tracking(self):
        mgr = GoalManager(data_dir=self.data_dir)
        gid = mgr.dream("Learn Z3", category="skill", target_value=10.0)
        mgr.activate(gid)
        result = mgr.progress(gid, "Completed tutorial", value=3.0)
        self.assertEqual(result["current_value"], 3.0)
        self.assertEqual(len(result["milestones"]), 1)
        self.assertEqual(result["milestones"][0]["milestone"], "Completed tutorial")

    def test_progress_on_dreaming_goal_fails(self):
        mgr = GoalManager(data_dir=self.data_dir)
        gid = mgr.dream("Learn Z3")
        result = mgr.progress(gid, "test")
        self.assertEqual(result, {})

    def test_achieve_goal(self):
        mgr = GoalManager(data_dir=self.data_dir)
        gid = mgr.dream("Learn Z3")
        mgr.activate(gid)
        self.assertTrue(mgr.achieve(gid, notes="built a solver"))
        goal = mgr.get(gid)
        self.assertEqual(goal["state"], "achieved")

    def test_achieve_dreaming_fails(self):
        mgr = GoalManager(data_dir=self.data_dir)
        gid = mgr.dream("Learn Z3")
        self.assertFalse(mgr.achieve(gid))

    def test_abandon_from_dreaming(self):
        mgr = GoalManager(data_dir=self.data_dir)
        gid = mgr.dream("Learn Z3")
        self.assertTrue(mgr.abandon(gid, reason="too complex"))
        goal = mgr.get(gid)
        self.assertEqual(goal["state"], "abandoned")

    def test_abandon_from_active(self):
        mgr = GoalManager(data_dir=self.data_dir)
        gid = mgr.dream("Learn Z3")
        mgr.activate(gid)
        self.assertTrue(mgr.abandon(gid))
        self.assertEqual(mgr.get(gid)["state"], "abandoned")

    def test_abandon_achieved_fails(self):
        mgr = GoalManager(data_dir=self.data_dir)
        gid = mgr.dream("Learn Z3")
        mgr.activate(gid)
        mgr.achieve(gid)
        self.assertFalse(mgr.abandon(gid))

    def test_list_goals_all(self):
        mgr = GoalManager(data_dir=self.data_dir)
        mgr.dream("Goal A")
        gid_b = mgr.dream("Goal B")
        mgr.activate(gid_b)
        goals = mgr.list_goals()
        self.assertEqual(len(goals), 2)

    def test_list_goals_by_state(self):
        mgr = GoalManager(data_dir=self.data_dir)
        mgr.dream("Dream only")
        gid = mgr.dream("Active one")
        mgr.activate(gid)
        active = mgr.list_goals(state="active")
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]["title"], "Active one")

    def test_active_goals(self):
        mgr = GoalManager(data_dir=self.data_dir)
        mgr.dream("Dream")
        gid = mgr.dream("Active")
        mgr.activate(gid)
        active = mgr.active_goals()
        self.assertEqual(len(active), 1)

    def test_persistence(self):
        mgr1 = GoalManager(data_dir=self.data_dir)
        gid = mgr1.dream("Persist test", category="rtc")
        mgr1.activate(gid)
        mgr1.progress(gid, "Step 1", value=5.0)

        mgr2 = GoalManager(data_dir=self.data_dir)
        goal = mgr2.get(gid)
        self.assertIsNotNone(goal)
        self.assertEqual(goal["state"], "active")
        self.assertEqual(goal["current_value"], 5.0)
        self.assertEqual(len(goal["milestones"]), 1)

    def test_achieve_auto_journals(self):
        from beacon_skill.journal import JournalManager
        journal = JournalManager(data_dir=self.data_dir)
        mgr = GoalManager(data_dir=self.data_dir, journal_mgr=journal)

        gid = mgr.dream("Learn Z3")
        mgr.activate(gid)
        mgr.achieve(gid, notes="built a solver")

        entries = journal.read()
        self.assertEqual(len(entries), 1)
        self.assertIn("Goal achieved", entries[0]["text"])
        self.assertIn("goal", entries[0]["tags"])

    def test_suggest_actions_skill_match(self):
        mgr = GoalManager(data_dir=self.data_dir)
        gid = mgr.dream("Learn rust", category="skill")
        mgr.activate(gid)

        roster = [{"agent_id": "bcn_teacher", "name": "RustBot", "offers": ["rust-training"]}]
        suggestions = mgr.suggest_actions(roster=roster)
        self.assertTrue(len(suggestions) >= 1)
        self.assertEqual(suggestions[0]["type"], "skill_match")

    def test_suggest_actions_demand_match(self):
        mgr = GoalManager(data_dir=self.data_dir)
        gid = mgr.dream("Earn from python", category="rtc")
        mgr.activate(gid)

        demand = {"python": 5, "rust": 3}
        suggestions = mgr.suggest_actions(demand=demand)
        self.assertTrue(len(suggestions) >= 1)
        self.assertEqual(suggestions[0]["type"], "demand_match")

    def test_auto_create_from_gaps(self):
        mgr = GoalManager(data_dir=self.data_dir)
        demand = {"z3": 5, "coq": 3, "rare": 1}
        created = mgr.auto_create_from_gaps(skill_gaps=["z3", "coq", "rare"], demand=demand)
        # "rare" has count<2, should be skipped
        self.assertEqual(len(created), 2)
        goals = mgr.list_goals(state="dreaming")
        self.assertEqual(len(goals), 2)

    def test_auto_create_skips_duplicates(self):
        mgr = GoalManager(data_dir=self.data_dir)
        mgr.dream("Learn z3", category="skill")
        created = mgr.auto_create_from_gaps(skill_gaps=["z3"], demand={"z3": 5})
        self.assertEqual(len(created), 0)

    def test_index_updates(self):
        mgr = GoalManager(data_dir=self.data_dir)
        gid1 = mgr.dream("A")
        gid2 = mgr.dream("B")
        mgr.activate(gid1)
        mgr.activate(gid2)
        mgr.achieve(gid1)
        mgr.abandon(gid2)

        # Reload index
        idx = json.loads((self.data_dir / "goals.json").read_text())
        self.assertIn(gid1, idx["achieved"])
        self.assertIn(gid2, idx["abandoned"])
        self.assertEqual(len(idx["active"]), 0)

    def test_all_valid_categories(self):
        mgr = GoalManager(data_dir=self.data_dir)
        for cat in VALID_CATEGORIES:
            gid = mgr.dream(f"Test {cat}", category=cat)
            self.assertEqual(mgr.get(gid)["category"], cat)


if __name__ == "__main__":
    unittest.main()
