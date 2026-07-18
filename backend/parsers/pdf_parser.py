"""
PDF Parser — Handles searchable PDFs, scanned PDFs, and password-protected PDFs.
Uses pdfplumber for native text extraction, falls back to OCR for scanned pages.
Processes page-by-page to minimize memory usage.
"""
from __future__ import annotations

import io
import logging
import tempfile
import time
from pathlib import Path
from typing import Optional

import numpy as np

from backend.models import Cell, Table, ProcessingResult, ProcessingStatus
from backend.utils import detect_data_type, parse_number, release_memory

logger = logging.getLogger(__name__)


class PDFParser:
    """
    Comprehensive PDF parser with hybrid extraction:
    1. Try native text extraction (pdfplumber)
    2. Try table extraction (pdfplumber tables / camelot / tabula)
    3. Fall back to OCR for scanned pages
    """

    def __init__(self, ocr_manager=None, preprocessor=None):
        self.ocr_manager = ocr_manager
        self.preprocessor = preprocessor

    def parse(self, file_path: str | Path, password: str | None = None,
              page_range: tuple[int, int] | None = None) -> ProcessingResult:
        """Parse a PDF file and extract all tables."""
        import pdfplumber

        result = ProcessingResult()
        result.filename = Path(file_path).name
        result.file_category = "pdf"
        result.status = ProcessingStatus.OCR_IN_PROGRESS
        start_time = time.time()

        try:
            pdf_kwargs = {}
            if password:
                pdf_kwargs["password"] = password

            with pdfplumber.open(str(file_path), **pdf_kwargs) as pdf:
                result.page_count = len(pdf.pages)
                logger.info(f"Processing PDF: {result.filename}, {result.page_count} pages")

                start_page = (page_range[0] - 1) if page_range else 0
                end_page = page_range[1] if page_range else result.page_count

                for page_num in range(start_page, min(end_page, result.page_count)):
                    try:
                        page = pdf.pages[page_num]
                        page_tables = self._extract_page(page, page_num + 1)

                        for table in page_tables:
                            table.page_number = page_num + 1
                            result.tables.append(table)

                        logger.debug(f"Page {page_num + 1}: extracted {len(page_tables)} tables")
                    except Exception as e:
                        logger.warning(f"Error on page {page_num + 1}: {e}")
                        result.warnings.append(f"Page {page_num + 1}: {str(e)}")

                    # Release memory after each page
                    release_memory()

            result.ocr_engine_used = "pdfplumber"
            result.status = ProcessingStatus.READY_FOR_REVIEW
            result.processing_time = time.time() - start_time

            if not result.tables:
                result.warnings.append("No tables detected in the PDF")

        except Exception as e:
            error_msg = str(e)
            if "password" in error_msg.lower() or "encrypted" in error_msg.lower():
                result.error_message = "PDF is password protected. Please provide the password."
            else:
                result.error_message = f"Failed to parse PDF: {error_msg}"
            result.status = ProcessingStatus.FAILED
            logger.error(f"PDF parsing failed: {error_msg}")

        return result

    def _extract_page(self, page, page_num: int) -> list[Table]:
        """Extract tables from a single PDF page."""
        tables: list[Table] = []

        # Strategy 1: Try native table extraction
        native_tables = self._extract_native_tables(page, page_num)
        if native_tables:
            tables.extend(native_tables)
            return tables

        # Strategy 2: Try text-based extraction
        text = page.extract_text() or ""
        if text.strip():
            text_table = self._text_to_table(text, page_num)
            if text_table and text_table.row_count > 0:
                tables.append(text_table)
                return tables

        # Strategy 3: Fall back to OCR
        if self.ocr_manager:
            ocr_tables = self._ocr_page(page, page_num)
            if ocr_tables:
                tables.extend(ocr_tables)

        return tables

    def _extract_native_tables(self, page, page_num: int) -> list[Table]:
        """Extract tables using pdfplumber's built-in table detection."""
        tables: list[Table] = []

        try:
            raw_tables = page.extract_tables({
                "vertical_strategy": "lines_strict",
                "horizontal_strategy": "lines_strict",
                "snap_tolerance": 5,
                "join_tolerance": 5,
                "edge_min_length": 10,
                "min_words_vertical": 1,
                "min_words_horizontal": 1,
            })

            if not raw_tables:
                # Try with text strategy as fallback
                raw_tables = page.extract_tables({
                    "vertical_strategy": "text",
                    "horizontal_strategy": "text",
                    "snap_tolerance": 5,
                    "join_tolerance": 5,
                })

            if not raw_tables:
                return tables

            for raw_table in raw_tables:
                if not raw_table or len(raw_table) < 1:
                    continue

                table = Table()
                table.source_engine = "pdfplumber"
                table.page_number = page_num
                table.has_borders = True

                for row_idx, raw_row in enumerate(raw_table):
                    if not raw_row:
                        continue

                    cells: list[Cell] = []
                    for col_idx, cell_value in enumerate(raw_row):
                        cell = Cell(row=row_idx, col=col_idx)
                        cell.raw_value = str(cell_value) if cell_value else ""
                        cell.value = cell.raw_value.strip() if cell.raw_value else ""
                        cell.confidence = 1.0  # Native extraction = high confidence

                        # Detect data type
                        if cell.value:
                            dt, parsed, fmt = detect_data_type(cell.value)
                            cell.data_type = dt
                            if dt in ("number", "currency", "percentage"):
                                cell.value = parsed
                            cell.format_string = fmt

                        # First row → header
                        if row_idx == 0:
                            cell.is_header = True
                            cell.font_bold = True

                        cells.append(cell)

                    table.cells.append(cells)

                # Extract headers
                if table.cells:
                    table.headers = [str(c.value) for c in table.cells[0]]
                    table.num_rows = len(table.cells)
                    table.num_cols = max(len(r) for r in table.cells) if table.cells else 0
                    tables.append(table)

        except Exception as e:
            logger.debug(f"Native table extraction failed: {e}")

        return tables

    def _text_to_table(self, text: str, page_num: int) -> Optional[Table]:
        """Convert plain text with tabular structure to a Table."""
        lines = [line for line in text.split('\n') if line.strip()]
        if len(lines) < 2:
            return None

        table = Table()
        table.source_engine = "pdfplumber_text"
        table.page_number = page_num
        table.has_borders = False

        # Try to detect delimiter (multiple spaces, tabs, pipes)
        import re
        for line_idx, line in enumerate(lines):
            # Split by multiple spaces (2+), tabs, or pipes
            parts = re.split(r'\s{2,}|\t|\|', line)
            parts = [p.strip() for p in parts if p.strip()]

            if not parts:
                continue

            cells: list[Cell] = []
            for col_idx, part in enumerate(parts):
                cell = Cell(row=line_idx, col=col_idx)
                cell.raw_value = part
                cell.value = part
                cell.confidence = 1.0

                if part:
                    dt, parsed, fmt = detect_data_type(part)
                    cell.data_type = dt
                    if dt in ("number", "currency", "percentage"):
                        cell.value = parsed
                    cell.format_string = fmt

                if line_idx == 0:
                    cell.is_header = True
                    cell.font_bold = True

                cells.append(cell)

            table.cells.append(cells)

        if table.cells and len(table.cells) > 1:
            table.headers = [str(c.value) for c in table.cells[0]]
            table.num_rows = len(table.cells)
            table.num_cols = max(len(r) for r in table.cells) if table.cells else 0
            return table

        return None

    def _ocr_page(self, page, page_num: int) -> list[Table]:
        """Convert PDF page to image and run OCR."""
        tables: list[Table] = []
        try:
            # Convert page to image
            pil_image = page.to_image(resolution=300).original
            img_array = np.array(pil_image)

            # Preprocess if available
            if self.preprocessor:
                img_array = self.preprocessor.preprocess(img_array)

            # Run OCR
            from backend.ocr import TableFromOCR
            ocr_result = self.ocr_manager.ocr_image(img_array, page_number=page_num)
            extractor = TableFromOCR()
            tables = extractor.extract_tables(ocr_result)

            # Clean up
            del img_array, pil_image
            release_memory()

        except Exception as e:
            logger.warning(f"OCR fallback failed for page {page_num}: {e}")

        return tables
