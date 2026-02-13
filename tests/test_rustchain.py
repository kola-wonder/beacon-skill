import json
import unittest

from beacon_skill.transports.rustchain import RustChainClient, RustChainKeypair


class TestRustChainSigning(unittest.TestCase):
    def test_sign_transfer_shape(self) -> None:
        kp = RustChainKeypair.generate()
        c = RustChainClient(base_url="https://example.invalid", verify_ssl=True)
        payload = c.sign_transfer(
            private_key_hex=kp.private_key_hex,
            to_address="RTC" + ("0" * 40),
            amount_rtc=1.5,
            memo="test",
            nonce=123,
        )
        self.assertEqual(payload["from_address"], kp.address)
        self.assertEqual(payload["nonce"], 123)
        self.assertEqual(payload["amount_rtc"], 1.5)
        # Basic sanity: JSON serialization should work.
        json.dumps(payload)

    def test_mnemonic_roundtrip(self) -> None:
        try:
            kp1 = RustChainKeypair.generate_with_mnemonic()
        except RuntimeError:
            self.skipTest("mnemonic package not installed")
        self.assertIsNotNone(kp1.mnemonic)
        words = kp1.mnemonic.split()
        self.assertEqual(len(words), 24)
        # Restore from same mnemonic.
        kp2 = RustChainKeypair.from_mnemonic(kp1.mnemonic)
        self.assertEqual(kp1.address, kp2.address)
        self.assertEqual(kp1.private_key_hex, kp2.private_key_hex)

    def test_encrypted_keystore(self) -> None:
        kp = RustChainKeypair.generate()
        pw = "test-wallet-pass"
        keystore = kp.export_encrypted(pw)
        self.assertTrue(keystore["encrypted"])
        self.assertEqual(keystore["address"], kp.address)
        # Restore.
        restored = RustChainKeypair.from_encrypted(keystore, pw)
        self.assertEqual(kp.address, restored.address)
        self.assertEqual(kp.private_key_hex, restored.private_key_hex)
        # Wrong password should fail.
        with self.assertRaises(ValueError):
            RustChainKeypair.from_encrypted(keystore, "wrong")


if __name__ == "__main__":
    unittest.main()
