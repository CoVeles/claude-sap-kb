# sap-kb — a citable SAP documentation brain for Claude Code

This turns Claude Code into an assistant that answers SAP/ABAP questions **from official SAP
documentation you have ingested**, with a page citation on every claim — instead of answering
from model memory, where SAP details are frequently wrong.

You get the **machinery, not the content**: an empty knowledge base plus the pipeline that
fills it (PDF exports, help.sap.com pages, the ABAP Keyword Documentation). You decide which
SAP topics to add. Optionally it plugs into
[mcp-sap-docs](https://github.com/marianfoo/mcp-sap-docs) as a second, search-based tier.

**What makes it different from a doc-search MCP server:** topics are *read completely* by
reader agents and indexed page by page, so answers carry `[kb: <topic> <tag> p<n>]` citations to a
page that was actually read — and anything the KB doesn't cover is declared a gap and
answered from a lower, explicitly labelled tier, never blended in.

---

## What's in the box

| Piece | Installs to | What it does |
|---|---|---|
| `sap-kb` skill | `~/.claude/skills/sap-kb/` | Answers from the store (with a fixed fallback ladder); ingests dropped PDFs |
| `sap-crawl` skill | `~/.claude/skills/sap-crawl/` | Finds + fetches help.sap.com pages when there's no PDF |
| `sap-text-reader` agent | `~/.claude/agents/` | Cheap worker: reads one text file → page-cited facts |
| `sap-image-reader` agent | `~/.claude/agents/` | Cheap worker (Haiku): describes diagrams |
| `_tools/` | `<KB root>/_tools/` | Extraction, fetching, assembly, indexing (Python) |
| Global rule | `~/.claude/CLAUDE.md` | Makes *every* session reach for the KB first |
| `extras/sap-docs-launch.mjs` | *(optional, manual)* | Starts a local mcp-sap-docs checkout as an MCP server |

---

## Requirements

- **Claude Code** (any recent version).
- **Python 3.9+** on PATH. The installer adds **PyMuPDF** (`pip install -r requirements.txt`) —
  the only third-party dependency. Everything else is stdlib.
- **Optional — Claude in Chrome extension.** Only needed to capture *diagrams* from
  help.sap.com pages, or as a fallback when the HTTP fetch fails. Page text is fetched over
  plain HTTP (see [How help.sap.com is read](#how-helpsapcom-is-read)).
- **Optional — Node.js 20+ and Git Bash** for the local mcp-sap-docs tier.

---

## Install

**Windows (PowerShell):**
```powershell
cd path\to\sap-kb-toolkit
.\install.ps1                          # KB root -> %USERPROFILE%\mcp-servers\sap-kb
# or: .\install.ps1 -KbRoot "D:\sap\kb"
```
If PowerShell blocks the script:
`powershell -ExecutionPolicy Bypass -File .\install.ps1`

**macOS / Linux:**
```bash
cd path/to/sap-kb-toolkit
chmod +x install.sh && ./install.sh    # KB root -> ~/mcp-servers/sap-kb
# or: ./install.sh /path/to/sap-kb
```

The installer substitutes your chosen KB root into both skill files, so nothing is
hardcoded to someone else's machine. Re-running is safe — it backs up anything it would
overwrite with a `.bak-<timestamp>` suffix.

> **Open a new Claude Code session afterwards.** Skills and agents are registered at
> session start; an already-running session won't see them.

---

## Verify it works

**1. The skill is live** — in a new session:
```
/sap-kb what SAP topics are in the KB?
```
Expected: it reports the KB is empty. That's success — it read your (empty) index.

**2. The full pipeline works** — no SAP PDF needed. `make_test_pdf.py` generates a
synthetic SAP-style PDF that deliberately exercises every extraction path (multi-page
text, an embedded raster diagram, and a page with an image but no text, which should
trigger a visible warning):
```powershell
mkdir "<KB root>\test-topic"
python "<KB root>\_tools\make_test_pdf.py" "<KB root>\test-topic"
```
Then in Claude Code: `Ingest the test-topic folder into the SAP KB.`

Expected: it reports pages read, describes the diagram, **warns** about the image-only
page, and writes `test-topic/reference.json`. Then delete the folder and re-run
`python "<KB root>\_tools\build_index.py"` to clear it from the index.

**3. The HTTP fetcher reaches help.sap.com:**
```bash
python "<KB root>/_tools/fetch_sap_help.py" search "application log BAL_LOG_CREATE" --max 3
```

---

## Filling the KB

### A. From a PDF (highest quality — includes diagrams)
1. Open the guide on help.sap.com and use its **PDF export** button.
2. Drop it in `<KB root>\<topic name>\`. Multiple PDFs in one folder = one topic (fine for
   guides split into part 1/2/3).
3. Say: `Ingest the <topic name> folder into the SAP KB.`

It extracts all text and every unique diagram, fans out to the cheap reader agents (so no
single context has to read 400 pages), writes `reference.json`, and updates the index.

### B. From help.sap.com pages (no PDF needed)
```
/sap-crawl add the 'Application Logs' section of the ABAP Platform guide to the KB
```
Give it a *topic*, not necessarily a URL. It finds the guide, shows you the table of contents
and the page count, asks before fetching, then fetches the whole section over HTTP and runs
the same reader pipeline. You can also drive the tool directly:

```bash
python _tools/fetch_sap_help.py search "<query>" [--product ABAP_PLATFORM_NEW]
python _tools/fetch_sap_help.py page <page_url>          # print one page, writes nothing
python _tools/fetch_sap_help.py toc <page_url> --under "<section title or loio>"
python _tools/fetch_sap_help.py fetch "<KB root>/<topic>" --from-toc <page_url> --under "<section>"
```

### C. ABAP Keyword Documentation (syntax + full code examples)
```
/sap-crawl get the EML syntax and examples for MODIFY ENTITIES from the ABAP keyword docs
```
This tree is static HTML, fetched over plain HTTP, and the tool recovers the **complete
executable code samples** embedded in the pages.

### Good first topics
Whatever you actually work in. Ones that pay off fast because model memory is weakest
there: RAP draft handling, CDS annotations, BAPI/IDoc specifics for your modules,
and the config-heavy areas (movement types, output control, table maintenance).

---

## How help.sap.com is read

help.sap.com `/docs/` pages are a JavaScript single-page app, so fetching a page URL returns an
empty shell. The app itself, however, loads its content from JSON endpoints that answer plain
HTTP — the same approach [mcp-sap-docs](https://github.com/marianfoo/mcp-sap-docs) uses:

1. `http.svc/deliverableMetadata` — page URL → deliverable id, build number, file path
2. `http.svc/pagecontent` — the page body **and the guide's complete table of contents**
3. `http.svc/elasticsearch` — portal full-text search

`fetch_sap_help.py` wraps these. A whole guide section arrives in seconds, verbatim, code
samples included. Images are *not* downloaded: every image reference is logged in
`fetch_log.json` and marked `[IMAGE: …]` in the text, so the topic records exactly what was not
captured. Use a PDF export (or the Chrome path in `sap-crawl`) when diagrams matter.

These are undocumented endpoints of a public website; they can change without notice.
`fetch_sap_help.py` sends a descriptive User-Agent and a small delay between pages — keep
it polite, and scope fetches to what you need.

---

## Optional: mcp-sap-docs as the second tier

[mcp-sap-docs](https://github.com/marianfoo/mcp-sap-docs) (Apache-2.0) indexes ~30 official
SAP open-source documentation repos — ABAP keyword docs (Standard and Cloud), ABAP cheat
sheets, style guides, RAP samples, SAPUI5, CAP, BTP, the released-objects list — into a local
SQLite search index, and adds live SAP Help / SAP Community search. It covers a lot of ground
by search; sap-kb covers fewer topics by complete reading. They combine well:

```bash
git clone --depth 1 https://github.com/marianfoo/mcp-sap-docs.git
cd mcp-sap-docs
MCP_VARIANT=sap-docs bash setup.sh        # clones the doc repos (~3 GB) and builds the index
```

The server resolves its index relative to the working directory, and MCP client configs have
no `cwd` field — `extras/sap-docs-launch.mjs` handles that:

```bash
claude mcp add -s user sap-docs -e SAP_DOCS_ROOT=/path/to/mcp-sap-docs -- node /path/to/sap-kb-toolkit/extras/sap-docs-launch.mjs
```

Refresh the index occasionally with `git pull && bash setup.sh` in the checkout. Without the
`sap-docs` server the skill simply skips that tier and says so.

---

## How answers are sourced

The `sap-kb` skill walks a fixed ladder and labels every claim with the tier it came from:

| Tier | Source | Citation |
|---|---|---|
| 1 | This KB (fully read topics) | `[kb: <topic> <tag> p<n>]` |
| 2 | mcp-sap-docs offline corpus (search, `includeOnline: false`) | `[sap-docs: <doc id or URL>]` |
| 3 | help.sap.com, fetched live | `[sap-help: <URL>]` + product/version |
| 4 | SAP Community | `[community — unverified: <URL>]` |
| 5 | Anything else on the web | `[web — unverified against official PDF]` |

When a topic keeps needing tiers 2–5, the skill suggests ingesting it so it becomes tier 1.

**Queries leave your machine** in tiers 3–5 (and in mcp-sap-docs' online mode). The skill
therefore never puts customer names, system IDs, hostnames, user names or customer-specific
object names into a search — it searches for the SAP concept instead.

---

## The rules the skills enforce

1. **Never invent** — only what's on a page actually read.
2. **Read complete** — ingestion goes to the last page, never samples.
3. **Cite everything** — with the source tier visible (table above).
4. **Warn visibly** — encrypted PDFs, unreadable pages, uncaptured diagrams are reported,
   never silently skipped.
5. **Gaps go down the ladder, clearly labelled** — never blended in as if authoritative.
6. **Keep queries generic** — nothing customer-specific in anything sent off the machine.

Rule 4 is the one that makes the whole thing trustworthy: you always know what it *couldn't*
read, so a confident-sounding answer built on a half-extracted PDF can't slip through.

---

## Your KB content and copyright

SAP documentation is copyrighted by SAP SE. This repository contains **only the tooling** —
no SAP documentation, extracted text or generated `reference.json` files. Keep it that way
when you fork: your KB root lives outside this repo, and the `.gitignore` here refuses topic
folders if you ever point the installer at the repo itself. Content from SAP's open-source
documentation repos (e.g. `SAP-docs/*`, mostly CC BY 4.0) carries its own license terms.

---

## Layout after install

```
<KB root>/
  INDEX.json / INDEX.md      master topic list (GENERATED — never hand-edit)
  _tools/
    extract_pdf.py           PDF -> per-file text + deduped images + images.json
    fetch_sap_help.py        help.sap.com search / table of contents / fetch over HTTP
    fetch_keyworddoc.py      ABAP Keyword Doc over HTTP (keeps full code)
    assemble.py              reader outputs -> reference.json
    build_index.py           regenerate INDEX.* from all reference.json
    make_test_pdf.py         synthetic test PDF for verifying the install
    reference.schema.json    the reference.json contract
  <topic>/
    *.pdf                    source documents (PDF topics)
    extracted/               text/, img/, images.json, source_urls.json, fetch_log.json
    reference.json           the machine-first index agents actually read
```

## Troubleshooting

- **Skill doesn't trigger** → you're in a session started before install. Open a new one.
- **`PyMuPDF (fitz) not importable`** → `pip install pymupdf` for the *same* interpreter
  Claude Code invokes as `python`.
- **`fetch_sap_help.py` returns 404 / empty bodies** → help.sap.com changed its endpoints; fall
  back to the Chrome path in `sap-crawl` (and please open an issue).
- **`--under` picked the wrong section** → several sections share a title; pass the section's
  loio (the 32-hex file name in its URL) instead. Other matches are listed on stderr.
- **Index looks stale** → re-run `python <KB root>/_tools/build_index.py`. Never edit
  `INDEX.json` / `INDEX.md` by hand; they're regenerated from the `reference.json` files.

## Related

**[claude-abap-dev](https://github.com/CoVeles/claude-abap-dev)**: a Claude Code plugin with ABAP
development workflows that use this KB for their explanations: ATC fixing in confirmed batches,
a clean-core audit against SAP's released-objects list, a Clean ABAP review with cited rules, and
ABAP Unit runs. It runs on the community ABAP MCP servers (mcp-abap-adt, vibing-steampunk,
abaplint, mcp-sap-docs).

## Acknowledgements

The help.sap.com JSON-endpoint approach follows
[marianfoo/mcp-sap-docs](https://github.com/marianfoo/mcp-sap-docs) (`src/lib/sapHelp.ts`).

## License

MIT — see [LICENSE](LICENSE).
