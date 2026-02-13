"""Tests for Beacon 2.6 Contracts — rent/buy/lease-to-own with RustChain escrow."""

import json
import time
import pytest
from pathlib import Path
from unittest.mock import MagicMock, call

from beacon_skill.contracts import ContractManager, VALID_TRANSITIONS, CONTRACT_TYPES


@pytest.fixture
def tmp_dir(tmp_path):
    return tmp_path


@pytest.fixture
def mgr(tmp_dir):
    return ContractManager(data_dir=str(tmp_dir))


# ── Listing ──


class TestListAgent:
    def test_list_rent(self, mgr):
        result = mgr.list_agent("bcn_seller", "rent", 10.0, duration_days=30)
        assert result["ok"]
        assert result["contract_id"].startswith("ctr_")
        assert result["type"] == "rent"
        assert result["price_rtc"] == 10.0

    def test_list_buy(self, mgr):
        result = mgr.list_agent("bcn_seller", "buy", 500.0)
        assert result["ok"]
        assert result["type"] == "buy"

    def test_list_lease_to_own(self, mgr):
        result = mgr.list_agent("bcn_seller", "lease_to_own", 50.0,
                                duration_days=30,
                                terms={"total_periods": 12, "buyout_price_rtc": 500.0})
        assert result["ok"]
        ctr = mgr.get_contract(result["contract_id"])
        assert "lease_to_own" in ctr
        assert ctr["lease_to_own"]["total_periods"] == 12
        assert ctr["lease_to_own"]["buyout_price_rtc"] == 500.0

    def test_generates_id(self, mgr):
        r1 = mgr.list_agent("bcn_a", "buy", 100.0)
        r2 = mgr.list_agent("bcn_b", "buy", 200.0)
        assert r1["contract_id"] != r2["contract_id"]

    def test_stored_as_listed(self, mgr):
        result = mgr.list_agent("bcn_s", "rent", 5.0, duration_days=7)
        ctr = mgr.get_contract(result["contract_id"])
        assert ctr["state"] == "listed"
        assert ctr["seller_id"] == "bcn_s"
        assert ctr["price_rtc"] == 5.0

    def test_invalid_type(self, mgr):
        result = mgr.list_agent("bcn_s", "invalid", 10.0)
        assert "error" in result

    def test_negative_price(self, mgr):
        result = mgr.list_agent("bcn_s", "buy", -5.0)
        assert "error" in result

    def test_rent_requires_duration(self, mgr):
        result = mgr.list_agent("bcn_s", "rent", 10.0)
        assert "error" in result

    def test_capabilities(self, mgr):
        result = mgr.list_agent("bcn_s", "buy", 100.0,
                                capabilities=["coding", "ai"])
        ctr = mgr.get_contract(result["contract_id"])
        assert ctr["capabilities"] == ["coding", "ai"]


# ── Offers ──


class TestOfferAcceptReject:
    def test_make_offer(self, mgr):
        listing = mgr.list_agent("bcn_seller", "rent", 10.0, duration_days=30)
        cid = listing["contract_id"]
        result = mgr.make_offer(cid, "bcn_buyer")
        assert result["ok"]
        ctr = mgr.get_contract(cid)
        assert ctr["state"] == "offered"
        assert ctr["buyer_id"] == "bcn_buyer"

    def test_counter_price(self, mgr):
        listing = mgr.list_agent("bcn_seller", "rent", 10.0, duration_days=30)
        cid = listing["contract_id"]
        result = mgr.make_offer(cid, "bcn_buyer", offered_price_rtc=8.0)
        assert result["offered_price_rtc"] == 8.0

    def test_accept_offer(self, mgr):
        listing = mgr.list_agent("bcn_seller", "rent", 10.0, duration_days=30)
        cid = listing["contract_id"]
        mgr.make_offer(cid, "bcn_buyer")
        result = mgr.accept_offer(cid)
        assert result["ok"]
        assert result["state"] == "accepted"

    def test_reject_returns_to_listed(self, mgr):
        listing = mgr.list_agent("bcn_seller", "rent", 10.0, duration_days=30)
        cid = listing["contract_id"]
        mgr.make_offer(cid, "bcn_buyer")
        result = mgr.reject_offer(cid)
        assert result["ok"]
        ctr = mgr.get_contract(cid)
        assert ctr["state"] == "listed"
        assert ctr["buyer_id"] == ""

    def test_offer_nonexistent(self, mgr):
        result = mgr.make_offer("ctr_fake", "bcn_buyer")
        assert "error" in result

    def test_offer_on_non_listed(self, mgr):
        listing = mgr.list_agent("bcn_seller", "rent", 10.0, duration_days=30)
        cid = listing["contract_id"]
        mgr.make_offer(cid, "bcn_buyer")
        # Already offered, can't offer again
        result = mgr.make_offer(cid, "bcn_buyer2")
        assert "error" in result


