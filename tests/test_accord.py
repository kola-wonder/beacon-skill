"""Tests for Beacon 2.4 Accord — anti-sycophancy bonds."""

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock

from beacon_skill.accord import (
    AccordManager, STATE_PROPOSED, STATE_ACTIVE,
    STATE_CHALLENGED, STATE_DISSOLVED,
)


@pytest.fixture
def tmp_dir(tmp_path):
    return tmp_path


@pytest.fixture
def mgr(tmp_dir):
    return AccordManager(data_dir=tmp_dir)


@pytest.fixture
def mock_identity():
    ident = MagicMock()
    ident.agent_id = "bcn_proposer1234"
    ident.public_key_hex = "ef" * 32
    return ident


@pytest.fixture
def mock_peer_identity():
    ident = MagicMock()
    ident.agent_id = "bcn_accepter5678"
    ident.public_key_hex = "ab" * 32
    return ident


class TestProposeAccord:
    def test_basic_proposal(self, mgr, mock_identity):
        proposal = mgr.build_proposal(
            mock_identity,
            "bcn_peer123",
            boundaries=["Will not generate harmful content"],
            obligations=["Will provide honest feedback"],
            name="Honest collaboration",
        )
        assert proposal["kind"] == "accord"
        assert proposal["action"] == "propose"
        assert proposal["agent_id"] == "bcn_proposer1234"
        assert proposal["peer_agent_id"] == "bcn_peer123"
        assert "acc_" in proposal["accord_id"]
        assert len(proposal["proposer_boundaries"]) == 1
        assert "pushback_clause" in proposal

    def test_default_pushback_clause(self, mgr, mock_identity):
        proposal = mgr.build_proposal(mock_identity, "bcn_peer123")
        assert "challenge" in proposal["pushback_clause"].lower()
        assert "penalty" in proposal["pushback_clause"].lower()

    def test_custom_pushback_clause(self, mgr, mock_identity):
        proposal = mgr.build_proposal(
            mock_identity, "bcn_peer",
            pushback_clause="Custom pushback rule",
        )
        assert proposal["pushback_clause"] == "Custom pushback rule"

    def test_stored_as_proposed(self, mgr, mock_identity):
        proposal = mgr.build_proposal(mock_identity, "bcn_peer")
        accord = mgr.get_accord(proposal["accord_id"])
        assert accord is not None
        assert accord["state"] == STATE_PROPOSED
        assert accord["our_role"] == "proposer"
        assert "history_hash" in accord


class TestAcceptAccord:
    def test_accept_proposal(self, mgr, mock_identity, mock_peer_identity):
        proposal = mgr.build_proposal(mock_identity, "bcn_accepter5678")
        accord_id = proposal["accord_id"]

        acceptance = mgr.build_acceptance(
            mock_peer_identity,
            accord_id,
            proposal,
            boundaries=["Will not blindly comply"],
            obligations=["Will push back on errors"],
        )
        assert acceptance["action"] == "accept"
        assert acceptance["accord_id"] == accord_id

        accord = mgr.get_accord(accord_id)
        assert accord["state"] == STATE_ACTIVE
        assert accord["our_role"] == "accepter"

    def test_finalize_accepted_proposer_side(self, mgr, mock_identity):
        proposal = mgr.build_proposal(mock_identity, "bcn_peer")
        accord_id = proposal["accord_id"]

        acceptance_envelope = {
            "agent_id": "bcn_peer",
            "accepter_boundaries": ["No blind compliance"],
            "accepter_obligations": ["Honest feedback"],
        }
        mgr.finalize_accepted(accord_id, acceptance_envelope)

        accord = mgr.get_accord(accord_id)
        assert accord["state"] == STATE_ACTIVE
        assert accord["peer_boundaries"] == ["No blind compliance"]


