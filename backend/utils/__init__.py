"""
Utility functions for file handling, formatting, hashing, and memory management.
"""
from __future__ import annotations

import gc
import hashlib
import logging
import os
import re
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ── File Utilities ──────────────────────────────────────────────────────────

def get_file_extension(filename: str) -> str:
    """Extract lowercase file extension without the dot."""
    return Path(filename).suffix.lower().lstrip(".")


def safe_filename(filename: str) -> str:
    """Sanitize filename for safe filesystem usage."""
    # Remove path separators and null bytes
    name = re.sub(r'[/\\:\x00]', '_', filename)
    # Remove leading/trailing whitespace and dots
    name = name.strip('. ')
    # Limit length
    if len(name) > 200:
        ext = Path(name).suffix
        name = name[:200 - len(ext)] + ext
    return name or "unnamed_file"


def ensure_directory(path: Path | str) -> Path:
    """Create directory if it doesn't exist, return Path object."""
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def cleanup_file(file_path: str | Path) -> None:
    """Safely delete a file."""
    try:
        p = Path(file_path)
        if p.exists() and p.is_file():
            p.unlink()
            logger.debug(f"Cleaned up: {p}")
    except Exception as e:
        logger.warning(f"Failed to clean up {file_path}: {e}")


def cleanup_directory(dir_path: str | Path) -> None:
    """Safely delete a directory and all its contents."""
    try:
        p = Path(dir_path)
        if p.exists() and p.is_dir():
            shutil.rmtree(p, ignore_errors=True)
            logger.debug(f"Cleaned up directory: {p}")
    except Exception as e:
        logger.warning(f"Failed to clean up directory {dir_path}: {e}")


def get_temp_path(prefix: str = "docexcel_", suffix: str = "") -> Path:
    """Create a temporary file path in the system temp directory."""
    fd, path = tempfile.mkstemp(prefix=prefix, suffix=suffix)
    os.close(fd)
    return Path(path)


def get_human_readable_size(size_bytes: int) -> str:
    """Convert bytes to human-readable format."""
    for unit in ["B", "KB", "MB", "GB"]:
        if abs(size_bytes) < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


# ── Format Utilities ────────────────────────────────────────────────────────

# Indian number format: 1,23,45,678.90
_INDIAN_NUMBER_RE = re.compile(r'^[₹Rs.\s]*[-]?\d{1,2}(?:,\d{2})*(?:,\d{3})(?:\.\d+)?$')
# International format: 123,456.78
_INTL_NUMBER_RE = re.compile(r'^[$€£¥₹Rs.\s]*[-]?\d{1,3}(?:,\d{3})*(?:\.\d+)?$')
# Plain number with optional decimals
_PLAIN_NUMBER_RE = re.compile(r'^[-]?\d+(?:\.\d+)?$')
# Parenthetical negative: (1,234.56)
_PAREN_NEGATIVE_RE = re.compile(r'^\([\d,.\s]+\)$')
# Currency symbols
_CURRENCY_RE = re.compile(r'[₹$€£¥]|Rs\.?|INR|USD|EUR|GBP|AED')
# Date patterns
_DATE_PATTERNS = [
    (r'\d{2}[/-]\d{2}[/-]\d{4}', '%d/%m/%Y'),
    (r'\d{2}[/-]\d{2}[/-]\d{2}', '%d/%m/%y'),
    (r'\d{4}[/-]\d{2}[/-]\d{2}', '%Y/%m/%d'),
    (r'\d{2}\s+\w{3}\s+\d{4}', '%d %b %Y'),
    (r'\d{2}\s+\w+\s+\d{4}', '%d %B %Y'),
    (r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}', None),  # Generic fallback
]
# Percentage
_PERCENTAGE_RE = re.compile(r'^[-]?\d+(?:\.\d+)?\s*%$')
# GSTIN
_GSTIN_RE = re.compile(r'^\d{2}[A-Z]{5}\d{4}[A-Z]{1}[A-Z\d]{1}[Z]{1}[A-Z\d]{1}$')
# PAN
_PAN_RE = re.compile(r'^[A-Z]{5}\d{4}[A-Z]{1}$')
# IFSC
_IFSC_RE = re.compile(r'^[A-Z]{4}0[A-Z0-9]{6}$')
# HSN Code (4, 6, or 8 digits)
_HSN_RE = re.compile(r'^\d{4}(?:\d{2})?(?:\d{2})?$')
# SAC Code (6 digits starting with 99)
_SAC_RE = re.compile(r'^99\d{4}$')


