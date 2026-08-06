# -*- coding: utf-8 -*-
"""Logic tests for scripts/ask.py — validation and answer classification.

Run: py -3 -m unittest tests.test_ask   (from the repo root)
No network, no DB: only the pure functions are tested here; the send/wait
path is covered by the live smoke procedure (plan Task 8).
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import ask  # noqa: E402


class TestPrepareOptions(unittest.TestCase):
    def test_truncates_before_hashing_boundary(self):
        opts = ask._prepare_options(["x" * 150])
        self.assertEqual(len(opts[0]), 100)

    def test_numbers_duplicates_after_truncation(self):
        long_a = "x" * 100 + "-a"
        long_b = "x" * 100 + "-b"  # identical after truncation to 100
        opts = ask._prepare_options([long_a, long_b])
        self.assertNotEqual(opts[0], opts[1])
        self.assertTrue(opts[0].startswith("1) "))
        self.assertTrue(opts[1].startswith("2) "))

    def test_rejects_more_than_twelve(self):
        with self.assertRaises(ValueError):
            ask._prepare_options([str(i) for i in range(13)])

    def test_clamps_selectable_count(self):
        self.assertEqual(ask._clamp_selectable(0, 3), 1)
        self.assertEqual(ask._clamp_selectable(5, 3), 1)
        self.assertEqual(ask._clamp_selectable(2, 3), 2)


class TestClassifyVote(unittest.TestCase):
    # The PREPARED options — what the poll was sent with, so what the bridge
    # hashed and what a vote's content comes back as.
    OPTIONS = ["Yes, continue", "Stop"]

    def test_label_containing_comma_space_round_trips(self):
        # The bridge joins selected labels with ", ", so a naive split would
        # truncate this to "Yes" — a label no caller can match.
        self.assertEqual(ask._classify_vote("Yes, continue", self.OPTIONS),
                         "Yes, continue")

    def test_plain_label(self):
        self.assertEqual(ask._classify_vote("Stop", self.OPTIONS), "Stop")

    def test_multi_select_takes_the_first_label(self):
        self.assertEqual(ask._classify_vote("Stop, Yes, continue", self.OPTIONS),
                         "Stop")

    def test_cleared_vote_is_none(self):
        self.assertIsNone(ask._classify_vote("", self.OPTIONS))


class TestClassifyText(unittest.TestCase):
    OPTIONS = ["Continue", "Pick another", "Cancel"]

    def test_bare_number(self):
        self.assertEqual(ask._classify_text("2", self.OPTIONS, None), "Pick another")

    def test_exact_option_text_case_insensitive(self):
        self.assertEqual(ask._classify_text("cancel", self.OPTIONS, None), "Cancel")

    def test_alias(self):
        aliases = {"Continue": {"yes", "כן"}}
        self.assertEqual(ask._classify_text("כן", self.OPTIONS, aliases), "Continue")

    def test_unrelated_text_is_none(self):
        self.assertIsNone(ask._classify_text("what's for dinner", self.OPTIONS, None))

    def test_out_of_range_number_is_none(self):
        self.assertIsNone(ask._classify_text("7", self.OPTIONS, None))

    def test_alias_beats_positional_number(self):
        # approvals' legacy sets contain "1"/"2"/"0"; aliases must win over
        # positional digits or "2" maps to Deny on a 2-option card.
        aliases = {"Deny": {"0"}, "Always": {"2"}}
        self.assertEqual(ask._classify_text("2", ["A", "Deny"], aliases), "Always")


class TestClassifyReaction(unittest.TestCase):
    def test_reaction_alias_hit(self):
        aliases = {"Allow once": {"👍", "✅"}}
        self.assertEqual(ask._classify_reaction("👍", aliases), "Allow once")

    def test_variation_selector_stripped(self):
        aliases = {"Always": {"❤️"}}
        self.assertEqual(ask._classify_reaction("❤", aliases), "Always")

    def test_no_aliases_means_none(self):
        self.assertIsNone(ask._classify_reaction("👍", None))


class TestCapability(unittest.TestCase):
    def test_missing_file_is_optimistic(self):
        self.assertTrue(ask._poll_capable("contact", surfaces={}))

    def test_explicit_false_blocks(self):
        self.assertFalse(ask._poll_capable("main", surfaces={"main": False}))


if __name__ == "__main__":
    unittest.main()
