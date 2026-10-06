#!/usr/bin/env python3
"""
Fetch help.sap.com /docs/ pages over plain HTTP (no browser), via the portal's own JSON API.

The /docs/ site is a JS SPA, but the SPA reads its content from JSON endpoints that answer
plain HTTP (same approach as marianfoo/mcp-sap-docs, src/lib/sapHelp.ts):
  1. http.svc/deliverableMetadata  (product, deliverable, topic) -> deliverable id + buildNo + filePath
  2. http.svc/pagecontent          (deliverable id, buildNo, filePath) -> page HTML body + fullToc
  3. http.svc/elasticsearch        full-text search across the portal

Usage:
  python fetch_sap_help.py search "<query>" [--product ABAP_PLATFORM_NEW] [--max 20]
  python fetch_sap_help.py page <page_url>                       (print one page, writes nothing)
  python fetch_sap_help.py toc <page_url> [--under <loio|title text>]
  python fetch_sap_help.py fetch <topic_dir> <page_url> [<page_url> ...] [--tag web]
  python fetch_sap_help.py fetch <topic_dir> --from-toc <page_url> [--under <loio|title>] [--max 200]

`fetch` writes the corpus the sap-kb pipeline consumes (same format as the sap-crawl skill):
  <topic_dir>/extracted/text/01_<tag>.md   blocks of  "## PAGE n / SOURCE_URL: / TITLE:" + text
  <topic_dir>/extracted/source_urls.json   [{page, url, title, loio, version}]
  <topic_dir>/extracted/fetch_log.json     warnings: failed pages, images NOT captured
Pages that fail are logged and reported, never silently skipped. Images are not downloaded:
their references are logged so the caller can decide (screenshot via sap-crawl if they matter).
"""
import sys
import os
import re
import json
import time
import argparse
import html as ihtml
import urllib.request
import urllib.parse
from html.parser import HTMLParser

BASE = "https://help.sap.com"
HEADERS = {"Accept": "application/json", "User-Agent": "sap-kb/fetch_sap_help", "Referer": BASE}


def _get_json(path, params):
    url = f"{BASE}/http.svc/{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=45) as r:
        return json.load(r)


def parse_docs_url(url):
    """https://help.sap.com/docs/<product>/<deliverable>/<topic>.html[?version=..&locale=..]"""
    u = urllib.parse.urlparse(url)
    parts = [p for p in u.path.split("/") if p]
    if len(parts) < 3 or parts[0] != "docs":
        raise ValueError(f"not a help.sap.com/docs/ page URL: {url}")
    q = urllib.parse.parse_qs(u.query)
    topic = parts[3] if len(parts) > 3 else ""
    if topic and not topic.endswith(".html"):
        topic += ".html"
    return {
        "product": parts[1],
        "deliverable": parts[2],
        "topic": topic,
        "version": q.get("version", ["LATEST"])[0],
        "language": q.get("locale", ["en-US"])[0],
    }


def resolve(url):
    """Page URL -> (deliverable meta, page data) or raises."""
    p = parse_docs_url(url)
    meta = _get_json("deliverableMetadata", {
        "product_url": p["product"], "topic_url": p["topic"], "deliverable_url": p["deliverable"],
        "version": p["version"], "language": p["language"],
        "loadlandingpageontopicnotfound": "true", "deliverableInfo": "1",
    })["data"]
    d = meta["deliverable"]
    page = _get_json("pagecontent", {
        "deliverableInfo": "1", "deliverable_id": d["id"], "buildNo": d["buildNo"],
        "file_path": meta.get("filePath") or p["topic"],
    })["data"]
    return p, d, page


