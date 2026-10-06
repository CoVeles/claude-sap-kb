#!/usr/bin/env python3
"""
Fetch + parse ABAP Keyword Documentation pages over pure HTTP (no browser).

The ABAP Keyword Documentation (help.sap.com/doc/abapdocu_*_htm/.../ABEN*.html) is
STATIC HTML — unlike the /docs/ SPA — so it can be fetched directly and parsed. Each
page's executable source code is stored in `codeN: "..."` JS variables in the raw HTML.

Usage:
    python fetch_keyworddoc.py <ABEN_url> [<ABEN_url> ...]
Prints, per page: title, description paragraphs, and code blocks (as JSON).
Importable: parse(url) -> {"url","title","paragraphs":[...],"codes":[...]}
"""
import sys
import re
import json
import html as ihtml
import urllib.request

BASE = "https://help.sap.com/doc/abapdocu_latest_index_htm/latest/en-US/"


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")


def _extract_codes(h):
    codes = []
    for m in re.finditer(r'code(\d+):\s*"', h):
        j = m.end()
        buf = []
        while j < len(h):
            ch = h[j]
            if ch == "\\":
                buf.append(h[j:j + 2]); j += 2; continue
            if ch == '"':
                break
            buf.append(ch); j += 1
        raw = "".join(buf)
        code = (raw.replace("\\ ", "")      # stray backslash-space continuations
                   .replace("\\n", "\n").replace("\\t", "\t")
                   .replace('\\"', '"').replace("\\\\", "\\"))
        code = "\n".join(line.rstrip() for line in code.splitlines()).strip()
        if code:
            codes.append(code)
    return codes


def _strip(html_fragment):
    txt = re.sub(r"<[^>]+>", "", html_fragment)
    return ihtml.unescape(txt).strip()


def parse(url):
    if not url.startswith("http"):
        url = BASE + url
    h = fetch(url)
    mt = re.search(r"<title>(.*?)</title>", h, re.S)
    title = (_strip(mt.group(1)).replace("| ABAP Keyword Documentation", "").strip()
             if mt else "")
    paras = [p for p in (_strip(x) for x in re.findall(r"<p[^>]*>(.*?)</p>", h, re.S)) if p]
    return {"url": url, "title": title, "paragraphs": paras, "codes": _extract_codes(h)}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python fetch_keyworddoc.py <ABEN_url> [...]"); sys.exit(1)
    out = [parse(u) for u in sys.argv[1:]]
    print(json.dumps(out, indent=2, ensure_ascii=False))
