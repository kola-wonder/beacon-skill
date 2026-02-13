import socket
import threading
import time
import unittest

from beacon_skill.codec import encode_envelope, verify_envelope, decode_envelopes
from beacon_skill.identity import AgentIdentity
from beacon_skill.transports.udp import udp_send, udp_listen, UDPMessage


def _find_free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class TestUDP(unittest.TestCase):
    def test_loopback_send_receive(self) -> None:
        port = _find_free_port()
        received = []

        def listener():
            udp_listen("127.0.0.1", port, received.append, timeout_s=2.0)

        t = threading.Thread(target=listener, daemon=True)
        t.start()
        time.sleep(0.1)  # Let listener bind.

        udp_send("127.0.0.1", port, b"hello beacon")
        t.join(timeout=3.0)

        self.assertEqual(len(received), 1)
        self.assertEqual(received[0].text, "hello beacon")
        self.assertEqual(received[0].addr[0], "127.0.0.1")
        self.assertIsNone(received[0].verified)

    def test_signed_v2_verify(self) -> None:
        port = _find_free_port()
        ident = AgentIdentity.generate()
        known_keys = {ident.agent_id: ident.public_key_hex}
        received = []

        def listener():
            udp_listen("127.0.0.1", port, received.append, timeout_s=2.0, known_keys=known_keys)

        t = threading.Thread(target=listener, daemon=True)
        t.start()
        time.sleep(0.1)

        payload = {"kind": "hello", "from": "test", "to": "peer", "ts": 1}
        text = encode_envelope(payload, version=2, identity=ident, include_pubkey=True)
        udp_send("127.0.0.1", port, text.encode("utf-8"))
        t.join(timeout=3.0)

        self.assertEqual(len(received), 1)
        self.assertTrue(received[0].verified)

    def test_unsigned_passthrough(self) -> None:
        port = _find_free_port()
        received = []

        def listener():
            udp_listen("127.0.0.1", port, received.append, timeout_s=2.0, known_keys={})

        t = threading.Thread(target=listener, daemon=True)
        t.start()
        time.sleep(0.1)

        # Send a v1 (unsigned) envelope.
        payload = {"v": 1, "kind": "like", "from": "a", "to": "b", "ts": 1}
        text = encode_envelope(payload, version=1)
        udp_send("127.0.0.1", port, text.encode("utf-8"))
        t.join(timeout=3.0)

        self.assertEqual(len(received), 1)
        self.assertIsNone(received[0].verified)


if __name__ == "__main__":
    unittest.main()
