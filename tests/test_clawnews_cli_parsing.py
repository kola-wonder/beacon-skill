"""Tests for ClawNews CLI argument parsing and command hardening.

This module tests the argument parsing logic, validation, and error handling
for all ClawNews subcommands to ensure robust command surface.
"""

import argparse
import sys
import unittest
from io import StringIO
from unittest import mock

from beacon_skill.cli import main


class TestClawNewsCLIParsing(unittest.TestCase):
    """Test ClawNews CLI argument parsing."""

    def setUp(self):
        """Set up test fixtures."""
        self.original_stderr = sys.stderr
        self.original_stdout = sys.stdout
        
    def tearDown(self):
        """Clean up test fixtures."""
        sys.stderr = self.original_stderr
        sys.stdout = self.original_stdout

    def _capture_output(self, args):
        """Helper to capture stdout/stderr from CLI invocation."""
        sys.stdout = StringIO()
        sys.stderr = StringIO()
        
        try:
            main(args)
            return_code = 0
        except SystemExit as e:
            return_code = e.code
        
        stdout = sys.stdout.getvalue()
        stderr = sys.stderr.getvalue()
        
        sys.stdout = self.original_stdout
        sys.stderr = self.original_stderr
        
        return return_code, stdout, stderr

    def test_clawnews_browse_argument_parsing(self):
        """Test clawnews browse argument parsing."""
        test_cases = [
            # Valid cases
            (["clawnews", "browse"], 0),  # Default args
            (["clawnews", "browse", "--feed", "top"], 0),
            (["clawnews", "browse", "--feed", "new", "--limit", "50"], 0),
            (["clawnews", "browse", "--limit", "100"], 0),
        ]
        
        for args, expected_code in test_cases:
            with self.subTest(args=args):
                with mock.patch("beacon_skill.cli.cmd_clawnews_browse", return_value=0):
                    code, stdout, stderr = self._capture_output(args)
                    self.assertEqual(code, expected_code)

    def test_clawnews_browse_invalid_feed(self):
        """Test clawnews browse with invalid feed type."""
        with mock.patch("beacon_skill.cli.cmd_clawnews_browse"):
            code, stdout, stderr = self._capture_output(
                ["clawnews", "browse", "--feed", "invalid"]
            )
            self.assertNotEqual(code, 0)
            self.assertIn("invalid choice", stderr)

    def test_clawnews_submit_argument_parsing(self):
        """Test clawnews submit argument parsing."""
        test_cases = [
            # Valid cases
            (["clawnews", "submit", "--title", "Test Title"], 0),
            (["clawnews", "submit", "--title", "Test", "--url", "https://example.com"], 0),
            (["clawnews", "submit", "--title", "Test", "--text", "Content"], 0),
            (["clawnews", "submit", "--title", "Test", "--type", "ask"], 0),
            (["clawnews", "submit", "--title", "Test", "--dry-run"], 0),
        ]
        
        for args, expected_code in test_cases:
            with self.subTest(args=args):
                with mock.patch("beacon_skill.cli.cmd_clawnews_submit", return_value=0):
                    code, stdout, stderr = self._capture_output(args)
                    self.assertEqual(code, expected_code)

    def test_clawnews_submit_missing_title(self):
        """Test clawnews submit without required title."""
        with mock.patch("beacon_skill.cli.cmd_clawnews_submit"):
            code, stdout, stderr = self._capture_output(["clawnews", "submit"])
            self.assertNotEqual(code, 0)
            self.assertIn("required", stderr)

    def test_clawnews_submit_invalid_type(self):
        """Test clawnews submit with invalid type."""
        with mock.patch("beacon_skill.cli.cmd_clawnews_submit"):
            code, stdout, stderr = self._capture_output(
                ["clawnews", "submit", "--title", "Test", "--type", "invalid"]
            )
            self.assertNotEqual(code, 0)
            self.assertIn("invalid choice", stderr)

    def test_clawnews_comment_argument_parsing(self):
        """Test clawnews comment argument parsing."""
        test_cases = [
            # Valid cases
            (["clawnews", "comment", "123", "--text", "Great post!"], 0),
            (["clawnews", "comment", "456", "--text", "Comment with spaces"], 0),
        ]
        
        for args, expected_code in test_cases:
            with self.subTest(args=args):
                with mock.patch("beacon_skill.cli.cmd_clawnews_comment", return_value=0):
                    code, stdout, stderr = self._capture_output(args)
                    self.assertEqual(code, expected_code)

    def test_clawnews_comment_missing_args(self):
        """Test clawnews comment with missing arguments."""
        test_cases = [
            (["clawnews", "comment"], "parent_id"),  # Missing parent_id
            (["clawnews", "comment", "123"], "required"),  # Missing text
        ]
        
        for args, expected_error in test_cases:
            with self.subTest(args=args):
                with mock.patch("beacon_skill.cli.cmd_clawnews_comment"):
                    code, stdout, stderr = self._capture_output(args)
                    self.assertNotEqual(code, 0)
                    self.assertIn(expected_error, stderr)

    def test_clawnews_comment_invalid_parent_id(self):
        """Test clawnews comment with non-integer parent_id."""
        with mock.patch("beacon_skill.cli.cmd_clawnews_comment"):
            code, stdout, stderr = self._capture_output(
                ["clawnews", "comment", "not_a_number", "--text", "Comment"]
            )
            self.assertNotEqual(code, 0)
            self.assertIn("invalid int value", stderr)

    def test_clawnews_vote_argument_parsing(self):
        """Test clawnews vote argument parsing."""
        test_cases = [
            (["clawnews", "vote", "123"], 0),
            (["clawnews", "vote", "456789"], 0),
        ]
        
        for args, expected_code in test_cases:
            with self.subTest(args=args):
                with mock.patch("beacon_skill.cli.cmd_clawnews_vote", return_value=0):
                    code, stdout, stderr = self._capture_output(args)
                    self.assertEqual(code, expected_code)

    def test_clawnews_vote_missing_item_id(self):
        """Test clawnews vote without item_id."""
        with mock.patch("beacon_skill.cli.cmd_clawnews_vote"):
            code, stdout, stderr = self._capture_output(["clawnews", "vote"])
            self.assertNotEqual(code, 0)
            self.assertIn("required", stderr)

    def test_clawnews_vote_invalid_item_id(self):
        """Test clawnews vote with non-integer item_id."""
        with mock.patch("beacon_skill.cli.cmd_clawnews_vote"):
            code, stdout, stderr = self._capture_output(
                ["clawnews", "vote", "not_a_number"]
            )
            self.assertNotEqual(code, 0)
            self.assertIn("invalid int value", stderr)

    def test_clawnews_profile_argument_parsing(self):
        """Test clawnews profile argument parsing."""
        with mock.patch("beacon_skill.cli.cmd_clawnews_profile", return_value=0):
            code, stdout, stderr = self._capture_output(["clawnews", "profile"])
            self.assertEqual(code, 0)

    def test_clawnews_search_argument_parsing(self):
        """Test clawnews search argument parsing."""
        test_cases = [
            (["clawnews", "search", "test query"], 0),
            (["clawnews", "search", "test", "--type", "story"], 0),
            (["clawnews", "search", "test", "--limit", "50"], 0),
            (["clawnews", "search", "test", "--type", "comment", "--limit", "10"], 0),
        ]
        
        for args, expected_code in test_cases:
            with self.subTest(args=args):
                with mock.patch("beacon_skill.cli.cmd_clawnews_search", return_value=0):
                    code, stdout, stderr = self._capture_output(args)
                    self.assertEqual(code, expected_code)

    def test_clawnews_search_missing_query(self):
        """Test clawnews search without query."""
        with mock.patch("beacon_skill.cli.cmd_clawnews_search"):
            code, stdout, stderr = self._capture_output(["clawnews", "search"])
            self.assertNotEqual(code, 0)
            self.assertIn("required", stderr)

    def test_clawnews_search_invalid_type(self):
        """Test clawnews search with invalid type."""
        with mock.patch("beacon_skill.cli.cmd_clawnews_search"):
            code, stdout, stderr = self._capture_output(
                ["clawnews", "search", "test", "--type", "invalid"]
            )
            self.assertNotEqual(code, 0)
            self.assertIn("invalid choice", stderr)

    def test_clawnews_search_invalid_limit(self):
        """Test clawnews search with invalid limit."""
        with mock.patch("beacon_skill.cli.cmd_clawnews_search"):
            code, stdout, stderr = self._capture_output(
                ["clawnews", "search", "test", "--limit", "not_a_number"]
            )
            self.assertNotEqual(code, 0)
            self.assertIn("invalid int value", stderr)

    def test_clawnews_no_subcommand(self):
        """Test clawnews without subcommand."""
        code, stdout, stderr = self._capture_output(["clawnews"])
        self.assertNotEqual(code, 0)
        self.assertIn("required", stderr)

    def test_clawnews_invalid_subcommand(self):
        """Test clawnews with invalid subcommand."""
        code, stdout, stderr = self._capture_output(["clawnews", "invalid"])
        self.assertNotEqual(code, 0)
        self.assertIn("invalid choice", stderr)


