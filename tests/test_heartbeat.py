"""Tests for Beacon 2.4 Heartbeat — proof of life protocol."""

import json
import time
import pytest
from pathlib import Path
from unittest.mock import MagicMock

from beacon_skill.heartbeat import HeartbeatManager


@pytest.fixture
def tmp_dir(tmp_path):
    return tmp_path


@pytest.fixture
def mgr(tmp_dir):
    return HeartbeatManager(data_dir=tmp_dir)


@pytest.fixture
def mock_identity():
    ident = MagicMock()
    ident.agent_id = "bcn_hearttest1234"
    ident.public_key_hex = "cd" * 32
    return ident


class TestBuildHeartbeat:
    def test_basic_heartbeat(self, mgr, mock_identity):
        payload = mgr.build_heartbeat(mock_identity)
        assert payload["kind"] == "heartbeat"
        assert payload["agent_id"] == "bcn_hearttest1234"
        assert payload["status"] == "alive"
        assert payload["beat_count"] == 1
        assert "ts" in payload
        assert "uptime_s" in payload

    def test_beat_count_increments(self, mgr, mock_identity):
        p1 = mgr.build_heartbeat(mock_identity)
        p2 = mgr.build_heartbeat(mock_identity)
        p3 = mgr.build_heartbeat(mock_identity)
        assert p1["beat_count"] == 1
        assert p2["beat_count"] == 2
        assert p3["beat_count"] == 3

    def test_degraded_status(self, mgr, mock_identity):
        payload = mgr.build_heartbeat(mock_identity, status="degraded")
        assert payload["status"] == "degraded"

    def test_shutting_down(self, mgr, mock_identity):
        payload = mgr.build_heartbeat(mock_identity, status="shutting_down")
        assert payload["status"] == "shutting_down"

    def test_with_health_metrics(self, mgr, mock_identity):
        health = {"cpu_percent": 45.2, "memory_gb": 12.5, "disk_free_gb": 100}
        payload = mgr.build_heartbeat(mock_identity, health=health)
        assert payload["health"]["cpu_percent"] == 45.2


class TestProcessHeartbeat:
    def test_process_peer(self, mgr):
        envelope = {
            "kind": "heartbeat",
            "agent_id": "bcn_peer123",
            "name": "TestPeer",
            "status": "alive",
            "beat_count": 5,
            "uptime_s": 3600,
            "ts": int(time.time()),
        }
        result = mgr.process_heartbeat(envelope)
        assert result["agent_id"] == "bcn_peer123"
        assert result["status"] == "alive"
        assert result["assessment"] == "healthy"

    def test_no_agent_id_returns_error(self, mgr):
        result = mgr.process_heartbeat({"kind": "heartbeat"})
        assert "error" in result

    def test_gap_tracking(self, tmp_dir):
        """Gap is measured from last_beat to current time.time(), so we fake the state."""
        mgr = HeartbeatManager(data_dir=tmp_dir)
        # Manually inject a peer with old last_beat
        state = mgr._load_state()
        state["peers"]["bcn_gapper"] = {
            "last_beat": int(time.time()) - 100,
            "status": "alive",
        }
        mgr._save_state(state)

        # New heartbeat arrives — gap should be ~100s
        result = mgr.process_heartbeat({
            "agent_id": "bcn_gapper",
            "status": "alive",
            "ts": int(time.time()),
        })
        assert result["gap_s"] >= 99


class TestPeerAssessment:
    def test_healthy_peer(self, mgr):
        mgr.process_heartbeat({
            "agent_id": "bcn_healthy",
            "status": "alive",
            "ts": int(time.time()),
        })
        status = mgr.peer_status("bcn_healthy")
        assert status["assessment"] == "healthy"

    def test_shutting_down_peer(self, mgr):
        mgr.process_heartbeat({
            "agent_id": "bcn_shutdown",
            "status": "shutting_down",
            "ts": int(time.time()),
        })
        status = mgr.peer_status("bcn_shutdown")
        assert status["assessment"] == "shutting_down"

    def test_unknown_peer(self, mgr):
        assert mgr.peer_status("bcn_unknown") is None

    def test_all_peers(self, mgr):
        now = int(time.time())
        for i in range(5):
            mgr.process_heartbeat({
                "agent_id": f"bcn_peer{i}",
                "status": "alive",
                "ts": now,
            })
        peers = mgr.all_peers()
        assert len(peers) == 5

    def test_silent_peers_empty_when_healthy(self, mgr):
        mgr.process_heartbeat({
            "agent_id": "bcn_fresh",
            "status": "alive",
            "ts": int(time.time()),
        })
        assert len(mgr.silent_peers()) == 0


class TestOwnStatus:
    def test_own_status_after_beat(self, mgr, mock_identity):
        mgr.build_heartbeat(mock_identity)
        own = mgr.own_status()
        assert own["beat_count"] == 1
        assert own["status"] == "alive"

    def test_own_status_empty(self, mgr):
        assert mgr.own_status() == {}


class TestPruneDead:
    def test_prune_removes_old(self, tmp_dir):
        mgr = HeartbeatManager(data_dir=tmp_dir, config={"heartbeat": {"dead_threshold_s": 10}})
        # Manually inject a stale peer
        state = mgr._load_state()
        state["peers"]["bcn_dead"] = {
            "last_beat": int(time.time()) - 1000,
            "status": "alive",
        }
        mgr._save_state(state)

        removed = mgr.prune_dead(max_age_s=100)
        assert removed == 1

    def test_prune_keeps_fresh(self, mgr):
        mgr.process_heartbeat({
            "agent_id": "bcn_fresh",
            "status": "alive",
            "ts": int(time.time()),
        })
        removed = mgr.prune_dead(max_age_s=9999)
        assert removed == 0


