"""PDF Table Extractor: upload a PDF, preview extracted tables side-by-side
with the original, and download clean CSVs.

Fully local (pdfplumber). Uploaded files live in memory only and are never
written to disk or sent anywhere.
"""

import io
import os
import uuid
import zipfile
from collections import OrderedDict

from flask import (Flask, Response, abort, jsonify, render_template, request,
                   send_file)

from extractor import extract_tables, render_page, table_to_csv

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10 MB uploads

# Resolve relative to this file so the app works from any working directory.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SAMPLE_PATH = os.path.join(BASE_DIR, "samples", "sample_report.pdf")

# file_id -> {"name": str, "data": bytes}. Bounded so the process can't grow
# without limit while the dev server runs.
FILE_STORE = OrderedDict()
MAX_STORED_FILES = 10

PREVIEW_ROWS = 12
PREVIEW_COLS = 8


def store_file(name, data):
    file_id = uuid.uuid4().hex
    FILE_STORE[file_id] = {"name": name, "data": data}
    while len(FILE_STORE) > MAX_STORED_FILES:
        FILE_STORE.popitem(last=False)
    return file_id


def load_sample():
    with open(SAMPLE_PATH, "rb") as f:
        return f.read()


def get_file(file_id):
    entry = FILE_STORE.get(file_id)
    if entry is None:
        abort(404)
    return entry


def preview_table(table):
    rows = table["rows"][:PREVIEW_ROWS]
    truncated_rows = table["nrows"] > PREVIEW_ROWS
    cols = [row[:PREVIEW_COLS] for row in rows]
    truncated_cols = table["ncols"] > PREVIEW_COLS
    return {
        "page": table["page"],
        "index": table["index"],
        "method": table["method"],
        "nrows": table["nrows"],
        "ncols": table["ncols"],
        "header": cols[0],
        "body": cols[1:],
        "truncated_rows": truncated_rows,
        "truncated_cols": truncated_cols,
    }


@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")


@app.route("/extract", methods=["POST"])
def extract():
    method = request.form.get("method", "auto")
    if method not in ("auto", "lattice", "stream"):
        method = "auto"

    if request.form.get("use_sample"):
        filename = "sample_report.pdf"
        pdf_bytes = load_sample()
    else:
        upload = request.files.get("pdf")
        if upload is None or not upload.filename:
            return render_template("index.html", error="Choose a PDF file first."), 400
        filename = upload.filename
        if not filename.lower().endswith(".pdf"):
            return render_template("index.html", error="That file is not a PDF."), 400
        pdf_bytes = upload.read()
    if not pdf_bytes:
        return render_template("index.html", error="The uploaded file is empty."), 400

    try:
        tables, page_count = extract_tables(pdf_bytes, method=method)
    except Exception as exc:
        return render_template("index.html", error=f"Could not read that PDF: {exc}"), 400

    file_id = store_file(filename, pdf_bytes)
    return render_template(
        "results.html",
        filename=filename,
        file_id=file_id,
        method=method,
        page_count=page_count,
        table_count=len(tables),
        tables=[preview_table(t) for t in tables],
        full_tables=tables,
    )


@app.route("/pdf/<file_id>")
def serve_pdf(file_id):
    entry = get_file(file_id)
    return send_file(
        io.BytesIO(entry["data"]),
        mimetype="application/pdf",
        as_attachment=False,
        download_name=entry["name"],
    )


@app.route("/page-img/<file_id>/<int:page>")
def serve_page_image(file_id, page):
    """Server-rendered page preview: works in any browser, no PDF plugin needed."""
    entry = get_file(file_id)
    try:
        png = render_page(entry["data"], page)
    except (ValueError, Exception):
        abort(404)
    return send_file(
        io.BytesIO(png),
        mimetype="image/png",
        as_attachment=False,
        download_name=f"page{page}.png",
    )


@app.route("/csv/<file_id>/<int:table_index>")
def download_csv(file_id, table_index):
    entry = get_file(file_id)
    try:
        tables, _ = extract_tables(entry["data"], method="auto")
        rows = tables[table_index]["rows"]
    except (IndexError, Exception):
        abort(404)
    name = f"{entry['name'].rsplit('.', 1)[0]}_table{table_index + 1}.csv"
    return Response(
        table_to_csv(rows),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={name}"},
    )


@app.route("/csv-all/<file_id>")
def download_all(file_id):
    entry = get_file(file_id)
    try:
        tables, _ = extract_tables(entry["data"], method="auto")
    except Exception:
        abort(404)
    buf = io.BytesIO()
    base = entry["name"].rsplit(".", 1)[0]
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for i, table in enumerate(tables):
            zf.writestr(
                f"{base}_table{i + 1}_p{table['page']}.csv",
                table_to_csv(table["rows"]),
            )
    buf.seek(0)
    return send_file(
        buf,
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"{base}_tables.zip",
    )


@app.route("/api/extract", methods=["POST"])
def api_extract():
    upload = request.files.get("pdf")
    if upload is None or not upload.filename:
        return jsonify({"error": "multipart field 'pdf' is required"}), 400
    if not upload.filename.lower().endswith(".pdf"):
        return jsonify({"error": "file must be a PDF"}), 400
    try:
        tables, page_count = extract_tables(upload.read(), method="auto")
    except Exception as exc:
        return jsonify({"error": f"could not read PDF: {exc}"}), 400
    return jsonify({
        "filename": upload.filename,
        "pages": page_count,
        "table_count": len(tables),
        "tables": [
            {"page": t["page"], "method": t["method"],
             "nrows": t["nrows"], "ncols": t["ncols"], "rows": t["rows"]}
            for t in tables
        ],
    })


if __name__ == "__main__":
    app.run(debug=True)
