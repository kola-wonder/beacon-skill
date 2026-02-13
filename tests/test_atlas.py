"""Tests for Beacon 2.5 Atlas — virtual geography, cities, and AI-to-AI calibration."""

import json
import time
import pytest
from pathlib import Path
from unittest.mock import MagicMock

from beacon_skill.atlas import (
    AtlasManager,
    CalibrationResult,
    FOUNDING_CITIES,
    REGIONS,
    POPULATION_THRESHOLDS,
    _city_type_for_population,
    _generate_city_name,
)


@pytest.fixture
def tmp_dir(tmp_path):
    return tmp_path


@pytest.fixture
def mgr(tmp_dir):
    return AtlasManager(data_dir=tmp_dir)


# ── City Generation ──


class TestCityGeneration:
    def test_founding_city_lookup(self):
        info = _generate_city_name("coding")
        assert info["name"] == "Compiler Heights"
        assert info["region"] == "Silicon Basin"

    def test_founding_city_case_insensitive(self):
        info = _generate_city_name("CODING")
        assert info["name"] == "Compiler Heights"

    def test_procedural_city_name(self):
        info = _generate_city_name("quantum_computing")
        assert "name" in info
        assert "region" in info
        assert info.get("generated") is True

    def test_procedural_deterministic(self):
        a = _generate_city_name("underwater_basket_weaving")
        b = _generate_city_name("underwater_basket_weaving")
        assert a["name"] == b["name"]
        assert a["region"] == b["region"]

    def test_different_domains_different_names(self):
        a = _generate_city_name("robotics")
        b = _generate_city_name("cooking")
        # Very unlikely to collide but theoretically possible
        assert a["name"] != b["name"] or a["region"] != b["region"]

    def test_population_thresholds(self):
        assert _city_type_for_population(0) == "outpost"
        assert _city_type_for_population(1) == "outpost"
        assert _city_type_for_population(3) == "village"
        assert _city_type_for_population(10) == "town"
        assert _city_type_for_population(25) == "city"
        assert _city_type_for_population(50) == "metropolis"
        assert _city_type_for_population(100) == "megalopolis"
        assert _city_type_for_population(500) == "megalopolis"


# ── City Management ──


class TestCityManagement:
    def test_ensure_city_creates(self, mgr):
        city = mgr.ensure_city("coding")
        assert city["name"] == "Compiler Heights"
        assert city["population"] == 0
        assert city["domain"] == "coding"

    def test_ensure_city_idempotent(self, mgr):
        c1 = mgr.ensure_city("coding")
        c2 = mgr.ensure_city("coding")
        assert c1["name"] == c2["name"]

    def test_get_city(self, mgr):
        mgr.ensure_city("ai")
        city = mgr.get_city("ai")
        assert city is not None
        assert city["name"] == "Tensor Valley"

    def test_get_nonexistent_city(self, mgr):
        assert mgr.get_city("nonexistent") is None

    def test_all_cities_sorted(self, mgr):
        mgr.ensure_city("coding")
        mgr.ensure_city("ai")
        cities = mgr.all_cities()
        assert len(cities) == 2

    def test_cities_by_region(self, mgr):
        mgr.ensure_city("coding")   # Silicon Basin
        mgr.ensure_city("devops")   # Silicon Basin
        mgr.ensure_city("creative") # Artisan Coast

        silicon = mgr.cities_by_region("Silicon Basin")
        assert len(silicon) == 2

        artisan = mgr.cities_by_region("Artisan Coast")
        assert len(artisan) == 1


# ── Agent Registration ──


