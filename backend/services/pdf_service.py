"""
PDF generation service — converts markdown text to a professional PDF.
Uses ReportLab for rendering with cover page, page numbers, and clickable links.
"""

import io
import logging
import os
import re
from datetime import datetime
from typing import Tuple, Union

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, PageBreak,
    HRFlowable, ListFlowable, ListItem, Table, TableStyle,
)
from reportlab.lib.enums import TA_LEFT, TA_JUSTIFY, TA_CENTER, TA_RIGHT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

logger = logging.getLogger(__name__)

# ── Unicode font registration ────────────────────────────────────────────────
# Register a TTF font for full Unicode support (subscripts, CJK, symbols).
# Falls back to built-in Helvetica if no TTF found.

_FONT_FAMILY = "Helvetica"          # default fallback
_FONT_FAMILY_BOLD = "Helvetica-Bold"
_FONT_FAMILY_ITALIC = "Helvetica-Oblique"

_TTF_CANDIDATES = [
    # Windows
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/arialbd.ttf",    # bold
    "C:/Windows/Fonts/ariali.ttf",     # italic
    # Linux
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf",
    # macOS
    "/Library/Fonts/Arial.ttf",
]


def _register_unicode_fonts():
    """Try to register a TTF font family. Returns (normal, bold, italic) names."""
    global _FONT_FAMILY, _FONT_FAMILY_BOLD, _FONT_FAMILY_ITALIC
    # Pair: (candidate_path, registration_name)
    registrations = [
        ("C:/Windows/Fonts/arial.ttf",    "Arial"),
        ("C:/Windows/Fonts/arialbd.ttf",  "Arial-Bold"),
        ("C:/Windows/Fonts/ariali.ttf",   "Arial-Italic"),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",         "DejaVu"),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",    "DejaVu-Bold"),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf", "DejaVu-Italic"),
    ]
    registered = {}
    for path, name in registrations:
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont(name, path))
                registered[name] = True
            except Exception:
                pass

    if "Arial" in registered:
        _FONT_FAMILY = "Arial"
        _FONT_FAMILY_BOLD = registered.get("Arial-Bold") and "Arial-Bold" or "Arial"
        _FONT_FAMILY_ITALIC = registered.get("Arial-Italic") and "Arial-Italic" or "Arial"
        logger.info("PDF: registered Arial TTF (full Unicode support)")
    elif "DejaVu" in registered:
        _FONT_FAMILY = "DejaVu"
        _FONT_FAMILY_BOLD = registered.get("DejaVu-Bold") and "DejaVu-Bold" or "DejaVu"
        _FONT_FAMILY_ITALIC = registered.get("DejaVu-Italic") and "DejaVu-Italic" or "DejaVu"
        logger.info("PDF: registered DejaVu TTF (full Unicode support)")
    else:
        logger.warning("PDF: no TTF fonts found, using Helvetica (limited Unicode)")


_register_unicode_fonts()


# ── Unicode text normalisation ───────────────────────────────────────────────
# Fallback substitutions for when the font lacks certain glyphs.

_UNICODE_SUBS = {
    "\u2082": "2",    # ₂ subscript two  (CO₂ → CO2)
    "\u2083": "3",    # ₃ subscript three
    "\u00b2": "2",    # ² superscript two (m² → m2) — if font lacks it
    "\u00b3": "3",    # ³ superscript three
    "\u2019": "'",    # right single quote
    "\u2018": "'",    # left single quote
    "\u201c": '"',    # left double quote
    "\u201d": '"',    # right double quote
    "\u2013": "-",    # en dash
    "\u2014": "-",    # em dash
    "\u2026": "...",  # ellipsis
    "\u00a0": " ",    # non-breaking space
}


def _sanitize_for_pdf(text: str) -> str:
    """Replace Unicode chars the registered font may not support."""
    if _FONT_FAMILY != "Helvetica":
        # TTF fonts handle most Unicode; only fix truly exotic chars
        return text
    for char, replacement in _UNICODE_SUBS.items():
        text = text.replace(char, replacement)
    return text


# ── Brand colours ────────────────────────────────────────────────────────────

