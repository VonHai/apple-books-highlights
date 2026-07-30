# apple-books-highlights

Export the underlines, highlights and notes you make in the **macOS Books (Apple Books)** app to clean, Obsidian-friendly Markdown — one note per book, grouped by chapter, in reading order.

> [中文说明见下方](#中文说明)

## Why this exists

Highlights and underlines you make in Apple Books are **not** stored in the `.epub` file. They live in Apple Books' own SQLite databases:

```
~/Library/Containers/com.apple.iBooksX/Data/Documents/
├── AEAnnotation/AEAnnotation_*.sqlite   ← the annotations (underline / highlight / note)
└── BKLibrary/BKLibrary-*.sqlite         ← the book title / author table
```

So the only way to get your highlights out is to read those two databases directly. This tool does that safely:

- It **copies** the databases (with their `-wal` / `-shm` write-ahead logs) into a temp dir and queries them **read-only** — so it sees annotations Books hasn't flushed to disk yet, and never locks the running app.
- It orders annotations by their `epubcfi` reading position (numerically, so `/6/2` comes before `/6/14`).
- It probes the schema at runtime, because the column holding the chapter title is undocumented and its name has changed across macOS versions — if it's missing, chapter headers are simply skipped instead of crashing.

## Install

Requires **macOS** and **Python 3.8+** (only the standard library — no third-party dependencies).

```bash
# Run directly
python3 apple_books_highlights.py --list

# …or install as a command
pipx install .          # or: pip install .
apple-books-highlights --list
```

## Usage

```bash
# List every book that has annotations (title + count)
apple-books-highlights --list

# Export one book (fuzzy, case-insensitive title match)
apple-books-highlights --book "Sapiens"

# Preview to the screen without writing a file
apple-books-highlights --book "Sapiens" --stdout

# Export every annotated book, one Markdown note each
apple-books-highlights --all

# Choose the output directory and language (en | zh)
apple-books-highlights --all --out ~/notes --lang zh
```

| Flag | Meaning |
|------|---------|
| `--list` | List all annotated books and their highlight counts |
| `--book TITLE` | Fuzzy-match one book by title and export it |
| `--asset ID` | Export one book by exact asset id |
| `--all` | Export every annotated book |
| `--out DIR` | Output directory (default `./AppleBooksHighlights`) |
| `--lang {en,zh}` | Output language (default `en`) |
| `--stdout` | Print to the screen instead of writing files |

## Output

Each book becomes a Markdown file with YAML front-matter and Obsidian callout blocks:

```markdown
---
title: Sapiens
author: Yuval Noah Harari
source: Apple Books (macOS)
exported: 2026-07-30
highlights: 42
tags: [reading-notes, apple-books, highlights]
---

# Sapiens — Highlights

> [!info] Export info
> Author: Yuval Noah Harari
> Source: macOS Books (Apple Books) annotation database
> Exported: 2026-07-30 14:12
> 42 annotations — 30 underlines / 12 highlights / 5 with notes

---

## Part One: The Cognitive Revolution

> [!quote] 1. Highlight
> History began when humans invented gods.
>
> 💬 **Note**: the seed of the whole book
```

## Tests

```bash
python3 -m unittest discover -s tests -v
```

The tests cover the pure logic (CFI ordering, filename sanitising, schema-column selection, Markdown rendering) and need no Apple Books database.

## Notes & limitations

- **macOS only.** It reads local Apple Books databases; there is no iOS equivalent path.
- Reads your data **read-only** and never writes to the Apple Books databases.
- The annotation schema is Apple's private, undocumented format; a future macOS update could change it. If export ever fails with a schema error, please open an issue with your macOS version.

## License

[MIT](LICENSE)

---

## 中文说明

把你在 **macOS「图书」(Apple Books)** 里画的下划线、高亮和批注,导出成干净的 Markdown 读书笔记 —— 每本一篇,按章节分组,按阅读顺序排列,对 Obsidian 友好。

**为什么需要它:** 你在「图书」里画的线**不会写进 `.epub` 文件**,而是存在 Apple Books 自己的 SQLite 数据库里,所以必须直接读那两个库。本工具会把数据库连同 `-wal`/`-shm` 预写日志**复制到临时目录后只读查询**——既能拿到还没落盘的最新标注,也不会锁住正在运行的 App。

**用法:**

```bash
python3 apple_books_highlights.py --list            # 列出所有有标注的书
python3 apple_books_highlights.py --book "活着"       # 按书名模糊匹配导出一本
python3 apple_books_highlights.py --all --lang zh    # 导出全部,中文输出
```

仅支持 **macOS**,只需 **Python 3.8+**(纯标准库,无需 pip 安装任何依赖)。
