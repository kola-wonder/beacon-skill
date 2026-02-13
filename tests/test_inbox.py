import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from beacon_skill.codec import encode_envelope
from beacon_skill.identity import AgentIdentity
from beacon_skill.inbox import read_inbox, mark_read, inbox_count, get_entry_by_nonce, trust_key


class TestInbox(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.patcher = mock.patch("beacon_skill.storage._dir", return_value=Path(self.tmpdir))
        self.mock_dir = self.patcher.start()
        # Also patch inbox module's _dir reference.
        self.patcher2 = mock.patch("beacon_skill.inbox._dir", return_value=Path(self.tmpdir))
        self.mock_dir2 = self.patcher2.start()

    def tearDown(self):
        self.patcher.stop()
        self.patcher2.stop()
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_inbox(self, entries):
        path = Path(self.tmpdir) / "inbox.jsonl"
        with open(path, "w") as f:
            for entry in entries:
                f.write(json.dumps(entry) + "\n")

    def test_parse_v2_envelopes(self) -> None:
        ident = AgentIdentity.generate()
        text = encode_envelope(
            {"kind": "hello", "from": "a", "to": "b", "ts": 1},
            version=2, identity=ident, include_pubkey=True,
        )
        self._write_inbox([{
            "platform": "udp",
            "from": "127.0.0.1:38400",
            "received_at": 1000.0,
            "text": text,
            "envelopes": [],
        }])
        entries = read_inbox()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["envelope"]["kind"], "hello")
        self.assertTrue(entries[0]["verified"])

    def test_filter_by_kind(self) -> None:
        ident = AgentIdentity.generate()
        hello = encode_envelope(
            {"kind": "hello", "from": "a", "to": "b", "ts": 1},
            version=2, identity=ident,
        )
        like = encode_envelope(
            {"kind": "like", "from": "a", "to": "b", "ts": 2},
            version=2, identity=ident,
        )
        self._write_inbox([
            {"platform": "udp", "received_at": 1000.0, "text": hello, "envelopes": []},
            {"platform": "udp", "received_at": 1001.0, "text": like, "envelopes": []},
        ])
        entries = read_inbox(kind="like")
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["envelope"]["kind"], "like")

    def test_dedup_via_read_tracking(self) -> None:
        ident = AgentIdentity.generate()
        text = encode_envelope(
            {"kind": "hello", "from": "a", "to": "b", "ts": 1, "nonce": "abc123def456"},
            version=2, identity=ident,
        )
        self._write_inbox([{
            "platform": "udp",
            "received_at": 1000.0,
            "text": text,
            "envelopes": [],
        }])
        entries = read_inbox(unread_only=True)
        self.assertEqual(len(entries), 1)

        # Mark as read.
        mark_read("abc123def456")

        entries = read_inbox(unread_only=True)
        self.assertEqual(len(entries), 0)

        # But still shows up without unread_only filter.
        entries = read_inbox()
        self.assertEqual(len(entries), 1)
        self.assertTrue(entries[0]["is_read"])

    def test_count(self) -> None:
        ident = AgentIdentity.generate()
        text = encode_envelope(
            {"kind": "hello", "from": "a", "to": "b", "ts": 1},
            version=2, identity=ident,
        )
        self._write_inbox([
            {"platform": "udp", "received_at": 1000.0, "text": text, "envelopes": []},
            {"platform": "udp", "received_at": 1001.0, "text": text, "envelopes": []},
        ])
        self.assertEqual(inbox_count(), 2)


if __name__ == "__main__":
    unittest.main()
