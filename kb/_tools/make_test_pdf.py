#!/usr/bin/env python3
"""
Generate a small, realistic SAP-style PDF to prove the sap-kb pipeline
end-to-end BEFORE a real help.sap.com PDF is dropped in.

It exercises every extraction path:
  - multi-page text  (page tagging)
  - an embedded RASTER diagram  (get_images -> PNG extraction)
  - a page with an image but NO text  (the "visual read required" warning)

Usage: python make_test_pdf.py <topic_dir>   ->  <topic_dir>/source.pdf
"""
import sys
import os
import fitz


def build_diagram_png(path):
    """Draw a crude RAP architecture diagram and rasterize it to PNG."""
    scratch = fitz.open()
    p = scratch.new_page(width=420, height=220)

    def box(x0, y0, x1, y1, fill, label):
        p.draw_rect(fitz.Rect(x0, y0, x1, y1), color=(0, 0, 0), fill=fill, width=1)
        p.insert_text((x0 + 8, y0 + 26), label, fontsize=11, color=(0, 0, 0))

    box(20, 30, 150, 80, (0.80, 0.90, 1.0), "Fiori Elements")
    box(20, 130, 150, 180, (0.85, 0.95, 0.85), "OData V4")
    box(270, 30, 400, 80, (1.0, 0.92, 0.80), "Behavior Defn")
    box(270, 130, 400, 180, (0.95, 0.85, 0.95), "CDS View Entity")

    p.draw_line(fitz.Point(150, 55), fitz.Point(270, 55), color=(0, 0, 0), width=1)
    p.draw_line(fitz.Point(150, 155), fitz.Point(270, 155), color=(0, 0, 0), width=1)
    p.draw_line(fitz.Point(85, 80), fitz.Point(85, 130), color=(0, 0, 0), width=1)
    p.draw_line(fitz.Point(335, 80), fitz.Point(335, 130), color=(0, 0, 0), width=1)
    p.insert_text((165, 50), "consumes", fontsize=8, color=(0.3, 0.3, 0.3))

    pix = p.get_pixmap(matrix=fitz.Matrix(2, 2))
    pix.save(path)
    scratch.close()


def main(topic_dir):
    os.makedirs(topic_dir, exist_ok=True)
    diagram = os.path.join(topic_dir, "_diagram_tmp.png")
    build_diagram_png(diagram)

    doc = fitz.open()

    # Page 1 — intro text
    p1 = doc.new_page()
    p1.insert_text((72, 90), "SAP RESTful Application Programming Model (RAP)",
                   fontsize=15, color=(0, 0, 0))
    p1.insert_textbox(
        fitz.Rect(72, 120, 520, 400),
        "The ABAP RESTful Application Programming Model (RAP) is the standard "
        "programming model for building SAP HANA-optimized, cloud-ready OData "
        "services in SAP S/4HANA and the SAP BTP ABAP environment.\n\n"
        "A RAP business object is defined by four artifacts: a CDS data model, "
        "a behavior definition (BDEF), a behavior implementation (ABAP class), "
        "and a service definition exposed via a service binding as OData V4 or V2.\n\n"
        "Transaction ADT (Eclipse) is the primary development environment; the "
        "relevant tools are grouped under the 'ABAP Development Tools'.",
        fontsize=11, color=(0, 0, 0),
    )

    # Page 2 — text + embedded diagram
    p2 = doc.new_page()
    p2.insert_text((72, 90), "RAP — Runtime Architecture", fontsize=15, color=(0, 0, 0))
    p2.insert_textbox(
        fitz.Rect(72, 120, 520, 230),
        "At runtime a RAP service flows from a Fiori Elements UI through an OData V4 "
        "service binding into the behavior definition, which delegates to the CDS "
        "view entity acting as the transactional data model. Managed and unmanaged "
        "implementation types determine whether RAP or the developer provides the "
        "standard operations (create, update, delete, lock).",
        fontsize=11, color=(0, 0, 0),
    )
    p2.insert_image(fitz.Rect(120, 250, 480, 470), filename=diagram)

    # Page 3 — image only, NO text (triggers "visual read required" warning)
    p3 = doc.new_page()
    p3.insert_image(fitz.Rect(120, 200, 480, 420), filename=diagram)

    out = os.path.join(topic_dir, "source.pdf")
    doc.save(out)
    doc.close()
    os.remove(diagram)
    print(f"wrote {out}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: python make_test_pdf.py <topic_dir>")
        sys.exit(1)
    main(sys.argv[1])