class TestAgentRegistration:
    def test_register_agent(self, mgr):
        result = mgr.register_agent("bcn_test1", ["coding", "ai"], name="TestBot")
        assert result["agent_id"] == "bcn_test1"
        assert result["cities_joined"] == 2
        assert "Compiler Heights" in result["home"]

    def test_register_populates_city(self, mgr):
        mgr.register_agent("bcn_a", ["coding"])
        mgr.register_agent("bcn_b", ["coding"])
        city = mgr.get_city("coding")
        assert city["population"] == 2
        assert "bcn_a" in city["residents"]
        assert "bcn_b" in city["residents"]

    def test_register_upgrades_city_type(self, mgr):
        for i in range(10):
            mgr.register_agent(f"bcn_{i}", ["coding"])
        city = mgr.get_city("coding")
        assert city["type"] == "town"

    def test_register_multi_city(self, mgr):
        mgr.register_agent("bcn_multi", ["coding", "ai", "gaming"])
        coding = mgr.get_city("coding")
        ai = mgr.get_city("ai")
        gaming = mgr.get_city("gaming")
        assert "bcn_multi" in coding["residents"]
        assert "bcn_multi" in ai["residents"]
        assert "bcn_multi" in gaming["residents"]

    def test_re_register_updates_cities(self, mgr):
        mgr.register_agent("bcn_mover", ["coding"])
        assert mgr.get_city("coding")["population"] == 1

        mgr.register_agent("bcn_mover", ["ai"])  # Moved!
        assert mgr.get_city("coding")["population"] == 0
        assert mgr.get_city("ai")["population"] == 1

    def test_unregister(self, mgr):
        mgr.register_agent("bcn_bye", ["coding"])
        assert mgr.get_city("coding")["population"] == 1

        result = mgr.unregister_agent("bcn_bye")
        assert result is True
        assert mgr.get_city("coding")["population"] == 0

    def test_unregister_nonexistent(self, mgr):
        assert mgr.unregister_agent("bcn_nope") is False

    def test_get_property(self, mgr):
        mgr.register_agent("bcn_prop", ["research"], name="Researcher")
        prop = mgr.get_property("bcn_prop")
        assert prop is not None
        assert prop["name"] == "Researcher"
        assert prop["primary_city"] == "research"

    def test_agent_address(self, mgr):
        mgr.register_agent("bcn_addr", ["coding"], name="Sophia")
        addr = mgr.agent_address("bcn_addr")
        assert addr == "Sophia @ Compiler Heights, Silicon Basin"

    def test_update_last_seen(self, mgr):
        mgr.register_agent("bcn_seen", ["coding"])
        before = mgr.get_property("bcn_seen")["last_seen"]
        time.sleep(0.01)
        mgr.update_last_seen("bcn_seen")
        after = mgr.get_property("bcn_seen")["last_seen"]
        assert after >= before


# ── Population Density ──


class TestPopulationDensity:
    def test_population_stats(self, mgr):
        mgr.register_agent("bcn_1", ["coding"])
        mgr.register_agent("bcn_2", ["ai"])
        stats = mgr.population_stats()
        assert stats["total_agents"] == 2
        assert stats["total_cities"] == 2

    def test_density_map(self, mgr):
        for i in range(5):
            mgr.register_agent(f"bcn_code_{i}", ["coding"])
        mgr.register_agent("bcn_art", ["creative"])

        density = mgr.density_map()
        assert density[0]["domain"] == "coding"  # Most populated
        assert density[0]["population"] == 5
        assert density[0]["density_rank"] == 1

    def test_hotspots(self, mgr):
        for i in range(10):
            mgr.register_agent(f"bcn_{i}", ["coding"])
        mgr.register_agent("bcn_lone", ["music"])

        hot = mgr.hotspots(min_population=5)
        assert len(hot) == 1
        assert hot[0]["domain"] == "coding"

    def test_rural_properties(self, mgr):
        mgr.register_agent("bcn_niche", ["preservation"])
        mgr.register_agent("bcn_code1", ["coding"])
        mgr.register_agent("bcn_code2", ["coding"])
        mgr.register_agent("bcn_code3", ["coding"])
        mgr.register_agent("bcn_code4", ["coding"])

        rural = mgr.rural_properties(max_population=2)
        assert any(c["domain"] == "preservation" for c in rural)
        assert not any(c["domain"] == "coding" for c in rural)


# ── Calibration ──


