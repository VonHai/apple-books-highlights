#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Export your Apple Books (macOS) underlines / highlights / notes to Markdown.

Why this exists
---------------
Underlines and highlights you make in the macOS **Books** app are *not* written
into the ``.epub`` file. They live in Apple Books' own SQLite databases:

    ~/Library/Containers/com.apple.iBooksX/Data/Documents/
        AEAnnotation/AEAnnotation_*.sqlite   <- the annotations (underline/highlight/note)
        BKLibrary/BKLibrary-*.sqlite         <- the book title / author table

So to export your highlights you have to read those two databases, not the EPUB.

This tool copies both databases (together with their ``-wal`` / ``-shm``
write-ahead logs) into a temp dir and queries them read-only, so it (a) sees
annotations Books hasn't flushed to disk yet and (b) never locks the running app.

Output is Obsidian-friendly Markdown (callout blocks), grouped by chapter and
ordered by reading position.

Usage
-----
    # List every book that has annotations (title + count)
    apple-books-highlights --list

    # Export one book (fuzzy, case-insensitive title match)
    apple-books-highlights --book "Sapiens"

    # Preview to screen without writing a file
    apple-books-highlights --book "Sapiens" --stdout

    # Export every annotated book, one note per book
    apple-books-highlights --all

    # Choose output dir and output language (en | zh)
    apple-books-highlights --all --out ~/notes --lang zh

Requirements: macOS + Python 3.8+ (``sqlite3`` is in the stdlib). No pip deps.

