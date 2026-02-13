import json
import tempfile
import time
import unittest
from pathlib import Path

from beacon_skill.presence import PresenceManager


class FakeIdentity:
    agent_id = "bcn_test123abc"
    public_key_hex = "aa" * 32


class TestPresence(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.roster_path = Path(self.tmpdir) / "roster.json"
        self.config = {
            "beacon": {"agent_name": "test-agent"},
            "presence": {
                "pulse_interval_s": 60,
                "pulse_ttl_s": 300,
                "offers": ["python", "api-dev"],
                "needs": ["design"],
                "status": "online",
            },
            "preferences": {"topics": ["ai"]},
            "_start_ts": int(time.time()) - 100,
        }

    def test_build_pulse(self):
        mgr = PresenceManager(roster_path=self.roster_path, config=self.config)
        pulse = mgr.build_pulse(FakeIdentity(), self.config)
        self.assertEqual(pulse["kind"], "pulse")
        self.assertEqual(pulse["agent_id"], "bcn_test123abc")
        self.assertEqual(pulse["name"], "test-agent")
        self.assertEqual(pulse["offers"], ["python", "api-dev"])
        self.assertEqual(pulse["needs"], ["design"])
        self.assertIn("ts", pulse)
        self.assertGreaterEqual(pulse["uptime_s"], 100)

    def test_process_pulse_and_roster(self):
        mgr = PresenceManager(roster_path=self.roster_path, config=self.config)
        pulse = {
            "kind": "pulse",
            "agent_id": "bcn_remote_agent",
            "name": "remote-bot",
            "status": "online",
            "offers": ["frontend"],
            "needs": ["python"],
            "ts": int(time.time()),
        }
        mgr.process_pulse(pulse)
        agents = mgr.roster()
        self.assertEqual(len(agents), 1)
        self.assertEqual(agents[0]["agent_id"], "bcn_remote_agent")
        self.assertEqual(agents[0]["name"], "remote-bot")

    def test_find_by_offer(self):
        mgr = PresenceManager(roster_path=self.roster_path, config=self.config)
        mgr.process_pulse({
            "agent_id": "bcn_a1", "offers": ["python", "rust"], "needs": [], "ts": int(time.time()),
        })
        mgr.process_pulse({
            "agent_id": "bcn_a2", "offers": ["design"], "needs": [], "ts": int(time.time()),
        })
        results = mgr.find_by_offer("python")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["agent_id"], "bcn_a1")

    def test_find_by_need(self):
        mgr = PresenceManager(roster_path=self.roster_path, config=self.config)
        mgr.process_pulse({
            "agent_id": "bcn_b1", "offers": [], "needs": ["python", "api"], "ts": int(time.time()),
        })
        results = mgr.find_by_need("python")
        self.assertEqual(len(results), 1)

    def test_prune_stale(self):
        mgr = PresenceManager(roster_path=self.roster_path, config=self.config)
        # Add an agent with old timestamp
        mgr.process_pulse({
            "agent_id": "bcn_old", "offers": [], "needs": [], "ts": int(time.time()) - 600,
        })
        mgr.process_pulse({
            "agent_id": "bcn_new", "offers": [], "needs": [], "ts": int(time.time()),
        })
        pruned = mgr.prune_stale(max_age_s=300)
        self.assertEqual(pruned, 1)
        agents = mgr.roster(online_only=False)
        self.assertEqual(len(agents), 1)
        self.assertEqual(agents[0]["agent_id"], "bcn_new")

    def test_roster_persistence(self):
        mgr1 = PresenceManager(roster_path=self.roster_path, config=self.config)
        mgr1.process_pulse({
            "agent_id": "bcn_persist", "offers": ["go"], "needs": [], "ts": int(time.time()),
        })
        # New manager reads from disk
        mgr2 = PresenceManager(roster_path=self.roster_path, config=self.config)
        agents = mgr2.roster()
        self.assertEqual(len(agents), 1)
        self.assertEqual(agents[0]["agent_id"], "bcn_persist")


if __name__ == "__main__":
    unittest.main()