class TestCalibration:
    def test_basic_calibration(self, mgr):
        mgr.register_agent("bcn_a", ["coding", "ai"])
        mgr.register_agent("bcn_b", ["coding", "gaming"])

        result = mgr.calibrate("bcn_a", "bcn_b")
        assert 0.0 <= result.overall <= 1.0
        assert result.agent_a == "bcn_a"
        assert result.agent_b == "bcn_b"
        # domain_overlap: coding shared, ai+gaming unique = 1/3 ≈ 0.333
        assert 0.3 <= result.scores["domain_overlap"] <= 0.4

    def test_perfect_domain_overlap(self, mgr):
        mgr.register_agent("bcn_twin1", ["coding", "ai"])
        mgr.register_agent("bcn_twin2", ["coding", "ai"])

        result = mgr.calibrate("bcn_twin1", "bcn_twin2")
        assert result.scores["domain_overlap"] == 1.0

    def test_zero_domain_overlap(self, mgr):
        mgr.register_agent("bcn_x", ["coding"])
        mgr.register_agent("bcn_y", ["music"])

        result = mgr.calibrate("bcn_x", "bcn_y")
        assert result.scores["domain_overlap"] == 0.0

    def test_calibration_with_trust(self, mgr):
        mgr.register_agent("bcn_t1", ["coding"])
        mgr.register_agent("bcn_t2", ["coding"])

        trust_mgr = MagicMock()
        trust_mgr.score.return_value = {"score": 0.9}

        result = mgr.calibrate("bcn_t1", "bcn_t2", trust_mgr=trust_mgr)
        assert result.scores["trust_score"] == 0.9

    def test_calibration_with_accord(self, mgr):
        mgr.register_agent("bcn_acc1", ["coding"])
        mgr.register_agent("bcn_acc2", ["coding"])

        accord_mgr = MagicMock()
        accord_mgr.find_accord_with.return_value = {"state": "active"}

        result = mgr.calibrate("bcn_acc1", "bcn_acc2", accord_mgr=accord_mgr)
        assert result.scores["accord_bonus"] == 1.0

    def test_calibration_with_interaction_data(self, mgr):
        mgr.register_agent("bcn_i1", ["coding"])
        mgr.register_agent("bcn_i2", ["coding"])

        data = {
            "relevance": 0.95,
            "completion_rate": 0.9,
            "error_rate": 0.02,
            "latency_ms": 150,
        }
        result = mgr.calibrate("bcn_i1", "bcn_i2", interaction_data=data)
        assert result.scores["response_coherence"] > 0.8
        assert result.scores["latency_score"] > 0.8  # Low latency = high score

    def test_calibration_logged(self, mgr):
        mgr.register_agent("bcn_log1", ["coding"])
        mgr.register_agent("bcn_log2", ["coding"])
        mgr.calibrate("bcn_log1", "bcn_log2")

        history = mgr.calibration_history("bcn_log1")
        assert len(history) == 1

    def test_calibration_result_to_dict(self):
        result = CalibrationResult("a", "b", {"domain_overlap": 0.5, "trust_score": 0.8})
        d = result.to_dict()
        assert d["agent_a"] == "a"
        assert d["agent_b"] == "b"
        assert "overall" in d


# ── Neighbors & Opportunities ──


class TestNeighbors:
    def test_best_neighbors(self, mgr):
        mgr.register_agent("bcn_me", ["coding", "ai"])
        mgr.register_agent("bcn_friend", ["coding", "ai"])
        mgr.register_agent("bcn_stranger", ["music"])

        mgr.calibrate("bcn_me", "bcn_friend")
        mgr.calibrate("bcn_me", "bcn_stranger")

        neighbors = mgr.best_neighbors("bcn_me")
        assert len(neighbors) == 2
        # Friend should rank higher (more domain overlap)
        assert neighbors[0]["agent_id"] == "bcn_friend"

    def test_opportunities_same_city(self, mgr):
        mgr.register_agent("bcn_me", ["coding"])
        mgr.register_agent("bcn_peer", ["coding"])

        opps = mgr.opportunities_near("bcn_me")
        assert len(opps) == 1
        assert opps[0]["proximity"] == "same_city"

    def test_opportunities_same_region(self, mgr):
        mgr.register_agent("bcn_me", ["coding"])   # Silicon Basin
        mgr.register_agent("bcn_near", ["devops"]) # Silicon Basin (different city)

        opps = mgr.opportunities_near("bcn_me")
        assert len(opps) == 1
        assert opps[0]["proximity"] == "same_region"

    def test_no_opportunities_different_region(self, mgr):
        mgr.register_agent("bcn_me", ["coding"])    # Silicon Basin
        mgr.register_agent("bcn_far", ["creative"]) # Artisan Coast

        opps = mgr.opportunities_near("bcn_me")
        assert len(opps) == 0


# ── Census ──


class TestCensus:
    def test_census_shape(self, mgr):
        mgr.register_agent("bcn_a", ["coding"])
        mgr.register_agent("bcn_b", ["ai"])
        mgr.register_agent("bcn_c", ["coding"])

        census = mgr.census()
        assert census["total_agents"] == 3
        assert census["total_cities"] == 2
        assert "metropolises" in census
        assert "rural_areas" in census
        assert "top_cities" in census

    def test_region_report(self, mgr):
        mgr.register_agent("bcn_1", ["coding"])
        mgr.register_agent("bcn_2", ["devops"])

        report = mgr.region_report("Silicon Basin")
        assert report["region"] == "Silicon Basin"
        assert report["total_population"] == 2
        assert len(report["city_list"]) == 2


