"""
Data models for the document processing pipeline.
"""
from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional


class DocumentType(Enum):
    """Supported document categories."""
    INVOICE = "invoice"
    BANK_STATEMENT = "bank_statement"
    GST_RETURN = "gst_return"
    TAX_FORM = "tax_form"
    BALANCE_SHEET = "balance_sheet"
    PROFIT_LOSS = "profit_loss"
    TRIAL_BALANCE = "trial_balance"
    LEDGER = "ledger"
    SALARY_SLIP = "salary_slip"
    RECEIPT = "receipt"
    BILL = "bill"
    VOUCHER = "voucher"
    CREDIT_NOTE = "credit_note"
    DEBIT_NOTE = "debit_note"
    PURCHASE_ORDER = "purchase_order"
    DELIVERY_NOTE = "delivery_note"
    QUOTATION = "quotation"
    CHEQUE = "cheque"
    FORM_16 = "form_16"
    FORM_26AS = "form_26as"
    STOCK_REGISTER = "stock_register"
    FIXED_ASSET = "fixed_asset"
    INSURANCE = "insurance"
    LOAN_STATEMENT = "loan_statement"
    INVESTMENT_STATEMENT = "investment_statement"
    ATTENDANCE = "attendance"
    PAYROLL = "payroll"
    HANDWRITTEN = "handwritten"
    GENERIC_TABLE = "generic_table"
    UNKNOWN = "unknown"


class ProcessingStatus(Enum):
    """Processing states for a document."""
    QUEUED = "queued"
    PREPROCESSING = "preprocessing"
    OCR_IN_PROGRESS = "ocr_in_progress"
    TABLE_DETECTION = "table_detection"
    VALIDATION = "validation"
    READY_FOR_REVIEW = "ready_for_review"
    EXPORTING = "exporting"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class OCREngine(Enum):
    """Available OCR engines."""
    PADDLEOCR = "paddleocr"
    TESSERACT = "tesseract"
    EASYOCR = "easyocr"
    PDFPLUMBER = "pdfplumber"
    CAMELOT = "camelot"
    TABULA = "tabula"
    PYMUPDF = "pymupdf"
    NATIVE = "native"


@dataclass
class Cell:
    """Represents a single cell in a table."""
    value: Any = ""
    raw_value: str = ""
    confidence: float = 1.0
    data_type: str = "text"  # text, number, currency, date, percentage, gstin, pan, etc.
    row: int = 0
    col: int = 0
    row_span: int = 1
    col_span: int = 1
    is_header: bool = False
    is_merged: bool = False
    font_bold: bool = False
    font_size: float = 11.0
    alignment: str = "left"
    format_string: str = ""
    currency_symbol: str = ""
    validation_error: str = ""
    semantic_label: str = ""  # e.g., "date", "invoice_no", "amount", "gstin"

    def to_dict(self) -> dict:
        return {
            "value": self.value if self.value is not None else "",
            "raw_value": self.raw_value,
            "confidence": round(self.confidence, 3),
            "data_type": self.data_type,
            "row": self.row,
            "col": self.col,
            "row_span": self.row_span,
            "col_span": self.col_span,
            "is_header": self.is_header,
            "is_merged": self.is_merged,
            "font_bold": self.font_bold,
            "semantic_label": self.semantic_label,
            "validation_error": self.validation_error,
            "format_string": self.format_string,
            "currency_symbol": self.currency_symbol,
        }


@dataclass
class Table:
    """Represents a detected table with rows and columns."""
    table_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    cells: list[list[Cell]] = field(default_factory=list)
    headers: list[str] = field(default_factory=list)
    title: str = ""
    page_number: int = 1
    confidence: float = 1.0
    num_rows: int = 0
    num_cols: int = 0
    has_borders: bool = True
    is_continuation: bool = False
    source_engine: str = ""
    metadata: dict = field(default_factory=dict)

    @property
    def row_count(self) -> int:
        return len(self.cells)

    @property
    def col_count(self) -> int:
        return max((len(row) for row in self.cells), default=0)

    def to_dict(self) -> dict:
        return {
            "table_id": self.table_id,
            "title": self.title,
            "page_number": self.page_number,
            "confidence": round(self.confidence, 3),
            "num_rows": self.row_count,
            "num_cols": self.col_count,
            "has_borders": self.has_borders,
            "is_continuation": self.is_continuation,
            "source_engine": self.source_engine,
            "headers": self.headers,
            "cells": [[cell.to_dict() for cell in row] for row in self.cells],
            "metadata": self.metadata,
        }

    def get_column_values(self, col_index: int) -> list[Cell]:
        """Get all values in a specific column."""
        result = []
        for row in self.cells:
            if col_index < len(row):
                result.append(row[col_index])
        return result


@dataclass
class ValidationResult:
    """Result of a validation check."""
    field: str = ""
    check_type: str = ""  # arithmetic, format, gst, pan, etc.
    is_valid: bool = True
    expected_value: Any = None
    actual_value: Any = None
    message: str = ""
    severity: str = "warning"  # info, warning, error
    row: int = -1
    col: int = -1

    def to_dict(self) -> dict:
        return {
            "field": self.field,
            "check_type": self.check_type,
            "is_valid": self.is_valid,
            "expected_value": str(self.expected_value) if self.expected_value else "",
            "actual_value": str(self.actual_value) if self.actual_value else "",
            "message": self.message,
            "severity": self.severity,
            "row": self.row,
            "col": self.col,
        }


@dataclass
class ProcessingResult:
    """Complete result of processing a document."""
    document_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    filename: str = ""
    file_hash: str = ""
    file_size: int = 0
    file_category: str = ""
    document_type: DocumentType = DocumentType.UNKNOWN
    status: ProcessingStatus = ProcessingStatus.QUEUED
    tables: list[Table] = field(default_factory=list)
    validations: list[ValidationResult] = field(default_factory=list)
    ocr_engine_used: str = ""
    processing_time: float = 0.0
    page_count: int = 0
    error_message: str = ""
    warnings: list[str] = field(default_factory=list)
    output_path: str = ""
    metadata: dict = field(default_factory=dict)
    start_time: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "document_id": self.document_id,
            "filename": self.filename,
            "file_hash": self.file_hash,
            "file_size": self.file_size,
            "file_category": self.file_category,
            "document_type": self.document_type.value,
            "status": self.status.value,
            "tables": [t.to_dict() for t in self.tables],
            "validations": [v.to_dict() for v in self.validations],
            "ocr_engine_used": self.ocr_engine_used,
            "processing_time": round(self.processing_time, 2),
            "page_count": self.page_count,
            "error_message": self.error_message,
            "warnings": self.warnings,
            "output_path": self.output_path,
            "metadata": self.metadata,
        }

    def mark_completed(self) -> None:
        self.status = ProcessingStatus.COMPLETED
        self.processing_time = time.time() - self.start_time

    def mark_failed(self, error: str) -> None:
        self.status = ProcessingStatus.FAILED
        self.error_message = error
        self.processing_time = time.time() - self.start_time


def compute_file_hash(file_path: str | Path) -> str:
    """Compute SHA-256 hash of a file for duplicate detection."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()