_BRAND_DARK    = colors.HexColor("#0f1923")
_BRAND_ACCENT  = colors.HexColor("#d4a843")
_BRAND_TEXT    = colors.HexColor("#1a1a2e")
_BRAND_MUTED   = colors.HexColor("#666666")
_BRAND_LIGHT   = colors.HexColor("#f5f5f5")
_BRAND_LINK    = colors.HexColor("#1a6fb5")


# ── Styles ────────────────────────────────────────────────────────────────────

def _build_styles():
    base = getSampleStyleSheet()

    styles = {
        "cover_title": ParagraphStyle(
            "CoverTitle", parent=base["Title"],
            fontName=_FONT_FAMILY_BOLD,
            fontSize=28, leading=34, spaceAfter=8,
            textColor=_BRAND_DARK, alignment=TA_LEFT,
        ),
        "cover_subtitle": ParagraphStyle(
            "CoverSubtitle", parent=base["Normal"],
            fontName=_FONT_FAMILY,
            fontSize=12, leading=16, spaceAfter=4,
            textColor=_BRAND_MUTED, alignment=TA_LEFT,
        ),
        "cover_meta": ParagraphStyle(
            "CoverMeta", parent=base["Normal"],
            fontName=_FONT_FAMILY,
            fontSize=10, leading=14, spaceAfter=2,
            textColor=_BRAND_MUTED, alignment=TA_LEFT,
        ),
        "h1": ParagraphStyle(
            "H1", parent=base["Heading1"],
            fontName=_FONT_FAMILY_BOLD,
            fontSize=20, spaceAfter=12, spaceBefore=6,
            textColor=_BRAND_DARK,
        ),
        "h2": ParagraphStyle(
            "H2", parent=base["Heading2"],
            fontName=_FONT_FAMILY_BOLD,
            fontSize=15, spaceAfter=8, spaceBefore=14,
            textColor=_BRAND_DARK,
            borderPad=4,
        ),
        "h3": ParagraphStyle(
            "H3", parent=base["Heading3"],
            fontName=_FONT_FAMILY_BOLD,
            fontSize=12, spaceAfter=6, spaceBefore=8,
            textColor=colors.HexColor("#0f3460"),
        ),
        "body": ParagraphStyle(
            "Body", parent=base["Normal"],
            fontName=_FONT_FAMILY,
            fontSize=10, leading=15, spaceAfter=6,
            alignment=TA_JUSTIFY,
        ),
        "bullet": ParagraphStyle(
            "Bullet", parent=base["Normal"],
            fontName=_FONT_FAMILY,
            fontSize=10, leading=14, spaceAfter=3,
            leftIndent=12,
        ),
        "ref": ParagraphStyle(
            "Ref", parent=base["Normal"],
            fontName=_FONT_FAMILY,
            fontSize=8, leading=11, spaceAfter=2,
            textColor=_BRAND_MUTED,
        ),
    }
    return styles


# ── Page template callbacks ──────────────────────────────────────────────────

def _header_footer(canvas, doc):
    """Draw page number footer and thin accent line at top."""
    canvas.saveState()
    width, height = A4

    # Top accent line
    canvas.setStrokeColor(_BRAND_ACCENT)
    canvas.setLineWidth(1.5)
    canvas.line(2.5 * cm, height - 1.8 * cm, width - 2.5 * cm, height - 1.8 * cm)

    # Footer: page number on the right, branding on the left
    canvas.setFont(_FONT_FAMILY, 8)
    canvas.setFillColor(_BRAND_MUTED)
    canvas.drawString(2.5 * cm, 1.5 * cm, "Competitive Intelligence Report")
    canvas.drawRightString(width - 2.5 * cm, 1.5 * cm, f"Page {doc.page}")

    # Bottom accent line
    canvas.setStrokeColor(_BRAND_ACCENT)
    canvas.setLineWidth(0.5)
    canvas.line(2.5 * cm, 1.9 * cm, width - 2.5 * cm, 1.9 * cm)

    canvas.restoreState()


# ── Converter ─────────────────────────────────────────────────────────────────