class _Text(HTMLParser):
    """HTML fragment -> readable text: headings, paragraphs, lists, pipe tables, fenced code."""
    BLOCK = {"p", "div", "section", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "dt", "dd",
             "br", "table", "ul", "ol", "dl", "figcaption", "caption"}
    SKIP = {"script", "style", "head", "nav", "noscript"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.skip, self.pre, self.cells, self.images = [], 0, 0, None, []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in self.SKIP:
            self.skip += 1
        elif self.skip:
            return
        elif tag == "pre":
            self.pre += 1
            self.out.append("\n```\n")
        elif tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self.out.append("\n" + "#" * min(int(tag[1]) + 1, 6) + " ")
        elif tag == "li":
            self.out.append("\n- ")
        elif tag == "tr":
            self.cells = []
        elif tag in ("td", "th") and self.cells is not None:
            self.cells.append("")
        elif tag == "img":
            self.images.append({"src": a.get("src", ""), "alt": a.get("alt", "") or a.get("title", "")})
            self.out.append(f" [IMAGE: {a.get('alt') or a.get('src', '')}] ")
        elif tag in self.BLOCK:
            self.out.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP:
            self.skip = max(0, self.skip - 1)
        elif self.skip:
            return
        elif tag == "pre":
            self.pre = max(0, self.pre - 1)
            self.out.append("\n```\n")
        elif tag == "tr" and self.cells is not None:
            self.out.append("\n| " + " | ".join(c.strip().replace("\n", " ") for c in self.cells) + " |")
            self.cells = None
        elif tag in self.BLOCK:
            self.out.append("\n")

    def handle_data(self, data):
        if self.skip:
            return
        if self.cells is not None and self.cells:
            self.cells[-1] += data
        elif self.pre:
            self.out.append(data)
        else:
            self.out.append(re.sub(r"\s+", " ", data))

    def text(self):
        t = "".join(self.out)
        t = re.sub(r"[ \t]+\n", "\n", t)
        return re.sub(r"\n{3,}", "\n\n", t).strip()


def html_to_text(body):
    m = re.search(r"<body[^>]*>(.*)</body>", body, re.S | re.I)
    parser = _Text()
    parser.feed(m.group(1) if m else body)
    return parser.text(), parser.images


def walk_toc(nodes, depth=0):
    for n in nodes or []:
        yield depth, n
        yield from walk_toc(n.get("c"), depth + 1)


def _size(n):
    return sum(1 for _ in walk_toc([n]))


def subtree(toc, under):
    """TOC nodes rooted at `under`: exact loio/file match, else exact title, else the largest
    subtree whose title contains it (other candidates are listed on stderr)."""
    if not under:
        return toc
    key = under.lower().removesuffix(".html")
    exact, titled, partial = [], [], []
    for _, n in walk_toc(toc):
        title = (n.get("t") or "").lower()
        if (n.get("u") or "").lower().removesuffix(".html") == key:
            exact.append(n)
        elif title == key:
            titled.append(n)
        elif key in title:
            partial.append(n)
    pool = sorted(exact or titled or partial, key=_size, reverse=True)
    if not pool:
        raise SystemExit(f"--under '{under}' matched no TOC node")
    if len(pool) > 1:
        print(f"--under '{under}': {len(pool)} matches, using '{pool[0].get('t')}' ({_size(pool[0])} nodes); others: "
              + "; ".join(f"{n.get('t')} [{n.get('u')}]" for n in pool[1:8]), file=sys.stderr)
    return [pool[0]]


def page_url(p, file_u, version=None):
    v = version or p["version"]
    q = f"?version={v}&locale={p['language']}" if v and v != "LATEST" else f"?locale={p['language']}"
    return f"{BASE}/docs/{p['product']}/{p['deliverable']}/{file_u}{q}"


def cmd_search(a):
    params = {"transtype": "standard,html,pdf,others", "state": "PRODUCTION", "product": a.product or "",
              "version": "", "q": a.query, "to": str(a.max - 1), "area": "content", "advancedSearch": "0",
              "excludeNotSearchable": "1", "language": "en-US"}
    res = _get_json("elasticsearch", params).get("data", {}).get("results", [])
    for r in res:
        url = r.get("url", "")
        print(json.dumps({"title": r.get("title"), "product": r.get("product"), "version": r.get("version"),
                          "url": url if url.startswith("http") else BASE + url,
                          "snippet": re.sub(r"<[^>]+>", "", r.get("snippet") or "")[:200]}, ensure_ascii=False))


def cmd_page(a):
    """Print one page (title, product/version, URL, text) to stdout — writes nothing."""
    p, d, page = resolve(a.url)
    text, imgs = html_to_text(page.get("body") or "")
    if not text:
        raise SystemExit(f"empty page body: {a.url}")
    print(f"TITLE: {page.get('currentPage', {}).get('t') or ''}")
    print(f"PRODUCT: {d.get('productName')} {d.get('versionName') or d.get('version')}")
    print(f"SOURCE_URL: {a.url}")
    if page.get("isMachineTranslated"):
        print("[NOTE: machine-translated page]")
    if imgs:
        print(f"[{len(imgs)} image(s) referenced, not shown]")
    print()
    print(text)


def cmd_toc(a):
    p, d, page = resolve(a.url)
    nodes = subtree(page["deliverable"].get("fullToc") or [], a.under)
    print(f"# {page['deliverable'].get('title')} — {d.get('productName')} {d.get('versionName')}", file=sys.stderr)
    n = 0
    for depth, node in walk_toc(nodes):
        if node.get("u"):
            n += 1
            print(f"{n:4d} {'  ' * depth}{node.get('t')}  <{page_url(p, node['u'])}>")
    print(f"{n} pages", file=sys.stderr)


def cmd_fetch(a):
    urls = list(a.urls)
    if a.from_toc:
        p, d, page = resolve(a.from_toc)
        for _, node in walk_toc(subtree(page["deliverable"].get("fullToc") or [], a.under)):
            if node.get("u"):
                urls.append(page_url(p, node["u"]))
    if not urls:
        raise SystemExit("no pages: give URLs or --from-toc")
    if len(urls) > a.max:
        raise SystemExit(f"{len(urls)} pages exceeds --max {a.max}; narrow with --under or raise --max")

    out_dir = os.path.join(a.topic_dir, "extracted")
    os.makedirs(os.path.join(out_dir, "text"), exist_ok=True)
    corpus_path = os.path.join(out_dir, "text", f"01_{a.tag}.md")
    pages, failures, images = [], [], []
    with open(corpus_path, "w", encoding="utf-8") as f:
        for i, url in enumerate(urls, 1):
            try:
                p, d, page = resolve(url)
                title = page.get("currentPage", {}).get("t") or ""
                text, imgs = html_to_text(page.get("body") or "")
                if not text:
                    raise ValueError("empty body")
                if page.get("isMachineTranslated"):
                    text = "[NOTE: machine-translated page]\n" + text
                f.write(f"\n## PAGE {i}\nSOURCE_URL: {url}\nTITLE: {title}\n\n{text}\n")
                pages.append({"page": i, "url": url, "title": title,
                              "loio": page.get("currentPage", {}).get("loio"), "version": d.get("version")})
                images += [{"page": i, **im} for im in imgs]
                print(f"[{i}/{len(urls)}] ok   {title}", file=sys.stderr)
            except Exception as e:  # never skip silently: log + report
                failures.append({"page": i, "url": url, "error": str(e)})
                f.write(f"\n## PAGE {i}\nSOURCE_URL: {url}\n[FETCH FAILED: {e}]\n")
                print(f"[{i}/{len(urls)}] FAIL {url}: {e}", file=sys.stderr)
            time.sleep(a.delay)

    with open(os.path.join(out_dir, "source_urls.json"), "w", encoding="utf-8") as f:
        json.dump(pages, f, indent=1, ensure_ascii=False)
    log = {"corpus": corpus_path, "pages_ok": len(pages), "pages_failed": failures,
           "images_not_captured": images,
           "warnings": ([f"{len(failures)} page(s) failed to fetch"] if failures else []) +
                       ([f"{len(images)} image(s) referenced but not captured"] if images else [])}
    with open(os.path.join(out_dir, "fetch_log.json"), "w", encoding="utf-8") as f:
        json.dump(log, f, indent=1, ensure_ascii=False)
    print(json.dumps({k: (v if k != "images_not_captured" else len(v)) for k, v in log.items()}, indent=1))
    if failures:
        sys.exit(2)


def main():
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("search"); s.add_argument("query"); s.add_argument("--product"); s.add_argument("--max", type=int, default=20)
    pg = sub.add_parser("page"); pg.add_argument("url")
    t = sub.add_parser("toc"); t.add_argument("url"); t.add_argument("--under")
    fe = sub.add_parser("fetch"); fe.add_argument("topic_dir"); fe.add_argument("urls", nargs="*")
    fe.add_argument("--from-toc"); fe.add_argument("--under"); fe.add_argument("--tag", default="web")
    fe.add_argument("--max", type=int, default=200); fe.add_argument("--delay", type=float, default=0.3)
    a = ap.parse_args()
    {"search": cmd_search, "page": cmd_page, "toc": cmd_toc, "fetch": cmd_fetch}[a.cmd](a)


if __name__ == "__main__":
    main()
