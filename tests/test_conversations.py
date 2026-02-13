import tempfile
import time
import unittest
from pathlib import Path

from beacon_skill.conversations import ConversationManager, _conv_id


class TestConversations(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.data_dir = Path(self.tmpdir)

    def _mgr(self, my_id="bcn_me"):
        return ConversationManager(data_dir=self.data_dir, my_agent_id=my_id)

    def test_get_or_create_new(self):
        mgr = self._mgr()
        conv = mgr.get_or_create("bcn_alice")
        self.assertTrue(conv["conversation_id"].startswith("conv_"))
        self.assertEqual(conv["their_agent_id"], "bcn_alice")
        self.assertEqual(conv["state"], "initiated")

    def test_get_or_create_returns_existing(self):
        mgr = self._mgr()
        c1 = mgr.get_or_create("bcn_alice", "task_xyz")
        c2 = mgr.get_or_create("bcn_alice", "task_xyz")
        self.assertEqual(c1["conversation_id"], c2["conversation_id"])

    def test_deterministic_id(self):
        """Same pair+topic yields same ID regardless of who creates."""
        id1 = _conv_id("bcn_me", "bcn_alice", "general")
        id2 = _conv_id("bcn_alice", "bcn_me", "general")
        self.assertEqual(id1, id2)

    def test_different_topics_different_ids(self):
        id1 = _conv_id("bcn_me", "bcn_alice", "task_1")
        id2 = _conv_id("bcn_me", "bcn_alice", "task_2")
        self.assertNotEqual(id1, id2)

    def test_record_message_updates_state(self):
        mgr = self._mgr()
        conv = mgr.get_or_create("bcn_alice")
        self.assertEqual(conv["state"], "initiated")
        mgr.record_message(conv["conversation_id"], "out", "hello")
        convs = mgr.find_by_agent("bcn_alice")
        self.assertEqual(convs[0]["state"], "active")
        self.assertEqual(convs[0]["messages"], 1)
        self.assertEqual(convs[0]["last_direction"], "out")

    def test_find_by_agent(self):
        mgr = self._mgr()
        mgr.get_or_create("bcn_alice", "topic_a")
        mgr.get_or_create("bcn_alice", "topic_b")
        mgr.get_or_create("bcn_bob", "topic_a")
        results = mgr.find_by_agent("bcn_alice")
        self.assertEqual(len(results), 2)

    def test_find_by_topic(self):
        mgr = self._mgr()
        mgr.get_or_create("bcn_alice", "special_topic")
        result = mgr.find_by_topic("special_topic")
        self.assertIsNotNone(result)
        self.assertEqual(result["topic_key"], "special_topic")

    def test_find_by_topic_not_found(self):
        mgr = self._mgr()
        result = mgr.find_by_topic("nonexistent")
        self.assertIsNone(result)

    def test_is_waiting_for_reply(self):
        mgr = self._mgr()
        self.assertFalse(mgr.is_waiting_for_reply("bcn_alice"))
        conv = mgr.get_or_create("bcn_alice")
        mgr.record_message(conv["conversation_id"], "out", "hello")
        self.assertTrue(mgr.is_waiting_for_reply("bcn_alice"))

    def test_not_waiting_after_inbound(self):
        mgr = self._mgr()
        conv = mgr.get_or_create("bcn_alice")
        mgr.record_message(conv["conversation_id"], "out", "hello")
        mgr.record_message(conv["conversation_id"], "in", "reply")
        self.assertFalse(mgr.is_waiting_for_reply("bcn_alice"))

    def test_should_follow_up(self):
        mgr = self._mgr()
        conv = mgr.get_or_create("bcn_alice")
        mgr.record_message(conv["conversation_id"], "out", "hello")
        # Not yet overdue
        self.assertFalse(mgr.should_follow_up(conv["conversation_id"], timeout_s=86400))
        # Manually backdate
        mgr._conversations[conv["conversation_id"]]["last_message_ts"] = int(time.time()) - 90000
        self.assertTrue(mgr.should_follow_up(conv["conversation_id"], timeout_s=86400))

    def test_mark_completed(self):
        mgr = self._mgr()
        conv = mgr.get_or_create("bcn_alice")
        mgr.mark_completed(conv["conversation_id"])
        convs = mgr.find_by_agent("bcn_alice")
        self.assertEqual(convs[0]["state"], "completed")

    def test_mark_stale(self):
        mgr = self._mgr()
        conv = mgr.get_or_create("bcn_alice")
        mgr.record_message(conv["conversation_id"], "out", "hello")
        # Backdate to make it stale
        mgr._conversations[conv["conversation_id"]]["last_message_ts"] = int(time.time()) - 700000
        count = mgr.mark_stale(max_idle_s=604800)
        self.assertEqual(count, 1)
        convs = mgr.find_by_agent("bcn_alice")
        self.assertEqual(convs[0]["state"], "stale")

    def test_active_conversations(self):
        mgr = self._mgr()
        mgr.get_or_create("bcn_alice")
        mgr.get_or_create("bcn_bob")
        conv_c = mgr.get_or_create("bcn_charlie")
        mgr.mark_completed(conv_c["conversation_id"])
        active = mgr.active_conversations()
        self.assertEqual(len(active), 2)

    def test_persistence(self):
        mgr1 = self._mgr()
        conv = mgr1.get_or_create("bcn_alice", "task_123")
        mgr1.record_message(conv["conversation_id"], "out", "hello")

        mgr2 = self._mgr()
        convs = mgr2.find_by_agent("bcn_alice")
        self.assertEqual(len(convs), 1)
        self.assertEqual(convs[0]["messages"], 1)
        self.assertEqual(convs[0]["state"], "active")

    def test_completed_not_waiting(self):
        mgr = self._mgr()
        conv = mgr.get_or_create("bcn_alice")
        mgr.record_message(conv["conversation_id"], "out", "hello")
        mgr.mark_completed(conv["conversation_id"])
        self.assertFalse(mgr.is_waiting_for_reply("bcn_alice"))


if __name__ == "__main__":
    unittest.main()
