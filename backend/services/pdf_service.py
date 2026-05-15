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
# Register TTF fonts for Unicode support. Latin fonts (Arial/DejaVu) for English,
# CJK fonts (Microsoft YaHei / Noto Sans CJK) for Chinese.

_FONT_FAMILY = "Helvetica"          # default fallback
_FONT_FAMILY_BOLD = "Helvetica-Bold"
_FONT_FAMILY_ITALIC = "Helvetica-Oblique"

_CJK_FONT_FAMILY: str | None = None
_CJK_FONT_FAMILY_BOLD: str | None = None


def _register_unicode_fonts():
    """Register Latin and CJK font families."""
    global _FONT_FAMILY, _FONT_FAMILY_BOLD, _FONT_FAMILY_ITALIC
    global _CJK_FONT_FAMILY, _CJK_FONT_FAMILY_BOLD

    # ── Latin fonts ──────────────────────────────────────────────────────
    latin_registrations = [
        ("C:/Windows/Fonts/arial.ttf",    "Arial"),
        ("C:/Windows/Fonts/arialbd.ttf",  "Arial-Bold"),
        ("C:/Windows/Fonts/ariali.ttf",   "Arial-Italic"),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",         "DejaVu"),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",    "DejaVu-Bold"),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf", "DejaVu-Italic"),
    ]
    registered = {}
    for path, name in latin_registrations:
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
        logger.info("PDF: registered Arial TTF (Latin)")
    elif "DejaVu" in registered:
        _FONT_FAMILY = "DejaVu"
        _FONT_FAMILY_BOLD = registered.get("DejaVu-Bold") and "DejaVu-Bold" or "DejaVu"
        _FONT_FAMILY_ITALIC = registered.get("DejaVu-Italic") and "DejaVu-Italic" or "DejaVu"
        logger.info("PDF: registered DejaVu TTF (Latin)")
    else:
        logger.warning("PDF: no TTF fonts found, using Helvetica (limited Unicode)")

    # ── CJK fonts ────────────────────────────────────────────────────────
    cjk_registrations = [
        # Windows — Microsoft YaHei (.ttc, subfontIndex=0)
        ("C:/Windows/Fonts/msyh.ttc",    "MSYH",      0),
        ("C:/Windows/Fonts/msyhbd.ttc",   "MSYH-Bold", 0),
        # Linux — Noto Sans CJK (installed via fonts-noto-cjk package)
        ("/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf", "NotoSansCJK",      None),
        ("/usr/share/fonts/opentype/noto/NotoSansCJKsc-Bold.otf",    "NotoSansCJK-Bold", None),
        # Alternative Linux paths
        ("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",   "NotoSansCJK",      0),
        ("/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",      "NotoSansCJK-Bold", 0),
    ]
    cjk_registered = {}
    for entry in cjk_registrations:
        path, name, subfont_index = entry
        if name in cjk_registered:
            continue  # already registered this name
        if not os.path.exists(path):
            continue
        try:
            if subfont_index is not None:
                pdfmetrics.registerFont(TTFont(name, path, subfontIndex=subfont_index))
            else:
                pdfmetrics.registerFont(TTFont(name, path))
            cjk_registered[name] = True
        except Exception as exc:
            logger.debug("PDF: failed to register CJK font %s: %s", name, exc)

    if "MSYH" in cjk_registered:
        _CJK_FONT_FAMILY = "MSYH"
        _CJK_FONT_FAMILY_BOLD = "MSYH-Bold" if "MSYH-Bold" in cjk_registered else "MSYH"
        logger.info("PDF: registered Microsoft YaHei (CJK)")
    elif "NotoSansCJK" in cjk_registered:
        _CJK_FONT_FAMILY = "NotoSansCJK"
        _CJK_FONT_FAMILY_BOLD = "NotoSansCJK-Bold" if "NotoSansCJK-Bold" in cjk_registered else "NotoSansCJK"
        logger.info("PDF: registered Noto Sans CJK")
    else:
        logger.warning("PDF: no CJK fonts found — Chinese PDF output will have missing glyphs")


def _has_cjk(text: str) -> bool:
    """Return True if text contains CJK Unified Ideographs."""
    for ch in text[:2000]:
        if '\u4e00' <= ch <= '\u9fff' or '\u3400' <= ch <= '\u4dbf':
            return True
    return False


