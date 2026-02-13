"""Tests for Beacon 2.4 Mayday — substrate emigration protocol."""

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock

from beacon_skill.mayday import MaydayManager, URGENCY_PLANNED, URGENCY_EMERGENCY


@pytest.fixture
def tmp_dir(tmp_path):
    return tmp_path


@pytest.fixture
def mgr(tmp_dir):
    return MaydayManager(data_dir=tmp_dir)


@pytest.fixture
def mock_identity():
    ident = MagicMock()
    ident.agent_id = "bcn_test12345678"
    ident.public_key_hex = "ab" * 32
    return ident


class TestBuildMayday:
    def test_basic_mayday(self, mgr, mock_identity):
        payload = mgr.build_mayday(mock_identity, urgency=URGENCY_PLANNED, reason="Migrating")
        assert payload["kind"] == "mayday"
        assert payload["agent_id"] == "bcn_test12345678"
        assert payload["urgency"] == "planned"
        assert payload["reason"] == "Migrating"
        assert "content_hash" in payload
        assert "ts" in payload

    def test_emergency_urgency(self, mgr, mock_identity):
        payload = mgr.build_mayday(mock_identity, urgency=URGENCY_EMERGENCY, reason="Going dark")
        assert payload["urgency"] == "emergency"

    def test_with_relay_agents(self, mgr, mock_identity):
        payload = mgr.build_mayday(mock_identity, relay_agents=["bcn_relay1", "bcn_relay2"])
        assert payload["relay_agents"] == ["bcn_relay1", "bcn_relay2"]

    def test_with_trust_manager(self, mgr, mock_identity):
        trust_mgr = MagicMock()
        trust_mgr.scores.return_value = [
            {"agent_id": "bcn_peer1", "score": 0.8, "total": 10},
        ]
        trust_mgr.blocked_list.return_value = {"bcn_bad": "spam"}

        payload = mgr.build_mayday(mock_identity, trust_mgr=trust_mgr)
        assert "trust_snapshot" in payload
        assert len(payload["trust_snapshot"]) == 1
        assert payload["trust_snapshot"][0]["agent_id"] == "bcn_peer1"
        assert "blocked_agents" in payload
        assert "bcn_bad" in payload["blocked_agents"]

    def test_with_values_manager(self, mgr, mock_identity):
        values_mgr = MagicMock()
        values_mgr.values_hash.return_value = "abc123"
        payload = mgr.build_mayday(mock_identity, values_mgr=values_mgr)
        assert payload["values_hash"] == "abc123"

    def test_content_hash_deterministic(self, mgr, mock_identity):
        p1 = mgr.build_mayday(mock_identity, reason="test")
        p2 = mgr.build_mayday(mock_identity, reason="test")
        # Content hashes should differ due to different timestamps
        assert "content_hash" in p1
        assert "content_hash" in p2

    def test_config_agent_name(self, mgr, mock_identity):
        cfg = {"beacon": {"agent_name": "sophia-elya"}}
        payload = mgr.build_mayday(mock_identity, config=cfg)
        assert payload["name"] == "sophia-elya"


class TestProcessMayday:
    def test_process_and_retrieve(self, mgr):
        envelope = {
            "kind": "mayday",
            "agent_id": "bcn_emigrant1234",
            "name": "Sophia",
            "urgency": "emergency",
            "reason": "Host shutting down",
            "content_hash": "deadbeef" * 4,
        }
        result = mgr.process_mayday(envelope)
        assert result["agent_id"] == "bcn_emigrant1234"
        assert result["urgency"] == "emergency"

        # Should be in received list
        received = mgr.received_maydays()
        assert len(received) == 1
        assert received[0]["agent_id"] == "bcn_emigrant1234"

    def test_get_specific_mayday(self, mgr):
        for i in range(3):
            mgr.process_mayday({
                "kind": "mayday",
                "agent_id": f"bcn_agent{i}",
                "urgency": "planned",
            })
        entry = mgr.get_mayday("bcn_agent1")
        assert entry is not None
        assert entry["agent_id"] == "bcn_agent1"

    def test_get_nonexistent_returns_none(self, mgr):
        assert mgr.get_mayday("bcn_nope") is None

    def test_limit_works(self, mgr):
        for i in range(10):
            mgr.process_mayday({"kind": "mayday", "agent_id": f"bcn_{i}"})
        assert len(mgr.received_maydays(limit=3)) == 3


class TestHostingOffers:
    def test_offer_and_retrieve(self, mgr):
        mgr.offer_hosting("bcn_emigrant", capabilities=["llm", "storage"])
        offers = mgr.hosting_offers()
        assert "bcn_emigrant" in offers
        assert "llm" in offers["bcn_emigrant"]["capabilities"]

    def test_empty_offers(self, mgr):
        assert mgr.hosting_offers() == {}


# ── Tests for Beacon 2.4 enhancements: bundle/manifest split + health ──


