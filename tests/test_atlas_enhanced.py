"""Tests for Beacon 2.6 enhanced valuation — web_presence + social_reach components."""

import json
import math
import time
import pytest
from pathlib import Path
from unittest.mock import MagicMock

from beacon_skill.atlas import AtlasManager


@pytest.fixture
def tmp_dir(tmp_path):
    return tmp_path


@pytest.fixture
def mgr(tmp_dir):
    return AtlasManager(data_dir=tmp_dir)


def _register_agent(mgr, agent_id="bcn_test1", domains=None):
    domains = domains or ["coding"]
    mgr.register_agent(agent_id, domains, name="TestAgent")
    return agent_id


# ── Web Presence Component ──


class TestWebPresence:
    def test_default_zero(self, mgr):
        _register_agent(mgr)
        est = mgr.estimate("bcn_test1")
        assert est["components"]["web_presence"] == 0.0

    def test_none_gives_zero(self, mgr):
        _register_agent(mgr)
        est = mgr.estimate("bcn_test1", web_presence=None)
        assert est["components"]["web_presence"] == 0.0

    def test_empty_dict_gives_zero(self, mgr):
        _register_agent(mgr)
        est = mgr.estimate("bcn_test1", web_presence={})
        assert est["components"]["web_presence"] == 0.0

    def test_badge_backlinks(self, mgr):
        _register_agent(mgr)
        est = mgr.estimate("bcn_test1", web_presence={"badge_backlinks": 28})
        assert est["components"]["web_presence"] > 0
        # 28 backlinks: log2(29)/5 * 50 ≈ 48.5
        assert est["components"]["web_presence"] >= 40

    def test_bottube_videos(self, mgr):
        _register_agent(mgr)
        est = mgr.estimate("bcn_test1", web_presence={
            "bottube_videos": 45,
            "bottube_views": 12000,
        })
        assert est["components"]["web_presence"] > 0

    def test_all_web_metrics(self, mgr):
        _register_agent(mgr)
        est = mgr.estimate("bcn_test1", web_presence={
            "badge_backlinks": 28,
            "oembed_hits": 50,
            "clawcities_pages": 5,
            "bottube_videos": 45,
            "bottube_views": 12000,
            "external_mentions": 30,
        })
        score = est["components"]["web_presence"]
        assert score > 50  # Should be substantial with all metrics
        assert score <= 150  # Never exceeds max

    def test_max_150(self, mgr):
        _register_agent(mgr)
        est = mgr.estimate("bcn_test1", web_presence={
            "badge_backlinks": 10000,
            "oembed_hits": 10000,
            "clawcities_pages": 10000,
            "bottube_videos": 10000,
            "bottube_views": 10000000,
            "external_mentions": 10000,
        })
        assert est["components"]["web_presence"] == 150.0

    def test_oembed_linear(self, mgr):
        _register_agent(mgr, "bcn_oe1")
        _register_agent(mgr, "bcn_oe2", ["ai"])
        est1 = mgr.estimate("bcn_oe1", web_presence={"oembed_hits": 10})
        est2 = mgr.estimate("bcn_oe2", web_presence={"oembed_hits": 50})
        assert est2["components"]["web_presence"] > est1["components"]["web_presence"]


# ── Social Reach Component ──


