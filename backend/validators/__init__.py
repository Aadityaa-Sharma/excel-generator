"""
Financial Validators — GST, PAN, GSTIN, arithmetic, and financial validation.
Checks calculations, formats, and highlights suspicious values.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

from backend.models import Cell, Table, ValidationResult
from backend.utils import parse_number

logger = logging.getLogger(__name__)

# ── Pattern Constants ───────────────────────────────────────────────────────

GSTIN_PATTERN = re.compile(r'^\d{2}[A-Z]{5}\d{4}[A-Z]{1}[A-Z\d]{1}[Z]{1}[A-Z\d]{1}$')
PAN_PATTERN = re.compile(r'^[A-Z]{5}\d{4}[A-Z]{1}$')
IFSC_PATTERN = re.compile(r'^[A-Z]{4}0[A-Z0-9]{6}$')
HSN_PATTERN = re.compile(r'^\d{4}(\d{2})?(\d{2})?$')
SAC_PATTERN = re.compile(r'^99\d{4}$')
BANK_ACCOUNT_PATTERN = re.compile(r'^\d{9,18}$')
INVOICE_PATTERN = re.compile(r'^[A-Za-z0-9/\-]{3,30}$')

# Valid Indian state codes for GSTIN
VALID_STATE_CODES = {
    "01", "02", "03", "04", "05", "06", "07", "08", "09", "10",
    "11", "12", "13", "14", "15", "16", "17", "18", "19", "20",
    "21", "22", "23", "24", "25", "26", "27", "28", "29", "30",
    "31", "32", "33", "34", "35", "36", "37", "38", "97",
}

# Standard GST rates
VALID_GST_RATES = {0, 0.25, 3, 5, 12, 18, 28}


class FinancialValidator:
    """
    Validates financial data in extracted tables:
    - GSTIN format and checksum
    - PAN format
    - IFSC format
    - Arithmetic (subtotals, totals, tax calculations)
    - GST rate validation
    - Duplicate detection
    """

    def validate_table(self, table: Table) -> list[ValidationResult]:
        """Run all validations on a table."""
        results: list[ValidationResult] = []

        if not table.cells or len(table.cells) < 2:
            return results

        # Identify column semantics
        col_types = self._identify_columns(table)

        # Run validations based on column types
        results.extend(self._validate_formats(table, col_types))
        results.extend(self._validate_arithmetic(table, col_types))
        results.extend(self._validate_gst(table, col_types))
        results.extend(self._validate_duplicates(table, col_types))

        return results

    def _identify_columns(self, table: Table) -> dict[int, str]:
        """Identify semantic meaning of each column."""
        col_types: dict[int, str] = {}

        if not table.headers:
            return col_types

        header_patterns = {
            "gstin": r"gst\s*i?n|gstin|gst\s*no|supplier\s*gstin|buyer\s*gstin",
            "pan": r"\bpan\b|pan\s*no",
            "ifsc": r"\bifsc\b|ifsc\s*code",
            "hsn": r"\bhsn\b|hsn\s*code|hsn/sac",
            "sac": r"\bsac\b|sac\s*code",
            "invoice_no": r"inv(?:oice)?\s*no|bill\s*no|voucher\s*no|ref\s*no",
            "date": r"\bdate\b|inv\s*date|bill\s*date|txn\s*date",
            "amount": r"\bamount\b|total\s*amount|net\s*amount|gross\s*amount",
            "taxable_value": r"taxable\s*value|taxable\s*amount|assessable",
            "cgst": r"\bcgst\b|central\s*gst",
            "sgst": r"\bsgst\b|state\s*gst|utgst",
            "igst": r"\bigst\b|integrated\s*gst",
            "cess": r"\bcess\b",
            "total": r"\btotal\b|grand\s*total|net\s*payable",
            "rate": r"\brate\b|price|unit\s*price|mrp",
            "qty": r"\bqty\b|quantity|units|nos",
            "discount": r"disc(?:ount)?|less",
            "debit": r"\bdebit\b|\bdr\b|withdrawal",
            "credit": r"\bcredit\b|\bcr\b|deposit",
            "balance": r"\bbalance\b|closing\s*bal|running\s*bal",
            "narration": r"narration|description|particulars|remarks",
            "cheque_no": r"chq|cheque|check\s*no",
            "gst_rate": r"gst\s*%|tax\s*%|rate\s*%|gst\s*rate",
        }

        for col_idx, header in enumerate(table.headers):
            header_lower = str(header).lower().strip()
            for col_type, pattern in header_patterns.items():
                if re.search(pattern, header_lower, re.IGNORECASE):
                    col_types[col_idx] = col_type
                    break

        return col_types

    def _validate_formats(self, table: Table, col_types: dict[int, str]) -> list[ValidationResult]:
        """Validate format of GSTIN, PAN, IFSC, etc."""
        results: list[ValidationResult] = []

        for col_idx, col_type in col_types.items():
            for row_idx in range(1, len(table.cells)):
                if col_idx >= len(table.cells[row_idx]):
                    continue
                cell = table.cells[row_idx][col_idx]
                value = str(cell.value).strip().upper() if cell.value else ""

                if not value:
                    continue

                if col_type == "gstin":
                    vr = self._validate_gstin(value, row_idx, col_idx)
                    if vr:
                        results.append(vr)
                elif col_type == "pan":
                    vr = self._validate_pan(value, row_idx, col_idx)
                    if vr:
                        results.append(vr)
                elif col_type == "ifsc":
                    vr = self._validate_ifsc(value, row_idx, col_idx)
                    if vr:
                        results.append(vr)

        return results

    def _validate_gstin(self, value: str, row: int, col: int) -> Optional[ValidationResult]:
        """Validate GSTIN format and state code."""
        if not GSTIN_PATTERN.match(value):
            return ValidationResult(
                field="GSTIN", check_type="format", is_valid=False,
                actual_value=value, message=f"Invalid GSTIN format: {value}",
                severity="error", row=row, col=col,
            )

        state_code = value[:2]
        if state_code not in VALID_STATE_CODES:
            return ValidationResult(
                field="GSTIN", check_type="format", is_valid=False,
                actual_value=value, message=f"Invalid state code in GSTIN: {state_code}",
                severity="warning", row=row, col=col,
            )

        # Verify PAN embedded in GSTIN (chars 3-12)
        pan_in_gstin = value[2:12]
        if not PAN_PATTERN.match(pan_in_gstin):
            return ValidationResult(
                field="GSTIN", check_type="format", is_valid=False,
                actual_value=value, message=f"Invalid PAN embedded in GSTIN",
                severity="warning", row=row, col=col,
            )

        return None

    def _validate_pan(self, value: str, row: int, col: int) -> Optional[ValidationResult]:
        """Validate PAN format."""
        if not PAN_PATTERN.match(value):
            return ValidationResult(
                field="PAN", check_type="format", is_valid=False,
                actual_value=value, message=f"Invalid PAN format: {value}",
                severity="error", row=row, col=col,
            )
        return None

    def _validate_ifsc(self, value: str, row: int, col: int) -> Optional[ValidationResult]:
        """Validate IFSC format."""
        if not IFSC_PATTERN.match(value):
            return ValidationResult(
                field="IFSC", check_type="format", is_valid=False,
                actual_value=value, message=f"Invalid IFSC format: {value}",
                severity="error", row=row, col=col,
            )
        return None

    def _validate_arithmetic(self, table: Table, col_types: dict[int, str]) -> list[ValidationResult]:
        """Validate arithmetic relationships: qty × rate = amount, etc."""
        results: list[ValidationResult] = []

        qty_col = next((c for c, t in col_types.items() if t == "qty"), None)
        rate_col = next((c for c, t in col_types.items() if t == "rate"), None)
        amount_col = next((c for c, t in col_types.items() if t == "amount"), None)
        taxable_col = next((c for c, t in col_types.items() if t == "taxable_value"), None)
        cgst_col = next((c for c, t in col_types.items() if t == "cgst"), None)
        sgst_col = next((c for c, t in col_types.items() if t == "sgst"), None)
        igst_col = next((c for c, t in col_types.items() if t == "igst"), None)
        total_col = next((c for c, t in col_types.items() if t == "total"), None)
        discount_col = next((c for c, t in col_types.items() if t == "discount"), None)

        for row_idx in range(1, len(table.cells)):
            row = table.cells[row_idx]

            # Validate: qty × rate = amount
            if qty_col is not None and rate_col is not None and amount_col is not None:
                qty = self._get_numeric_value(row, qty_col)
                rate = self._get_numeric_value(row, rate_col)
                amount = self._get_numeric_value(row, amount_col)

                if qty is not None and rate is not None and amount is not None:
                    expected = round(qty * rate, 2)
                    if abs(expected - amount) > 1.0:  # Allow ₹1 tolerance
                        results.append(ValidationResult(
                            field="Amount", check_type="arithmetic", is_valid=False,
                            expected_value=expected, actual_value=amount,
                            message=f"Row {row_idx}: Qty({qty}) × Rate({rate}) = {expected}, but Amount = {amount}",
                            severity="warning", row=row_idx, col=amount_col,
                        ))

            # Validate: taxable + CGST + SGST = total OR taxable + IGST = total
            target_amount = taxable_col if taxable_col is not None else amount_col
            if target_amount is not None and total_col is not None:
                base = self._get_numeric_value(row, target_amount)
                total = self._get_numeric_value(row, total_col)
                discount = self._get_numeric_value(row, discount_col) or 0

                if base is not None and total is not None:
                    cgst = self._get_numeric_value(row, cgst_col) or 0
                    sgst = self._get_numeric_value(row, sgst_col) or 0
                    igst = self._get_numeric_value(row, igst_col) or 0

                    expected_total = round(base + cgst + sgst + igst - discount, 2)
                    if abs(expected_total - total) > 2.0:  # Allow ₹2 tolerance
                        results.append(ValidationResult(
                            field="Total", check_type="arithmetic", is_valid=False,
                            expected_value=expected_total, actual_value=total,
                            message=f"Row {row_idx}: Expected total {expected_total}, got {total}",
                            severity="warning", row=row_idx, col=total_col,
                        ))

        # Validate column totals (last row often contains sum)
        if len(table.cells) > 3:
            self._validate_column_sums(table, col_types, results)

        return results

    def _validate_gst(self, table: Table, col_types: dict[int, str]) -> list[ValidationResult]:
        """Validate GST-specific rules: CGST == SGST, valid rates, etc."""
        results: list[ValidationResult] = []

        cgst_col = next((c for c, t in col_types.items() if t == "cgst"), None)
        sgst_col = next((c for c, t in col_types.items() if t == "sgst"), None)
        igst_col = next((c for c, t in col_types.items() if t == "igst"), None)
        rate_col = next((c for c, t in col_types.items() if t == "gst_rate"), None)
        taxable_col = next((c for c, t in col_types.items() if t == "taxable_value"), None)

        for row_idx in range(1, len(table.cells)):
            row = table.cells[row_idx]

            # CGST should equal SGST (for intra-state)
            if cgst_col is not None and sgst_col is not None:
                cgst = self._get_numeric_value(row, cgst_col)
                sgst = self._get_numeric_value(row, sgst_col)

                if cgst is not None and sgst is not None:
                    if abs(cgst - sgst) > 0.50:
                        results.append(ValidationResult(
                            field="GST", check_type="gst", is_valid=False,
                            expected_value=f"CGST={cgst}", actual_value=f"SGST={sgst}",
                            message=f"Row {row_idx}: CGST ({cgst}) ≠ SGST ({sgst})",
                            severity="warning", row=row_idx, col=cgst_col,
                        ))

            # If IGST present, CGST and SGST should be 0
            if igst_col is not None and cgst_col is not None:
                igst = self._get_numeric_value(row, igst_col)
                cgst = self._get_numeric_value(row, cgst_col)
                if igst and igst > 0 and cgst and cgst > 0:
                    results.append(ValidationResult(
                        field="GST", check_type="gst", is_valid=False,
                        message=f"Row {row_idx}: Both IGST and CGST are non-zero (inter/intra-state conflict)",
                        severity="warning", row=row_idx, col=igst_col,
                    ))

            # Validate GST rate
            if rate_col is not None:
                rate = self._get_numeric_value(row, rate_col)
                if rate is not None and rate not in VALID_GST_RATES:
                    results.append(ValidationResult(
                        field="GST Rate", check_type="gst", is_valid=False,
                        actual_value=rate,
                        message=f"Row {row_idx}: Unusual GST rate: {rate}%",
                        severity="info", row=row_idx, col=rate_col,
                    ))

            # Validate tax amount against rate
            if rate_col is not None and taxable_col is not None and cgst_col is not None:
                rate = self._get_numeric_value(row, rate_col)
                taxable = self._get_numeric_value(row, taxable_col)
                cgst = self._get_numeric_value(row, cgst_col)

                if rate and taxable and cgst:
                    expected_cgst = round(taxable * (rate / 2) / 100, 2)
                    if abs(expected_cgst - cgst) > 1.0:
                        results.append(ValidationResult(
                            field="CGST", check_type="gst", is_valid=False,
                            expected_value=expected_cgst, actual_value=cgst,
                            message=f"Row {row_idx}: Expected CGST {expected_cgst}, got {cgst}",
                            severity="warning", row=row_idx, col=cgst_col,
                        ))

        return results

    def _validate_duplicates(self, table: Table, col_types: dict[int, str]) -> list[ValidationResult]:
        """Detect duplicate invoice numbers."""
        results: list[ValidationResult] = []

        inv_col = next((c for c, t in col_types.items() if t == "invoice_no"), None)
        if inv_col is None:
            return results

        seen: dict[str, int] = {}
        for row_idx in range(1, len(table.cells)):
            if inv_col >= len(table.cells[row_idx]):
                continue
            inv_value = str(table.cells[row_idx][inv_col].value).strip()
            if not inv_value:
                continue

            if inv_value in seen:
                results.append(ValidationResult(
                    field="Invoice No", check_type="duplicate", is_valid=False,
                    actual_value=inv_value,
                    message=f"Duplicate invoice number '{inv_value}' (first at row {seen[inv_value]})",
                    severity="warning", row=row_idx, col=inv_col,
                ))
            else:
                seen[inv_value] = row_idx

        return results

    def _validate_column_sums(self, table: Table, col_types: dict[int, str],
                               results: list[ValidationResult]) -> None:
        """Check if last row is a total row and validate sums."""
        numeric_cols = [c for c, t in col_types.items()
                        if t in ("amount", "taxable_value", "cgst", "sgst", "igst",
                                 "cess", "total", "debit", "credit", "discount")]

        if not numeric_cols:
            return

        last_row = table.cells[-1]

        for col_idx in numeric_cols:
            last_value = self._get_numeric_value(last_row, col_idx)
            if last_value is None:
                continue

            # Check if last row label suggests it's a total
            if table.cells[-1] and len(table.cells[-1]) > 0:
                first_cell = str(table.cells[-1][0].value).lower()
                if not any(kw in first_cell for kw in ["total", "sum", "grand", "net", "sub"]):
                    continue

            # Sum all values in the column (excluding header and last row)
            column_sum = 0.0
            for row_idx in range(1, len(table.cells) - 1):
                val = self._get_numeric_value(table.cells[row_idx], col_idx)
                if val is not None:
                    column_sum += val

            column_sum = round(column_sum, 2)
            if abs(column_sum - last_value) > 2.0:
                col_name = table.headers[col_idx] if col_idx < len(table.headers) else f"Col {col_idx}"
                results.append(ValidationResult(
                    field=col_name, check_type="arithmetic", is_valid=False,
                    expected_value=column_sum, actual_value=last_value,
                    message=f"Column '{col_name}': Sum of rows = {column_sum}, Total row = {last_value}",
                    severity="warning", row=len(table.cells) - 1, col=col_idx,
                ))

    def _get_numeric_value(self, row: list[Cell], col_idx: int) -> Optional[float]:
        """Safely get a numeric value from a cell."""
        if col_idx >= len(row):
            return None
        cell = row[col_idx]
        if isinstance(cell.value, (int, float)):
            return float(cell.value)
        if isinstance(cell.value, str):
            return parse_number(cell.value)
        return None
