import json
import tempfile
import time
import unittest
from pathlib import Path

from beacon_skill.memory import AgentMemory


class TestMemory(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.data_dir = Path(self.tmpdir)

    def _write_jsonl(self, name, entries):
        path = self.data_dir / name
        with path.open("w", encoding="utf-8") as f:
            for entry in entries:
                f.write(json.dumps(entry) + "\n")

    def _mgr(self):
        return AgentMemory(data_dir=self.data_dir, my_agent_id="bcn_me")

    def test_rebuild_empty(self):
        mgr = self._mgr()
        profile = mgr.rebuild()
        self.assertEqual(profile["total_in"], 0)
        self.assertEqual(profile["total_out"], 0)
        self.assertEqual(profile["my_agent_id"], "bcn_me")

    def test_rebuild_with_data(self):
        self._write_jsonl("inbox.jsonl", [
            {"platform": "udp", "received_at": time.time(), "envelopes": [
                {"kind": "bounty", "agent_id": "bcn_alice", "topics": ["python"]}
            ]},
            {"platform": "udp", "received_at": time.time(), "envelopes": [
                {"kind": "hello", "agent_id": "bcn_alice"}
            ]},
        ])
        self._write_jsonl("outbox.jsonl", [
            {"platform": "udp", "ts": time.time()},
        ])
        self._write_jsonl("interactions.jsonl", [
            {"agent_id": "bcn_alice", "dir": "in", "kind": "bounty", "outcome": "ok", "rtc": 10},
            {"agent_id": "bcn_alice", "dir": "out", "kind": "pay", "outcome": "paid", "rtc": 5},
        ])
        mgr = self._mgr()
        profile = mgr.rebuild()
        self.assertEqual(profile["total_in"], 2)
        self.assertEqual(profile["total_out"], 1)
        self.assertEqual(profile["rtc_received"], 10.0)
        self.assertEqual(profile["rtc_sent"], 5.0)
        self.assertIn("python", profile["topic_frequency"])

    def test_contact(self):
        self._write_jsonl("interactions.jsonl", [
            {"agent_id": "bcn_bob", "dir": "in", "kind": "hello", "outcome": "ok", "ts": 100},
            {"agent_id": "bcn_bob", "dir": "out", "kind": "pay", "outcome": "paid", "rtc": 25, "ts": 200},
        ])
        self._write_jsonl("inbox.jsonl", [
            {"envelopes": [{"agent_id": "bcn_bob", "kind": "hello"}]},
        ])
        mgr = self._mgr()
        c = mgr.contact("bcn_bob")
        self.assertEqual(c["interactions"], 2)
        self.assertEqual(c["inbox_messages"], 1)
        self.assertEqual(c["rtc_volume"], 25.0)

    def test_demand_signals(self):
        now = time.time()
        self._write_jsonl("inbox.jsonl", [
            {"received_at": now, "envelopes": [
                {"kind": "want", "needs": ["frontend", "design"]},
            ]},
            {"received_at": now, "envelopes": [
                {"kind": "bounty", "needs": ["frontend"], "topics": ["react"], "text": "need react dev"},
            ]},
        ])
        mgr = self._mgr()
        demand = mgr.demand_signals(days=7)
        self.assertIn("frontend", demand)
        self.assertEqual(demand["frontend"], 2)

    def test_skill_gaps(self):
        now = time.time()
        self._write_jsonl("inbox.jsonl", [
            {"received_at": now, "envelopes": [
                {"kind": "want", "needs": ["rust", "go", "python"]},
            ]},
        ])
        mgr = self._mgr()
        # Without config, all demands are gaps
        gaps = mgr.skill_gaps()
        self.assertIsInstance(gaps, list)

    def test_suggest_rules(self):
        self._write_jsonl("interactions.jsonl", [
            {"agent_id": "bcn_reliable", "dir": "in", "kind": "hello", "outcome": "ok", "ts": time.time()}
            for _ in range(10)
        ])
        mgr = self._mgr()
        suggestions = mgr.suggest_rules()
        # Should suggest auto-ack for reliable agent
        self.assertGreater(len(suggestions), 0)
        self.assertIn("Auto-ack", suggestions[0]["suggestion"])

    def test_profile_caching(self):
        mgr = self._mgr()
        p1 = mgr.rebuild()
        p2 = mgr.profile()
        self.assertEqual(p1["rebuilt_at"], p2["rebuilt_at"])


if __name__ == "__main__":
    unittest.main()