def detect_data_type(value: str) -> tuple[str, Any, str]:
    """
    Detect the data type of a string value.
    Returns: (data_type, parsed_value, format_string)
    """
    if not value or not value.strip():
        return "text", "", ""

    val = value.strip()

    # Check GSTIN
    if _GSTIN_RE.match(val.upper()):
        return "gstin", val.upper(), ""

    # Check PAN
    if _PAN_RE.match(val.upper()):
        return "pan", val.upper(), ""

    # Check IFSC
    if _IFSC_RE.match(val.upper()):
        return "ifsc", val.upper(), ""

    # Check percentage
    if _PERCENTAGE_RE.match(val):
        num_str = val.replace('%', '').strip()
        try:
            return "percentage", float(num_str) / 100, "0.00%"
        except ValueError:
            pass

    # Check SAC (6 digits starting with 99) — must be before HSN check
    if _SAC_RE.match(val):
        return "sac", val, "@"

    # Check HSN (4, 6, or 8 digits)
    if _HSN_RE.match(val) and len(val) in (4, 6, 8):
        return "hsn", val, "@"  # Text format in Excel

    # Check parenthetical negatives: (1,234.56)
    if _PAREN_NEGATIVE_RE.match(val):
        num_str = val.strip('()').replace(',', '').strip()
        try:
            return "number", -float(num_str), "#,##0.00"
        except ValueError:
            pass

    # Check currency values
    currency_match = _CURRENCY_RE.search(val)
    if currency_match:
        currency_symbol = currency_match.group()
        num_str = _CURRENCY_RE.sub('', val).replace(',', '').strip()
        # Handle Dr/Cr suffixes
        num_str = re.sub(r'\s*(Dr|Cr|dr|cr)\.?\s*$', '', num_str).strip()
        try:
            parsed = float(num_str)
            if 'Dr' in val or 'dr' in val:
                parsed = -abs(parsed)
            fmt = '₹#,##0.00' if '₹' in val or 'Rs' in val or 'INR' in val else '#,##0.00'
            return "currency", parsed, fmt
        except ValueError:
            pass

    # Check Indian number format (must have at least one comma)
    if ',' in val and _INDIAN_NUMBER_RE.match(val):
        num_str = re.sub(r'[₹Rs\s]', '', val).replace(',', '')
        try:
            return "number", float(num_str), "#,##0.00"
        except ValueError:
            pass

    # Check international number format (must have at least one comma)
    if ',' in val and _INTL_NUMBER_RE.match(val):
        num_str = re.sub(r'[$€£¥₹Rs\s]', '', val).replace(',', '')
        try:
            return "number", float(num_str), "#,##0.00"
        except ValueError:
            pass

    # Check plain number
    if _PLAIN_NUMBER_RE.match(val):
        try:
            if '.' in val:
                return "number", float(val), "#,##0.00"
            return "number", int(val), "#,##0"
        except ValueError:
            pass

    # Check dates
    for pattern, fmt in _DATE_PATTERNS:
        if re.match(pattern, val):
            if fmt:
                try:
                    # Handle both / and - separators
                    normalized = val.replace('-', '/')
                    parsed = datetime.strptime(normalized, fmt)
                    return "date", parsed, "DD/MM/YYYY"
                except ValueError:
                    pass
            return "date", val, "DD/MM/YYYY"

    # HSN and SAC already checked above

    return "text", val, ""


def parse_number(value: str) -> Optional[float]:
    """
    Parse a number string, handling Indian/international formats,
    currency symbols, parenthetical negatives, Dr/Cr notation.
    """
    if not value or not value.strip():
        return None

    val = value.strip()

    # Handle parenthetical negatives
    if val.startswith('(') and val.endswith(')'):
        val = '-' + val[1:-1]

    # Remove currency symbols and whitespace
    val = _CURRENCY_RE.sub('', val).strip()

    # Handle Dr/Cr
    is_debit = bool(re.search(r'\b(Dr|dr)\.?\s*$', val))
    val = re.sub(r'\s*(Dr|Cr|dr|cr)\.?\s*$', '', val).strip()

    # Remove commas
    val = val.replace(',', '')

    # Remove spaces
    val = val.replace(' ', '')

    try:
        result = float(val)
        if is_debit:
            result = -abs(result)
        return result
    except (ValueError, TypeError):
        return None


def format_indian_number(number: float, decimals: int = 2) -> str:
    """Format number in Indian numbering system (12,34,567.89)."""
    if number < 0:
        return '-' + format_indian_number(-number, decimals)

    integer_part = int(number)
    decimal_part = round(number - integer_part, decimals)

    int_str = str(integer_part)

    if len(int_str) <= 3:
        formatted = int_str
    else:
        last_three = int_str[-3:]
        remaining = int_str[:-3]
        # Group remaining digits in pairs
        groups = []
        while remaining:
            groups.insert(0, remaining[-2:])
            remaining = remaining[:-2]
        formatted = ','.join(groups) + ',' + last_three

    if decimals > 0:
        dec_str = f"{decimal_part:.{decimals}f}"[2:]
        return formatted + '.' + dec_str
    return formatted


def parse_date(value: str) -> Optional[datetime]:
    """Try multiple date formats to parse a date string."""
    if not value or not value.strip():
        return None

    val = value.strip()
    formats = [
        '%d/%m/%Y', '%d-%m-%Y', '%d.%m.%Y',
        '%d/%m/%y', '%d-%m-%y',
        '%Y/%m/%d', '%Y-%m-%d',
        '%m/%d/%Y', '%m-%d-%Y',
        '%d %b %Y', '%d %B %Y',
        '%b %d, %Y', '%B %d, %Y',
        '%d-%b-%Y', '%d-%b-%y',
    ]
    for fmt in formats:
        try:
            return datetime.strptime(val, fmt)
        except ValueError:
            continue
    return None


# ── Memory Utilities ────────────────────────────────────────────────────────

def release_memory() -> None:
    """Force garbage collection to free memory."""
    gc.collect()
    logger.debug("Memory released via gc.collect()")


def get_memory_usage_mb() -> float:
    """Get current process memory usage in MB."""
    try:
        import resource
        usage = resource.getrusage(resource.RUSAGE_SELF)
        return usage.ru_maxrss / (1024 * 1024)  # macOS returns bytes
    except (ImportError, AttributeError):
        try:
            import psutil
            process = psutil.Process(os.getpid())
            return process.memory_info().rss / (1024 * 1024)
        except ImportError:
            return 0.0


# ── Hash Utilities ──────────────────────────────────────────────────────────

def compute_file_hash(file_path: str | Path) -> str:
    """Compute SHA-256 hash for duplicate detection."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def compute_content_hash(content: bytes) -> str:
    """Compute SHA-256 hash of byte content."""
    return hashlib.sha256(content).hexdigest()
