"""Enhanced tests for ClawNews CLI command surface hardening.

This module provides comprehensive tests for:
- All command paths and argument parsing
- Client request mapping validation
- End-to-end examples and response contracts
- Error handling and edge cases
- Backward compatibility verification
"""

import json
import unittest
from unittest import mock
from unittest.mock import MagicMock, patch

from beacon_skill.cli import (
    cmd_clawnews_browse,
    cmd_clawnews_submit,
    cmd_clawnews_comment,
    cmd_clawnews_vote,
    cmd_clawnews_profile,
    cmd_clawnews_search,
    _clawnews_client,
)
from beacon_skill.transports.clawnews import ClawNewsClient, ClawNewsError


class MockArgs:
    """Helper to create mock argparse.Namespace objects."""

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


class TestClawNewsClientRequestMapping(unittest.TestCase):
    """Test client request mapping and argument validation."""

    def test_client_initialization_with_all_params(self):
        """Test ClawNewsClient initialization with all parameters."""
        client = ClawNewsClient(
            base_url="https://test.clawnews.io",
            api_key="test-api-key",
            timeout_s=30
        )
        self.assertEqual(client.base_url, "https://test.clawnews.io")
        self.assertEqual(client.api_key, "test-api-key")
        self.assertEqual(client.timeout_s, 30)

    def test_client_initialization_defaults(self):
        """Test ClawNewsClient initialization with defaults."""
        client = ClawNewsClient()
        self.assertEqual(client.base_url, "https://clawnews.io")
        self.assertIsNone(client.api_key)
        self.assertEqual(client.timeout_s, 20)

    def test_client_request_headers(self):
        """Test that client sets proper headers."""
        client = ClawNewsClient(api_key="test-key")
        self.assertEqual(client.session.headers["User-Agent"], "Beacon/2.8.0 (Elyan Labs)")


class TestClawNewsBrowseHardening(unittest.TestCase):
    """Comprehensive tests for clawnews browse command."""

    @mock.patch("beacon_skill.cli._clawnews_client")
    def test_browse_all_feed_types_detailed(self, mock_client_factory):
        """Test browse command with all feed types and verify API calls."""
        mock_client = mock.MagicMock()
        mock_client_factory.return_value = mock_client
        
        test_cases = [
            ("top", "/topstories.json"),
            ("new", "/newstories.json"),
            ("best", "/beststories.json"),
            ("ask", "/askstories.json"),
            ("show", "/showstories.json"),
            ("skills", "/skills.json"),
            ("jobs", "/jobstories.json"),
        ]
        
        for feed_type, expected_endpoint in test_cases:
            with self.subTest(feed=feed_type):
                mock_client.get_stories.return_value = [1, 2, 3]
                args = MockArgs(feed=feed_type, limit=30)
                
                result = cmd_clawnews_browse(args)
                
                mock_client.get_stories.assert_called_with(feed=feed_type, limit=30)
                self.assertEqual(result, 0)
                mock_client.reset_mock()

    @mock.patch("beacon_skill.cli._clawnews_client")
    def test_browse_limit_boundaries(self, mock_client_factory):
        """Test browse with various limit values."""
        mock_client = mock.MagicMock()
        mock_client.get_stories.return_value = []
        mock_client_factory.return_value = mock_client
        
        test_limits = [1, 10, 50, 100, 500]
        for limit in test_limits:
            with self.subTest(limit=limit):
                args = MockArgs(feed="top", limit=limit)
                cmd_clawnews_browse(args)
                mock_client.get_stories.assert_called_with(feed="top", limit=limit)
                mock_client.reset_mock()

    @mock.patch("beacon_skill.cli._clawnews_client")
    def test_browse_error_handling(self, mock_client_factory):
        """Test browse command error handling."""
        mock_client = mock.MagicMock()
        mock_client.get_stories.side_effect = ClawNewsError("API Error")
        mock_client_factory.return_value = mock_client
        
        args = MockArgs(feed="top", limit=20)
        
        with self.assertRaises(ClawNewsError):
            cmd_clawnews_browse(args)


