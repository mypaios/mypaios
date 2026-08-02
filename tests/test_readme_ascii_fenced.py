"""Regression guard for the animated hero banner introduced in the 1.13.51
docs rewrite (superseding issue #1390, which guarded the old plain-text ASCII
banner that this file replaced). The banner is now a <picture> element with
dark/light SVG sources so GitHub renders the theme-correct version instead of
a hand-drawn box-art banner. This pins that the <picture> block stays intact
and that the project name still reads prominently before the reader hits the
Features section.
"""
from pathlib import Path

README = Path(__file__).resolve().parent.parent / "README.md"


def test_readme_has_picture_banner_with_both_themes():
    text = README.read_text(encoding="utf-8")
    assert "<picture>" in text and "</picture>" in text, "hero banner <picture> element is missing"
    assert 'srcset="docs/banner-dark.svg"' in text, "dark-theme banner source is missing"
    assert 'src="docs/banner-light.svg"' in text, "light-theme banner source is missing"
    assert "MyPaiOS" in text.split("<picture>")[1].split("</picture>")[0], (
        "banner alt text should still name the project for accessibility/SEO"
    )


def test_readme_title_appears_before_features():
    text = README.read_text(encoding="utf-8")
    title_pos = text.find("MyPaiOS")
    features_pos = text.find("## Features")
    assert title_pos != -1 and features_pos != -1
    assert title_pos < features_pos, "MyPaiOS should be introduced before the Features section"