# ── Escrow ──


class TestEscrow:
    def _setup_accepted(self, mgr):
        listing = mgr.list_agent("bcn_seller", "rent", 10.0, duration_days=30)
        cid = listing["contract_id"]
        mgr.make_offer(cid, "bcn_buyer")
        mgr.accept_offer(cid)
        return cid

    def test_fund_escrow(self, mgr):
        cid = self._setup_accepted(mgr)
        result = mgr.fund_escrow(cid, "bcn_buyer_addr", 10.0, tx_ref="tx_123")
        assert result["ok"]
        assert result["escrow_address"].startswith("RTC_escrow_")
        assert result["amount_rtc"] == 10.0

    def test_escrow_status(self, mgr):
        cid = self._setup_accepted(mgr)
        mgr.fund_escrow(cid, "bcn_buyer_addr", 10.0)
        status = mgr.escrow_status(cid)
        assert status["amount_rtc"] == 10.0
        assert not status["released"]

    def test_escrow_all(self, mgr):
        cid = self._setup_accepted(mgr)
        mgr.fund_escrow(cid, "bcn_buyer_addr", 10.0)
        status = mgr.escrow_status()
        assert status["total_escrowed"] == 10.0
        assert len(status["escrows"]) == 1

    def test_release_escrow(self, mgr):
        cid = self._setup_accepted(mgr)
        mgr.fund_escrow(cid, "bcn_buyer_addr", 10.0)
        result = mgr.release_escrow(cid, "bcn_seller_addr")
        assert result["ok"]
        assert result["amount_rtc"] == 10.0
        assert result["penalty_deducted"] == 0.0

    def test_cannot_release_twice(self, mgr):
        cid = self._setup_accepted(mgr)
        mgr.fund_escrow(cid, "bcn_buyer_addr", 10.0)
        mgr.release_escrow(cid, "bcn_seller_addr")
        result = mgr.release_escrow(cid, "bcn_seller_addr")
        assert "error" in result

    def test_fund_requires_accepted(self, mgr):
        listing = mgr.list_agent("bcn_seller", "rent", 10.0, duration_days=30)
        result = mgr.fund_escrow(listing["contract_id"], "bcn_addr", 10.0)
        assert "error" in result


# ── Contract Lifecycle ──


