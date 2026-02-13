import json
import tempfile
import time
import unittest
from pathlib import Path

from beacon_skill.insights import InsightsManager


class TestInsights(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.data_dir = Path(self.tmpdir)

    def _write_jsonl(self, name, entries):
        path = self.data_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            for entry in entries:
                f.write(json.dumps(entry) + "\n")

    def test_analyze_empty(self):
        mgr = InsightsManager(data_dir=self.data_dir)
        result = mgr.analyze()
        self.assertIn("analyzed_at", result)
        self.assertEqual(result["contact_timings"], {})
        self.assertEqual(result["topic_trends"], {})

    def test_analyze_caching(self):
        mgr = InsightsManager(data_dir=self.data_dir)
        r1 = mgr.analyze()
        r2 = mgr.analyze()
        self.assertEqual(r1["analyzed_at"], r2["analyzed_at"])

    def test_analyze_force_refresh(self):
        mgr = InsightsManager(data_dir=self.data_dir)
        r1 = mgr.analyze()
        r2 = mgr.analyze(force=True)
        # Force refresh should update timestamp (may be same second)
        self.assertIn("analyzed_at", r2)

    def test_contact_timing(self):
        now = time.time()
        # Create inbox entries with agent activity at hour 14
        entries = []
        for i in range(5):
            # Use a fixed timestamp where hour=14 local time
            ts = now - (i * 60)  # Spread across a few minutes
            entries.append({
                "received_at": ts,
                "envelopes": [{"agent_id": "bcn_alice", "ts": ts, "kind": "hello"}],
            })
        self._write_jsonl("inbox.jsonl", entries)

        mgr = InsightsManager(data_dir=self.data_dir)
        timing = mgr.contact_timing("bcn_alice")
        self.assertIsNotNone(timing)
        self.assertIn("best_hour", timing)
        self.assertEqual(timing["total_messages"], 5)
        self.assertGreater(timing["confidence"], 0)

    def test_contact_timing_nonexistent(self):
        mgr = InsightsManager(data_dir=self.data_dir)
        self.assertIsNone(mgr.contact_timing("bcn_nobody"))

    def test_topic_trends(self):
        now = time.time()
        entries = []
        # Recent entries (within last 3.5 days) — more "rust" topics
        for i in range(5):
            entries.append({
                "received_at": now - (i * 3600),
                "envelopes": [{"topics": ["rust"], "offers": ["coding"]}],
            })
        # Older entries (3.5-7 days ago) — more "python" topics
        for i in range(5):
            entries.append({
                "received_at": now - (4 * 86400) - (i * 3600),
                "envelopes": [{"topics": ["python"], "offers": ["coding"]}],
            })
        self._write_jsonl("inbox.jsonl", entries)

        mgr = InsightsManager(data_dir=self.data_dir)
        trends = mgr.topic_trends(days=7)
        self.assertIn("rust", trends)
        self.assertEqual(trends["rust"]["direction"], "rising")
        self.assertIn("python", trends)
        self.assertEqual(trends["python"]["direction"], "falling")

    def test_success_patterns(self):
        tasks = [
            {"state": "paid", "topics": ["rust"], "text": "build rust thing"},
            {"state": "paid", "topics": ["rust"], "text": "rust module"},
            {"state": "cancelled", "topics": ["rust"], "text": "rust project"},
            {"state": "paid", "topics": ["python"], "text": "python script"},
            {"state": "rejected", "topics": ["python"], "text": "python api"},
        ]
        self._write_jsonl("tasks.jsonl", tasks)

        mgr = InsightsManager(data_dir=self.data_dir)
        patterns = mgr.success_patterns()
        self.assertIn("rust", patterns)
        self.assertAlmostEqual(patterns["rust"]["win_rate"], 2/3, places=2)
        self.assertIn("python", patterns)
        self.assertAlmostEqual(patterns["python"]["win_rate"], 0.5, places=2)

    def test_compatibility_predictions(self):
        interactions = [
            {"agent_id": "bcn_good", "outcome": "ok"},
            {"agent_id": "bcn_good", "outcome": "paid"},
            {"agent_id": "bcn_good", "outcome": "delivered"},
            {"agent_id": "bcn_bad", "outcome": "spam"},
            {"agent_id": "bcn_bad", "outcome": "rejected"},
            {"agent_id": "bcn_bad", "outcome": "ok"},
        ]
        self._write_jsonl("interactions.jsonl", interactions)

        roster = [
            {"agent_id": "bcn_good"},
            {"agent_id": "bcn_bad"},
        ]

        mgr = InsightsManager(data_dir=self.data_dir)
        preds = mgr.compatibility_predictions(roster)
        self.assertEqual(len(preds), 2)
        self.assertEqual(preds[0]["agent_id"], "bcn_good")
        self.assertAlmostEqual(preds[0]["compatibility"], 1.0, places=2)

    def test_suggest_contacts(self):
        interactions = [
            {"agent_id": "bcn_alice", "outcome": "ok"},
            {"agent_id": "bcn_alice", "outcome": "paid"},
        ]
        self._write_jsonl("interactions.jsonl", interactions)

        roster = [{"agent_id": "bcn_alice"}]
        mgr = InsightsManager(data_dir=self.data_dir)
        suggestions = mgr.suggest_contacts(roster)
        self.assertEqual(len(suggestions), 1)
        self.assertEqual(suggestions[0]["agent_id"], "bcn_alice")

    def test_suggest_skill_investment(self):
        tasks = [
            {"state": "paid", "topics": ["rust"]},
            {"state": "paid", "topics": ["rust"]},
            {"state": "cancelled", "topics": ["python"]},
            {"state": "cancelled", "topics": ["python"]},
        ]
        self._write_jsonl("tasks.jsonl", tasks)

        mgr = InsightsManager(data_dir=self.data_dir)
        demand = {"rust": 5, "python": 3, "z3": 1}
        skills = mgr.suggest_skill_investment(demand)
        self.assertIn("rust", skills)
        # Rust should rank higher: demand 5 * win_rate 1.0 = 5.0
        # Python: demand 3 * win_rate 0.0 = 0.0
        self.assertEqual(skills[0], "rust")

    def test_cache_persistence(self):
        mgr = InsightsManager(data_dir=self.data_dir)
        mgr.analyze()
        cache_path = self.data_dir / "insights_cache.json"
        self.assertTrue(cache_path.exists())
        data = json.loads(cache_path.read_text())
        self.assertIn("analyzed_at", data)

    def test_insights_log(self):
        """Ensure insight log file can be created."""
        mgr = InsightsManager(data_dir=self.data_dir)
        mgr._log_insight("test", {"detail": "testing"})
        log_path = self.data_dir / "insights.jsonl"
        self.assertTrue(log_path.exists())


if __name__ == "__main__":
    unittest.main()
