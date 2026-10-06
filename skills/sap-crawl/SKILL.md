---
name: sap-crawl
description: >
  Find and ingest help.sap.com documentation into the sap-kb store. Give it a TOPIC (a
  subject, not necessarily a URL) and it discovers the relevant help.sap.com pages itself,
  fetches them over plain HTTP through the portal's JSON API (Chrome only as fallback), and
  writes the same machine-first reference.json the KB uses. Use when a topic is NOT already
  covered by a dropped PDF (the PDF path in skill sap-kb is preferred/higher quality).
  Triggers: "find <SAP topic> on help.sap.com", "crawl help.sap.com for <topic>", "add
  <topic> to the KB (no PDF)", "ingest this SAP help page/URL".
---

# sap-crawl — discover + ingest help.sap.com

Input is a **topic** (e.g. "RAP draft handling", "IDoc partner profiles") OR a direct URL.
help.sap.com renders client-side, so WebFetch/curl on a page URL returns an empty shell — but
the SPA loads its content from JSON endpoints (`/http.svc/...`) that answer plain HTTP. This
skill discovers the right pages, fetches them, and writes them into the KB in the SAME format
the sap-kb pipeline consumes.

## HTTP MODE (default — verified 2026-10-06)
Tool: `python {{SAP_KB_ROOT}}\_tools\fetch_sap_help.py`
(same endpoints marianfoo/mcp-sap-docs uses; output verified identical to the Chrome crawl,
incl. code samples).

1. **Find an entry page:** `fetch_sap_help.py search "<topic>" [--product ABAP_PLATFORM_NEW]`
   (portal full-text search; prints title/product/version/url per hit). WebSearch with
   `allowed_domains:["help.sap.com"]` also works. Pick the right product AND version.
2. **See the guide's structure:** `fetch_sap_help.py toc <page_url> [--under "<section title>|<loio>"]`
   — the full TOC of the deliverable comes back in one call; `--under` narrows to a section
   (exact loio > exact title > largest subtree containing the text; other matches are listed).
3. **Confirm scope with the user** (page list + count) — same rule as DISCOVER step 3.
4. **Fetch:** `fetch_sap_help.py fetch "<topic_dir>" --from-toc <page_url> --under "<section>"`
   (or list page URLs explicitly). Writes `extracted/text/01_web.md` (`## PAGE n / SOURCE_URL /
   TITLE` blocks), `extracted/source_urls.json`, `extracted/fetch_log.json`. `--max` caps pages
   (default 200). Exit code 2 = some pages failed → they are marked `[FETCH FAILED]` in the
   corpus; **warn the user**.
5. **Images are not downloaded.** `fetch_log.json → images_not_captured` lists every image
   reference; the corpus marks them `[IMAGE: alt]`. If a diagram matters for the topic, capture
   it with the Chrome procedure (CRAWL step 3) — otherwise log the count in `warnings`.
6. Continue with **CRAWL step 4 (Index)** and **step 5 (Provenance)** — set `warnings` to
   "fetched via help.sap.com JSON API (live), not an official PDF export".

Use the Chrome path below only when HTTP mode fails for a page, or to capture diagrams.

**Chrome path requirements:** the Claude in Chrome extension, with site permission for
help.sap.com (the extension asks on first use). Verified 2026-07-22: WebSearch discovery +
`navigate` + `get_page_text` return real content.

## PREFER PDF FIRST
Most help.sap.com guides have a **"PDF" export button**. If present, that is the better
path: export the PDF, drop it into `sap-kb/<topic>/`, and run the normal sap-kb INGEST
(PyMuPDF text + deduped images + visual reads). Only fall back to crawling when there is no
usable PDF export. Downloading a file needs the user's explicit OK first.

## DISCOVER via browser (fallback) — topic → candidate pages
1. **Search the domain, not the SPA.** The site's own search is JS-only and unreliable to
   drive; instead use `WebSearch` with `allowed_domains:["help.sap.com"]` and the topic (plus
   product context if known, e.g. "ABAP Cloud", "S/4HANA"). This returns real doc URLs.
   - `/docs/...` URLs = SPA guide pages (authoritative narrative — the main target).
   - `/doc/abapdocu_..._htm/...` URLs = ABAP Keyword Documentation (syntax reference — useful
     for language/EML/CDS/BDL questions). Both render in Chrome.
2. **Verify + expand.** `navigate` to the best hit and `get_page_text` (drop anything that
   returns "Page Not Found"). The rendered page includes the guide's **Table of Contents**;
   use `read_page {filter:"interactive"}` to read the ToC link hrefs and expand the topic to
   its sibling/child pages for fuller coverage. Run extra domain-scoped `WebSearch` queries to
   fill gaps.
3. **Confirm scope with the user.** Present the candidate URL list (and rough page count).
   Crawling is multi-step and side-effectful — get a yes on the set before crawling it all.
   Never crawl an entire product tree unprompted.

## Browser setup (once per session)
1. `list_connected_browsers` → confirm the browser with the user (per the required
   selection prompt) → `select_browser`.