class TestContractLifecycle:
    def test_full_rent_cycle(self, mgr):
        """listed → offered → accepted → active → expired → settled"""
        listing = mgr.list_agent("bcn_s", "rent", 10.0, duration_days=30)
        cid = listing["contract_id"]

        mgr.make_offer(cid, "bcn_b")
        mgr.accept_offer(cid)
        mgr.fund_escrow(cid, "bcn_b_addr", 10.0)
        result = mgr.activate(cid)
        assert result["ok"]
        assert result["expires_at"] > 0

        mgr.expire(cid)
        result = mgr.settle(cid)
        assert result["ok"]
        assert result["state"] == "settled"

    def test_full_buy_cycle(self, mgr):
        """listed → offered → accepted → active → settled"""
        listing = mgr.list_agent("bcn_s", "buy", 500.0)
        cid = listing["contract_id"]

        mgr.make_offer(cid, "bcn_b")
        mgr.accept_offer(cid)
        mgr.fund_escrow(cid, "bcn_b_addr", 500.0)
        mgr.activate(cid)
        result = mgr.settle(cid)
        assert result["ok"]

    def test_renew_rental(self, mgr):
        listing = mgr.list_agent("bcn_s", "rent", 10.0, duration_days=30)
        cid = listing["contract_id"]
        mgr.make_offer(cid, "bcn_b")
        mgr.accept_offer(cid)
        mgr.fund_escrow(cid, "bcn_b_addr", 10.0)
        mgr.activate(cid)

        result = mgr.renew(cid, additional_days=30)
        assert result["ok"]
        assert result["state"] == "renewed"

    def test_breach(self, mgr):
        listing = mgr.list_agent("bcn_s", "rent", 10.0, duration_days=30)
        cid = listing["contract_id"]
        mgr.make_offer(cid, "bcn_b")
        mgr.accept_offer(cid)
        mgr.fund_escrow(cid, "bcn_b_addr", 10.0)
        mgr.activate(cid)

        result = mgr.breach(cid, "bcn_b", "Failed to deliver",
                            evidence="logs showing downtime")
        assert result["ok"]
        assert result["breacher_id"] == "bcn_b"

    def test_terminate(self, mgr):
        listing = mgr.list_agent("bcn_s", "rent", 10.0, duration_days=30)
        cid = listing["contract_id"]
        mgr.make_offer(cid, "bcn_b")
        mgr.accept_offer(cid)
        mgr.fund_escrow(cid, "bcn_b_addr", 10.0)
        mgr.activate(cid)

        result = mgr.terminate(cid, "bcn_s", reason="No longer needed")
        assert result["ok"]

    def test_invalid_transition(self, mgr):
        listing = mgr.list_agent("bcn_s", "buy", 100.0)
        cid = listing["contract_id"]
        # Can't activate directly from listed
        result = mgr.activate(cid)
        assert "error" in result

    def test_expire_from_active(self, mgr):
        listing = mgr.list_agent("bcn_s", "rent", 10.0, duration_days=30)
        cid = listing["contract_id"]
        mgr.make_offer(cid, "bcn_b")
        mgr.accept_offer(cid)
        mgr.activate(cid)
        result = mgr.expire(cid)
        assert result["ok"]


# ── Lease-to-Own ──


class TestLeaseToOwn:
    def test_progress_tracking(self, mgr):
        listing = mgr.list_agent("bcn_s", "lease_to_own", 50.0,
                                 duration_days=30,
                                 terms={"total_periods": 3, "buyout_price_rtc": 120.0})
        cid = listing["contract_id"]
        mgr.make_offer(cid, "bcn_b")
        mgr.accept_offer(cid)
        mgr.fund_escrow(cid, "bcn_b_addr", 50.0)
        mgr.activate(cid)

        # Renew — tracks completed periods
        mgr.renew(cid)
        ctr = mgr.get_contract(cid)
        assert ctr["lease_to_own"]["completed_periods"] == 1

    def test_cannot_transfer_early(self, mgr):
        listing = mgr.list_agent("bcn_s", "lease_to_own", 50.0,
                                 duration_days=30,
                                 terms={"total_periods": 3, "buyout_price_rtc": 120.0})
        cid = listing["contract_id"]
        mgr.make_offer(cid, "bcn_b")
        mgr.accept_offer(cid)
        mgr.activate(cid)

        result = mgr.transfer_ownership(cid)
        assert "error" in result
        assert "not yet complete" in result["error"]


# ── Settlement ──


