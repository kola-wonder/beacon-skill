import os
import tempfile
import unittest

from beacon_skill.guard import check_envelope_window, clear_nonce_cache


class GuardTests(unittest.TestCase):
    def setUp(self):
        self._old_home = os.environ.get("HOME")
        self._tmp = tempfile.TemporaryDirectory()
        os.environ["HOME"] = self._tmp.name
        # ensure empty state
        clear_nonce_cache()

    def tearDown(self):
        if self._old_home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = self._old_home
        self._tmp.cleanup()

    def test_missing_nonce(self):
        ok, reason = check_envelope_window({"ts": 1000}, now=1000)
        self.assertFalse(ok)
        self.assertEqual(reason, "missing_nonce")

    def test_missing_ts(self):
        ok, reason = check_envelope_window({"nonce": "abc123"}, now=1000)
        self.assertFalse(ok)
        self.assertEqual(reason, "missing_ts")

    def test_stale_ts(self):
        ok, reason = check_envelope_window({"nonce": "abc123", "ts": 0}, now=2000, max_age_s=300)
        self.assertFalse(ok)
        self.assertEqual(reason, "stale_ts")

    def test_future_ts(self):
        ok, reason = check_envelope_window({"nonce": "abc123", "ts": 2000}, now=1000, max_future_skew_s=60)
        self.assertFalse(ok)
        self.assertEqual(reason, "future_ts")

    def test_replay_nonce(self):
        env = {"nonce": "abc123", "ts": 1000}
        ok1, reason1 = check_envelope_window(env, now=1000)
        ok2, reason2 = check_envelope_window(env, now=1000)
        self.assertTrue(ok1)
        self.assertEqual(reason1, "ok")
        self.assertFalse(ok2)
        self.assertEqual(reason2, "replay_nonce")


if __name__ == "__main__":
    unittest.main()
