import io
import os

import pytest
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.platypus import (PageBreak, Paragraph, SimpleDocTemplate, Spacer,
                                Table, TableStyle)
from reportlab.lib.styles import getSampleStyleSheet

from extractor import clean_table, extract_tables, render_page, table_to_csv

SAMPLE = os.path.join(os.path.dirname(__file__), "..", "samples", "sample_report.pdf")


def build_pdf(tables, path):
    """Write a one-page PDF containing the given row lists as ruled tables."""
    story = []
    styles = getSampleStyleSheet()
    story.append(Paragraph("Test document", styles["Title"]))
    story.append(Spacer(1, 0.2 * inch))
    for rows in tables:
        t = Table(rows)
        t.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.75, colors.black),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(t)
        story.append(Spacer(1, 0.2 * inch))
    SimpleDocTemplate(path, pagesize=letter).build(story)


@pytest.fixture()
def two_table_pdf(tmp_path):
    path = str(tmp_path / "two.pdf")
    build_pdf(
        [
            [["Name", "Age"], ["Ana", "30"], ["Bo", "25"]],
            [["City", "Pop"], ["Lima", "9M"], ["Oslo", "0.7M"]],
        ],
        path,
    )
    with open(path, "rb") as f:
        return f.read()


def test_sample_report_extracts_both_tables():
    with open(SAMPLE, "rb") as f:
        data = f.read()
    tables, pages = extract_tables(data)
    assert pages == 2
    assert len(tables) == 2

    sales = tables[0]
    assert sales["page"] == 1 and sales["method"] == "lattice"
    assert sales["nrows"] == 6 and sales["ncols"] == 5
    assert sales["rows"][0] == ["Region", "Q1", "Q2", "Q3", "Q4"]
    assert sales["rows"][1] == ["Northeast", "412", "438", "455", "501"]

    expenses = tables[1]
    assert expenses["page"] == 2 and expenses["method"] == "stream"
    assert expenses["nrows"] == 6 and expenses["ncols"] == 4
    assert expenses["rows"][0] == ["Category", "2024", "2025", "2026"]
    assert expenses["rows"][3] == ["Marketing", "480", "530", "575"]
    # Surrounding prose must not leak into the extracted table.
    assert not any("whitespace" in " ".join(r) for r in expenses["rows"])


def test_two_ruled_tables(two_table_pdf):
    tables, pages = extract_tables(two_table_pdf)
    assert pages == 1
    assert len(tables) == 2
    assert tables[0]["rows"][1] == ["Ana", "30"]
    assert tables[1]["rows"][0] == ["City", "Pop"]


def test_lattice_only_method(two_table_pdf):
    tables, _ = extract_tables(two_table_pdf, method="lattice")
    assert len(tables) == 2
    assert all(t["method"] == "lattice" for t in tables)


def test_bad_method_raises(two_table_pdf):
    with pytest.raises(ValueError):
        extract_tables(two_table_pdf, method="grid")


def test_non_positive_max_pages_raises(two_table_pdf):
    with pytest.raises(ValueError):
        extract_tables(two_table_pdf, max_pages=0)
    with pytest.raises(ValueError):
        extract_tables(two_table_pdf, max_pages=-3)


def test_garbage_bytes_raise(two_table_pdf=None):
    with pytest.raises(Exception):
        extract_tables(b"this is not a pdf at all")


def test_clean_table_strips_and_drops_empties():
    rows = [
        ["  Name ", "Age", ""],
        ["Ana", "30", ""],
        ["", "", ""],
        ["Bo", "", "x"],
    ]
    # The third column survives: it holds "x" in the last row.
    assert clean_table(rows) == [["Name", "Age", ""], ["Ana", "30", ""], ["Bo", "", "x"]]


def test_clean_table_empty():
    assert clean_table([]) == []
    assert clean_table([["", ""], ["", ""]]) == []


def test_render_page_and_bad_page():
    with open(SAMPLE, "rb") as f:
        data = f.read()
    png = render_page(data, 1)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    with pytest.raises(ValueError):
        render_page(data, 99)


def test_table_to_csv_quotes():
    rows = [["Name", "Note"], ["Ana", "loves, commas"]]
    csv_text = table_to_csv(rows)
    assert csv_text.splitlines()[0] == "Name,Note"
    assert '"loves, commas"' in csv_text


def test_max_pages_respected():
    story_pdf = io.BytesIO()
    styles = getSampleStyleSheet()
    story = []
    for i in range(5):
        story.append(Paragraph(f"Page {i}", styles["Title"]))
        story.append(PageBreak())
    SimpleDocTemplate(story_pdf, pagesize=letter).build(story)
    tables, pages = extract_tables(story_pdf.getvalue(), max_pages=2)
    assert pages == 5
    assert tables == []