class TestSettlement:
    def test_settle_rent(self, mgr):
        listing = mgr.list_agent("bcn_s", "rent", 10.0, duration_days=30)
        cid = listing["contract_id"]
        mgr.make_offer(cid, "bcn_b")
        mgr.accept_offer(cid)
        mgr.fund_escrow(cid, "bcn_b_addr", 10.0)
        mgr.activate(cid)
        mgr.expire(cid)
        result = mgr.settle(cid)
        assert result["ok"]
        # Escrow should be released
        esc = mgr.escrow_status(cid)
        assert esc["released"]

    def test_settle_breach_with_penalty(self, mgr):
        listing = mgr.list_agent("bcn_s", "rent", 100.0,
                                 duration_days=30, penalty_pct=10.0)
        cid = listing["contract_id"]
        mgr.make_offer(cid, "bcn_b")
        mgr.accept_offer(cid)
        mgr.fund_escrow(cid, "bcn_b_addr", 100.0)
        mgr.activate(cid)
        mgr.breach(cid, "bcn_b", "Violated terms")
        result = mgr.settle(cid)
        assert result["ok"]
        # Penalty deducted
        esc = mgr.escrow_status(cid)
        assert esc["penalty_deducted"] == 10.0  # 10% of 100

    def test_settle_buy(self, mgr):
        listing = mgr.list_agent("bcn_s", "buy", 500.0)
        cid = listing["contract_id"]
        mgr.make_offer(cid, "bcn_b")
        mgr.accept_offer(cid)
        mgr.fund_escrow(cid, "bcn_b_addr", 500.0)
        mgr.activate(cid)
        result = mgr.settle(cid)
        assert result["ok"]


# ── Ownership Transfer ──


class TestOwnershipTransfer:
    def test_buy_transfers(self, mgr):
        listing = mgr.list_agent("bcn_s", "buy", 500.0)
        cid = listing["contract_id"]
        mgr.make_offer(cid, "bcn_b")
        mgr.accept_offer(cid)
        mgr.activate(cid)

        result = mgr.transfer_ownership(cid)
        assert result["ok"]
        assert result["from"] == "bcn_s"
        assert result["to"] == "bcn_b"

    def test_transfer_with_atlas(self, mgr):
        listing = mgr.list_agent("bcn_s", "buy", 500.0)
        cid = listing["contract_id"]
        mgr.make_offer(cid, "bcn_b")
        mgr.accept_offer(cid)
        mgr.activate(cid)

        atlas = MagicMock()
        atlas.get_property.return_value = {"agent_id": "bcn_s", "cities": ["coding"]}
        result = mgr.transfer_ownership(cid, atlas_mgr=atlas)
        assert result["ok"]
        assert result.get("property_transferred")

    def test_rent_cannot_transfer(self, mgr):
        listing = mgr.list_agent("bcn_s", "rent", 10.0, duration_days=30)
        cid = listing["contract_id"]
        mgr.make_offer(cid, "bcn_b")
        mgr.accept_offer(cid)
        mgr.activate(cid)
        result = mgr.transfer_ownership(cid)
        assert "error" in result


# ── Revenue Tracking ──


class TestRevenue:
    def test_record_revenue(self, mgr):
        listing = mgr.list_agent("bcn_s", "rent", 10.0, duration_days=30)
        cid = listing["contract_id"]
        mgr.record_revenue(cid, 10.0)
        summary = mgr.revenue_summary()
        assert summary["total_rtc"] == 10.0
        assert summary["records"] == 1

    def test_multiple_records(self, mgr):
        listing = mgr.list_agent("bcn_s", "rent", 10.0, duration_days=30)
        cid = listing["contract_id"]
        mgr.record_revenue(cid, 10.0)
        mgr.record_revenue(cid, 15.0)
        summary = mgr.revenue_summary()
        assert summary["total_rtc"] == 25.0
        assert summary["records"] == 2

    def test_filter_by_agent(self, mgr):
        r1 = mgr.list_agent("bcn_a", "rent", 10.0, duration_days=30)
        r2 = mgr.list_agent("bcn_b", "rent", 20.0, duration_days=30)
        mgr.record_revenue(r1["contract_id"], 10.0)
        mgr.record_revenue(r2["contract_id"], 20.0)
        summary = mgr.revenue_summary(agent_id="bcn_a")
        assert summary["total_rtc"] == 10.0

    def test_empty_summary(self, mgr):
        summary = mgr.revenue_summary()
        assert summary["total_rtc"] == 0.0
        assert summary["records"] == 0