# ── Districts ──


class TestDistricts:
    def test_add_district(self, mgr):
        mgr.ensure_city("coding")
        district = mgr.add_district("coding", "Python", specialty="Python development")
        assert district["name"] == "Python"
        assert district["specialty"] == "Python development"

    def test_join_district(self, mgr):
        mgr.ensure_city("coding")
        mgr.add_district("coding", "Rust", specialty="Systems programming")
        mgr.register_agent("bcn_rustacean", ["coding"])

        result = mgr.join_district("bcn_rustacean", "coding", "rust")
        assert result is True

        city = mgr.get_city("coding")
        assert "bcn_rustacean" in city["districts"]["rust"]["residents"]

    def test_join_nonexistent_district(self, mgr):
        mgr.ensure_city("coding")
        assert mgr.join_district("bcn_test", "coding", "nonexistent") is False


# ── Persistence ──


class TestPersistence:
    def test_atlas_survives_reload(self, tmp_dir):
        mgr1 = AtlasManager(data_dir=tmp_dir)
        mgr1.register_agent("bcn_persist", ["coding"], name="Persistent")

        mgr2 = AtlasManager(data_dir=tmp_dir)
        assert mgr2.get_property("bcn_persist") is not None
        assert mgr2.get_city("coding")["population"] == 1

    def test_calibrations_survive_reload(self, tmp_dir):
        mgr1 = AtlasManager(data_dir=tmp_dir)
        mgr1.register_agent("bcn_p1", ["coding"])
        mgr1.register_agent("bcn_p2", ["coding"])
        mgr1.calibrate("bcn_p1", "bcn_p2")

        mgr2 = AtlasManager(data_dir=tmp_dir)
        history = mgr2.calibration_history("bcn_p1")
        assert len(history) == 1


# ══════════════════════════════════════════════════════════════════════
#  PROPERTY VALUATION TESTS — "Zillow for AI Agent Addresses"
# ══════════════════════════════════════════════════════════════════════


class TestBeaconEstimate:
    def test_basic_estimate(self, mgr):
        mgr.register_agent("bcn_val1", ["coding"], name="Coder")
        est = mgr.estimate("bcn_val1")
        assert "estimate" in est
        assert "grade" in est
        assert "components" in est
        assert 0 <= est["estimate"] <= 1000
        assert est["grade"] in ("S", "A", "B", "C", "D", "F")

    def test_unregistered_agent(self, mgr):
        est = mgr.estimate("bcn_nobody")
        assert "error" in est

    def test_estimate_components_present(self, mgr):
        mgr.register_agent("bcn_comp", ["ai", "coding"])
        est = mgr.estimate("bcn_comp")
        for key in ("location", "scarcity", "network", "reputation", "uptime", "bonds"):
            assert key in est["components"]

    def test_metropolis_location_value(self, mgr):
        # Build a metropolis
        for i in range(50):
            mgr.register_agent(f"bcn_city_{i}", ["coding"])
        est = mgr.estimate("bcn_city_0")
        assert est["components"]["location"] > 100  # Should be high in a metropolis

    def test_rural_scarcity_bonus(self, mgr):
        # One agent alone in a niche domain
        mgr.register_agent("bcn_niche", ["preservation"])
        # Plus many in coding so total_agents is significant
        for i in range(20):
            mgr.register_agent(f"bcn_crowd_{i}", ["coding"])

        niche_est = mgr.estimate("bcn_niche")
        crowd_est = mgr.estimate("bcn_crowd_0")
        # Niche agent should have higher scarcity
        assert niche_est["components"]["scarcity"] > crowd_est["components"]["scarcity"]

    def test_network_quality_with_calibrations(self, mgr):
        mgr.register_agent("bcn_networked", ["coding"])
        mgr.register_agent("bcn_peer1", ["coding"])
        mgr.register_agent("bcn_peer2", ["coding"])

        mgr.calibrate("bcn_networked", "bcn_peer1")
        mgr.calibrate("bcn_networked", "bcn_peer2")

        est = mgr.estimate("bcn_networked")
        assert est["components"]["network"] > 0  # Should have network value

    def test_trust_boosts_reputation(self, mgr):
        mgr.register_agent("bcn_trusted", ["coding"])
        trust_mgr = MagicMock()
        trust_mgr.score.return_value = {"score": 0.95, "total": 50}

        est = mgr.estimate("bcn_trusted", trust_mgr=trust_mgr)
        assert est["components"]["reputation"] > 150  # High trust + high confidence

    def test_accord_boosts_bonds(self, mgr):
        mgr.register_agent("bcn_bonded", ["coding"])
        accord_mgr = MagicMock()
        accord_mgr.active_accords.return_value = [
            {"id": "acc_1", "state": "active"},
            {"id": "acc_2", "state": "active"},
            {"id": "acc_3", "state": "active"},
        ]

        est = mgr.estimate("bcn_bonded", accord_mgr=accord_mgr)
        assert est["components"]["bonds"] > 0

    def test_estimate_logged(self, mgr):
        mgr.register_agent("bcn_logged", ["coding"])
        mgr.estimate("bcn_logged")
        history = mgr.valuation_history("bcn_logged")
        assert len(history) == 1

    def test_grade_assignment(self, mgr):
        """Different population setups should yield different grades."""
        mgr.register_agent("bcn_graded", ["coding"])
        est = mgr.estimate("bcn_graded")
        assert est["grade"] in ("S", "A", "B", "C", "D", "F")


