# -*- coding: utf-8 -*-
"""Logic tests for scripts/teleport.py — transcript parsing and matching.

Run: py -3 -m unittest tests.test_teleport
"""
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import teleport  # noqa: E402


def _write_transcript(root, munged, session_id, cwd, lines):
    d = root / munged
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"{session_id}.jsonl"
    payload = [json.dumps({"cwd": cwd, "type": "user",
                           "message": {"role": "user", "content": line}})
               for line in lines]
    f.write_text("\n".join(payload) + "\n", encoding="utf-8")
    return f


class TestDiscover(unittest.TestCase):
    def test_excludes_kit_root_and_extracts_fields(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write_transcript(root, "C--x-myrepo", "aaa-111", "C:\\x\\myrepo",
                              ["fix the login bug"])
            _write_transcript(root, "C--kit", "bbb-222", str(teleport.KIT_ROOT),
                              ["scan run"])
            found = teleport._discover_in(root)
            ids = [c["session_id"] for c in found]
            self.assertIn("aaa-111", ids)
            self.assertNotIn("bbb-222", ids)
            c = next(x for x in found if x["session_id"] == "aaa-111")
            self.assertEqual(c["repo"], "myrepo")
            self.assertIn("login", c["description"])

    def test_summary_line_beats_user_message(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            f = _write_transcript(root, "C--x-r2", "ccc-333", "C:\\x\\r2",
                                  ["something"])
            with f.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({"type": "summary",
                                     "summary": "Building the parser"}) + "\n")
            found = teleport._discover_in(root)
            c = next(x for x in found if x["session_id"] == "ccc-333")
            self.assertEqual(c["description"], "Building the parser")


class TestMatch(unittest.TestCase):
    CANDS = [
        {"session_id": "1", "repo": "shop-site", "description": "cart bug",
         "cwd": "", "mtime": 2.0, "transcript": ""},
        {"session_id": "2", "repo": "parser", "description": "grammar work",
         "cwd": "", "mtime": 1.0, "transcript": ""},
    ]

    def test_hint_narrows_to_one(self):
        hits = teleport._match("the parser one", self.CANDS)
        self.assertEqual([c["session_id"] for c in hits], ["2"])

    def test_no_hint_returns_all_newest_first(self):
        hits = teleport._match("", self.CANDS)
        self.assertEqual([c["session_id"] for c in hits], ["1", "2"])


class TestRequestState(unittest.TestCase):
    def test_roundtrip_and_ttl(self):
        with tempfile.TemporaryDirectory() as td:
            teleport.STATE_FILE = Path(td) / "teleport.json"
            cand = {"session_id": "s1", "cwd": "C:\\x\\r", "repo": "r",
                    "mtime": 0.0, "description": "", "transcript": ""}
            teleport.write_request(cand, "contact", "1234@s.whatsapp.net")
            st = teleport.read_state()
            self.assertEqual(st["phase"], "requested")
            self.assertEqual(st["channel"], "contact")
            # The conversation's jid rides along: announcements are
            # addressed to it, never to a channel's first chat_jid (the
            # group, on a main install).
            self.assertEqual(st["jid"], "1234@s.whatsapp.net")
            self.assertTrue(teleport.request_fresh(st))
            st["requested_at"] = time.time() - 999
            self.assertFalse(teleport.request_fresh(st))
            teleport.clear_state()
            self.assertIsNone(teleport.read_state())

    def test_jid_defaults_to_empty_not_missing(self):
        """A request written without a jid still carries the key — the
        watcher reads st["jid"] and falls back to the self-chat, so a
        missing key would be a KeyError on an announcement path."""
        with tempfile.TemporaryDirectory() as td:
            teleport.STATE_FILE = Path(td) / "teleport.json"
            cand = {"session_id": "s1", "cwd": "C:\\x\\r", "repo": "r",
                    "mtime": 0.0, "description": "", "transcript": ""}
            teleport.write_request(cand, "main")
            self.assertEqual(teleport.read_state()["jid"], "")


class TestPickerAddressing(unittest.TestCase):
    """The selection polls enumerate the repos open on this machine, so
    they must never be left to a channel's default recipient — on a
    group-configured main install that default is the GROUP."""

    CAND = {"session_id": "s1", "cwd": "C:\\x\\myrepo", "repo": "myrepo",
            "mtime": 0.0, "description": "building the thing",
            "transcript": ""}

    def _request(self, jid, candidates):
        """Run the real request() flow with only the ask-level sends
        stubbed out; returns the jid each picker was handed."""
        seen = {}

        def fake_confirm(candidate, channel, j):
            seen["confirm"] = j
            return teleport.strings.t("tp_continue")

        def fake_pick(cands, channel, j):
            seen["pick"] = j
            return cands[0]

        saved = (teleport.discover, teleport._confirm, teleport._pick)
        with tempfile.TemporaryDirectory() as td:
            teleport.STATE_FILE = Path(td) / "teleport.json"
            teleport.discover = lambda limit=40: list(candidates)
            teleport._confirm, teleport._pick = fake_confirm, fake_pick
            try:
                res = teleport.request("myrepo", "main", jid)
            finally:
                teleport.discover, teleport._confirm, teleport._pick = saved
            return seen, res, teleport.read_state()

    def test_missing_jid_falls_back_to_the_self_chat(self):
        seen, res, st = self._request("", [self.CAND])
        self.assertTrue(res["requested"])
        # One candidate -> the confirm poll. Never "" (the channel default).
        self.assertEqual(seen["confirm"], teleport.CFG["self_jid"])
        self.assertTrue(seen["confirm"])
        self.assertEqual(st["jid"], teleport.CFG["self_jid"])

    def test_explicit_jid_reaches_both_pickers(self):
        other = dict(self.CAND, session_id="s2", repo="myrepo-two")
        seen, res, st = self._request("999@s.whatsapp.net",
                                      [self.CAND, other])
        self.assertTrue(res["requested"])
        # Two hits -> the picker poll, addressed to the conversation.
        self.assertEqual(seen["pick"], "999@s.whatsapp.net")
        self.assertEqual(st["jid"], "999@s.whatsapp.net")


if __name__ == "__main__":
    unittest.main()