MIT License. https://github.com/VonHai/apple-books-highlights
"""

from __future__ import annotations

import argparse
import datetime as dt
import glob
import os
import re
import shutil
import sqlite3
import sys
import tempfile
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

HOME = os.path.expanduser("~")
BOOKS_ROOT = os.path.join(HOME, "Library/Containers/com.apple.iBooksX/Data/Documents")
ANNOT_GLOB = os.path.join(BOOKS_ROOT, "AEAnnotation", "AEAnnotation*.sqlite")
LIB_GLOB = os.path.join(BOOKS_ROOT, "BKLibrary", "BKLibrary*.sqlite")

# Apple Books stores timestamps as Core Data / "Cocoa" seconds, whose epoch is
# 2001-01-01 UTC rather than the Unix 1970 epoch.
COCOA_EPOCH = 978307200

# The column that holds the chapter/section title is undocumented and its name
# has drifted across macOS releases. We probe for these in order and use the
# first one that actually exists on this machine (see `_pick_chapter_column`).
CHAPTER_COLUMN_CANDIDATES = ("ZFUTUREPROOFING5", "ZPLLOCATIONRANGESTART")


class BooksExportError(Exception):
    """Raised for any user-facing failure (missing DB, no match, etc.).

    Raising instead of calling ``sys.exit`` deep inside helpers keeps the core
    importable and testable; the CLI boundary (`main`) turns it into exit code 1.
    """


@dataclass
class Book:
    asset_id: str
    title: str
    author: str = ""


@dataclass
class Annotation:
    text: str
    note: str = ""
    is_underline: bool = False
    cfi: str = ""
    chapter: str = ""


@dataclass
class ExportResult:
    book: Book
    count: int
    path: Optional[str] = None  # None when printed to stdout


# --------------------------------------------------------------------------- #
# Database access
# --------------------------------------------------------------------------- #
def _find_one(pattern: str, what: str) -> str:
    """Return the most recently modified file matching *pattern*."""
    hits = sorted(glob.glob(pattern))
    if not hits:
        raise BooksExportError(
            f"Could not find {what}: {pattern}\n"
            "Make sure macOS Books is installed and has been opened at least once."
        )
    return max(hits, key=os.path.getmtime)


def _copy_db(src: str, tmpdir: str) -> str:
    """Copy the .sqlite plus its -wal / -shm siblings so we read the latest data."""
    for suffix in ("", "-wal", "-shm"):
        p = src + suffix
        if os.path.exists(p):
            shutil.copy2(p, os.path.join(tmpdir, os.path.basename(p)))
    return os.path.join(tmpdir, os.path.basename(src))


def _connect(src: str, tmpdir: str) -> sqlite3.Connection:
    con = sqlite3.connect(_copy_db(src, tmpdir))
    con.row_factory = sqlite3.Row
    return con


def _table_columns(con: sqlite3.Connection, table: str) -> set:
    return {row["name"] for row in con.execute(f"PRAGMA table_info({table})")}


def _pick_chapter_column(columns: set) -> Optional[str]:
    """Chapter title lives in a version-dependent column; pick one that exists."""
    for candidate in CHAPTER_COLUMN_CANDIDATES:
        if candidate in columns:
            return candidate
    return None


def load_library(tmpdir: str) -> Dict[str, Book]:
    """Return ``{asset_id: Book}`` for every asset in the library."""
    con = _connect(_find_one(LIB_GLOB, "the BKLibrary database"), tmpdir)
    try:
        books: Dict[str, Book] = {}
        for r in con.execute(
            "SELECT ZASSETID, ZTITLE, ZAUTHOR FROM ZBKLIBRARYASSET "
            "WHERE ZASSETID IS NOT NULL"
        ):
            books[r["ZASSETID"]] = Book(
                asset_id=r["ZASSETID"],
                title=(r["ZTITLE"] or "Untitled"),
                author=(r["ZAUTHOR"] or ""),
            )
        return books
    finally:
        con.close()


def _cfi_sort_key(cfi: str):
    """Turn an ``epubcfi`` string into a numeric tuple so annotations sort by
    reading order, not lexicographically (which would put /6/14 before /6/2)."""
    if not cfi:
        return (10 ** 9,)
    return tuple(int(n) for n in re.findall(r"\d+", cfi)) or (10 ** 9,)


def load_annotations(asset_ids: Sequence[str], tmpdir: str) -> Dict[str, List[Annotation]]:
    """Return ``{asset_id: [Annotation, ...]}`` for the given assets, each list
    ordered by reading position. Assets with no annotations are simply absent."""
    if not asset_ids:
        return {}
    con = _connect(_find_one(ANNOT_GLOB, "the AEAnnotation database"), tmpdir)
    try:
        chapter_col = _pick_chapter_column(_table_columns(con, "ZAEANNOTATION"))
        chapter_select = f"{chapter_col} AS chapter" if chapter_col else "'' AS chapter"
        placeholders = ",".join("?" * len(asset_ids))
        rows = con.execute(
            f"""
            SELECT ZANNOTATIONASSETID       AS asset,
                   ZANNOTATIONSELECTEDTEXT  AS text,
                   ZANNOTATIONNOTE          AS note,
                   ZANNOTATIONISUNDERLINE   AS is_underline,
                   ZANNOTATIONLOCATION      AS cfi,
                   {chapter_select}
            FROM ZAEANNOTATION
            WHERE ZANNOTATIONASSETID IN ({placeholders})
              AND ZANNOTATIONDELETED = 0
              AND ZANNOTATIONSELECTEDTEXT IS NOT NULL
              AND TRIM(ZANNOTATIONSELECTEDTEXT) <> ''
            """,
            list(asset_ids),
        ).fetchall()
    except sqlite3.OperationalError as exc:
        raise BooksExportError(
            "Failed to read the annotation database; the Apple Books schema on "
            f"this macOS version may be unsupported.\n  sqlite3: {exc}"
        ) from exc
    finally:
        con.close()

    by_book: Dict[str, List[Annotation]] = {}
    for r in rows:
        by_book.setdefault(r["asset"], []).append(
            Annotation(
                text=r["text"],
                note=(r["note"] or ""),
                is_underline=bool(r["is_underline"]),
                cfi=(r["cfi"] or ""),
                chapter=(r["chapter"] or "").strip(),
            )
        )
    for anns in by_book.values():
        anns.sort(key=lambda a: _cfi_sort_key(a.cfi))
    return by_book


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #
LABELS = {
    "en": {
        "source": "Apple Books (macOS)",
        "tags": "[reading-notes, apple-books, highlights]",
        "heading_suffix": "Highlights",
        "info": "Export info",
        "author": "Author",
        "source_line": "Source: macOS Books (Apple Books) annotation database",
        "exported": "Exported",
        "summary": "{n} annotations — {u} underlines / {h} highlights / {c} with notes",
        "underline": "Underline",
        "highlight": "Highlight",
        "note": "Note",
    },
    "zh": {
        "source": "Apple Books (macOS 图书)",
        "tags": "[读书笔记, Apple图书, 划线摘录]",
        "heading_suffix": "划线摘录",
        "info": "导出信息",
        "author": "作者",
        "source_line": "来源：macOS「图书」(Apple Books) 标注数据库",
        "exported": "导出时间",
        "summary": "共 {n} 条 — 下划线 {u} / 高亮 {h} / 含批注 {c}",
        "underline": "下划线",
        "highlight": "高亮",
        "note": "批注",
    },
}


def render_markdown(book: Book, annotations: List[Annotation], lang: str = "en") -> str:
    """Render one book's annotations as Obsidian-flavoured Markdown."""
    t = LABELS.get(lang, LABELS["en"])
    n_under = sum(1 for a in annotations if a.is_underline)
    n_high = len(annotations) - n_under
    n_note = sum(1 for a in annotations if a.note.strip())
    today = dt.date.today().isoformat()
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M")

    out: List[str] = ["---", f"title: {book.title}"]
    if book.author:
        out.append(f"author: {book.author}")
    out += [
        f"source: {t['source']}",
        f"exported: {today}",
        f"highlights: {len(annotations)}",
        f"tags: {t['tags']}",
        "---",
        "",
        f"# {book.title} — {t['heading_suffix']}",
        "",
        f"> [!info] {t['info']}",
    ]
    if book.author:
        out.append(f"> {t['author']}: {book.author}")
    out += [
        f"> {t['source_line']}",
        f"> {t['exported']}: {now}",
        "> " + t["summary"].format(n=len(annotations), u=n_under, h=n_high, c=n_note),
        "",
        "---",
        "",
    ]

    last_chapter = None
    for i, a in enumerate(annotations, 1):
        if a.chapter and a.chapter != last_chapter:
            out += [f"## {a.chapter}", ""]
            last_chapter = a.chapter

        # Collapse blank lines inside a multi-line selection so the quote block
        # stays a single tidy callout.
        text = re.sub(r"\n{2,}", "\n> \n> ", a.text.strip()).replace("\n", "\n> ")
        kind = t["underline"] if a.is_underline else t["highlight"]
        out += [f"> [!quote] {i}. {kind}", f"> {text}"]
        if a.note.strip():
            out += ["> ", f"> \U0001f4ac **{t['note']}**: {a.note.strip().replace(chr(10), chr(10) + '> ')}"]
        out.append("")

    return "\n".join(out).rstrip() + "\n"