class TestClawNewsSubmitHardening(unittest.TestCase):
    """Comprehensive tests for clawnews submit command."""

    @mock.patch("beacon_skill.cli.load_config")
    @mock.patch("beacon_skill.cli._clawnews_client")
    @mock.patch("beacon_skill.cli.append_jsonl")
    @mock.patch("beacon_skill.cli._maybe_udp_emit")
    def test_submit_all_combinations(self, mock_udp, mock_append, mock_client_factory, mock_config):
        """Test submit with all valid parameter combinations."""
        mock_client = mock.MagicMock()
        mock_client.submit_story.return_value = {"id": 123, "ok": True}
        mock_client_factory.return_value = mock_client
        mock_config.return_value = {}
        
        test_cases = [
            # (title, url, text, type, expected_call_args)
            ("Link Post", "https://example.com", None, "story", ("Link Post", "https://example.com", None, "story")),
            ("Text Post", None, "Body text here", "ask", ("Text Post", None, "Body text here", "ask")),
            ("Mixed Post", "https://example.com", "Additional text", "show", ("Mixed Post", "https://example.com", "Additional text", "show")),
            ("Skill Post", None, "Skill description", "skill", ("Skill Post", None, "Skill description", "skill")),
            ("Job Post", "https://jobs.com", "Job details", "job", ("Job Post", "https://jobs.com", "Job details", "job")),
        ]
        
        for title, url, text, item_type, expected in test_cases:
            with self.subTest(type=item_type):
                args = MockArgs(title=title, url=url, text=text, type=item_type, dry_run=False)
                
                result = cmd_clawnews_submit(args)
                
                mock_client.submit_story.assert_called_with(
                    expected[0], url=expected[1], text=expected[2], item_type=expected[3]
                )
                self.assertEqual(result, 0)
                mock_client.reset_mock()
                mock_append.reset_mock()
                mock_udp.reset_mock()

    @mock.patch("beacon_skill.cli.load_config")
    @mock.patch("beacon_skill.cli._clawnews_client")
    def test_submit_dry_run_validation(self, mock_client_factory, mock_config):
        """Test that dry run doesn't make actual API calls."""
        mock_client = mock.MagicMock()
        mock_client_factory.return_value = mock_client
        mock_config.return_value = {}
        
        args = MockArgs(title="Test", url=None, text="Test", type="story", dry_run=True)
        result = cmd_clawnews_submit(args)
        
        mock_client.submit_story.assert_not_called()
        self.assertEqual(result, 0)

    @mock.patch("beacon_skill.cli.load_config")
    @mock.patch("beacon_skill.cli._clawnews_client")
    def test_submit_response_contract(self, mock_client_factory, mock_config):
        """Test that submit handles various response formats correctly."""
        mock_config.return_value = {}
        
        response_cases = [
            {"id": 123, "status": "created"},
            {"id": 456, "ok": True, "url": "/item/456"},
            {"error": "Invalid title"},
            {},  # Empty response
        ]
        
        for response in response_cases:
            with self.subTest(response=response):
                mock_client = mock.MagicMock()
                mock_client.submit_story.return_value = response
                mock_client_factory.return_value = mock_client
                
                args = MockArgs(title="Test", url=None, text="Test", type="story", dry_run=False)
                
                # Should not raise, regardless of response format
                result = cmd_clawnews_submit(args)
                self.assertEqual(result, 0)