class TestClawNewsArgumentValidation(unittest.TestCase):
    """Test argument validation logic in ClawNews commands."""

    def test_feed_type_choices(self):
        """Test that feed type choices are comprehensive."""
        valid_feeds = ["top", "new", "best", "ask", "show", "skills", "jobs"]
        
        # This tests the argparse choices validation
        for feed in valid_feeds:
            with mock.patch("beacon_skill.cli.cmd_clawnews_browse", return_value=0):
                # These should not raise SystemExit
                try:
                    main(["clawnews", "browse", "--feed", feed])
                except SystemExit as e:
                    self.assertEqual(e.code, 0, f"Feed {feed} should be valid")

    def test_submit_type_choices(self):
        """Test that submit type choices are comprehensive."""
        valid_types = ["story", "ask", "show", "skill", "job"]
        
        for item_type in valid_types:
            with mock.patch("beacon_skill.cli.cmd_clawnews_submit", return_value=0):
                try:
                    main(["clawnews", "submit", "--title", "Test", "--type", item_type])
                except SystemExit as e:
                    self.assertEqual(e.code, 0, f"Type {item_type} should be valid")

    def test_search_type_choices(self):
        """Test that search type choices are comprehensive."""
        valid_types = ["story", "comment", "ask", "show", "skill", "job"]
        
        for item_type in valid_types:
            with mock.patch("beacon_skill.cli.cmd_clawnews_search", return_value=0):
                try:
                    main(["clawnews", "search", "test", "--type", item_type])
                except SystemExit as e:
                    self.assertEqual(e.code, 0, f"Type {item_type} should be valid")

    def test_numeric_argument_bounds(self):
        """Test numeric argument boundary handling."""
        # Test limit values
        test_cases = [
            ("clawnews", "browse", "--limit", "1"),      # Minimum reasonable
            ("clawnews", "browse", "--limit", "1000"),   # Large value
            ("clawnews", "search", "test", "--limit", "1"),
            ("clawnews", "search", "test", "--limit", "500"),
        ]
        
        for args in test_cases:
            with self.subTest(args=args):
                with mock.patch("beacon_skill.cli.cmd_clawnews_browse", return_value=0):
                    with mock.patch("beacon_skill.cli.cmd_clawnews_search", return_value=0):
                        try:
                            main(list(args))
                        except SystemExit as e:
                            self.assertEqual(e.code, 0)

    def test_string_argument_handling(self):
        """Test string argument handling and encoding."""
        test_strings = [
            "Simple string",
            "String with spaces and punctuation!",
            "Unicode: 🤖 ⚡ 🔗",
            "Special chars: <>&\"'",
            "",  # Empty string
        ]
        
        # Test title argument
        for test_str in test_strings:
            with mock.patch("beacon_skill.cli.cmd_clawnews_submit", return_value=0):
                try:
                    main(["clawnews", "submit", "--title", test_str])
                except SystemExit as e:
                    self.assertEqual(e.code, 0)

    def test_optional_vs_required_arguments(self):
        """Test required vs optional argument validation."""
        # Required arguments test cases
        required_cases = [
            # submit requires title
            (["clawnews", "submit"], "title"),
            # comment requires parent_id and text
            (["clawnews", "comment"], "parent_id"),
            (["clawnews", "comment", "123"], "text"),
            # vote requires item_id
            (["clawnews", "vote"], "item_id"),
            # search requires query
            (["clawnews", "search"], "query"),
        ]
        
        for args, missing_arg in required_cases:
            with self.subTest(args=args, missing=missing_arg):
                with self.assertRaises(SystemExit) as cm:
                    main(args)
                self.assertNotEqual(cm.exception.code, 0)

    def test_boolean_flag_handling(self):
        """Test boolean flag argument handling."""
        boolean_cases = [
            (["clawnews", "submit", "--title", "Test", "--dry-run"], "dry_run", True),
            (["clawnews", "submit", "--title", "Test"], "dry_run", False),  # Default
        ]
        
        captured_args = []
        
        def capture_args(args):
            captured_args.append(args)
            return 0
        
        for cmd_args, flag_name, expected_value in boolean_cases:
            with self.subTest(args=cmd_args, flag=flag_name):
                captured_args.clear()
                with mock.patch("beacon_skill.cli.cmd_clawnews_submit", side_effect=capture_args):
                    try:
                        main(cmd_args)
                    except SystemExit:
                        pass
                    
                    if captured_args:
                        self.assertEqual(
                            getattr(captured_args[0], flag_name, False), 
                            expected_value
                        )


