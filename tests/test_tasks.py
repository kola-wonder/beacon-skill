import tempfile
import unittest
from pathlib import Path

from beacon_skill.tasks import TaskManager


class TestTasks(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.data_dir = Path(self.tmpdir)

    def _mgr(self):
        return TaskManager(data_dir=self.data_dir)

    def test_create_task(self):
        mgr = self._mgr()
        task_id = mgr.create({
            "kind": "bounty",
            "agent_id": "bcn_poster",
            "reward_rtc": 50,
            "text": "Build a REST API",
            "task_id": "aabbcc",
        })
        self.assertEqual(task_id, "aabbcc")
        t = mgr.get("aabbcc")
        self.assertIsNotNone(t)
        self.assertEqual(t["state"], "open")
        self.assertEqual(t["poster"], "bcn_poster")
        self.assertEqual(t["reward_rtc"], 50)

    def test_valid_transition(self):
        mgr = self._mgr()
        mgr.create({"kind": "bounty", "agent_id": "bcn_p", "reward_rtc": 25, "task_id": "t1"})
        mgr.transition("t1", "offered", {"agent_id": "bcn_worker", "text": "I can do it"})
        t = mgr.get("t1")
        self.assertEqual(t["state"], "offered")
        self.assertEqual(t["worker"], "bcn_worker")

    def test_invalid_transition_raises(self):
        mgr = self._mgr()
        mgr.create({"kind": "bounty", "agent_id": "bcn_p", "task_id": "t2"})
        # Can't go from open to delivered directly
        with self.assertRaises(ValueError):
            mgr.transition("t2", "delivered")

    def test_full_lifecycle(self):
        mgr = self._mgr()
        mgr.create({"kind": "bounty", "agent_id": "bcn_poster", "reward_rtc": 100, "task_id": "t3"})
        mgr.transition("t3", "offered", {"agent_id": "bcn_worker", "text": "I'll do it"})
        mgr.transition("t3", "accepted", {"worker": "bcn_worker"})
        mgr.transition("t3", "delivered", {"delivery_url": "https://github.com/pr/1"})
        mgr.transition("t3", "confirmed", {"agent_id": "bcn_poster"})
        mgr.transition("t3", "paid", {"amount_rtc": 100})
        t = mgr.get("t3")
        self.assertEqual(t["state"], "paid")

    def test_cancellation(self):
        mgr = self._mgr()
        mgr.create({"kind": "bounty", "agent_id": "bcn_p", "task_id": "t4"})
        mgr.transition("t4", "cancelled", {"reason": "Changed my mind"})
        t = mgr.get("t4")
        self.assertEqual(t["state"], "cancelled")

    def test_list_tasks(self):
        mgr = self._mgr()
        mgr.create({"kind": "bounty", "agent_id": "bcn_p", "task_id": "t5"})
        mgr.create({"kind": "bounty", "agent_id": "bcn_p", "task_id": "t6"})
        mgr.transition("t6", "offered", {"agent_id": "bcn_w"})
        all_tasks = mgr.list_tasks()
        self.assertEqual(len(all_tasks), 2)
        open_tasks = mgr.list_tasks(state="open")
        self.assertEqual(len(open_tasks), 1)

    def test_my_tasks(self):
        mgr = self._mgr()
        mgr.create({"kind": "bounty", "agent_id": "bcn_poster", "task_id": "t7"})
        mgr.transition("t7", "offered", {"agent_id": "bcn_worker"})
        my = mgr.my_tasks("bcn_poster")
        self.assertEqual(len(my), 1)
        my_worker = mgr.my_tasks("bcn_worker")
        self.assertEqual(len(my_worker), 1)

    def test_auto_transition(self):
        mgr = self._mgr()
        mgr.create({"kind": "bounty", "agent_id": "bcn_p", "task_id": "t8"})
        result = mgr.auto_transition_from_envelope({
            "kind": "offer", "task_id": "t8", "agent_id": "bcn_w", "text": "On it"
        })
        self.assertIsNotNone(result)
        self.assertEqual(result["state"], "offered")

    def test_auto_transition_invalid(self):
        mgr = self._mgr()
        mgr.create({"kind": "bounty", "agent_id": "bcn_p", "task_id": "t9"})
        # Can't go directly to delivered
        result = mgr.auto_transition_from_envelope({
            "kind": "deliver", "task_id": "t9", "delivery_url": "https://example.com"
        })
        self.assertIsNone(result)

    def test_nonexistent_task(self):
        mgr = self._mgr()
        t = mgr.get("nonexistent")
        self.assertIsNone(t)


if __name__ == "__main__":
    unittest.main()