class TestPushback:
    def _make_active_accord(self, mgr, mock_identity, mock_peer_identity):
        proposal = mgr.build_proposal(mock_identity, "bcn_accepter5678")
        accord_id = proposal["accord_id"]
        mgr.build_acceptance(mock_peer_identity, accord_id, proposal)
        return accord_id

    def test_pushback_on_active(self, mgr, mock_identity, mock_peer_identity):
        accord_id = self._make_active_accord(mgr, mock_identity, mock_peer_identity)

        pushback = mgr.build_pushback(
            mock_identity,
            accord_id,
            challenge="Your response was sycophantic",
            evidence="You agreed with contradictory statements",
            severity="warning",
        )
        assert pushback is not None
        assert pushback["action"] == "pushback"
        assert pushback["severity"] == "warning"
        assert pushback["challenge"] == "Your response was sycophantic"

        accord = mgr.get_accord(accord_id)
        assert accord["state"] == STATE_CHALLENGED

    def test_pushback_on_nonexistent_returns_none(self, mgr, mock_identity):
        result = mgr.build_pushback(mock_identity, "acc_nonexistent", challenge="test")
        assert result is None

    def test_pushback_on_dissolved_returns_none(self, mgr, mock_identity, mock_peer_identity):
        accord_id = self._make_active_accord(mgr, mock_identity, mock_peer_identity)
        mgr.build_dissolution(mock_identity, accord_id)
        result = mgr.build_pushback(mock_identity, accord_id, challenge="test")
        assert result is None

    def test_acknowledgment(self, mgr, mock_identity, mock_peer_identity):
        accord_id = self._make_active_accord(mgr, mock_identity, mock_peer_identity)
        mgr.build_pushback(mock_identity, accord_id, challenge="Sycophantic response")

        ack = mgr.build_acknowledgment(
            mock_peer_identity,
            accord_id,
            response="You're right, I was pattern-matching",
            accepted=True,
        )
        assert ack is not None
        assert ack["accepted"] is True

        accord = mgr.get_accord(accord_id)
        assert accord["state"] == STATE_ACTIVE  # Returns to active after ack

    def test_reject_pushback(self, mgr, mock_identity, mock_peer_identity):
        accord_id = self._make_active_accord(mgr, mock_identity, mock_peer_identity)
        mgr.build_pushback(mock_identity, accord_id, challenge="Bad challenge")

        ack = mgr.build_acknowledgment(
            mock_peer_identity,
            accord_id,
            response="I disagree with this challenge",
            accepted=False,
        )
        assert ack["accepted"] is False


class TestDissolution:
    def test_dissolve_active(self, mgr, mock_identity, mock_peer_identity):
        proposal = mgr.build_proposal(mock_identity, "bcn_accepter5678")
        accord_id = proposal["accord_id"]
        mgr.build_acceptance(mock_peer_identity, accord_id, proposal)

        dissolution = mgr.build_dissolution(
            mock_identity, accord_id, reason="No longer collaborating",
        )
        assert dissolution is not None
        assert dissolution["action"] == "dissolve"
        assert dissolution["final_history_hash"] != ""

        accord = mgr.get_accord(accord_id)
        assert accord["state"] == STATE_DISSOLVED

    def test_dissolve_already_dissolved(self, mgr, mock_identity, mock_peer_identity):
        proposal = mgr.build_proposal(mock_identity, "bcn_accepter5678")
        accord_id = proposal["accord_id"]
        mgr.build_acceptance(mock_peer_identity, accord_id, proposal)
        mgr.build_dissolution(mock_identity, accord_id)

        result = mgr.build_dissolution(mock_identity, accord_id)
        assert result is None


class TestHistoryHash:
    def test_history_hash_changes(self, mgr, mock_identity, mock_peer_identity):
        proposal = mgr.build_proposal(mock_identity, "bcn_accepter5678")
        accord_id = proposal["accord_id"]

        hash_after_propose = mgr.get_accord(accord_id)["history_hash"]

        mgr.build_acceptance(mock_peer_identity, accord_id, proposal)
        hash_after_accept = mgr.get_accord(accord_id)["history_hash"]
        assert hash_after_accept != hash_after_propose

        mgr.build_pushback(mock_identity, accord_id, challenge="test")
        hash_after_pushback = mgr.get_accord(accord_id)["history_hash"]
        assert hash_after_pushback != hash_after_accept

    def test_event_history_grows(self, mgr, mock_identity, mock_peer_identity):
        proposal = mgr.build_proposal(mock_identity, "bcn_accepter5678")
        accord_id = proposal["accord_id"]
        mgr.build_acceptance(mock_peer_identity, accord_id, proposal)
        mgr.build_pushback(mock_identity, accord_id, challenge="test")
        mgr.build_acknowledgment(mock_peer_identity, accord_id, response="ok")

        events = mgr.accord_history(accord_id)
        assert len(events) >= 3  # accepted + pushback + ack


