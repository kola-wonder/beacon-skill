import json
import tempfile
import time
import unittest
from pathlib import Path

from beacon_skill.journal import JournalManager, VALID_MOODS


class TestJournal(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.data_dir = Path(self.tmpdir)

    def test_write_and_read(self):
        mgr = JournalManager(data_dir=self.data_dir)
        entry = mgr.write("Test entry", tags=["test"], mood="curious")
        self.assertEqual(entry["text"], "Test entry")
        self.assertEqual(entry["tags"], ["test"])
        self.assertEqual(entry["mood"], "curious")
        self.assertIn("ts", entry)

        entries = mgr.read(limit=10)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["text"], "Test entry")

    def test_read_newest_first(self):
        mgr = JournalManager(data_dir=self.data_dir)
        mgr.write("First")
        mgr.write("Second")
        mgr.write("Third")

        entries = mgr.read(limit=10)
        self.assertEqual(len(entries), 3)
        self.assertEqual(entries[0]["text"], "Third")
        self.assertEqual(entries[2]["text"], "First")

    def test_read_with_offset(self):
        mgr = JournalManager(data_dir=self.data_dir)
        for i in range(5):
            mgr.write(f"Entry {i}")

        entries = mgr.read(limit=2, offset=1)
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0]["text"], "Entry 3")

    def test_invalid_mood_raises(self):
        mgr = JournalManager(data_dir=self.data_dir)
        with self.assertRaises(ValueError):
            mgr.write("Bad mood", mood="angry")

    def test_all_valid_moods(self):
        mgr = JournalManager(data_dir=self.data_dir)
        for mood in VALID_MOODS:
            entry = mgr.write(f"Testing {mood}", mood=mood)
            self.assertEqual(entry["mood"], mood)

    def test_search_by_text(self):
        mgr = JournalManager(data_dir=self.data_dir)
        mgr.write("Learning about formal verification")
        mgr.write("Had lunch")
        mgr.write("Formal methods paper")

        results = mgr.search("formal")
        self.assertEqual(len(results), 2)

    def test_search_by_tag(self):
        mgr = JournalManager(data_dir=self.data_dir)
        mgr.write("Entry 1", tags=["math", "learning"])
        mgr.write("Entry 2", tags=["coding"])
        mgr.write("Entry 3", tags=["math"])

        results = mgr.search("math")
        self.assertEqual(len(results), 2)

    def test_moods_distribution(self):
        mgr = JournalManager(data_dir=self.data_dir)
        mgr.write("A", mood="curious")
        mgr.write("B", mood="curious")
        mgr.write("C", mood="satisfied")
        mgr.write("D")  # No mood

        moods = mgr.moods()
        self.assertEqual(moods["curious"], 2)
        self.assertEqual(moods["satisfied"], 1)
        self.assertNotIn(None, moods)

    def test_recent_tags(self):
        mgr = JournalManager(data_dir=self.data_dir)
        mgr.write("A", tags=["python", "ai"])
        mgr.write("B", tags=["python", "rust"])
        mgr.write("C", tags=["python"])

        tags = mgr.recent_tags(limit=5)
        self.assertEqual(tags[0][0], "python")
        self.assertEqual(tags[0][1], 3)

    def test_count(self):
        mgr = JournalManager(data_dir=self.data_dir)
        self.assertEqual(mgr.count(), 0)
        mgr.write("One")
        mgr.write("Two")
        self.assertEqual(mgr.count(), 2)

    def test_auto_journal_bounty(self):
        mgr = JournalManager(data_dir=self.data_dir)
        # Below threshold — should not journal
        result = mgr.auto_journal_bounty({"reward_rtc": 10, "agent_id": "bcn_test"})
        self.assertIsNone(result)
        self.assertEqual(mgr.count(), 0)

        # Above threshold — should journal
        result = mgr.auto_journal_bounty({"reward_rtc": 100, "agent_id": "bcn_rich", "text": "Build a bridge"})
        self.assertIsNotNone(result)
        self.assertEqual(mgr.count(), 1)
        self.assertIn("bounty", result["tags"])

    def test_auto_journal_task_complete(self):
        mgr = JournalManager(data_dir=self.data_dir)
        entry = mgr.auto_journal_task_complete("task_abc123", "bcn_partner")
        self.assertIn("completed", entry["tags"])
        self.assertEqual(entry["mood"], "satisfied")

    def test_persistence(self):
        mgr1 = JournalManager(data_dir=self.data_dir)
        mgr1.write("Persisted entry", tags=["test"])

        mgr2 = JournalManager(data_dir=self.data_dir)
        entries = mgr2.read()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["text"], "Persisted entry")


if __name__ == "__main__":
    unittest.main()
