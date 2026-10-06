#!/usr/bin/env python3
"""
sap-kb PDF extractor — local, offline, deterministic, no page limit.

Treats a topic FOLDER as one corpus: extracts ALL text (tagged by file + page)
and every embedded raster image from EVERY *.pdf in the folder. Identical images
(same pixels, e.g. an icon repeated 200x) are deduped by content hash and saved
ONCE, so the Haiku image-reader never reads the same picture twice.

Usage:
    python extract_pdf.py "<topic_dir>"

Writes:
    <topic_dir>/extracted/content.md            all text; "# FILE <name>" then "## PAGE n"
    <topic_dir>/extracted/img/IMG<k>.png         each UNIQUE image, once
    <topic_dir>/extracted/images.json            manifest for the image-reader agent
    -> prints a JSON summary to stdout

Rules it enforces (so downstream agents cannot silently skip content):
  * Reads EVERY pdf to its LAST page. No sampling.
  * Flags every page with NO extractable text as "visual read required".
  * Reports encrypted / unreadable PDFs as a per-file failure, never a guess.
"""
import sys
import os
import re
import glob
import json
import hashlib

try:
    import fitz  # PyMuPDF
except Exception as e:  # pragma: no cover
    print(json.dumps({"ok": False, "error": f"PyMuPDF (fitz) not importable: {e}"}))
    sys.exit(2)


def extract_one(pdf_path, img_dir, text_dir, idx, lines, images, order):
    """Extract one PDF into the combined buffer AND its own text file; register unique images."""
    name = os.path.basename(pdf_path)
    warnings = []
    lines.append(f"\n\n\n# FILE {name}\n")
    flines = [f"# {name}\n"]           # per-file text buffer

    def emit(s):
        lines.append(s)
        flines.append(s)

    def finish(summary):
        text_path = os.path.join(text_dir, f"{idx:02d}_{name}.md")
        with open(text_path, "w", encoding="utf-8") as f:
            f.write("\n".join(flines))
        summary["text_file"] = os.path.relpath(text_path, os.path.dirname(text_dir))
        return summary

    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        emit(f"_[CANNOT OPEN {name} — {e}]_")
        return finish({"file": name, "ok": False, "error": f"cannot open: {e}", "pages": 0,
                       "unique_images_added": 0, "empty_text_pages": [],
                       "warnings": [f"{name}: cannot open ({e})"]})

    if doc.needs_pass:
        doc.close()
        emit(f"_[ENCRYPTED {name} — password required, not read]_")
        return finish({"file": name, "ok": False, "error": "encrypted", "pages": 0,
                       "unique_images_added": 0, "empty_text_pages": [],
                       "warnings": [f"{name}: encrypted / password-protected"]})

    n_pages = doc.page_count
    empty_text_pages = []
    seen_xrefs = set()
    added = 0

    for i in range(n_pages):
        page_no = i + 1
        try:
            page = doc.load_page(i)
        except Exception as e:
            warnings.append(f"{name} page {page_no}: failed to load ({e})")
            emit(f"\n## PAGE {page_no}\n\n_[FAILED TO LOAD — {e}]_")
            continue

        text = page.get_text("text").strip()
        emit(f"\n## PAGE {page_no}\n")
        if text:
            emit(text)
        else:
            empty_text_pages.append(page_no)
            emit("_[no extractable text — likely scanned or vector-only; "
                 "any image below MUST be read visually]_")

        for info in page.get_images(full=True):
            xref = info[0]
            if xref in seen_xrefs:
                continue
            seen_xrefs.add(xref)
            try:
                pix = fitz.Pixmap(doc, xref)
                if pix.n - pix.alpha >= 4:  # CMYK etc -> RGB
                    pix = fitz.Pixmap(fitz.csRGB, pix)
                w, h = pix.width, pix.height
                png = pix.tobytes("png")
                pix = None
            except Exception as e:
                warnings.append(f"{name} page {page_no} image (xref {xref}): {e}")
                emit(f"\n_[UNREADABLE IMAGE on page {page_no} — {e}]_")
                continue

            sha = hashlib.sha256(png).hexdigest()[:12]
            rec = images.get(sha)
            if rec is None:                       # new unique image -> save once
                order[0] += 1
                img_id = f"IMG{order[0]}"
                fname = f"{img_id}.png"
                with open(os.path.join(img_dir, fname), "wb") as f:
                    f.write(png)
                rec = {"id": img_id, "path": os.path.join("extracted", "img", fname),
                       "w": w, "h": h, "pages": []}
                images[sha] = rec
                added += 1
            rec["pages"].append({"file": name, "page": page_no})
            emit(f"\n![{rec['id']}]({os.path.join('img', os.path.basename(rec['path']))}) "
                 f"<!-- {name} p{page_no}, {rec['id']} ({rec['w']}x{rec['h']}) -->")

    doc.close()
    if empty_text_pages:
        warnings.append(f"{name}: {len(empty_text_pages)} page(s) had NO extractable text "
                        f"(visual read required): {empty_text_pages[:30]}")
    return finish({"file": name, "ok": True, "pages": n_pages, "unique_images_added": added,
                   "empty_text_pages": empty_text_pages, "warnings": warnings})


def extract(topic_dir):
    pdfs = sorted(glob.glob(os.path.join(topic_dir, "*.pdf")))
    if not pdfs:
        return {"ok": False, "error": f"no *.pdf found in {topic_dir}"}, 2

    out_dir = os.path.join(topic_dir, "extracted")
    img_dir = os.path.join(out_dir, "img")
    text_dir = os.path.join(out_dir, "text")
    os.makedirs(img_dir, exist_ok=True)
    os.makedirs(text_dir, exist_ok=True)

    lines = ["# Extracted corpus", "",
             f"- source files: {[os.path.basename(p) for p in pdfs]}",
             "- `# FILE <name>` then `## PAGE n`; unique images inline as `img/IMG<k>.png`",
             "- per-file text also in `extracted/text/NN_<name>.md` (for chunked reading)"]
    images = {}       # sha -> record
    order = [0]       # mutable counter for IMG ids
    files = [extract_one(p, img_dir, text_dir, i + 1, lines, images, order)
             for i, p in enumerate(pdfs)]

    content_path = os.path.join(out_dir, "content.md")
    with open(content_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    manifest = sorted(images.values(), key=lambda r: int(r["id"][3:]))
    images_json = os.path.join(out_dir, "images.json")
    with open(images_json, "w", encoding="utf-8") as f:
        json.dump({"topic_dir": topic_dir, "unique_images": len(manifest),
                   "images": manifest}, f, indent=2, ensure_ascii=False)

    all_warnings = [w for fr in files for w in fr.get("warnings", [])]
    total_pages = sum(fr.get("pages", 0) for fr in files)
    total_image_hits = sum(len(r["pages"]) for r in manifest)
    any_fail = any(not fr["ok"] for fr in files)

    return {
        "ok": not any_fail,
        "files": files,
        "total_pages": total_pages,
        "unique_images": len(manifest),
        "image_occurrences": total_image_hits,
        "warnings": all_warnings,
        "content_md": content_path,
        "images_json": images_json,
    }, (0 if not any_fail else 1)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: python extract_pdf.py <topic_dir>")
        sys.exit(1)
    result, code = extract(sys.argv[1])
    print(json.dumps(result, indent=2))
    sys.exit(code)
