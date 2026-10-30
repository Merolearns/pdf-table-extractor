"""Generate samples/sample_report.pdf: a two-page demo PDF.

Page 1 carries a ruled (grid-line) table -> exercises the "lattice" strategy.
Page 2 carries a line-less, whitespace-aligned table plus normal prose
-> exercises the "stream" strategy.
"""

import os

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (PageBreak, Paragraph, SimpleDocTemplate, Spacer,
                                Table, TableStyle)

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "sample_report.pdf")


def build():
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph("Quarterly Sales Report — FY 2026", styles["Title"]))
    story.append(Spacer(1, 0.2 * inch))
    story.append(Paragraph(
        "Revenue by region, in thousands of dollars. Figures are unaudited and "
        "for demonstration purposes only.", styles["Normal"]))
    story.append(Spacer(1, 0.25 * inch))

    sales = [
        ["Region", "Q1", "Q2", "Q3", "Q4"],
        ["Northeast", "412", "438", "455", "501"],
        ["Midwest", "388", "401", "419", "460"],
        ["South", "521", "544", "562", "610"],
        ["West", "477", "495", "510", "555"],
        ["International", "305", "342", "371", "418"],
    ]
    t = Table(sales, colWidths=[1.8 * inch] + [0.9 * inch] * 4)
    t.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.75, colors.black),
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(t)
    story.append(PageBreak())

    story.append(Paragraph("Operating Expenses — FY 2026", styles["Title"]))
    story.append(Spacer(1, 0.2 * inch))
    story.append(Paragraph(
        "The table below lists operating expenses by category. Unlike the sales "
        "table, it uses no grid lines; columns are separated by whitespace.", styles["Normal"]))
    story.append(Spacer(1, 0.25 * inch))

    expenses = [
        ["Category", "2024", "2025", "2026"],
        ["Payroll", "1820", "1940", "2085"],
        ["Facilities", "640", "655", "690"],
        ["Marketing", "480", "530", "575"],
        ["Cloud infrastructure", "310", "365", "420"],
        ["Travel", "150", "165", "180"],
    ]
    t2 = Table(expenses, colWidths=[2.4 * inch] + [1.0 * inch] * 3)
    t2.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, 0), 1.25, colors.black),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(t2)
    story.append(Spacer(1, 0.25 * inch))
    story.append(Paragraph(
        "Note: expense figures exclude one-time restructuring costs. Full audit "
        "trail available in the finance system.", styles["Normal"]))

    SimpleDocTemplate(OUT, pagesize=letter).build(story)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    build()
