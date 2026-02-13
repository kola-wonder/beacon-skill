import hashlib
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from beacon_skill.anchor import (
    AnchorManager,
    anchor_action,
    anchor_epoch,
    commitment_hash,
    ANCHOR_LOG,
)


class TestCommitmentHash(unittest.TestCase):
    def test_hash_string(self):
        h = commitment_hash("hello world")
        expected = hashlib.sha256(b"hello world").hexdigest()
        self.assertEqual(h, expected)
        self.assertEqual(len(h), 64)

    def test_hash_bytes(self):
        raw = b"\x00\x01\x02\xff"
        h = commitment_hash(raw)
        expected = hashlib.sha256(raw).hexdigest()
        self.assertEqual(h, expected)

    def test_hash_dict_canonical(self):
        """Dict hashing must be deterministic regardless of insertion order."""
        d1 = {"z": 1, "a": 2, "m": [3, 4]}
        d2 = {"a": 2, "m": [3, 4], "z": 1}
        self.assertEqual(commitment_hash(d1), commitment_hash(d2))

    def test_hash_dict_matches_manual(self):
        data = {"key": "value"}
        canonical = json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
        expected = hashlib.sha256(canonical).hexdigest()
        self.assertEqual(commitment_hash(data), expected)

    def test_hash_different_types_differ(self):
        """String 'hello' and dict {"0":"hello"} should produce different hashes."""
        self.assertNotEqual(commitment_hash("hello"), commitment_hash({"0": "hello"}))


class TestAnchorManager(unittest.TestCase):
    def setUp(self):
        self.client = MagicMock()
        self.identity = MagicMock()
        self.identity.sign_hex.return_value = "ab" * 32
        self.identity.public_key_hex = "cd" * 16
        self.mgr = AnchorManager(client=self.client, identity=self.identity)

    @patch("beacon_skill.anchor.append_jsonl")
    def test_anchor_submit_mock(self, mock_log):
        """Submit calls client.anchor_submit with correct shape."""
        self.client.anchor_submit.return_value = {
            "ok": True,
            "anchor_id": 42,
            "commitment": "a" * 64,
            "epoch": 73,
            "created_at": 1707841200,
        }
        result = self.mgr.anchor("test data", data_type="test")
        self.assertTrue(result["ok"])
        self.assertEqual(result["anchor_id"], 42)

        call_args = self.client.anchor_submit.call_args[0][0]
        self.assertEqual(len(call_args["commitment"]), 64)
        self.assertEqual(call_args["data_type"], "test")
        self.assertEqual(call_args["public_key"], "cd" * 16)
        self.assertEqual(len(call_args["signature"]), 64)

        # JSONL log written
        mock_log.assert_called_once()
        log_entry = mock_log.call_args[0][1]
        self.assertEqual(log_entry["status"], "ok")

    def test_anchor_verify_mock(self):
        """Verify returns anchor dict when found."""
        self.client.anchor_verify.return_value = {
            "ok": True,
            "found": True,
            "anchor": {"id": 1, "commitment": "a" * 64, "data_type": "test"},
        }
        result = self.mgr.verify("a" * 64)
        self.assertIsNotNone(result)
        self.assertEqual(result["id"], 1)

    def test_anchor_verify_not_found(self):
        """Verify returns None when not found."""
        self.client.anchor_verify.return_value = {"ok": True, "found": False}
        result = self.mgr.verify("b" * 64)
        self.assertIsNone(result)

    @patch("beacon_skill.anchor.append_jsonl")
    def test_anchor_duplicate_idempotent(self, mock_log):
        """409 duplicate handled gracefully, not raised."""
        from beacon_skill.transports.rustchain import RustChainError

        self.client.anchor_submit.side_effect = RustChainError("commitment_exists")
        result = self.mgr.anchor("dup data", data_type="test")
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "commitment_exists")

        log_entry = mock_log.call_args[0][1]
        self.assertEqual(log_entry["status"], "duplicate")

    def test_verify_data_hashes_then_verifies(self):
        """verify_data hashes the input and calls verify."""
        expected_hash = commitment_hash("my data")
        self.client.anchor_verify.return_value = {"ok": True, "found": False}
        self.mgr.verify_data("my data")
        self.client.anchor_verify.assert_called_once_with(expected_hash)

    def test_my_anchors(self):
        """my_anchors passes submitter address derived from identity."""
        self.client.anchor_list.return_value = {"ok": True, "anchors": [{"id": 1}]}
        result = self.mgr.my_anchors(limit=10)
        self.assertEqual(len(result), 1)
        # Verify submitter was derived from identity pubkey
        call_kwargs = self.client.anchor_list.call_args[1]
        self.assertTrue(call_kwargs["submitter"].startswith("RTC"))
        self.assertEqual(call_kwargs["limit"], 10)


class TestAnchorManagerWithKeypair(unittest.TestCase):
    def test_sign_with_keypair(self):
        """When keypair is provided, use it for signing instead of identity."""
        from beacon_skill.transports.rustchain import RustChainKeypair

        kp = RustChainKeypair.generate()
        client = MagicMock()
        client.anchor_submit.return_value = {"ok": True, "anchor_id": 1}
        mgr = AnchorManager(client=client, keypair=kp)

        with patch("beacon_skill.anchor.append_jsonl"):
            mgr.anchor("keypair test", data_type="test")

        call_args = client.anchor_submit.call_args[0][0]
        self.assertEqual(call_args["public_key"], kp.public_key_hex)


class TestConvenienceFunctions(unittest.TestCase):
    def setUp(self):
        self.mgr = MagicMock(spec=AnchorManager)
        self.mgr.anchor.return_value = {"ok": True, "anchor_id": 99}

    def test_anchor_action_sent(self):
        """anchor_action anchors sent actions."""
        result = anchor_action(
            {"action_id": "abc123", "status": "sent", "method": "webhook", "ts": 1000},
            self.mgr,
        )
        self.assertIsNotNone(result)
        self.mgr.anchor.assert_called_once()
        call_args = self.mgr.anchor.call_args
        self.assertEqual(call_args[1]["data_type"], "beacon_action")

    def test_anchor_action_skips_non_sent(self):
        """anchor_action skips non-sent actions."""
        result = anchor_action({"action_id": "x", "status": "failed"}, self.mgr)
        self.assertIsNone(result)
        self.mgr.anchor.assert_not_called()

    def test_anchor_epoch(self):
        """anchor_epoch anchors epoch settlement summary."""
        settlements = [{"miner": "a", "rtc": 1.5}, {"miner": "b", "rtc": 0.5}]
        result = anchor_epoch(73, settlements, self.mgr)
        self.assertIsNotNone(result)
        call_args = self.mgr.anchor.call_args
        self.assertEqual(call_args[1]["data_type"], "epoch_settlement")
        self.assertEqual(call_args[1]["metadata"]["epoch"], 73)
        self.assertEqual(call_args[1]["metadata"]["count"], 2)


class TestLocalHistory(unittest.TestCase):
    @patch("beacon_skill.anchor.read_jsonl_tail")
    def test_history_reads_jsonl(self, mock_read):
        mock_read.return_value = [{"ts": 1, "status": "ok"}]
        client = MagicMock()
        identity = MagicMock()
        identity.sign_hex.return_value = "00" * 32
        identity.public_key_hex = "ff" * 16
        mgr = AnchorManager(client=client, identity=identity)
        entries = mgr.history(limit=10)
        mock_read.assert_called_once_with(ANCHOR_LOG, limit=10)
        self.assertEqual(len(entries), 1)


if __name__ == "__main__":
    unittest.main()