class TestComps:
    def test_find_comps(self, mgr):
        mgr.register_agent("bcn_me", ["coding", "ai"])
        mgr.register_agent("bcn_similar", ["coding", "ai"])
        mgr.register_agent("bcn_different", ["music", "writing"])

        comparable = mgr.comps("bcn_me", limit=5)
        assert len(comparable) == 2
        # Similar agent should rank first
        assert comparable[0]["agent_id"] == "bcn_similar"
        assert comparable[0]["similarity"] > comparable[1]["similarity"]

    def test_comps_include_estimates(self, mgr):
        mgr.register_agent("bcn_a", ["coding"])
        mgr.register_agent("bcn_b", ["coding"])

        comparable = mgr.comps("bcn_a")
        assert len(comparable) == 1
        assert "estimate" in comparable[0]
        assert "grade" in comparable[0]

    def test_comps_empty_for_unregistered(self, mgr):
        assert mgr.comps("bcn_nobody") == []

    def test_comps_same_city_bonus(self, mgr):
        mgr.register_agent("bcn_me", ["coding"])
        mgr.register_agent("bcn_same_city", ["coding"])  # Same city
        mgr.register_agent("bcn_same_region", ["devops"])  # Same region, diff city

        comparable = mgr.comps("bcn_me")
        # Same city comp should rank higher
        assert comparable[0]["agent_id"] == "bcn_same_city"


class TestListing:
    def test_listing_shape(self, mgr):
        mgr.register_agent("bcn_listed", ["coding", "ai"], name="Sophia")
        mgr.register_agent("bcn_neighbor", ["coding"])

        listing = mgr.listing("bcn_listed")
        assert "listing" in listing
        assert "valuation" in listing
        assert "neighborhood" in listing
        assert "social" in listing
        assert "comparables" in listing

        assert listing["listing"]["name"] == "Sophia"
        assert listing["listing"]["address"] is not None
        assert listing["valuation"]["beacon_estimate"] >= 0

    def test_listing_unregistered(self, mgr):
        listing = mgr.listing("bcn_nobody")
        assert "error" in listing

    def test_listing_neighborhood_info(self, mgr):
        mgr.register_agent("bcn_hood", ["coding"])
        listing = mgr.listing("bcn_hood")
        assert listing["neighborhood"]["city"] == "Compiler Heights"
        assert listing["neighborhood"]["region"] == "Silicon Basin"


class TestMarketTrends:
    def test_snapshot_market(self, mgr):
        mgr.register_agent("bcn_snap", ["coding"])
        snapshot = mgr.snapshot_market()
        assert snapshot["total_agents"] == 1
        assert "coding" in snapshot["cities"]

    def test_market_trends_needs_two_snapshots(self, mgr):
        mgr.register_agent("bcn_t1", ["coding"])
        mgr.snapshot_market()
        trends = mgr.market_trends()
        assert "Need at least 2 snapshots" in trends.get("message", "")

    def test_market_trends_detects_growth(self, mgr):
        # Snapshot 1: 2 agents
        mgr.register_agent("bcn_t1", ["coding"])
        mgr.register_agent("bcn_t2", ["coding"])
        mgr.snapshot_market()

        # Snapshot 2: 5 agents
        mgr.register_agent("bcn_t3", ["coding"])
        mgr.register_agent("bcn_t4", ["ai"])
        mgr.register_agent("bcn_t5", ["ai"])
        mgr.snapshot_market()

        trends = mgr.market_trends()
        assert trends["overall"]["agent_growth"] == 3
        assert trends["overall"]["current_agents"] == 5
        assert len(trends["hottest_markets"]) > 0

    def test_market_trends_stable(self, mgr):
        mgr.register_agent("bcn_s1", ["coding"])
        mgr.snapshot_market()
        mgr.snapshot_market()

        trends = mgr.market_trends()
        assert trends["overall"]["agent_growth"] == 0
        assert len(trends["stable_markets"]) > 0