# --------------------------------------------------------------------------- #
# Output
# --------------------------------------------------------------------------- #
def _safe_filename(name: str) -> str:
    name = re.sub(r'[\\/:*?"<>|]', "_", name).strip()
    return name[:120] or "Untitled"


def _unique_path(out_dir: str, book: Book) -> str:
    """Pick a path that won't clobber a same-titled book already exported."""
    base = _safe_filename(book.title)
    path = os.path.join(out_dir, base + ".md")
    if os.path.exists(path):
        # Disambiguate with a short slice of the asset id rather than overwrite.
        path = os.path.join(out_dir, f"{base} ({book.asset_id[:8]}).md")
    return path


def export_book(
    book: Book, annotations: List[Annotation], out_dir: str, to_stdout: bool, lang: str
) -> ExportResult:
    md = render_markdown(book, annotations, lang)
    if to_stdout:
        print(md)
        return ExportResult(book=book, count=len(annotations), path=None)
    os.makedirs(out_dir, exist_ok=True)
    path = _unique_path(out_dir, book)
    with open(path, "w", encoding="utf-8") as f:
        f.write(md)
    return ExportResult(book=book, count=len(annotations), path=path)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _resolve_targets(args, library: Dict[str, Book], tmpdir: str) -> List[str]:
    """Turn the CLI selector (--book / --asset / --all) into a list of asset ids
    that actually have annotations, loading only what's needed."""
    if args.asset:
        candidates = [args.asset] if args.asset in library else []
    elif args.book:
        kw = args.book.lower()
        candidates = [aid for aid, b in library.items() if kw in b.title.lower()]
    else:  # --all
        candidates = list(library.keys())

    annotated = set(load_annotations(candidates, tmpdir))

    if args.asset and args.asset not in annotated:
        raise BooksExportError(f"asset id {args.asset} has no annotations or does not exist.")
    if args.book:
        matches = [aid for aid in candidates if aid in annotated]
        if not matches:
            raise BooksExportError(
                f'No annotated book matches "{args.book}". Try --list to see what is available.'
            )
        if len(matches) > 1:
            names = "\n".join("  - " + library[aid].title for aid in matches)
            raise BooksExportError(
                f'"{args.book}" matched {len(matches)} books, please be more specific:\n{names}'
            )
        return matches
    return [aid for aid in candidates if aid in annotated]


