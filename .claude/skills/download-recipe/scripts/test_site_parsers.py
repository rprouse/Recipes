# /// script
# requires-python = ">=3.10"
# dependencies = ["beautifulsoup4", "pytest"]
# ///
"""Unit tests for site_parsers, run offline against hand-written fixtures.

Fixtures are minimal HTML reproducing the exact structures found on
outdooreats.com on 2026-08-10 — inline microdata plus the theme's
`.recipe-digits` block. They are hand-written rather than saved pages so the
tests stay small and state precisely which markup each behaviour depends on.
"""
import site_parsers


GATED_HTML = """
<html><body>
  <h1>BLTA Grain Bowl</h1>
  <div class="mepr-unauthorized">
    <h2>Join the Outdoor Eats Recipe Club</h2>
    <p>Get access to all 300+ recipes.</p>
  </div>
</body></html>
"""


def test_parser_for_resolves_outdooreats():
    assert site_parsers.parser_for("https://outdooreats.com/recipe/hiker-pasta/") is not None


def test_parser_for_ignores_www_prefix():
    assert site_parsers.parser_for("https://www.outdooreats.com/recipe/hiker-pasta/") is not None


def test_parser_for_returns_none_for_other_hosts():
    assert site_parsers.parser_for("https://cooking.nytimes.com/recipes/1234-thing") is None
    assert site_parsers.parser_for("https://www.seriouseats.com/some-recipe") is None


def test_gated_page_reports_gated():
    assert site_parsers._parse_outdooreats(GATED_HTML, {}) == {"gated": True}


if __name__ == "__main__":
    import sys
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