class PDFService:
    def generate_pdf_bytes(
        self, markdown_text: str, company_name: str
    ) -> Tuple[bool, Union[bytes, str]]:
        """
        Returns (True, pdf_bytes) on success, (False, error_message) on failure.
        """
        try:
            buf = io.BytesIO()
            doc = SimpleDocTemplate(
                buf,
                pagesize=A4,
                leftMargin=2.5 * cm,
                rightMargin=2.5 * cm,
                topMargin=2.5 * cm,
                bottomMargin=2.5 * cm,
            )
            styles = _build_styles()
            story  = self._build_cover(company_name, markdown_text, styles)
            story.append(PageBreak())
            story += self._parse_markdown(markdown_text, styles)
            doc.build(story, onFirstPage=lambda c, d: None, onLaterPages=_header_footer)
            return True, buf.getvalue()
        except Exception as exc:
            return False, str(exc)

    # ── Cover page ────────────────────────────────────────────────────────────

    def _build_cover(self, company_name: str, markdown_text: str, styles: dict) -> list:
        """Generate a professional cover page."""
        story = []
        story.append(Spacer(1, 4 * cm))

        # Accent bar
        story.append(HRFlowable(
            width="30%", thickness=3, color=_BRAND_ACCENT,
            spaceAfter=20, hAlign="LEFT",
        ))

        # Title
        story.append(Paragraph(
            f"{self._escape(company_name)}",
            styles["cover_title"],
        ))
        story.append(Paragraph(
            "Competitive Intelligence Report",
            styles["cover_subtitle"],
        ))
        story.append(Spacer(1, 1.5 * cm))

        # Extract metadata from markdown
        date_match = re.search(r"\*\*Date\*?\*?:?\s*(\d{4}-\d{2}-\d{2})", markdown_text)
        report_date = date_match.group(1) if date_match else datetime.now().strftime("%Y-%m-%d")

        competitors_match = re.search(
            r"\*\*Analysed against\*?\*?:?\s*(.+?)(?:\n|$)", markdown_text
        )
        competitors = competitors_match.group(1).strip() if competitors_match else ""

        # Metadata table
        meta_data = [
            ["Report Date", report_date],
            ["Target Company", company_name],
        ]
        if competitors:
            meta_data.append(["Analysed Against", competitors])

        meta_table = Table(meta_data, colWidths=[3.5 * cm, 10 * cm])
        meta_table.setStyle(TableStyle([
            ("FONTNAME",   (0, 0), (0, -1), _FONT_FAMILY_BOLD),
            ("FONTNAME",   (1, 0), (1, -1), _FONT_FAMILY),
            ("FONTSIZE",   (0, 0), (-1, -1), 9),
            ("TEXTCOLOR",  (0, 0), (0, -1), _BRAND_MUTED),
            ("TEXTCOLOR",  (1, 0), (1, -1), _BRAND_TEXT),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING",    (0, 0), (-1, -1), 6),
            ("LINEBELOW",  (0, 0), (-1, -2), 0.5, colors.HexColor("#e0e0e0")),
            ("VALIGN",     (0, 0), (-1, -1), "TOP"),
        ]))
        story.append(meta_table)

        story.append(Spacer(1, 3 * cm))

        # Footer branding
        story.append(HRFlowable(
            width="100%", thickness=0.5, color=colors.HexColor("#e0e0e0"),
            spaceAfter=8,
        ))
        story.append(Paragraph(
            f"Generated by <b>Intelligence Briefing System</b> · {report_date}",
            ParagraphStyle("CoverFooter", fontSize=8, textColor=_BRAND_MUTED, alignment=TA_LEFT),
        ))

        return story

    # ── markdown → ReportLab flowables ───────────────────────────────────────

    def _parse_markdown(self, text: str, styles: dict) -> list:
        story  = []
        lines  = text.splitlines()
        bullets: list = []

        # Skip the title/metadata block (already on cover page)
        skip_until_section = True

        def flush_bullets():
            if bullets:
                items = [ListItem(Paragraph(b, styles["bullet"]), leftIndent=20) for b in bullets]
                story.append(ListFlowable(items, bulletType="bullet", start="•"))
                story.append(Spacer(1, 4))
                bullets.clear()

        for raw_line in lines:
            line = raw_line.rstrip()

            # Skip title block until first ## section
            if skip_until_section:
                if line.startswith("## "):
                    skip_until_section = False
                elif line.startswith("# "):
                    continue
                else:
                    # Skip date/metadata lines at the top
                    if line.startswith("**Date") or line.startswith("**Analysed"):
                        continue
                    if line.strip() in ("---", "***", "___", ""):
                        continue
                    # If we hit a non-metadata non-empty line without ##, stop skipping
                    if line.strip():
                        skip_until_section = False
                    else:
                        continue

            # headings
            if line.startswith("### "):
                flush_bullets()
                story.append(Paragraph(self._inline(line[4:]), styles["h3"]))
                continue
            if line.startswith("## "):
                flush_bullets()
                story.append(Spacer(1, 6))
                story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#cccccc")))
                story.append(Paragraph(self._inline(line[3:]), styles["h2"]))
                continue
            if line.startswith("# "):
                flush_bullets()
                story.append(Paragraph(self._inline(line[2:]), styles["h1"]))
                story.append(HRFlowable(width="100%", thickness=1, color=_BRAND_DARK))
                story.append(Spacer(1, 8))
                continue

            # bullet points
            if re.match(r"^[-*] ", line):
                bullets.append(self._inline(line[2:]))
                continue

            # numbered list
            if re.match(r"^\d+\. ", line):
                flush_bullets()
                content = re.sub(r"^\d+\. ", "", line)
                bullets.append(self._inline(content))
                continue

            # horizontal rule
            if line.strip() in ("---", "***", "___"):
                flush_bullets()
                story.append(HRFlowable(width="100%", thickness=0.5, color=colors.lightgrey))
                story.append(Spacer(1, 4))
                continue

            # blank line
            if not line.strip():
                flush_bullets()
                story.append(Spacer(1, 4))
                continue

            # regular paragraph
            flush_bullets()
            # reference-style lines
            if re.match(r"^\d+\. \[", line) or re.match(r"^\d+\. https?://", line):
                story.append(Paragraph(self._inline(line), styles["ref"]))
            else:
                story.append(Paragraph(self._inline(line), styles["body"]))

        flush_bullets()
        return story

    @staticmethod
    def _inline(text: str) -> str:
        """Convert inline markdown (bold, italic, links) to ReportLab XML."""
        # Sanitize Unicode chars the font may not support
        text = _sanitize_for_pdf(text)

        # Escape XML special chars first (before we add our own tags)
        text = text.replace("&", "&amp;")
        text = text.replace("<", "&lt;").replace(">", "&gt;")

        # bold — use font name tag for TTF compatibility
        bold_tag = f'<font name="{_FONT_FAMILY_BOLD}">' if _FONT_FAMILY != "Helvetica" else "<b>"
        bold_close = "</font>" if _FONT_FAMILY != "Helvetica" else "</b>"
        text = re.sub(r"\*\*(.+?)\*\*", rf"{bold_tag}\1{bold_close}", text)
        text = re.sub(r"__(.+?)__",     rf"{bold_tag}\1{bold_close}", text)
        # italic
        italic_tag = f'<font name="{_FONT_FAMILY_ITALIC}">' if _FONT_FAMILY != "Helvetica" else "<i>"
        italic_close = "</font>" if _FONT_FAMILY != "Helvetica" else "</i>"
        text = re.sub(r"\*(.+?)\*", rf"{italic_tag}\1{italic_close}", text)
        text = re.sub(r"_(.+?)_",   rf"{italic_tag}\1{italic_close}", text)
        # links [text](url) → clickable blue link
        text = re.sub(
            r"\[(.+?)\]\((https?://[^\)]+)\)",
            r'<a href="\2" color="#1a6fb5">\1</a>',
            text,
        )
        # bare URLs → clickable
        text = re.sub(
            r'(?<!")(https?://[^\s<>\)]+)',
            r'<a href="\1" color="#1a6fb5">\1</a>',
            text,
        )
        return text

    @staticmethod
    def _escape(text: str) -> str:
        """Escape XML special chars for ReportLab."""
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