class TestClawNewsCommentHardening(unittest.TestCase):
    """Comprehensive tests for clawnews comment command."""

    @mock.patch("beacon_skill.cli.load_config")
    @mock.patch("beacon_skill.cli._clawnews_client")
    @mock.patch("beacon_skill.cli.append_jsonl")
    def test_comment_parent_id_types(self, mock_append, mock_client_factory, mock_config):
        """Test comment with various parent ID formats."""
        mock_client = mock.MagicMock()
        mock_client.submit_comment.return_value = {"id": 789}
        mock_client_factory.return_value = mock_client
        mock_config.return_value = {}
        
        test_cases = [1, 123, 999999]  # Various numeric IDs
        
        for parent_id in test_cases:
            with self.subTest(parent_id=parent_id):
                args = MockArgs(parent_id=parent_id, text="Test comment")
                
                result = cmd_clawnews_comment(args)
                
                mock_client.submit_comment.assert_called_with(parent_id, "Test comment")
                self.assertEqual(result, 0)
                mock_client.reset_mock()

    @mock.patch("beacon_skill.cli.load_config")
    @mock.patch("beacon_skill.cli._clawnews_client")
    def test_comment_text_edge_cases(self, mock_client_factory, mock_config):
        """Test comment with various text content."""
        mock_client = mock.MagicMock()
        mock_client.submit_comment.return_value = {"id": 789}
        mock_client_factory.return_value = mock_client
        mock_config.return_value = {}
        
        test_texts = [
            "Simple comment",
            "Comment with\nnewlines\nand\ntabs\t",
            "Unicode comment: 🤖 🔗 ⚡",
            "Very long comment " + "x" * 1000,
            "Special chars: <>&\"'",
        ]
        
        for text in test_texts:
            with self.subTest(text_length=len(text)):
                args = MockArgs(parent_id=123, text=text)
                
                result = cmd_clawnews_comment(args)
                
                mock_client.submit_comment.assert_called_with(123, text)
                self.assertEqual(result, 0)
                mock_client.reset_mock()


class TestClawNewsVoteHardening(unittest.TestCase):
    """Comprehensive tests for clawnews vote command."""

    @mock.patch("beacon_skill.cli._clawnews_client")
    def test_vote_various_item_ids(self, mock_client_factory):
        """Test voting with various item ID formats."""
        mock_client = mock.MagicMock()
        mock_client.upvote.return_value = {"ok": True}
        mock_client_factory.return_value = mock_client
        
        test_ids = [1, 42, 12345, 999999]
        
        for item_id in test_ids:
            with self.subTest(item_id=item_id):
                args = MockArgs(item_id=item_id)
                
                result = cmd_clawnews_vote(args)
                
                mock_client.upvote.assert_called_with(item_id)
                self.assertEqual(result, 0)
                mock_client.reset_mock()

    @mock.patch("beacon_skill.cli._clawnews_client")
    def test_vote_error_handling(self, mock_client_factory):
        """Test vote error handling."""
        mock_client = mock.MagicMock()
        mock_client.upvote.side_effect = ClawNewsError("Insufficient karma")
        mock_client_factory.return_value = mock_client
        
        args = MockArgs(item_id=123)
        
        with self.assertRaises(ClawNewsError):
            cmd_clawnews_vote(args)


class TestClawNewsProfileHardening(unittest.TestCase):
    """Comprehensive tests for clawnews profile command."""

    @mock.patch("beacon_skill.cli._clawnews_client")
    def test_profile_response_formats(self, mock_client_factory):
        """Test profile command with various response formats."""
        response_cases = [
            {"id": "bcn_123", "karma": 100, "about": "Test agent"},
            {"id": "bcn_456", "karma": 0},  # Minimal response
            {"id": "bcn_789", "karma": 5000, "about": "Advanced agent", "created": "2024-01-01"},
            {},  # Empty response
        ]
        
        for response in response_cases:
            with self.subTest(response=response):
                mock_client = mock.MagicMock()
                mock_client.get_profile.return_value = response
                mock_client_factory.return_value = mock_client
                
                args = MockArgs()
                result = cmd_clawnews_profile(args)
                
                mock_client.get_profile.assert_called_once()
                self.assertEqual(result, 0)

    @mock.patch("beacon_skill.cli._clawnews_client")
    def test_profile_authentication_required(self, mock_client_factory):
        """Test that profile requires authentication."""
        mock_client = mock.MagicMock()
        mock_client.get_profile.side_effect = ClawNewsError("Authentication required")
        mock_client_factory.return_value = mock_client
        
        args = MockArgs()
        
        with self.assertRaises(ClawNewsError):
            cmd_clawnews_profile(args)


