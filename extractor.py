"""Table extraction from PDFs.

Two detection strategies (via pdfplumber):
- lattice: finds tables drawn with explicit lines (typical of exported reports)
- stream: finds tables from aligned text columns (line-less tables)

"auto" runs both and keeps the best tables per page. Everything is then
cleaned up: cells are stripped, fully-empty rows and columns are dropped.
"""

import io

import pdfplumber

LATTICE_SETTINGS = {"vertical_strategy": "lines", "horizontal_strategy": "lines"}
STREAM_SETTINGS = {"vertical_strategy": "text", "horizontal_strategy": "text"}

# Stream detection needs at least this many cleaned rows to count as a table.
# It keeps wrapped prose (which the text strategy often mistakes for rows)
# out of the results.
MIN_STREAM_ROWS = 3


def clean_table(rows):
    """Strip cells, drop fully-empty rows, then fully-empty columns."""
    if not rows:
        return []
    cleaned = [[(c or "").strip() for c in row] for row in rows]
    cleaned = [row for row in cleaned if any(cell for cell in row)]
    if not cleaned:
        return []
    width = max(len(row) for row in cleaned)
    padded = [row + [""] * (width - len(row)) for row in cleaned]
    keep = [i for i in range(width) if any(row[i] for row in padded)]
    return [[row[i] for i in keep] for row in padded]


def _split_stream_table(table):
    """Split one stream-detected table into real tables.

    The text strategy tiles the whole text region into row bands, so wrapped
    prose lines become abnormally tall bands mixed in with the table rows.
    Tall bands are split points; only groups with at least MIN_STREAM_ROWS
    cleaned rows are kept as tables.
    """
    raw = table.extract()
    heights = [row.bbox[3] - row.bbox[1] for row in table.rows]
    if not heights:
        # A stream-detected table with no rows has no median height to
        # split on; there is nothing to extract from it.
        return []
    median = sorted(heights)[len(heights) // 2]
    groups, current = [], []
    for row, height in zip(raw, heights):
        if current and height > 1.6 * median:
            groups.append(current)
            current = []
        current.append(row)
    if current:
        groups.append(current)
    tables = []
    for group in groups:
        cleaned = clean_table(group)
        if len(cleaned) >= MIN_STREAM_ROWS:
            tables.append(cleaned)
    return tables


def _extract_stream(page):
    """Stream extraction with prose filtering (see _split_stream_table)."""
    tables = []
    for table in page.find_tables(STREAM_SETTINGS):
        for rows in _split_stream_table(table):
            tables.append(rows)
    return tables


def _same_table(a, b):
    if len(a) != len(b):
        return False
    return all(
        len(ra) == len(rb) and all(ca == cb for ca, cb in zip(ra, rb))
        for ra, rb in zip(a, b)
    )


def _rows_equal_modulo_splits(a, b):
    """True when both tables hold the same rows, but one splits cells further.

    Stream detection sometimes chops a narrow column in two ("Pop" -> "P",
    "op") while lattice gets it right. Joining the cells back up exposes
    that the two tables are the same table.
    """
    if len(a) != len(b):
        return False
    return all("".join(ra) == "".join(rb) for ra, rb in zip(a, b))


def _dedupe(tables):
    """Drop duplicate tables, keeping the one found first (lattice wins)."""
    unique = []
    for table in tables:
        dup = False
        for u in unique:
            if table["page"] != u["page"]:
                continue
            if _same_table(table["rows"], u["rows"]) or _rows_equal_modulo_splits(table["rows"], u["rows"]):
                dup = True
                break
        if not dup:
            unique.append(table)
    return unique


def extract_tables(pdf_bytes, method="auto", max_pages=20):
    """Extract tables from PDF bytes.

    Returns (tables, page_count) where tables is a list of dicts:
    {"page": 1-based page number, "index": index on that page,
     "method": "lattice"|"stream", "rows": list of row lists,
     "nrows": int, "ncols": int}.

    Stream detection keeps only tables with 3+ rows (see MIN_STREAM_ROWS);
    tiny line-less tables may be missed. Scanned/image PDFs have no text
    to extract and return nothing.
    """
    if method not in ("auto", "lattice", "stream"):
        raise ValueError("method must be 'auto', 'lattice' or 'stream'")
    if max_pages < 1:
        # pdf.pages[:-5] would silently drop the last five pages, so a bad
        # limit fails loudly instead of returning partial results.
        raise ValueError("max_pages must be at least 1")

    tables = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        page_count = len(pdf.pages)
        pages = pdf.pages[:max_pages]
        for page in pages:
            found = []
            if method in ("auto", "lattice"):
                raw = page.extract_tables(LATTICE_SETTINGS) or []
                for rows in raw:
                    rows = clean_table(rows)
                    if rows:
                        found.append({"method": "lattice", "rows": rows})
            if method in ("auto", "stream"):
                for rows in _extract_stream(page):
                    found.append({"method": "stream", "rows": rows})
            found = _dedupe([{
                "page": page.page_number,
                "index": i,
                "method": t["method"],
                "rows": t["rows"],
                "nrows": len(t["rows"]),
                "ncols": len(t["rows"][0]),
            } for i, t in enumerate(found)])
            for i, table in enumerate(found):
                table["index"] = i
                tables.append(table)
    return tables, page_count


def render_page(pdf_bytes, page_number, resolution=110):
    """Render one PDF page (1-based) to PNG bytes for the side-by-side preview."""
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        if page_number < 1 or page_number > len(pdf.pages):
            raise ValueError(f"page {page_number} out of range (1-{len(pdf.pages)})")
        img = pdf.pages[page_number - 1].to_image(resolution=resolution)
        buf = io.BytesIO()
        img.original.save(buf, format="PNG")
        return buf.getvalue()


def table_to_csv(rows):
    """Render cleaned table rows as a CSV string (all fields quoted)."""
    import csv

    buf = io.StringIO()
    writer = csv.writer(buf, quoting=csv.QUOTE_MINIMAL)
    writer.writerows(rows)
    return buf.getvalue()