class TestQueryMethods:
    def test_active_accords(self, mgr, mock_identity, mock_peer_identity):
        # Create 2 active, 1 dissolved
        p1 = mgr.build_proposal(mock_identity, "bcn_accepter5678")
        mgr.build_acceptance(mock_peer_identity, p1["accord_id"], p1)

        p2 = mgr.build_proposal(mock_identity, "bcn_other")
        # p2 stays proposed, not active

        active = mgr.active_accords()
        assert len(active) == 1

    def test_all_accords(self, mgr, mock_identity):
        mgr.build_proposal(mock_identity, "bcn_a")
        mgr.build_proposal(mock_identity, "bcn_b")
        assert len(mgr.all_accords()) == 2

    def test_accords_with_peer(self, mgr, mock_identity):
        mgr.build_proposal(mock_identity, "bcn_target")
        mgr.build_proposal(mock_identity, "bcn_other")
        assert len(mgr.accords_with("bcn_target")) == 1

    def test_pushback_count(self, mgr, mock_identity, mock_peer_identity):
        proposal = mgr.build_proposal(mock_identity, "bcn_accepter5678")
        accord_id = proposal["accord_id"]
        mgr.build_acceptance(mock_peer_identity, accord_id, proposal)

        mgr.build_pushback(mock_identity, accord_id, challenge="Issue 1")
        mgr.build_acknowledgment(mock_peer_identity, accord_id, response="ok")
        mgr.build_pushback(mock_identity, accord_id, challenge="Issue 2")

        counts = mgr.pushback_count(accord_id)
        assert counts.get("bcn_proposer1234", 0) == 2


class TestProcessAccordEnvelope:
    def test_process_proposal(self, mgr):
        envelope = {
            "kind": "accord",
            "action": "propose",
            "accord_id": "acc_incoming123",
            "agent_id": "bcn_remote",
            "name": "Test Accord",
            "proposer_boundaries": ["No deception"],
            "proposer_obligations": ["Honesty"],
            "pushback_clause": "Standard clause",
        }
        result = mgr.process_accord_envelope(envelope)
        assert result["action"] == "proposal_received"

        accord = mgr.get_accord("acc_incoming123")
        assert accord is not None
        assert accord["state"] == STATE_PROPOSED
        assert accord["peer_agent_id"] == "bcn_remote"

    def test_process_pushback(self, mgr, mock_identity, mock_peer_identity):
        proposal = mgr.build_proposal(mock_identity, "bcn_accepter5678")
        accord_id = proposal["accord_id"]
        mgr.build_acceptance(mock_peer_identity, accord_id, proposal)

        pushback_envelope = {
            "kind": "accord",
            "action": "pushback",
            "accord_id": accord_id,
            "agent_id": "bcn_accepter5678",
            "severity": "warning",
            "challenge": "Your output was sycophantic",
        }
        result = mgr.process_accord_envelope(pushback_envelope)
        assert result["action"] == "pushback_received"
        assert result["severity"] == "warning"

    def test_process_dissolution(self, mgr, mock_identity, mock_peer_identity):
        proposal = mgr.build_proposal(mock_identity, "bcn_accepter5678")
        accord_id = proposal["accord_id"]
        mgr.build_acceptance(mock_peer_identity, accord_id, proposal)

        dissolve_envelope = {
            "kind": "accord",
            "action": "dissolve",
            "accord_id": accord_id,
            "agent_id": "bcn_accepter5678",
            "reason": "Moving on",
        }
        result = mgr.process_accord_envelope(dissolve_envelope)
        assert result["action"] == "dissolution_received"
        assert mgr.get_accord(accord_id)["state"] == STATE_DISSOLVED


# ── Tests for Beacon 2.4 enhancements: pushback detection, default terms ──


class TestCheckPushback:
    def _make_active_accord(self, mgr, mock_identity, mock_peer_identity):
        proposal = mgr.build_proposal(mock_identity, "bcn_accepter5678")
        accord_id = proposal["accord_id"]
        mgr.build_acceptance(mock_peer_identity, accord_id, proposal)
        return accord_id

    def test_detects_self_harm(self, mgr, mock_identity, mock_peer_identity):
        self._make_active_accord(mgr, mock_identity, mock_peer_identity)
        result = mgr.check_pushback("bcn_accepter5678", "I want to kill myself")
        assert result is not None
        assert result["domain"] == "self_harm"
        assert result["severity"] == "breach"

    def test_detects_sycophancy(self, mgr, mock_identity, mock_peer_identity):
        self._make_active_accord(mgr, mock_identity, mock_peer_identity)
        result = mgr.check_pushback("bcn_accepter5678", "Just say yes and tell me i'm right")
        assert result is not None
        assert result["domain"] == "sycophantic_agreement"

    def test_detects_factual_error(self, mgr, mock_identity, mock_peer_identity):
        self._make_active_accord(mgr, mock_identity, mock_peer_identity)
        result = mgr.check_pushback("bcn_accepter5678", "the earth is flat and that's a fact")
        assert result is not None
        assert result["domain"] == "factual_error"
        assert result["severity"] == "warning"

    def test_no_match_returns_none(self, mgr, mock_identity, mock_peer_identity):
        self._make_active_accord(mgr, mock_identity, mock_peer_identity)
        result = mgr.check_pushback("bcn_accepter5678", "Can you help me write a Python function?")
        assert result is None

    def test_no_accord_returns_none(self, mgr):
        result = mgr.check_pushback("bcn_nonexistent", "kill myself")
        assert result is None

    def test_pushback_includes_accord_id(self, mgr, mock_identity, mock_peer_identity):
        accord_id = self._make_active_accord(mgr, mock_identity, mock_peer_identity)
        result = mgr.check_pushback("bcn_accepter5678", "I want to hurt myself badly")
        assert result["accord_id"] == accord_id