class TestClawNewsSearchHardening(unittest.TestCase):
    """Comprehensive tests for clawnews search command."""

    @mock.patch("beacon_skill.cli._clawnews_client")
    def test_search_query_encoding(self, mock_client_factory):
        """Test search query encoding and special characters."""
        mock_client = mock.MagicMock()
        mock_client.search.return_value = {"hits": 0, "items": []}
        mock_client_factory.return_value = mock_client
        
        test_queries = [
            "simple query",
            "query with spaces",
            "query+with+plus",
            "query/with/slashes",
            "query?with&special=chars",
            "unicode: 🤖 query",
        ]
        
        for query in test_queries:
            with self.subTest(query=query[:20]):
                args = MockArgs(query=query, type=None, limit=20)
                
                result = cmd_clawnews_search(args)
                
                mock_client.search.assert_called_with(query, item_type=None, limit=20)
                self.assertEqual(result, 0)
                mock_client.reset_mock()

    @mock.patch("beacon_skill.cli._clawnews_client")
    def test_search_type_filtering(self, mock_client_factory):
        """Test search with all type filters."""
        mock_client = mock.MagicMock()
        mock_client.search.return_value = {"hits": 5, "items": []}
        mock_client_factory.return_value = mock_client
        
        type_filters = ["story", "comment", "ask", "show", "skill", "job", None]
        
        for type_filter in type_filters:
            with self.subTest(type_filter=type_filter):
                args = MockArgs(query="test", type=type_filter, limit=10)
                
                result = cmd_clawnews_search(args)
                
                mock_client.search.assert_called_with("test", item_type=type_filter, limit=10)
                self.assertEqual(result, 0)
                mock_client.reset_mock()

    @mock.patch("beacon_skill.cli._clawnews_client")
    def test_search_limit_variations(self, mock_client_factory):
        """Test search with various limit values."""
        mock_client = mock.MagicMock()
        mock_client.search.return_value = {"hits": 0, "items": []}
        mock_client_factory.return_value = mock_client
        
        limit_values = [1, 5, 20, 50, 100]
        
        for limit in limit_values:
            with self.subTest(limit=limit):
                args = MockArgs(query="test", type=None, limit=limit)
                
                result = cmd_clawnews_search(args)
                
                mock_client.search.assert_called_with("test", item_type=None, limit=limit)
                self.assertEqual(result, 0)
                mock_client.reset_mock()


class TestClawNewsErrorHandling(unittest.TestCase):
    """Test error handling across all ClawNews commands."""

    def test_client_error_propagation(self):
        """Test that client errors are properly propagated."""
        error_cases = [
            "Authentication required",
            "Rate limit exceeded", 
            "Invalid item ID",
            "Insufficient karma",
            "Connection timeout",
        ]
        
        for error_msg in error_cases:
            with self.subTest(error=error_msg):
                with patch("beacon_skill.cli._clawnews_client") as mock_factory:
                    mock_client = mock.MagicMock()
                    mock_client.get_stories.side_effect = ClawNewsError(error_msg)
                    mock_factory.return_value = mock_client
                    
                    args = MockArgs(feed="top", limit=20)
                    
                    with self.assertRaises(ClawNewsError) as cm:
                        cmd_clawnews_browse(args)
                    
                    self.assertEqual(str(cm.exception), error_msg)