class TestHeartbeatLog:
    def test_log_written(self, mgr):
        mgr.process_heartbeat({
            "agent_id": "bcn_logged",
            "status": "alive",
            "beat_count": 1,
            "ts": int(time.time()),
        })
        log = mgr.heartbeat_log()
        assert len(log) == 1
        assert log[0]["agent_id"] == "bcn_logged"

    def test_empty_log(self, mgr):
        assert mgr.heartbeat_log() == []


# ── Tests for Beacon 2.4 enhancements ──


class TestBeat:
    """Tests for the beat() convenience method."""

    def test_beat_returns_heartbeat(self, mgr, mock_identity):
        result = mgr.beat(mock_identity)
        assert "heartbeat" in result
        assert result["heartbeat"]["kind"] == "heartbeat"
        assert result["heartbeat"]["beat_count"] == 1

    def test_beat_logs_sent(self, mgr, mock_identity):
        mgr.beat(mock_identity)
        log = mgr.heartbeat_log()
        sent = [e for e in log if e.get("direction") == "sent"]
        assert len(sent) == 1

    def test_beat_with_anchor(self, mgr, mock_identity):
        anchor_mgr = MagicMock()
        anchor_mgr.anchor.return_value = {"anchor_id": "anc_123", "ok": True}

        result = mgr.beat(mock_identity, anchor=True, anchor_mgr=anchor_mgr)
        assert "anchor" in result
        assert result["anchor"]["ok"] is True
        anchor_mgr.anchor.assert_called_once()

    def test_beat_without_anchor(self, mgr, mock_identity):
        result = mgr.beat(mock_identity, anchor=False)
        assert "anchor" not in result

    def test_beat_anchor_error_captured(self, mgr, mock_identity):
        anchor_mgr = MagicMock()
        anchor_mgr.anchor.side_effect = RuntimeError("no connection")

        result = mgr.beat(mock_identity, anchor=True, anchor_mgr=anchor_mgr)
        assert "anchor_error" in result
        assert "no connection" in result["anchor_error"]

    def test_beat_increments_count(self, mgr, mock_identity):
        r1 = mgr.beat(mock_identity)
        r2 = mgr.beat(mock_identity)
        assert r1["heartbeat"]["beat_count"] == 1
        assert r2["heartbeat"]["beat_count"] == 2


class TestCheckSilence:
    def test_no_silent_peers(self, mgr):
        mgr.process_heartbeat({
            "agent_id": "bcn_active",
            "status": "alive",
            "ts": int(time.time()),
        })
        assert mgr.check_silence() == []

    def test_detects_silent_peer(self, tmp_dir):
        mgr = HeartbeatManager(data_dir=tmp_dir)
        state = mgr._load_state()
        state["peers"]["bcn_gone"] = {
            "last_beat": int(time.time()) - 2000,
            "status": "alive",
            "name": "GoneAgent",
        }
        mgr._save_state(state)

        silent = mgr.check_silence(threshold_s=100)
        assert len(silent) == 1
        assert silent[0]["agent_id"] == "bcn_gone"
        assert silent[0]["silence_s"] >= 1900

    def test_custom_threshold(self, tmp_dir):
        mgr = HeartbeatManager(data_dir=tmp_dir)
        state = mgr._load_state()
        state["peers"]["bcn_recent"] = {
            "last_beat": int(time.time()) - 50,
            "status": "alive",
        }
        mgr._save_state(state)

        # 100s threshold → not silent (only 50s ago)
        assert mgr.check_silence(threshold_s=100) == []
        # 10s threshold → silent (50s > 10s)
        assert len(mgr.check_silence(threshold_s=10)) == 1


class TestMyHistory:
    def test_my_history_filters_sent(self, mgr, mock_identity):
        mgr.beat(mock_identity)
        mgr.process_heartbeat({"agent_id": "bcn_other", "status": "alive"})
        own = mgr.my_history()
        assert all(e.get("direction") == "sent" for e in own)

    def test_agent_history(self, mgr):
        for i in range(3):
            mgr.process_heartbeat({"agent_id": "bcn_target", "status": "alive", "beat_count": i})
        mgr.process_heartbeat({"agent_id": "bcn_other", "status": "alive"})

        history = mgr.agent_history("bcn_target")
        assert len(history) == 3
        assert all(e["agent_id"] == "bcn_target" for e in history)


class TestDailyDigest:
    def test_digest_shape(self, mgr, mock_identity):
        mgr.beat(mock_identity)
        mgr.process_heartbeat({"agent_id": "bcn_peer1", "status": "alive"})

        digest = mgr.daily_digest()
        assert "date" in digest
        assert digest["own_beat_count"] == 1
        assert digest["peers_seen"] >= 1
        assert "total_peers" in digest
        assert "ts" in digest

    def test_digest_empty_state(self, mgr):
        digest = mgr.daily_digest()
        assert digest["own_beat_count"] == 0
        assert digest["peers_seen"] == 0


class TestAnchorDigest:
    def test_anchor_digest_success(self, mgr, mock_identity):
        mgr.beat(mock_identity)
        anchor_mgr = MagicMock()
        anchor_mgr.anchor.return_value = {"anchor_id": "anc_digest", "ok": True}

        result = mgr.anchor_digest(anchor_mgr)
        assert result is not None
        assert result["ok"] is True
        anchor_mgr.anchor.assert_called_once()
        call_args = anchor_mgr.anchor.call_args
        assert call_args[1]["data_type"] == "heartbeat_digest"

    def test_anchor_digest_failure(self, mgr):
        anchor_mgr = MagicMock()
        anchor_mgr.anchor.side_effect = RuntimeError("offline")
        result = mgr.anchor_digest(anchor_mgr)
        assert result is None