2. `tabs_context_mcp {createIfEmpty:true}` to get/create a tab.
If a page returns a permission error, ask the user to click **Allow** on the extension's
prompt for help.sap.com.

## CRAWL procedure via Chrome (fallback; steps 4–5 apply to HTTP mode too)
Let `<topic_dir>` = `{{SAP_KB_ROOT}}\<slug>`.

1. **Use the page list from DISCOVER** (confirmed with the user). Keep it ordered.

2. **Read each page.** For every URL, in order:
   - `navigate` to it, then `get_page_text`.
   - Append to `<topic_dir>/extracted/text/01_<slug>.md` a block:
     ```
     ## PAGE <n>
     SOURCE_URL: <url>
     <rendered text>
     ```
     (page number = crawl order; the SOURCE_URL line makes every fact traceable.)
   - If a page fails to render or returns "Page Not Found" → **log it and warn the user**;
     never invent the content.

3. **Diagrams.** When a page shows a figure (or says "This image is interactive"), capture it:
   screenshot the figure with the `computer` tool (or open the image URL) and save to
   `<topic_dir>/extracted/img/IMG<k>.png`. Record `{id, path, pages:[{file,page}], w, h}` into
   `<topic_dir>/extracted/images.json` (same manifest shape as extract_pdf.py). Interactive
   diagrams: capture the default rendered state and note in the description that it is interactive.
   If you cannot capture a diagram, log it — do not describe from imagination.

4. **Index (reuse the tested pipeline).**
   - Text: run one or more `sap-text-reader` agents over the `text/*.md` file(s). Tell each its
     `file_tag` (e.g. `web`). Facts cite `"<file_tag> p<n>"`; the SOURCE_URL line ties each page
     back to its URL.
   - Images: run `sap-image-reader` (Haiku) over `images.json` substantial images.
   - Assemble: `python {{SAP_KB_ROOT}}\_tools\assemble.py "<topic_dir>"
     --title "<title>" --date <YYYY-MM-DD>` (tolerates topics with no images).
   - Index: `python {{SAP_KB_ROOT}}\_tools\build_index.py`.

5. **Provenance.** In the resulting `reference.json`, add a `source_urls` list mapping page
   number → URL, and set every source's `file` to the guide URL. Crawl-sourced facts are
   authoritative help.sap.com content (not a random web page), but note in `warnings` that the
   topic was crawled (live SPA), not from an official PDF export.

## Keyword Documentation mode (ABENABAP tree — /doc/abapdocu_*_htm/...)
The ABAP Keyword Documentation (root `ABENABAP.html`, `/doc/abapdocu_*_htm/.../ABEN*.html` and
`ABAP*.html`) is a large, useful syntax reference + examples. Unlike the `/docs/` SPA it is
**static HTML** — so DON'T use the browser for it. Verified 2026-07-22:

- **FETCH OVER HTTP — no browser.** Use `python {{SAP_KB_ROOT}}\_tools\fetch_keyworddoc.py <ABEN_url> [...]`
  (or import `parse(url)`), which fetches the static HTML directly and returns
  `{title, paragraphs[], codes[]}`. This is fast, reliable, and — crucially — recovers the FULL
  executable source code, which the browser path CANNOT get (the browser's `get_page_text` misses
  it and the extension's data-leak filter blocks returning the code via `javascript_tool`). The
  code lives in `codeN:"..."` variables in the raw HTML; the tool unescapes it to clean ABAP.
- **DISCOVER** page URLs with `WebSearch allowed_domains:["help.sap.com"]`, then normalize to the
  latest index: `https://help.sap.com/doc/abapdocu_latest_index_htm/latest/en-US/<PAGE>.html`
  (concept pages start `ABEN*`, statement/syntax pages start `ABAP*`, examples end `_ABEXA`).
  Some guessed page names return empty (200 but no content) — drop those.
- **SCOPE IT.** The full tree is thousands of pages — never crawl all of ABENABAP. Pick a bounded
  set for the topic, cap the count, confirm scope with the user, `log()` the cap.
- **Build the corpus** as `extracted/text/*.md` with, per page: `SOURCE_URL`, `TITLE`, the
  description paragraphs, and each code block as a ```abap fenced block. Then text-reader (tell it
  to index facts + `code_refs` but NOT re-dump the code) → assemble. Keep the full code in the
  corpus file; reference.json points to it. Store the page→URL map in `source_urls`.
- Fall back to the browser only if a specific page is NOT static HTML.

## RULES (same as sap-kb, non-negotiable)
- Never imagine. Only record text actually rendered on a page, and images actually captured.
- Read every page in the enumerated list; never sample. Warn visibly about any page/diagram
  that would not load or capture, and log it — never silently skip.
- Cite every fact (page number + SOURCE_URL). 
- Choose the most privacy-preserving option on any cookie/consent banner; do not log in,
  submit forms, or click irreversible controls. Do not download files without the user's OK.