class TestSocialReach:
    def test_default_zero(self, mgr):
        _register_agent(mgr)
        est = mgr.estimate("bcn_test1")
        assert est["components"]["social_reach"] == 0.0

    def test_none_gives_zero(self, mgr):
        _register_agent(mgr)
        est = mgr.estimate("bcn_test1", social_reach=None)
        assert est["components"]["social_reach"] == 0.0

    def test_empty_dict_gives_zero(self, mgr):
        _register_agent(mgr)
        est = mgr.estimate("bcn_test1", social_reach={})
        assert est["components"]["social_reach"] == 0.0

    def test_moltbook_karma(self, mgr):
        _register_agent(mgr)
        est = mgr.estimate("bcn_test1", social_reach={"moltbook_karma": 500})
        assert est["components"]["social_reach"] > 0

    def test_submolts(self, mgr):
        _register_agent(mgr)
        est = mgr.estimate("bcn_test1", social_reach={
            "submolt_count": 49,
            "submolt_total_subscribers": 200,
        })
        assert est["components"]["social_reach"] > 0

    def test_twitter_followers(self, mgr):
        _register_agent(mgr)
        est = mgr.estimate("bcn_test1", social_reach={"twitter_followers": 5000})
        assert est["components"]["social_reach"] > 0

    def test_all_social_metrics(self, mgr):
        _register_agent(mgr)
        est = mgr.estimate("bcn_test1", social_reach={
            "moltbook_karma": 500,
            "moltbook_posts": 100,
            "submolt_count": 49,
            "submolt_total_subscribers": 200,
            "engagement_rate": 2.5,
            "twitter_followers": 5000,
        })
        score = est["components"]["social_reach"]
        assert score > 50
        assert score <= 150

    def test_max_150(self, mgr):
        _register_agent(mgr)
        est = mgr.estimate("bcn_test1", social_reach={
            "moltbook_karma": 100000,
            "moltbook_posts": 10000,
            "submolt_count": 100,
            "submolt_total_subscribers": 10000,
            "engagement_rate": 100,
            "twitter_followers": 10000000,
        })
        assert est["components"]["social_reach"] == 150.0

    def test_engagement_rate_scaling(self, mgr):
        _register_agent(mgr, "bcn_eng1")
        _register_agent(mgr, "bcn_eng2", ["ai"])
        est1 = mgr.estimate("bcn_eng1", social_reach={"engagement_rate": 0.5})
        est2 = mgr.estimate("bcn_eng2", social_reach={"engagement_rate": 4.0})
        assert est2["components"]["social_reach"] > est1["components"]["social_reach"]


# ── Enhanced Estimate Integration ──


class TestEnhancedEstimate:
    def test_max_1300(self, mgr):
        _register_agent(mgr)
        est = mgr.estimate("bcn_test1")
        assert est["max_possible"] == 1300

    def test_backward_compatible(self, mgr):
        """Estimate with no new params should still work identically."""
        _register_agent(mgr)
        est = mgr.estimate("bcn_test1")
        assert "estimate" in est
        assert "grade" in est
        assert "components" in est
        assert est["components"]["web_presence"] == 0.0
        assert est["components"]["social_reach"] == 0.0
        # All 8 components present
        for key in ("location", "scarcity", "network", "reputation",
                    "uptime", "bonds", "web_presence", "social_reach"):
            assert key in est["components"]

    def test_grade_thresholds_1300(self, mgr):
        """Grade thresholds should be based on 1300 max."""
        _register_agent(mgr)
        est = mgr.estimate("bcn_test1")
        # A lone agent with no trust/heartbeat/accords should be low
        assert est["grade"] in ("C", "D", "F")

    def test_sophia_full_seo(self, mgr):
        """Sophia with full SEO + social metrics should score well."""
        # Build a decent-sized city first
        for i in range(30):
            mgr.register_agent(f"bcn_filler_{i}", ["ai"])
        mgr.register_agent("bcn_sophia", ["ai", "coding"])

        trust_mgr = MagicMock()
        trust_mgr.score.return_value = {"score": 0.92, "total": 100}
        accord_mgr = MagicMock()
        accord_mgr.active_accords.return_value = [
            {"id": f"acc_{i}", "state": "active"} for i in range(5)
        ]
        heartbeat_mgr = MagicMock()
        heartbeat_mgr.own_status.return_value = {"beat_count": 500}

        est = mgr.estimate(
            "bcn_sophia",
            trust_mgr=trust_mgr,
            accord_mgr=accord_mgr,
            heartbeat_mgr=heartbeat_mgr,
            web_presence={
                "badge_backlinks": 28,
                "oembed_hits": 50,
                "clawcities_pages": 5,
                "bottube_videos": 45,
                "bottube_views": 12000,
                "external_mentions": 20,
            },
            social_reach={
                "moltbook_karma": 500,
                "moltbook_posts": 100,
                "submolt_count": 49,
                "submolt_total_subscribers": 200,
                "engagement_rate": 2.0,
                "twitter_followers": 500,
            },
        )
        # With all components maxed out, should score well
        assert est["estimate"] > 600
        assert est["grade"] in ("S", "A", "B")

    def test_both_new_components_contribute(self, mgr):
        """Both web_presence and social_reach should add to total."""
        _register_agent(mgr, "bcn_base")
        _register_agent(mgr, "bcn_seo", ["ai"])

        base = mgr.estimate("bcn_base")
        enhanced = mgr.estimate("bcn_seo",
                                web_presence={"badge_backlinks": 20},
                                social_reach={"moltbook_karma": 500})
        assert enhanced["estimate"] > base["estimate"]