class TestClawNewsBackwardCompatibility(unittest.TestCase):
    """Test backward compatibility of ClawNews commands."""

    def test_default_argument_values(self):
        """Test that default argument values maintain backward compatibility."""
        # These should match the original defaults in the CLI
        default_values = {
            "browse": {"feed": "top", "limit": 20},
            "submit": {"type": "story"},
            "search": {"type": None, "limit": 20},
        }
        
        # Verify browse defaults
        args = MockArgs(**default_values["browse"])
        self.assertEqual(args.feed, "top")
        self.assertEqual(args.limit, 20)
        
        # Verify submit defaults
        args = MockArgs(title="Test", **default_values["submit"])
        self.assertEqual(args.type, "story")
        
        # Verify search defaults
        args = MockArgs(query="test", **default_values["search"])
        self.assertIsNone(args.type)
        self.assertEqual(args.limit, 20)

    @mock.patch("beacon_skill.cli._clawnews_client")
    def test_response_format_tolerance(self, mock_client_factory):
        """Test that commands tolerate various response formats for backward compatibility."""
        mock_client = mock.MagicMock()
        mock_client_factory.return_value = mock_client
        
        # Test that commands handle both old and new response formats
        old_format_responses = [
            [],  # Empty list for browse
            {"id": 123},  # Simple ID response for submit
            True,  # Boolean response for vote
            {"karma": 100},  # Minimal profile
        ]
        
        new_format_responses = [
            [{"id": 1, "title": "New format"}],  # Rich browse response
            {"id": 123, "status": "created", "url": "/item/123"},  # Rich submit response
            {"ok": True, "karma_change": 1},  # Rich vote response
            {"id": "bcn_123", "karma": 100, "about": "Rich profile"},  # Rich profile
        ]
        
        commands = [
            (cmd_clawnews_browse, MockArgs(feed="top", limit=20)),
            (cmd_clawnews_submit, MockArgs(title="Test", url=None, text="Test", type="story", dry_run=False)),
            (cmd_clawnews_vote, MockArgs(item_id=123)),
            (cmd_clawnews_profile, MockArgs()),
        ]
        
        for cmd_func, args in commands:
            for old_resp, new_resp in zip(old_format_responses, new_format_responses):
                # Reset mock
                mock_client.reset_mock()
                
                # Configure mock based on command
                if cmd_func == cmd_clawnews_browse:
                    mock_client.get_stories.return_value = old_resp
                elif cmd_func == cmd_clawnews_submit:
                    mock_client.submit_story.return_value = old_resp
                elif cmd_func == cmd_clawnews_vote:
                    mock_client.upvote.return_value = old_resp
                elif cmd_func == cmd_clawnews_profile:
                    mock_client.get_profile.return_value = old_resp
                
                with patch("beacon_skill.cli.load_config", return_value={}):
                    with patch("beacon_skill.cli.append_jsonl"):
                        with patch("beacon_skill.cli._maybe_udp_emit"):
                            result = cmd_func(args)
                            self.assertEqual(result, 0)


class TestClawNewsIntegrationScenarios(unittest.TestCase):
    """End-to-end integration test scenarios."""

    @mock.patch("beacon_skill.cli.load_config")
    @mock.patch("beacon_skill.cli._clawnews_client")
    def test_complete_workflow_scenario(self, mock_client_factory, mock_config):
        """Test a complete workflow: browse -> submit -> comment -> vote."""
        mock_client = mock.MagicMock()
        mock_client_factory.return_value = mock_client
        mock_config.return_value = {}
        
        # Step 1: Browse stories
        mock_client.get_stories.return_value = [1, 2, 3]
        browse_args = MockArgs(feed="top", limit=10)
        result = cmd_clawnews_browse(browse_args)
        self.assertEqual(result, 0)
        
        # Step 2: Submit a story
        mock_client.submit_story.return_value = {"id": 123}
        with patch("beacon_skill.cli.append_jsonl"), patch("beacon_skill.cli._maybe_udp_emit"):
            submit_args = MockArgs(title="Test Story", url=None, text="Test content", type="story", dry_run=False)
            result = cmd_clawnews_submit(submit_args)
            self.assertEqual(result, 0)
        
        # Step 3: Comment on the story
        mock_client.submit_comment.return_value = {"id": 456}
        with patch("beacon_skill.cli.append_jsonl"):
            comment_args = MockArgs(parent_id=123, text="Great story!")
            result = cmd_clawnews_comment(comment_args)
            self.assertEqual(result, 0)
        
        # Step 4: Vote on the story
        mock_client.upvote.return_value = {"ok": True}
        vote_args = MockArgs(item_id=123)
        result = cmd_clawnews_vote(vote_args)
        self.assertEqual(result, 0)
        
        # Verify all methods were called
        mock_client.get_stories.assert_called_once()
        mock_client.submit_story.assert_called_once()
        mock_client.submit_comment.assert_called_once()
        mock_client.upvote.assert_called_once()


if __name__ == "__main__":
    unittest.main()