def _resolve_fonts(language: str, text: str) -> tuple:
    """Pick the right font triple (normal, bold, italic) based on language/content."""
    use_cjk = (language == "zh" or _has_cjk(text)) and _CJK_FONT_FAMILY is not None
    if use_cjk:
        return (
            _CJK_FONT_FAMILY,
            _CJK_FONT_FAMILY_BOLD or _CJK_FONT_FAMILY,
            _CJK_FONT_FAMILY,  # CJK fonts typically don't have italic; reuse normal
        )
    return _FONT_FAMILY, _FONT_FAMILY_BOLD, _FONT_FAMILY_ITALIC


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


def _sanitize_for_pdf(text: str, font: str = "Helvetica") -> str:
    """Replace Unicode chars the font may not support. Skip for any registered TTF."""
    if font != "Helvetica":
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

def _build_styles(font: str, font_bold: str):
    base = getSampleStyleSheet()

    styles = {
        "cover_title": ParagraphStyle(
            "CoverTitle", parent=base["Title"],
            fontName=font_bold,
            fontSize=28, leading=34, spaceAfter=8,
            textColor=_BRAND_DARK, alignment=TA_LEFT,
        ),
        "cover_subtitle": ParagraphStyle(
            "CoverSubtitle", parent=base["Normal"],
            fontName=font,
            fontSize=12, leading=16, spaceAfter=4,
            textColor=_BRAND_MUTED, alignment=TA_LEFT,
        ),
        "cover_meta": ParagraphStyle(
            "CoverMeta", parent=base["Normal"],
            fontName=font,
            fontSize=10, leading=14, spaceAfter=2,
            textColor=_BRAND_MUTED, alignment=TA_LEFT,
        ),
        "h1": ParagraphStyle(
            "H1", parent=base["Heading1"],
            fontName=font_bold,
            fontSize=20, spaceAfter=12, spaceBefore=6,
            textColor=_BRAND_DARK,
        ),
        "h2": ParagraphStyle(
            "H2", parent=base["Heading2"],
            fontName=font_bold,
            fontSize=15, spaceAfter=8, spaceBefore=14,
            textColor=_BRAND_DARK,
            borderPad=4,
        ),
        "h3": ParagraphStyle(
            "H3", parent=base["Heading3"],
            fontName=font_bold,
            fontSize=12, spaceAfter=6, spaceBefore=8,
            textColor=colors.HexColor("#0f3460"),
        ),
        "body": ParagraphStyle(
            "Body", parent=base["Normal"],
            fontName=font,
            fontSize=10, leading=15, spaceAfter=6,
            alignment=TA_JUSTIFY,
        ),
        "bullet": ParagraphStyle(
            "Bullet", parent=base["Normal"],
            fontName=font,
            fontSize=10, leading=14, spaceAfter=3,
            leftIndent=12,
        ),
        "ref": ParagraphStyle(
            "Ref", parent=base["Normal"],
            fontName=font,
            fontSize=8, leading=11, spaceAfter=2,
            textColor=_BRAND_MUTED,
        ),
    }
    return styles


# ── Page template callbacks ──────────────────────────────────────────────────

def _make_header_footer(font: str):
    """Create a header/footer callback that uses the given font."""
    def _header_footer(canvas, doc):
        canvas.saveState()
        width, height = A4

        # Top accent line
        canvas.setStrokeColor(_BRAND_ACCENT)
        canvas.setLineWidth(1.5)
        canvas.line(2.5 * cm, height - 1.8 * cm, width - 2.5 * cm, height - 1.8 * cm)

        # Footer: page number on the right, branding on the left
        canvas.setFont(font, 8)
        canvas.setFillColor(_BRAND_MUTED)
        canvas.drawString(2.5 * cm, 1.5 * cm, "市场调研报告")
        canvas.drawRightString(width - 2.5 * cm, 1.5 * cm, f"Page {doc.page}")

        # Bottom accent line
        canvas.setStrokeColor(_BRAND_ACCENT)
        canvas.setLineWidth(0.5)
        canvas.line(2.5 * cm, 1.9 * cm, width - 2.5 * cm, 1.9 * cm)

        canvas.restoreState()
    return _header_footer


