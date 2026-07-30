"""Unit tests for the pure-Python parts (no Apple Books database required)."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from apple_books_highlights import (  # noqa: E402
    Annotation,
    Book,
    _cfi_sort_key,
    _pick_chapter_column,
    _safe_filename,
    render_markdown,
)


class CfiSortKeyTests(unittest.TestCase):
    def test_numeric_order_beats_lexicographic(self):
        # "/6/14" must sort AFTER "/6/2", which string comparison would get wrong.
        self.assertLess(_cfi_sort_key("epubcfi(/6/2)"), _cfi_sort_key("epubcfi(/6/14)"))

    def test_empty_cfi_sorts_last(self):
        self.assertGreater(_cfi_sort_key(""), _cfi_sort_key("epubcfi(/6/999)"))


class SafeFilenameTests(unittest.TestCase):
    def test_strips_path_separators_and_illegal_chars(self):
        self.assertEqual(_safe_filename('a/b:c*?"<>|d'), "a_b_c______d")

    def test_blank_falls_back(self):
        self.assertEqual(_safe_filename("   "), "Untitled")

    def test_truncates_long_names(self):
        self.assertEqual(len(_safe_filename("x" * 500)), 120)


class ChapterColumnTests(unittest.TestCase):
    def test_prefers_first_available_candidate(self):
        self.assertEqual(
            _pick_chapter_column({"ZPLLOCATIONRANGESTART", "ZFUTUREPROOFING5"}),
            "ZFUTUREPROOFING5",
        )

    def test_returns_none_when_absent(self):
        self.assertIsNone(_pick_chapter_column({"SOMETHING_ELSE"}))


class RenderMarkdownTests(unittest.TestCase):
    def setUp(self):
        self.book = Book(asset_id="ABC123", title="Sapiens", author="Yuval Noah Harari")
        self.anns = [
            Annotation(text="History began when humans invented gods.", is_underline=False, chapter="Part 1"),
            Annotation(text="A note-worthy line.", note="my thought", is_underline=True, chapter="Part 1"),
        ]

    def test_frontmatter_and_heading(self):
        md = render_markdown(self.book, self.anns, lang="en")
        self.assertTrue(md.startswith("---\n"))
        self.assertIn("title: Sapiens", md)
        self.assertIn("author: Yuval Noah Harari", md)
        self.assertIn("# Sapiens — Highlights", md)

    def test_summary_counts(self):
        md = render_markdown(self.book, self.anns, lang="en")
        self.assertIn("2 annotations — 1 underlines / 1 highlights / 1 with notes", md)

    def test_chapter_header_emitted_once(self):
        md = render_markdown(self.book, self.anns, lang="en")
        self.assertEqual(md.count("## Part 1"), 1)

    def test_note_rendered(self):
        md = render_markdown(self.book, self.anns, lang="en")
        self.assertIn("**Note**: my thought", md)

    def test_zh_labels(self):
        md = render_markdown(self.book, self.anns, lang="zh")
        self.assertIn("划线摘录", md)
        self.assertIn("含批注", md)

    def test_ends_with_single_newline(self):
        md = render_markdown(self.book, self.anns, lang="en")
        self.assertTrue(md.endswith("\n"))
        self.assertFalse(md.endswith("\n\n"))


if __name__ == "__main__":
    unittest.main()
