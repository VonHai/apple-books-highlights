# apple-books-highlights

把你在 **macOS「图书」(Apple Books)** 里画的下划线、高亮和批注,导出成干净的 Markdown 读书笔记 —— 每本一篇,按章节分组,按阅读顺序排列,对 Obsidian 友好。

> 英文说明书见下 · [English below](#english)

## 为什么需要它

你在 Apple Books 里画的下划线和高亮**不会写进 `.epub` 文件**,而是存在 Apple Books 自己的 SQLite 数据库里:

```
~/Library/Containers/com.apple.iBooksX/Data/Documents/
├── AEAnnotation/AEAnnotation_*.sqlite   ← 标注内容(下划线 / 高亮 / 批注)
└── BKLibrary/BKLibrary-*.sqlite         ← 书名 / 作者对照表
```

所以想把划线导出来,只能直接读这两个库。本工具做得很稳妥:

- 把数据库(连同 `-wal` / `-shm` 预写日志)**复制**到临时目录后**只读**查询 —— 既能拿到「图书」还没落盘的最新标注,也不会锁住正在运行的 App。
- 按 `epubcfi` 阅读位置**数值排序**(所以 `/6/2` 排在 `/6/14` 前面,而不是按字符串字典序)。
- 运行时探测 schema:存章节标题的那一列是未文档化的、名字在不同 macOS 版本会变 —— 该列缺失时**优雅跳过章节标题**,而不是直接崩溃。

## 安装

需要 **macOS** 和 **Python 3.8+**(纯标准库,无需 pip 安装任何依赖)。

```bash
# 直接运行
python3 apple_books_highlights.py --list

# 或装成命令
pipx install .          # 或:pip install .
apple-books-highlights --list
```

## 用法

```bash
# 列出所有有标注的书(书名 + 条数)
apple-books-highlights --list

# 导出某本书(按书名片段模糊匹配,不区分大小写)
apple-books-highlights --book "活着"

# 先预览不写文件(打印到屏幕)
apple-books-highlights --book "活着" --stdout

# 导出所有有标注的书,每本一篇 Markdown
apple-books-highlights --all

# 指定输出目录和语言(en | zh)
apple-books-highlights --all --out ~/notes --lang zh
```

| 参数 | 含义 |
|------|------|
| `--list` | 列出所有有标注的书及条数 |
| `--book 书名` | 按书名模糊匹配导出一本 |
| `--asset ID` | 按 asset id 精确导出一本 |
| `--all` | 导出所有有标注的书 |
| `--out 目录` | 输出目录(默认 `./AppleBooksHighlights`) |
| `--lang {en,zh}` | 输出语言(默认 `en`) |
| `--stdout` | 打印到屏幕而不写文件 |

## 输出示例

每本书生成一个带 YAML front-matter 和 Obsidian callout 的 Markdown 文件:

```markdown
---
title: 活着
author: 余华
source: Apple Books (macOS 图书)
exported: 2026-07-30
highlights: 42
tags: [读书笔记, Apple图书, 划线摘录]
---

# 活着 — 划线摘录

> [!info] 导出信息
> 作者: 余华
> 来源:macOS「图书」(Apple Books) 标注数据库
> 导出时间: 2026-07-30 14:12
> 共 42 条 — 下划线 30 / 高亮 12 / 含批注 5

---

## 第一章

> [!quote] 1. 高亮
> 人是为活着本身而活着的,而不是为了活着之外的任何事物而活着。
>
> 💬 **批注**:全书的题眼
```

## 测试

```bash
python3 -m unittest discover -s tests -v
```

测试覆盖纯逻辑(CFI 排序、文件名清洗、schema 列选择、Markdown 渲染),不需要 Apple Books 数据库。

## 说明与限制

- **仅 macOS**:读取本地 Apple Books 数据库,iOS 没有对应路径。
- 全程**只读**你的数据,绝不写入 Apple Books 数据库。
- 标注 schema 是 Apple 私有、未文档化的格式,未来 macOS 更新可能改动。若导出报 schema 错误,欢迎带上你的 macOS 版本提 issue。

## License

[MIT](LICENSE)

---

## English

Export the underlines, highlights and notes you make in the **macOS Books (Apple Books)** app to clean, Obsidian-friendly Markdown — one note per book, grouped by chapter, in reading order.

### Why this exists

Highlights and underlines you make in Apple Books are **not** stored in the `.epub` file. They live in Apple Books' own SQLite databases:

```
~/Library/Containers/com.apple.iBooksX/Data/Documents/
├── AEAnnotation/AEAnnotation_*.sqlite   ← the annotations (underline / highlight / note)
└── BKLibrary/BKLibrary-*.sqlite         ← the book title / author table
```

So the only way to get your highlights out is to read those two databases directly. This tool does that safely:

- It **copies** the databases (with their `-wal` / `-shm` write-ahead logs) into a temp dir and queries them **read-only** — so it sees annotations Books hasn't flushed to disk yet, and never locks the running app.
- It orders annotations by their `epubcfi` reading position (numerically, so `/6/2` comes before `/6/14`).
- It probes the schema at runtime, because the column holding the chapter title is undocumented and its name has changed across macOS versions — if it's missing, chapter headers are skipped instead of crashing.

### Install

Requires **macOS** and **Python 3.8+** (standard library only — no third-party dependencies).

```bash
python3 apple_books_highlights.py --list   # run directly
pipx install .                             # …or install as a command
apple-books-highlights --list
```

### Usage

```bash
apple-books-highlights --list                       # list every annotated book
apple-books-highlights --book "Sapiens"             # fuzzy-match one book by title
apple-books-highlights --book "Sapiens" --stdout    # preview without writing a file
apple-books-highlights --all                        # export every annotated book
apple-books-highlights --all --out ~/notes --lang en
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

### Tests

```bash
python3 -m unittest discover -s tests -v
```

The tests cover the pure logic (CFI ordering, filename sanitising, schema-column selection, Markdown rendering) and need no Apple Books database.

### Notes & limitations

- **macOS only.** It reads local Apple Books databases; there is no iOS equivalent path.
- Reads your data **read-only** and never writes to the Apple Books databases.
- The annotation schema is Apple's private, undocumented format; a future macOS update could change it. If export ever fails with a schema error, please open an issue with your macOS version.

### License

[MIT](LICENSE)