# ── Converter ─────────────────────────────────────────────────────────────────

class PDFService:
    def generate_pdf_bytes(
        self, markdown_text: str, company_name: str, language: str = "en",
    ) -> Tuple[bool, Union[bytes, str]]:
        """
        Returns (True, pdf_bytes) on success, (False, error_message) on failure.
        """
        try:
            # Resolve fonts based on language / content
            font, font_bold, font_italic = _resolve_fonts(language, markdown_text)
            self._font = font
            self._font_bold = font_bold
            self._font_italic = font_italic

            buf = io.BytesIO()
            doc = SimpleDocTemplate(
                buf,
                pagesize=A4,
                leftMargin=2.5 * cm,
                rightMargin=2.5 * cm,
                topMargin=2.5 * cm,
                bottomMargin=2.5 * cm,
            )
            styles = _build_styles(font, font_bold)
            story  = self._build_cover(company_name, markdown_text, styles)
            story.append(PageBreak())
            story += self._parse_markdown(markdown_text, styles)
            header_footer = _make_header_footer(font)
            doc.build(story, onFirstPage=lambda c, d: None, onLaterPages=header_footer)
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
            "市场调研报告",
            styles["cover_subtitle"],
        ))
        story.append(Spacer(1, 1.5 * cm))

        # Extract metadata from markdown
        date_match = re.search(r"\*\*Date\*?\*?:?\s*(\d{4}-\d{2}-\d{2})", markdown_text)
        report_date = date_match.group(1) if date_match else datetime.now().strftime("%Y-%m-%d")

        # Metadata table
        meta_data = [
            ["Report Date", report_date],
            ["Research Domain", company_name],
        ]

        meta_table = Table(meta_data, colWidths=[3.5 * cm, 10 * cm])
        meta_table.setStyle(TableStyle([
            ("FONTNAME",   (0, 0), (0, -1), self._font_bold),
            ("FONTNAME",   (1, 0), (1, -1), self._font),
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
            f"Generated by <b>Market Study Agent</b> · {report_date}",
            ParagraphStyle("CoverFooter", fontName=self._font, fontSize=8, textColor=_BRAND_MUTED, alignment=TA_LEFT),
        ))

        return story

    # ── markdown → ReportLab flowables ───────────────────────────────────────

    def _parse_markdown(self, text: str, styles: dict) -> list:
        story  = []
        lines  = text.splitlines()
        bullets: list = []
        table_buffer: list = []  # accumulates consecutive markdown table rows

        # Skip the title/metadata block (already on cover page)
        skip_until_section = True

        def flush_bullets():
            if bullets:
                items = [ListItem(Paragraph(b, styles["bullet"]), leftIndent=20) for b in bullets]
                story.append(ListFlowable(items, bulletType="bullet", start="•"))
                story.append(Spacer(1, 4))
                bullets.clear()

        def flush_table():
            if table_buffer:
                tbl = self._build_table(list(table_buffer), styles)
                if tbl is not None:
                    story.append(Spacer(1, 4))
                    story.append(tbl)
                    story.append(Spacer(1, 8))
                table_buffer.clear()

        for raw_line in lines:
            line = raw_line.rstrip()
            stripped = line.strip()

            # ── markdown table detection ─────────────────────────────────
            # A table row starts and ends with "|" and contains at least one "|" in the middle.
            is_table_row = (
                len(stripped) >= 2
                and stripped.startswith("|")
                and stripped.endswith("|")
                and stripped.count("|") >= 2
            )
            if is_table_row:
                # separator row like |---|---| or |:---|---:|  → skip but keep table open
                inner = stripped.strip("|")
                if inner.replace("|", "").replace("-", "").replace(":", "").replace(" ", "") == "":
                    continue
                # cells: split by "|", trim whitespace
                cells = [c.strip() for c in stripped.strip("|").split("|")]
                table_buffer.append(cells)
                # if we were skipping (header block), table also signals real content
                if skip_until_section:
                    skip_until_section = False
                continue
            else:
                # non-table line — flush any pending table before processing
                flush_table()

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
        flush_table()
        return story

    # ── markdown table → ReportLab Table ─────────────────────────────────
    def _build_table(self, rows: list, styles: dict):
        """Convert a list-of-list-of-cells markdown table into a styled Table flowable."""
        if not rows:
            return None
        # Normalize column count (longest row wins)
        max_cols = max(len(r) for r in rows)
        if max_cols == 0:
            return None
        for r in rows:
            while len(r) < max_cols:
                r.append("")

        # Adaptive font size based on column count
        if max_cols <= 3:
            font_size = 9
            cell_leading = 12
        elif max_cols <= 5:
            font_size = 8
            cell_leading = 11
        else:
            font_size = 7
            cell_leading = 10

        # Cell paragraph styles (so long content wraps inside cells)
        header_style = ParagraphStyle(
            "TableHeader",
            fontName=self._font_bold,
            fontSize=font_size,
            leading=cell_leading,
            textColor=colors.white,
            alignment=TA_CENTER,
        )
        body_style = ParagraphStyle(
            "TableCell",
            fontName=self._font,
            fontSize=font_size,
            leading=cell_leading,
            textColor=_BRAND_TEXT,
            alignment=TA_LEFT,
        )

        # Wrap each cell content in a Paragraph for auto-wrapping
        data = []
        for i, row in enumerate(rows):
            style = header_style if i == 0 else body_style
            data.append([Paragraph(self._inline(c) if c else "&nbsp;", style) for c in row])

        # Distribute width evenly across A4 usable area (21cm - 2.5cm*2 margins = 16cm)
        usable_width = 16 * cm
        col_widths = [usable_width / max_cols] * max_cols

        tbl = Table(data, colWidths=col_widths, repeatRows=1, hAlign="LEFT")
        tbl.setStyle(TableStyle([
            # Header row
            ("BACKGROUND",    (0, 0), (-1, 0), colors.HexColor("#4472C4")),
            ("TEXTCOLOR",     (0, 0), (-1, 0), colors.white),
            ("ALIGN",         (0, 0), (-1, 0), "CENTER"),
            ("VALIGN",        (0, 0), (-1, 0), "MIDDLE"),
            ("TOPPADDING",    (0, 0), (-1, 0), 6),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
            # Body
            ("VALIGN",        (0, 1), (-1, -1), "TOP"),
            ("ALIGN",         (0, 1), (-1, -1), "LEFT"),
            ("TOPPADDING",    (0, 1), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 1), (-1, -1), 4),
            ("LEFTPADDING",   (0, 0), (-1, -1), 4),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 4),
            # Borders + alternating row colours
            ("BOX",           (0, 0), (-1, -1), 0.5, colors.HexColor("#bfbfbf")),
            ("INNERGRID",     (0, 0), (-1, -1), 0.25, colors.HexColor("#d9d9d9")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F2F2F7")]),
        ]))
        return tbl

    def _inline(self, text: str) -> str:
        """Convert inline markdown (bold, italic, links) to ReportLab XML."""
        # Sanitize Unicode chars the font may not support
        text = _sanitize_for_pdf(text, self._font)

        # Escape XML special chars first (before we add our own tags)
        text = text.replace("&", "&amp;")
        text = text.replace("<", "&lt;").replace(">", "&gt;")

        # bold — use font name tag for TTF compatibility
        font_bold = self._font_bold
        font_italic = self._font_italic
        is_ttf = self._font != "Helvetica"
        bold_tag = f'<font name="{font_bold}">' if is_ttf else "<b>"
        bold_close = "</font>" if is_ttf else "</b>"
        text = re.sub(r"\*\*(.+?)\*\*", rf"{bold_tag}\1{bold_close}", text)
        text = re.sub(r"__(.+?)__",     rf"{bold_tag}\1{bold_close}", text)
        # italic
        italic_tag = f'<font name="{font_italic}">' if is_ttf else "<i>"
        italic_close = "</font>" if is_ttf else "</i>"
        text = re.sub(r"(?<!\*)\*(?!\*)([^*\n]+?)(?<!\*)\*(?!\*)", rf"{italic_tag}\1{italic_close}", text)
        # Underscore italic: skip intra-word underscores (e.g. inside URLs like t20241230_1395328.html)
        text = re.sub(r"(?<![A-Za-z0-9_])_([^_\n]+?)_(?![A-Za-z0-9_])", rf"{italic_tag}\1{italic_close}", text)
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
