---
name: sap-kb
description: >
  The SAP development knowledge base. Use this FIRST whenever you need any SAP,
  ABAP, S/4HANA, BTP, RAP, CDS, Fiori, OData, or SAP-config information — before
  answering from memory or searching the web. Reads a local, citable store of
  ingested SAP PDFs (help.sap.com exports), then falls back in a fixed order to the
  local sap-docs MCP (official SAP doc repos), live help.sap.com, Community, web —
  each tier cited distinctly. Also handles ingesting a newly dropped PDF into the store. Triggers on: SAP, ABAP, S/4HANA, SAP BTP, RAP, CDS, BOPF,
  Fiori, OData, SAPUI5, transaction codes, SAP Notes, "how does SAP ...".
---

# sap-kb — SAP development knowledge base

**KB root:** `{{SAP_KB_ROOT}}`
(the "main folder"). `INDEX.md` there is the master list of explored topics.

This skill has two jobs. Decide which by the request:
- **RETRIEVE** — someone needs SAP info → answer from the store (default).
- **INGEST** — a new `<topic>/` folder with PDF(s) was added → read it fully, build its `reference.json`, rebuild the index.

---

## THE RULES (non-negotiable — apply to both jobs)

1. **Never imagine.** State only what is present on a page you actually read or a
   source you actually fetched. No inference to fill gaps. No "SAP usually…".
2. **Always read complete.** Ingestion reads to the LAST page — never sample.
   Retrieval reads every page the topic's `reference.json` points to for the question.
3. **Always cite, with the source tier visible.** Every SAP claim carries one of:
   - `[kb: <topic> <tag> p<n>]` — this store, using the page's own cite from `reference.json`
     (e.g. `[kb: Application Log (BC-SRV-BAL) oo p25]`; the tag names the source file, so keep
     it — `p25` alone is ambiguous when a topic has several sources). Authoritative, fully read.
   - `[sap-docs: <doc id or URL>]` — the local `sap-docs` MCP's offline corpus (official SAP
     open-source doc repos: ABAP keyword docs, cheat sheets, style guides, RAP samples, UI5,
     CAP, BTP, released-objects list). Authoritative text, but found by search, not read whole.
   - `[sap-help: <URL>]` — a help.sap.com page fetched live (sap-docs `fetch`, or
     `fetch_sap_help.py`). Official, but say which product/version it belongs to.
   - `[community — unverified: <URL>]` — SAP Community / blogs. Never state these as fact.
   - `[web — unverified against official PDF]` — anything else from the web.
4. **Warn on anything unreadable.** If a page won't render, a PDF is encrypted/scanned,
   an image won't open, or the extractor reports failures — say so *visibly* to the user
   and log it. Never silently skip and continue as if it was read.
5. **Gaps → next tier, clearly flagged.** If the store lacks the answer, say so, then go down
   the RETRIEVE ladder. Never blend lower-tier facts in unmarked.
6. **Keep queries generic.** Searches leave the machine (sap-docs online mode, help.sap.com,
   web). Never put customer names, system IDs, hostnames, user names or customer-specific
   object names (Z*/Y* objects of a client) into a query — search for the SAP concept instead.

---

## RETRIEVE

1. Read `{{SAP_KB_ROOT}}\INDEX.json` (machine list; `INDEX.md` is its
   human mirror — same content).
2. Match the question to a topic. If one exists:
   - Open `<topic>/reference.json`. Search its `pages[]` (each has `file_tag`, `page`,
     `keywords`, `summary`, `facts[]` with `cite`), plus `keywords`, `entities` and `gaps`.
     Never load the whole file into context for a big topic — grep/filter it.
   - Read the source text of exactly those pages to confirm the facts:
     - PDF topic: `<topic>/*.pdf` with the `pages` arg (≤20/req); the tag maps to the PDF in
       `sources[]`.
     - Crawled/fetched topic (no PDF): `<topic>/extracted/text/NN_<tag>.md`, the `## PAGE <n>`
       block; its `SOURCE_URL` is in that block and in `reference.json → source_urls`.
   - If a cited diagram matters, open the image from `diagrams[]` (`path`) and read it visually.
   - Answer, citing `[kb: <topic> <tag> p<n>]` per claim (Rule 3). Mention the topic's
     `warnings` when they affect the answer (e.g. version skew between sources).