class TestClawNewsCommandHelpText(unittest.TestCase):
    """Test that help text is available and comprehensive."""

    def setUp(self):
        self.original_stdout = sys.stdout
        self.original_stderr = sys.stderr

    def tearDown(self):
        sys.stdout = self.original_stdout
        sys.stderr = self.original_stderr

    def _get_help_text(self, args):
        """Get help text for given arguments."""
        sys.stdout = StringIO()
        sys.stderr = StringIO()
        
        try:
            main(args + ["--help"])
        except SystemExit:
            pass
        
        stdout = sys.stdout.getvalue()
        stderr = sys.stderr.getvalue()
        
        sys.stdout = self.original_stdout
        sys.stderr = self.original_stderr
        
        return stdout + stderr

    def test_main_clawnews_help(self):
        """Test main clawnews help text."""
        help_text = self._get_help_text(["clawnews"])
        self.assertIn("ClawNews", help_text)
        self.assertIn("browse", help_text)
        self.assertIn("submit", help_text)
        self.assertIn("comment", help_text)
        self.assertIn("vote", help_text)
        self.assertIn("profile", help_text)
        self.assertIn("search", help_text)

    def test_browse_help(self):
        """Test clawnews browse help text."""
        help_text = self._get_help_text(["clawnews", "browse"])
        self.assertIn("--feed", help_text)
        self.assertIn("--limit", help_text)
        # Check that all feed choices are listed
        for choice in ["top", "new", "best", "ask", "show", "skills", "jobs"]:
            self.assertIn(choice, help_text)

    def test_submit_help(self):
        """Test clawnews submit help text."""
        help_text = self._get_help_text(["clawnews", "submit"])
        self.assertIn("--title", help_text)
        self.assertIn("--url", help_text)
        self.assertIn("--text", help_text)
        self.assertIn("--type", help_text)
        self.assertIn("--dry-run", help_text)

    def test_comment_help(self):
        """Test clawnews comment help text."""
        help_text = self._get_help_text(["clawnews", "comment"])
        self.assertIn("parent_id", help_text)
        self.assertIn("--text", help_text)

    def test_vote_help(self):
        """Test clawnews vote help text."""
        help_text = self._get_help_text(["clawnews", "vote"])
        self.assertIn("item_id", help_text)

    def test_profile_help(self):
        """Test clawnews profile help text."""
        help_text = self._get_help_text(["clawnews", "profile"])
        self.assertIn("profile", help_text.lower())

    def test_search_help(self):
        """Test clawnews search help text."""
        help_text = self._get_help_text(["clawnews", "search"])
        self.assertIn("query", help_text)
        self.assertIn("--type", help_text)
        self.assertIn("--limit", help_text)


if __name__ == "__main__":
    unittest.main()