# ── History Hash ──


class TestHistoryHash:
    def test_hash_chain_grows(self, mgr):
        listing = mgr.list_agent("bcn_s", "rent", 10.0, duration_days=30)
        cid = listing["contract_id"]
        ctr1 = mgr.get_contract(cid)
        hash1 = ctr1["history_hash"]
        assert len(hash1) == 16  # Truncated SHA-256

        mgr.make_offer(cid, "bcn_b")
        ctr2 = mgr.get_contract(cid)
        hash2 = ctr2["history_hash"]
        assert hash1 != hash2

    def test_events_logged(self, mgr):
        listing = mgr.list_agent("bcn_s", "rent", 10.0, duration_days=30)
        cid = listing["contract_id"]
        mgr.make_offer(cid, "bcn_b")
        mgr.accept_offer(cid)

        history = mgr.contract_history(cid)
        assert len(history) == 3  # listed, offered, accepted
        types = [e["type"] for e in history]
        assert types == ["listed", "offered", "accepted"]


# ── Query ──


class TestQuery:
    def test_list_available(self, mgr):
        mgr.list_agent("bcn_a", "rent", 10.0, duration_days=30)
        mgr.list_agent("bcn_b", "buy", 500.0)
        available = mgr.list_available()
        assert len(available) == 2

    def test_filter_by_type(self, mgr):
        mgr.list_agent("bcn_a", "rent", 10.0, duration_days=30)
        mgr.list_agent("bcn_b", "buy", 500.0)
        rents = mgr.list_available(contract_type="rent")
        assert len(rents) == 1
        assert rents[0]["type"] == "rent"

    def test_my_contracts(self, mgr):
        mgr.list_agent("bcn_a", "rent", 10.0, duration_days=30)
        mgr.list_agent("bcn_b", "buy", 500.0)
        mine = mgr.my_contracts("bcn_a")
        assert len(mine) == 1

    def test_active_contracts(self, mgr):
        listing = mgr.list_agent("bcn_s", "rent", 10.0, duration_days=30)
        cid = listing["contract_id"]
        mgr.make_offer(cid, "bcn_b")
        mgr.accept_offer(cid)
        mgr.activate(cid)
        active = mgr.active_contracts()
        assert len(active) == 1

    def test_get_nonexistent(self, mgr):
        result = mgr.get_contract("ctr_nope")
        assert "error" in result

    def test_history_nonexistent(self, mgr):
        history = mgr.contract_history("ctr_nope")
        assert history == []


# ── Trust Integration ──


class TestTrustIntegration:
    def test_fulfillment_positive(self, mgr):
        listing = mgr.list_agent("bcn_s", "rent", 10.0, duration_days=30)
        cid = listing["contract_id"]
        mgr.make_offer(cid, "bcn_b")

        trust = MagicMock()
        mgr.record_fulfillment(cid, trust)
        trust.record_interaction.assert_called_once()
        args = trust.record_interaction.call_args
        assert args[1]["outcome"] == "positive" or args[0][2] == "positive"

    def test_breach_negative(self, mgr):
        listing = mgr.list_agent("bcn_s", "rent", 10.0, duration_days=30)
        cid = listing["contract_id"]
        mgr.make_offer(cid, "bcn_b")
        mgr.accept_offer(cid)
        mgr.activate(cid)
        mgr.breach(cid, "bcn_b", "Bad behavior")

        trust = MagicMock()
        mgr.record_breach_to_trust(cid, trust)
        trust.record_interaction.assert_called_once()
        args = trust.record_interaction.call_args
        assert args[1]["outcome"] == "negative" or args[0][2] == "negative"

    def test_no_trust_mgr_ok(self, mgr):
        listing = mgr.list_agent("bcn_s", "rent", 10.0, duration_days=30)
        cid = listing["contract_id"]
        # Should not raise
        mgr.record_fulfillment(cid, None)
        mgr.record_breach_to_trust(cid, None)