3. If NO topic matches, or the matched topic marks the sub-question as a gap: **tell the user
   the KB has no coverage for X**, then continue down the ladder:
   a. **`sap-docs` MCP, offline corpus** — first choice for ABAP syntax/statements, ABAP Cloud
      vs Standard differences, RAP/BDL/EML, CDS, released APIs / clean core (`sap_search_objects`,
      `sap_get_object_details`), feature availability by release (`abap_feature_matrix`), UI5,
      Fiori elements, CAP, BTP. Call `search` with `includeOnline: false`, then `fetch` the
      best hits and read them before answering. Use `abapFlavor` (standard vs cloud) to match
      the user's system. Cite `[sap-docs: …]`.
   b. **help.sap.com live** — `search` with `includeOnline: true`, or without sap-docs:
      `python {{SAP_KB_ROOT}}\_tools\fetch_sap_help.py search "<query>"`, then
      read the hit with `fetch_sap_help.py page <url>` (prints the page, writes nothing). For the
      ABAP Keyword Documentation (`/doc/abapdocu_*` URLs, incl. release news `ABENNEWS-*`) use
      `python …\_tools\fetch_keyworddoc.py <url>`. This is the tier for S/4HANA functional/config
      topics (PP, MM, EWM, LO-VC, …), which the offline corpus does not cover. Cite
      `[sap-help: URL]` with product + version. If you reached a page by constructing its URL
      rather than through a search hit, say so.
   c. **SAP Community** (`sap_community_search`) — hints only, `[community — unverified]`.
   d. **Web** — `[web — unverified against official PDF]`.
   When a topic needed tier b–d and will come up again, suggest making it authoritative:
   export the guide's PDF into the KB, or fetch the section with `fetch_sap_help.py` (skill
   `sap-crawl`, HTTP mode) and ingest it.
4. Never answer an SAP question from model memory alone. If no tier yields it, say so plainly.
5. If the `sap-docs` MCP is not connected in this session (no `mcp__sap-docs__*` tools — e.g. the
   server was added after the session started), skip tier a/b-via-MCP and use the `_tools`
   scripts for help.sap.com; mention that sap-docs was unavailable. Note: "which release
   introduced X" questions are answered best by sap-docs `abap_feature_matrix`; without it, try
   the keyword docs' release news (`ABENNEWS-7xx-*`) via `fetch_keyworddoc.py`.

---

## INGEST (a new `<topic>/` folder with one or more PDFs was dropped in)

A topic is a FOLDER that may hold several PDFs (e.g. a guide split into part1/2/3).
The calling session ORCHESTRATES ingestion by fanning out to cheap reader subagents,
so no single context reads hundreds of pages. Steps:

1. **Extract (local Python, no page limit):**
   `python {{SAP_KB_ROOT}}\_tools\extract_pdf.py "<topic_dir>"`
   Writes, under `<topic_dir>/extracted/`:
   - `content.md` — all text combined; `text/NN_<name>.md` — per-file text (chunked reading)
   - `img/IMG<k>.png` — every UNIQUE image (identical images deduped by content hash)
   - `images.json` — manifest `{id, path, w, h, pages[]}`
   If any file reports `ok:false` (encrypted / unreadable) → **STOP and warn the user.**

2. **Read text — one `sap-text-reader` subagent per `text/NN_*.md` file (in parallel).**
   Pass it the absolute file path + a short `file_tag` (`part1`…). It returns JSON:
   per-page `facts` (each cited `"<tag> p<n>"`), `keywords`, `entities`, `gaps`.

3. **Read images — `sap-image-reader` subagent(s) (Haiku), in parallel batches.**
   Pass ONLY substantial images from `images.json` (both dims ≥ 40 px). Tiny/glyph
   images (< 40 px) are inline text icons — **skip them but LOG the count** (never
   silently drop). It returns `{id, type, description, visible_text}` per image.

4. **Assemble `<topic>/reference.json`** (schema: `_tools/reference.schema.json`) by
   merging text-reader pages + image-reader descriptions into `diagrams[]`. Set
   `pages_read`, `ingested_complete`, and `warnings` (unreadable pages/images +
   "N glyph images skipped"). Every fact keeps its page cite. Nothing invented.

5. **Rebuild the index:** `python {{SAP_KB_ROOT}}\_tools\build_index.py`
   (regenerates `INDEX.json` + `INDEX.md` from all `reference.json`; never hand-edit them).

6. **Report to the user:** pages read (e.g. "321/321"), substantial images described,
   glyphs skipped, and every warning. Lead with anything that could not be read.

`reference.json` is the machine artifact other agents consume — see
`_tools/reference.schema.json` for the exact shape.

---

## Alternate ingestion source: help.sap.com without a PDF
help.sap.com is a JS SPA, but its content is served by JSON endpoints that answer plain
HTTP. `_tools/fetch_sap_help.py` (search / toc / fetch) writes the same `extracted/text`
corpus the PDF path produces — whole guide sections in seconds, code samples included.
The `sap-crawl` skill drives it (HTTP mode) and falls back to Chrome only for failed pages
or diagrams. Images are not fetched by the HTTP tool; their count must go into `warnings`.

## Date handling
Use the real current date for `last_ingested` (do not guess). If unknown, ask.

