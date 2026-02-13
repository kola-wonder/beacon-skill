import json
import unittest

from beacon_skill.agent_card import generate_agent_card, verify_agent_card
from beacon_skill.identity import AgentIdentity


class TestAgentCard(unittest.TestCase):
    def test_generate_and_verify(self) -> None:
        ident = AgentIdentity.generate()
        card = generate_agent_card(
            ident,
            name="test-agent",
            transports={"udp": {"port": 38400}},
        )
        self.assertEqual(card["beacon_version"], "1.0.0")
        self.assertEqual(card["agent_id"], ident.agent_id)
        self.assertEqual(card["name"], "test-agent")
        self.assertIn("signature", card)
        self.assertTrue(verify_agent_card(card))

    def test_tampered_card_fails(self) -> None:
        ident = AgentIdentity.generate()
        card = generate_agent_card(ident, name="legit")
        self.assertTrue(verify_agent_card(card))
        # Tamper with the name.
        card["name"] = "hacked"
        self.assertFalse(verify_agent_card(card))

    def test_card_json_serializable(self) -> None:
        ident = AgentIdentity.generate()
        card = generate_agent_card(ident)
        text = json.dumps(card)
        restored = json.loads(text)
        self.assertTrue(verify_agent_card(restored))


if __name__ == "__main__":
    unittest.main()