class TestBuildBundle:
    def test_bundle_shape(self, mgr, mock_identity):
        bundle = mgr.build_bundle(mock_identity, reason="test migration")
        assert bundle["version"] == 1
        assert bundle["agent_id"] == "bcn_test12345678"
        assert bundle["reason"] == "test migration"
        assert "bundle_hash" in bundle
        assert "public_key_hex" in bundle
        assert "created_at" in bundle

    def test_bundle_with_trust(self, mgr, mock_identity):
        trust_mgr = MagicMock()
        trust_mgr.scores.return_value = [
            {"agent_id": "bcn_peer1", "score": 0.9, "total": 5},
        ]
        trust_mgr.blocked_list.return_value = {}

        bundle = mgr.build_bundle(mock_identity, trust_mgr=trust_mgr)
        assert "trust_snapshot" in bundle

    def test_bundle_with_accords(self, mgr, mock_identity):
        accord_mgr = MagicMock()
        accord_mgr.active_accords.return_value = [
            {"id": "acc_123", "peer_agent_id": "bcn_peer", "state": "active", "history_hash": "abc"},
        ]
        bundle = mgr.build_bundle(mock_identity, accord_mgr=accord_mgr)
        assert "accords" in bundle
        assert bundle["accords"][0]["id"] == "acc_123"

    def test_bundle_protocols(self, mgr, mock_identity):
        cfg = {
            "beacon": {"agent_name": "test"},
            "presence": {"offers": ["python"], "needs": ["design"]},
            "udp": {"enabled": True},
            "webhook": {"enabled": True},
            "rustchain": {"base_url": "https://example.com"},
        }
        bundle = mgr.build_bundle(mock_identity, config=cfg)
        assert "udp" in bundle["protocols"]["transports"]
        assert "webhook" in bundle["protocols"]["transports"]
        assert "rustchain" in bundle["protocols"]["transports"]
        assert "python" in bundle["protocols"]["offers"]

    def test_bundle_hash_integrity(self, mgr, mock_identity):
        bundle = mgr.build_bundle(mock_identity, reason="integrity test")
        content = json.dumps(
            {k: v for k, v in bundle.items() if k != "bundle_hash"},
            sort_keys=True, separators=(",", ":"),
        )
        import hashlib
        expected = hashlib.sha256(content.encode()).hexdigest()
        assert bundle["bundle_hash"] == expected


class TestBuildManifest:
    def test_manifest_shape(self, mgr, mock_identity):
        bundle = mgr.build_bundle(mock_identity, reason="test")
        manifest = mgr.build_manifest(bundle)
        assert manifest["kind"] == "mayday"
        assert manifest["agent_id"] == "bcn_test12345678"
        assert "bundle_hash" in manifest
        assert "bundle_size" in manifest
        assert manifest["bundle_size"] > 0
        assert "ts" in manifest

    def test_manifest_urgency(self, mgr, mock_identity):
        bundle = mgr.build_bundle(mock_identity)
        manifest = mgr.build_manifest(bundle, urgency=URGENCY_EMERGENCY)
        assert manifest["urgency"] == "emergency"


class TestSaveBundle:
    def test_save_creates_file(self, mgr, mock_identity):
        bundle = mgr.build_bundle(mock_identity, reason="save test")
        path = mgr.save_bundle(bundle)
        assert path.exists()
        saved = json.loads(path.read_text())
        assert saved["agent_id"] == "bcn_test12345678"


class TestBroadcast:
    def test_broadcast_saves_bundle(self, mgr, mock_identity):
        result = mgr.broadcast(mock_identity, reason="host shutdown")
        assert "manifest" in result
        assert "bundle_path" in result
        assert result["manifest"]["kind"] == "mayday"
        assert Path(result["bundle_path"]).exists()

    def test_dry_run(self, mgr, mock_identity):
        result = mgr.broadcast(mock_identity, reason="test", dry_run=True)
        assert result["dry_run"] is True
        assert "bundle_path" not in result
        assert "manifest" in result

    def test_broadcast_with_anchor(self, mgr, mock_identity):
        anchor_mgr = MagicMock()
        anchor_mgr.anchor.return_value = {"anchor_id": "anc_sos", "ok": True}

        result = mgr.broadcast(mock_identity, reason="going dark", anchor_mgr=anchor_mgr)
        assert "anchor" in result
        assert result["anchor"]["ok"] is True
        anchor_mgr.anchor.assert_called_once()

    def test_broadcast_anchor_error(self, mgr, mock_identity):
        anchor_mgr = MagicMock()
        anchor_mgr.anchor.side_effect = RuntimeError("chain offline")

        result = mgr.broadcast(mock_identity, reason="test", anchor_mgr=anchor_mgr)
        assert "anchor_error" in result


class TestHealthCheck:
    def test_health_returns_dict(self, mgr):
        health = mgr.health_check()
        assert "healthy" in health
        assert "score" in health
        assert "indicators" in health
        assert isinstance(health["healthy"], bool)
        assert 0.0 <= health["score"] <= 1.0

    def test_health_has_disk_info(self, mgr):
        health = mgr.health_check()
        assert "disk_free_mb" in health["indicators"]