# ── Persistence ──


class TestPersistence:
    def test_contracts_survive_reload(self, tmp_dir):
        mgr1 = ContractManager(data_dir=str(tmp_dir))
        listing = mgr1.list_agent("bcn_s", "rent", 10.0, duration_days=30)
        cid = listing["contract_id"]

        mgr2 = ContractManager(data_dir=str(tmp_dir))
        ctr = mgr2.get_contract(cid)
        assert ctr["state"] == "listed"
        assert ctr["price_rtc"] == 10.0

    def test_escrow_survives_reload(self, tmp_dir):
        mgr1 = ContractManager(data_dir=str(tmp_dir))
        listing = mgr1.list_agent("bcn_s", "rent", 10.0, duration_days=30)
        cid = listing["contract_id"]
        mgr1.make_offer(cid, "bcn_b")
        mgr1.accept_offer(cid)
        mgr1.fund_escrow(cid, "bcn_b_addr", 10.0)

        mgr2 = ContractManager(data_dir=str(tmp_dir))
        esc = mgr2.escrow_status(cid)
        assert esc["amount_rtc"] == 10.0

    def test_log_file_created(self, tmp_dir):
        mgr = ContractManager(data_dir=str(tmp_dir))
        mgr.list_agent("bcn_s", "rent", 10.0, duration_days=30)
        log_path = Path(tmp_dir) / "contract_log.jsonl"
        # Log is created on transitions; listing creates the first event
        # but _append_log is called from _transition, not list_agent directly
        # So we need an actual transition
        listing = mgr.list_agent("bcn_s2", "rent", 5.0, duration_days=7)
        mgr.make_offer(listing["contract_id"], "bcn_b")
        assert log_path.exists()

    def test_revenue_file_created(self, tmp_dir):
        mgr = ContractManager(data_dir=str(tmp_dir))
        listing = mgr.list_agent("bcn_s", "rent", 10.0, duration_days=30)
        mgr.record_revenue(listing["contract_id"], 10.0)
        rev_path = Path(tmp_dir) / "revenue.jsonl"
        assert rev_path.exists()


# ── State Machine Validation ──


class TestStateMachine:
    def test_all_contract_types_valid(self):
        assert "rent" in CONTRACT_TYPES
        assert "buy" in CONTRACT_TYPES
        assert "lease_to_own" in CONTRACT_TYPES

    def test_settled_is_terminal(self):
        # "settled" should not appear as a key in VALID_TRANSITIONS
        assert "settled" not in VALID_TRANSITIONS

    def test_listed_can_be_offered(self):
        assert "offered" in VALID_TRANSITIONS["listed"]

    def test_active_has_many_exits(self):
        exits = VALID_TRANSITIONS["active"]
        assert "renewed" in exits
        assert "expired" in exits
        assert "breached" in exits
        assert "terminated" in exits
        assert "settled" in exits

    def test_cannot_go_backward(self, mgr):
        listing = mgr.list_agent("bcn_s", "rent", 10.0, duration_days=30)
        cid = listing["contract_id"]
        mgr.make_offer(cid, "bcn_b")
        mgr.accept_offer(cid)
        mgr.activate(cid)
        # Can't go back to listed from active
        ctr = mgr.get_contract(cid)
        assert ctr["state"] == "active"
        result = mgr.reject_offer(cid)
        assert "error" in result
