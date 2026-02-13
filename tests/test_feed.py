import tempfile
import time
import unittest
from pathlib import Path

from beacon_skill.feed import FeedManager


class FakeTrustMgr:
    """Minimal fake trust manager for testing."""
    def __init__(self, scores=None):
        self._scores = scores or {}

    def score(self, agent_id):
        return self._scores.get(agent_id, {"score": 0, "total": 0})


class TestFeed(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.subs_path = Path(self.tmpdir) / "subscriptions.json"

    def _mgr(self):
        return FeedManager(subs_path=self.subs_path)

    def test_subscribe_agent(self):
        mgr = self._mgr()
        mgr.subscribe_agent("bcn_alice", alias="alice", priority=10)
        subs = mgr.subscriptions()
        self.assertIn("bcn_alice", subs["agents"])
        self.assertEqual(subs["agents"]["bcn_alice"]["priority"], 10)

    def test_subscribe_topic(self):
        mgr = self._mgr()
        mgr.subscribe_topic("python")
        mgr.subscribe_topic("ai")
        subs = mgr.subscriptions()
        self.assertIn("python", subs["topics"])
        self.assertIn("ai", subs["topics"])

    def test_unsubscribe(self):
        mgr = self._mgr()
        mgr.subscribe_topic("python")
        mgr.unsubscribe_topic("python")
        subs = mgr.subscriptions()
        self.assertNotIn("python", subs["topics"])

    def test_score_subscribed_agent(self):
        mgr = self._mgr()
        mgr.subscribe_agent("bcn_alice", priority=10)
        entry = {
            "envelope": {"kind": "hello", "agent_id": "bcn_alice", "ts": int(time.time())},
            "verified": True,
        }
        score = mgr.score_entry(entry)
        # Should be high: 50*(10/5) + kind(3) + verified(10) = 113
        self.assertGreater(score, 100)

    def test_score_topic_match(self):
        mgr = self._mgr()
        mgr.subscribe_topic("python")
        entry = {
            "envelope": {"kind": "bounty", "text": "Need a python developer", "ts": int(time.time())},
        }
        score = mgr.score_entry(entry)
        # bounty(10) + topic_match(20) = 30
        self.assertGreater(score, 25)

    def test_score_with_trust(self):
        mgr = self._mgr()
        trust = FakeTrustMgr(scores={
            "bcn_trusted": {"score": 0.8, "total": 10},
        })
        entry = {
            "envelope": {"kind": "hello", "agent_id": "bcn_trusted", "ts": int(time.time())},
        }
        score = mgr.score_entry(entry, trust_mgr=trust)
        # hello(3) + trust_bonus(15) = 18
        self.assertGreater(score, 15)

    def test_feed_filter(self):
        mgr = self._mgr()
        entries = [
            {"envelope": {"kind": "bounty", "agent_id": "bcn_a", "ts": int(time.time())}},
            {"envelope": {"kind": "ad", "agent_id": "bcn_b", "ts": int(time.time())}},
        ]
        results = mgr.feed(entries, min_score=5)
        # bounty scores 10, ad scores 1 — only bounty passes min_score=5
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["envelope"]["kind"], "bounty")

    def test_feed_sorted_by_score(self):
        mgr = self._mgr()
        mgr.subscribe_agent("bcn_top", priority=10)
        entries = [
            {"envelope": {"kind": "hello", "agent_id": "bcn_low", "ts": int(time.time())}},
            {"envelope": {"kind": "hello", "agent_id": "bcn_top", "ts": int(time.time())}},
        ]
        results = mgr.feed(entries)
        self.assertEqual(results[0]["envelope"]["agent_id"], "bcn_top")


if __name__ == "__main__":
    unittest.main()