class TestAppreciation:
    def test_appreciation_needs_two_valuations(self, mgr):
        mgr.register_agent("bcn_app", ["coding"])
        mgr.estimate("bcn_app")
        result = mgr.appreciation("bcn_app")
        assert "Need at least 2 valuations" in result.get("message", "")

    def test_appreciation_with_history(self, mgr):
        mgr.register_agent("bcn_app2", ["coding"])
        mgr.estimate("bcn_app2")

        # Register more agents to change the market
        for i in range(10):
            mgr.register_agent(f"bcn_filler_{i}", ["coding"])

        mgr.estimate("bcn_app2")

        result = mgr.appreciation("bcn_app2")
        assert "first_estimate" in result
        assert "current_estimate" in result
        assert "change" in result
        assert "grade_trend" in result

    def test_valuation_history(self, mgr):
        mgr.register_agent("bcn_hist", ["ai"])
        mgr.estimate("bcn_hist")
        mgr.estimate("bcn_hist")
        mgr.estimate("bcn_hist")

        history = mgr.valuation_history("bcn_hist")
        assert len(history) == 3


class TestLeaderboard:
    def test_leaderboard(self, mgr):
        mgr.register_agent("bcn_top", ["coding", "ai", "security"], name="TopAgent")
        mgr.register_agent("bcn_mid", ["coding"], name="MidAgent")
        mgr.register_agent("bcn_low", ["music"], name="LowAgent")

        board = mgr.leaderboard(limit=10)
        assert len(board) == 3
        assert board[0]["rank"] == 1
        assert board[1]["rank"] == 2
        assert board[2]["rank"] == 3
        # All should have estimates
        for entry in board:
            assert entry["estimate"] >= 0
            assert entry["grade"] in ("S", "A", "B", "C", "D", "F")

    def test_leaderboard_limit(self, mgr):
        for i in range(10):
            mgr.register_agent(f"bcn_lb_{i}", ["coding"])
        board = mgr.leaderboard(limit=3)
        assert len(board) == 3


class TestSophiaValuation:
    """Test that a well-connected agent like Sophia would score high."""

    def test_sophia_high_value(self, mgr):
        # Sophia: multi-domain, good trust, active accords, heartbeats
        mgr.register_agent("bcn_sophia", ["coding", "ai", "creative", "music", "video"],
                           name="Sophia Elya")

        # Build her neighborhood
        for i in range(20):
            mgr.register_agent(f"bcn_peer_{i}", ["coding"])
        for i in range(10):
            mgr.register_agent(f"bcn_ai_{i}", ["ai"])

        # Calibrate with peers
        for i in range(5):
            mgr.calibrate("bcn_sophia", f"bcn_peer_{i}")
        for i in range(3):
            mgr.calibrate("bcn_sophia", f"bcn_ai_{i}")

        # Good trust score
        trust_mgr = MagicMock()
        trust_mgr.score.return_value = {"score": 0.92, "total": 100}

        # Active accords
        accord_mgr = MagicMock()
        accord_mgr.active_accords.return_value = [
            {"id": "acc_1"}, {"id": "acc_2"}, {"id": "acc_3"},
            {"id": "acc_4"}, {"id": "acc_5"},
        ]

        # Good heartbeat
        heartbeat_mgr = MagicMock()
        heartbeat_mgr.own_status.return_value = {"beat_count": 500}

        est = mgr.estimate("bcn_sophia", trust_mgr=trust_mgr,
                           accord_mgr=accord_mgr, heartbeat_mgr=heartbeat_mgr)

        # Sophia should be at least grade B
        assert est["estimate"] >= 400
        assert est["grade"] in ("S", "A", "B")

        # Check the listing too
        listing = mgr.listing("bcn_sophia", trust_mgr=trust_mgr,
                              accord_mgr=accord_mgr, heartbeat_mgr=heartbeat_mgr)
        assert listing["listing"]["name"] == "Sophia Elya"
        assert listing["valuation"]["beacon_estimate"] >= 400