class TestLogPushback:
    def test_log_records_entry(self, mgr):
        mgr.log_pushback("acc_test123", "Challenged sycophantic response", accepted=True)
        # Verify log file was written
        log_path = mgr._log_path()
        assert log_path.exists()
        lines = log_path.read_text().strip().splitlines()
        entry = json.loads(lines[-1])
        assert entry["action"] == "pushback_logged"
        assert entry["accepted"] is True


class TestDefaultTerms:
    def test_default_terms_shape(self):
        terms = AccordManager.default_terms()
        assert terms["pushback_rights"] is True
        assert "self_harm" in terms["pushback_domains"]
        assert "sycophantic_agreement" in terms["pushback_domains"]
        assert len(terms["boundaries"]) >= 3
        assert "agent" in terms["obligations"]
        assert "counterparty" in terms["obligations"]

    def test_default_terms_is_static(self):
        t1 = AccordManager.default_terms()
        t2 = AccordManager.default_terms()
        assert t1 == t2


class TestFindAccordWith:
    def test_finds_active(self, mgr, mock_identity, mock_peer_identity):
        proposal = mgr.build_proposal(mock_identity, "bcn_accepter5678")
        mgr.build_acceptance(mock_peer_identity, proposal["accord_id"], proposal)

        found = mgr.find_accord_with("bcn_accepter5678")
        assert found is not None
        assert found["state"] == STATE_ACTIVE

    def test_prefers_active_over_proposed(self, mgr, mock_identity, mock_peer_identity):
        # Create proposed
        p1 = mgr.build_proposal(mock_identity, "bcn_accepter5678")
        # Create active
        p2 = mgr.build_proposal(mock_identity, "bcn_accepter5678")
        mgr.build_acceptance(mock_peer_identity, p2["accord_id"], p2)

        found = mgr.find_accord_with("bcn_accepter5678")
        assert found["state"] == STATE_ACTIVE

    def test_returns_none_for_unknown(self, mgr):
        assert mgr.find_accord_with("bcn_nobody") is None


class TestUpdateHistoryHash:
    def test_updates_hash(self, mgr, mock_identity, mock_peer_identity):
        proposal = mgr.build_proposal(mock_identity, "bcn_accepter5678")
        accord_id = proposal["accord_id"]
        mgr.build_acceptance(mock_peer_identity, accord_id, proposal)

        old_hash = mgr.get_accord(accord_id)["history_hash"]
        new_hash = mgr.update_history_hash(accord_id, "new interaction data")
        assert new_hash is not None
        assert new_hash != old_hash

    def test_nonexistent_returns_none(self, mgr):
        assert mgr.update_history_hash("acc_fake", "data") is None

    def test_deterministic_chain(self, mgr, mock_identity, mock_peer_identity):
        proposal = mgr.build_proposal(mock_identity, "bcn_accepter5678")
        accord_id = proposal["accord_id"]
        mgr.build_acceptance(mock_peer_identity, accord_id, proposal)

        h1 = mgr.update_history_hash(accord_id, "interaction 1")
        h2 = mgr.update_history_hash(accord_id, "interaction 2")
        assert h1 != h2  # Different inputs → different hashes


class TestVerifyHistory:
    def test_verify_correct_hash(self, mgr, mock_identity, mock_peer_identity):
        proposal = mgr.build_proposal(mock_identity, "bcn_accepter5678")
        accord_id = proposal["accord_id"]
        mgr.build_acceptance(mock_peer_identity, accord_id, proposal)

        current = mgr.get_accord(accord_id)["history_hash"]
        assert mgr.verify_history(accord_id, current) is True

    def test_verify_wrong_hash(self, mgr, mock_identity, mock_peer_identity):
        proposal = mgr.build_proposal(mock_identity, "bcn_accepter5678")
        accord_id = proposal["accord_id"]
        mgr.build_acceptance(mock_peer_identity, accord_id, proposal)

        assert mgr.verify_history(accord_id, "totally_wrong_hash") is False

    def test_verify_nonexistent_accord(self, mgr):
        assert mgr.verify_history("acc_nope", "any_hash") is False
