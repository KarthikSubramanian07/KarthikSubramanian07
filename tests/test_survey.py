#!/usr/bin/env python3
"""Minimal unit tests for survey.py helpers (no live network)."""

from __future__ import annotations

import datetime
import os
import sys
import tempfile
import unittest
from unittest import mock

from lxml import etree

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import survey  # noqa: E402


class SurveyHelpersTest(unittest.TestCase):
    def test_format_plural(self):
        self.assertEqual(survey.format_plural(1), "")
        self.assertEqual(survey.format_plural(0), "s")
        self.assertEqual(survey.format_plural(2), "s")

    def test_format_number(self):
        self.assertEqual(survey.format_number(1266), "1,266")
        self.assertEqual(survey.format_number(0), "0")

    def test_daily_readme_shape(self):
        birthday = datetime.datetime(2007, 6, 19)
        text = survey.daily_readme(birthday)
        self.assertRegex(text, r"^\d+ years?, \d+ months?, \d+ days?$")

    def test_require_access_token_exits_when_missing(self):
        with mock.patch.object(survey, "ACCESS_TOKEN", ""):
            with self.assertRaises(SystemExit) as ctx:
                survey.require_access_token()
            self.assertIn("ACCESS_TOKEN", str(ctx.exception))

    def test_find_and_replace_escapes_on_write(self):
        svg = (
            "<svg xmlns='http://www.w3.org/2000/svg'>"
            "<text id='weather_data'>old</text>"
            "</svg>"
        )
        root = etree.fromstring(svg.encode("utf-8"))
        survey.find_and_replace(root, "weather_data", "54°F · clear & sunny <ok>")
        with tempfile.NamedTemporaryFile(suffix=".svg", delete=False) as tmp:
            path = tmp.name
        try:
            etree.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)
            with open(path, "rb") as fh:
                raw = fh.read().decode("utf-8")
            self.assertIn("&amp;", raw)
            self.assertIn("&lt;ok&gt;", raw)
            self.assertNotIn("clear & sunny", raw)
        finally:
            os.unlink(path)

    def test_wmo_unknown_fallback(self):
        emoji, desc = survey.WMO_CODES.get(12345, ("🛰️", "unknown"))
        self.assertEqual(desc, "unknown")


if __name__ == "__main__":
    unittest.main()
