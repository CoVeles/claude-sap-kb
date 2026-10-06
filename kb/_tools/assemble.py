#!/usr/bin/env python3
"""
Assemble <topic>/reference.json from reader-agent outputs.

Expects, under <topic_dir>/extracted/:
  images.json               (from extract_pdf.py)
  _txtout_*.json            one per text chunk: {file_tag, pages[], keywords[], entities{}, gaps[]}
  _imgout_*.json            one per image batch: [{id, type, description, visible_text}]

Source files are tagged part1..N in sorted order (matching extract_pdf.py). Writes
<topic_dir>/reference.json per _tools/reference.schema.json and prints a summary.

Usage: python assemble.py "<topic_dir>" [--title "Nice Title"] [--date YYYY-MM-DD]
"""
import sys, os, re, glob, json, argparse, datetime


def uniq(seq):
    seen, out = set(), []
    for x in seq:
        k = x.lower() if isinstance(x, str) else json.dumps(x, sort_keys=True)
        if k not in seen:
            seen.add(k); out.append(x)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("topic_dir")
    ap.add_argument("--title", default=None)
    ap.add_argument("--date", default=datetime.date.today().isoformat())
    a = ap.parse_args()

    topic_dir = a.topic_dir
    ex = os.path.join(topic_dir, "extracted")
    folder = os.path.basename(os.path.normpath(topic_dir))

    # canonical file order -> tags (matches extract_pdf.py sorted glob)
    pdfs = [os.path.basename(p) for p in sorted(glob.glob(os.path.join(topic_dir, "*.pdf")))]
    tag_by_file = {f: f"part{i+1}" for i, f in enumerate(pdfs)}

    # ---- text ----
    txt_files = sorted(glob.glob(os.path.join(ex, "_txtout_*.json")))
    if not txt_files:
        sys.exit("no _txtout_*.json found — run the text-reader agents first")
    all_pages, all_keywords, gaps = [], [], []
    ent = {}
    for tf in txt_files:
        t = json.load(open(tf, encoding="utf-8"))
        tag = t.get("file_tag", "part1")
        for p in t.get("pages", []):
            p.setdefault("file_tag", tag)
            all_pages.append(p)
        all_keywords += t.get("keywords", [])
        gaps += t.get("gaps", [])
        for k, v in (t.get("entities", {}) or {}).items():
            ent.setdefault(k, [])
            ent[k] += v or []
    ent = {k: uniq(v) for k, v in ent.items() if v}
    all_keywords, gaps = uniq(all_keywords), uniq(gaps)
    all_pages.sort(key=lambda p: (p.get("file_tag", ""), p.get("page", 0)))

    # sources + coverage
    tags = sorted({p.get("file_tag") for p in all_pages})
    file_by_tag = {v: k for k, v in tag_by_file.items()}
    sources, warnings = [], []
    for tag in tags:
        pgs = [p["page"] for p in all_pages if p.get("file_tag") == tag]
        maxpg = max(pgs) if pgs else 0
        missing = [n for n in range(1, maxpg + 1) if n not in set(pgs)]
        sources.append({"tag": tag, "file": file_by_tag.get(tag, "?"), "pages": maxpg})
        if missing:
            warnings.append(f"{tag}: missing page records for {missing[:25]} (of {maxpg})")

    # ---- images ---- (crawl topics may have none)
    ij = os.path.join(ex, "images.json")
    manifest = json.load(open(ij, encoding="utf-8")) if os.path.isfile(ij) else {"images": []}
    by_id = {i["id"]: i for i in manifest["images"]}
    glyphs = [i for i in manifest["images"] if not (i["w"] >= 40 and i["h"] >= 40)]

    descs = []
    for f in sorted(glob.glob(os.path.join(ex, "_imgout_*.json"))):
        descs += json.load(open(f, encoding="utf-8"))
    descs = uniq(descs) if False else {d["id"]: d for d in descs}  # dedup by id, last wins

    diagrams = []
    for img_id, d in sorted(descs.items(), key=lambda kv: int(re.sub(r"\D", "", kv[0]) or 0)):
        rec = by_id.get(img_id)
        if not rec:
            continue
        cites = uniq([f"{tag_by_file.get(pg['file'], pg['file'])} p{pg['page']}" for pg in rec["pages"]])
        diagrams.append({
            "id": img_id, "path": rec["path"].replace("\\", "/"),
            "type": d.get("type", "other"), "pages": cites,
            "w": rec["w"], "h": rec["h"],
            "description": d.get("description", ""), "visible_text": d.get("visible_text", ""),
        })

    described = set(descs)
    substantial = {i["id"] for i in manifest["images"] if i["w"] >= 40 and i["h"] >= 40}
    undescribed = sorted(substantial - described, key=lambda s: int(re.sub(r"\D", "", s) or 0))
    if undescribed:
        warnings.append(f"{len(undescribed)} substantial images NOT described: {undescribed[:25]}")
    warnings.append(f"{len(glyphs)} tiny/glyph images (<40px) not visually read (inline icons): "
                    f"{[g['id'] for g in glyphs]}")

    ref = {
        "topic_id": folder,
        "topic": a.title or folder,
        "sources": [{"file": f"{s['tag']} = {s['file']}", "tag": s["tag"], "pages": s["pages"]} for s in sources],
        "pages_total": sum(s["pages"] for s in sources),
        "ingested_complete": not any(("missing" in w or "NOT described" in w) for w in warnings),
        "last_ingested": a.date,
        "warnings": warnings,
        "keywords": all_keywords,
        "entities": ent,
        "diagrams": diagrams,
        "pages": all_pages,
        "gaps": gaps,
    }
    out = os.path.join(topic_dir, "reference.json")
    json.dump(ref, open(out, "w", encoding="utf-8"), indent=2, ensure_ascii=False)

    print("pages_total:", ref["pages_total"], "| page_records:", len(all_pages),
          "| diagrams:", len(diagrams), "| substantial:", len(substantial),
          "| glyphs:", len(glyphs))
    print("sources:", [(s["tag"], s["file"], s["pages"]) for s in sources])
    print("keywords:", len(all_keywords), "| entities:", {k: len(v) for k, v in ent.items()})
    print("ingested_complete:", ref["ingested_complete"])
    for w in warnings:
        print("WARN:", w[:130])
    print("wrote", out)


if __name__ == "__main__":
    main()