def cmd_list(library: Dict[str, Book], tmpdir: str) -> None:
    annots = load_annotations(list(library.keys()), tmpdir)
    rows = sorted(
        ((len(v), library[aid].title, library[aid].author) for aid, v in annots.items()),
        reverse=True,
    )
    if not rows:
        print("No underlines / highlights found in Apple Books yet.")
        return
    print(f"{len(rows)} book(s) with annotations:\n")
    print(f"{'count':>5}  title")
    print("-" * 50)
    for cnt, title, author in rows:
        print(f"{cnt:>5}  {title}{('  — ' + author) if author else ''}")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="apple-books-highlights",
        description="Export macOS Apple Books underlines / highlights / notes to Markdown.",
    )
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--list", action="store_true", help="list every annotated book")
    g.add_argument("--book", metavar="TITLE", help="fuzzy-match one book by title and export it")
    g.add_argument("--asset", metavar="ID", help="export one book by exact asset id")
    g.add_argument("--all", action="store_true", help="export every annotated book")
    ap.add_argument(
        "--out",
        default=os.path.join(os.getcwd(), "AppleBooksHighlights"),
        help="output directory (default: ./AppleBooksHighlights)",
    )
    ap.add_argument("--lang", choices=("en", "zh"), default="en", help="output language (default: en)")
    ap.add_argument("--stdout", action="store_true", help="print to screen instead of writing a file")
    return ap


def run(args) -> int:
    if sys.platform != "darwin":
        raise BooksExportError("This tool only runs on macOS (it reads Apple Books' local databases).")

    with tempfile.TemporaryDirectory(prefix="abh_") as tmpdir:
        library = load_library(tmpdir)

        if args.list:
            cmd_list(library, tmpdir)
            return 0

        targets = _resolve_targets(args, library, tmpdir)
        if not targets:
            print("Nothing to export.")
            return 0

        annots = load_annotations(targets, tmpdir)
        written = 0
        for aid in targets:
            result = export_book(library[aid], annots[aid], args.out, args.stdout, args.lang)
            if result.path:
                written += 1
                print(f"✓ {result.book.title}: {result.count} → {result.path}")
        if written and not args.stdout:
            print(f"\nDone. Exported {written} book(s).")
        return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return run(args)
    except BooksExportError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
