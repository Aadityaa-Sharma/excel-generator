"""
Smart Detection — Column semantic mapping and document type classification.
Infers column meanings and document types from content patterns.
"""
from __future__ import annotations

import logging
import re
from collections import Counter
from typing import Optional

from backend.models import Cell, Table, DocumentType

logger = logging.getLogger(__name__)


# ── Semantic Column Mappings ────────────────────────────────────────────────

COLUMN_PATTERNS = {
    "Date": [
        r"\bdate\b", r"\bdt\b", r"txn\s*date", r"trans(?:action)?\s*date",
        r"invoice\s*date", r"bill\s*date", r"entry\s*date", r"value\s*date",
        r"posting\s*date", r"cheque\s*date",
    ],
    "Invoice No": [
        r"inv(?:oice)?\s*no", r"bill\s*no", r"ref\s*no", r"reference\s*no",
        r"doc(?:ument)?\s*no", r"voucher\s*no", r"receipt\s*no",
    ],
    "GSTIN": [
        r"gst\s*i?n", r"gstin", r"gst\s*no", r"supplier\s*gst",
        r"buyer\s*gst", r"party\s*gst",
    ],
    "PAN": [r"\bpan\b", r"pan\s*no", r"pan\s*number"],
    "Vendor/Supplier": [
        r"vendor", r"supplier", r"party\s*name", r"seller",
        r"from", r"billed\s*by", r"consignor",
    ],
    "Customer/Buyer": [
        r"customer", r"buyer", r"client", r"bill\s*to",
        r"ship\s*to", r"sold\s*to", r"consignee",
    ],
    "Description": [
        r"desc(?:ription)?", r"particular", r"item", r"product",
        r"narration", r"details", r"remark", r"goods",
    ],
    "HSN/SAC": [r"hsn", r"sac", r"hsn/sac", r"hsn\s*code", r"sac\s*code"],
    "Qty": [r"\bqty\b", r"quantity", r"units?", r"\bnos?\b", r"pcs"],
    "Rate": [
        r"\brate\b", r"price", r"unit\s*price", r"mrp",
        r"unit\s*rate", r"per\s*unit",
    ],
    "Amount": [
        r"\bamount\b", r"\bamt\b", r"total\s*amount", r"net\s*amount",
        r"gross\s*amount", r"value", r"line\s*total",
    ],
    "Taxable Value": [
        r"taxable\s*value", r"taxable\s*amount", r"assessable",
        r"base\s*amount", r"net\s*value",
    ],
    "Discount": [r"disc(?:ount)?", r"less", r"rebate", r"allowance"],
    "CGST": [r"\bcgst\b", r"central\s*gst", r"cgst\s*amt"],
    "SGST": [r"\bsgst\b", r"state\s*gst", r"sgst\s*amt", r"utgst"],
    "IGST": [r"\bigst\b", r"integrated\s*gst", r"igst\s*amt"],
    "CESS": [r"\bcess\b", r"cess\s*amount"],
    "GST Rate %": [r"gst\s*%", r"tax\s*%", r"rate\s*%", r"gst\s*rate", r"tax\s*rate"],
    "Total": [
        r"\btotal\b", r"grand\s*total", r"net\s*payable",
        r"invoice\s*total", r"bill\s*total",
    ],
    "Debit": [r"\bdebit\b", r"\bdr\b", r"withdrawal"],
    "Credit": [r"\bcredit\b", r"\bcr\b", r"deposit"],
    "Balance": [r"\bbalance\b", r"closing\s*bal", r"running\s*bal", r"avail\s*bal"],
    "Narration": [r"narration", r"description", r"memo", r"remark", r"particular"],
    "Cheque No": [r"chq", r"cheque", r"check\s*no", r"instrument"],
    "Reference": [r"\bref\b", r"reference", r"utr", r"txn\s*id"],
    "Bank": [r"\bbank\b", r"bank\s*name"],
    "IFSC": [r"\bifsc\b", r"ifsc\s*code"],
    "Account No": [r"a/?c\s*no", r"account\s*no", r"acct"],
    "Place of Supply": [r"place\s*of\s*supply", r"pos", r"state"],
    "Round Off": [r"round\s*off", r"rounding"],
    "TDS": [r"\btds\b", r"tax\s*deducted"],
    "TCS": [r"\btcs\b", r"tax\s*collected"],
    "Sr No": [r"sr\s*no", r"s\.?\s*no", r"sl\s*no", r"#", r"sno", r"\bno\b"],
}


class SmartColumnDetector:
    """
    Detects semantic meaning of table columns using header text and data patterns.
    Renames generic OCR headers to meaningful names.
    """

    def detect_and_rename(self, table: Table) -> Table:
        """Analyze and rename columns with semantic labels."""
        if not table.cells or not table.headers:
            return table

        for col_idx, header in enumerate(table.headers):
            semantic = self._match_header(str(header))

            if semantic:
                # Update header
                table.headers[col_idx] = semantic

                # Update header cell
                if table.cells and col_idx < len(table.cells[0]):
                    table.cells[0][col_idx].semantic_label = semantic.lower().replace(" ", "_")
                    table.cells[0][col_idx].value = semantic

                # Update data cells
                for row in table.cells[1:]:
                    if col_idx < len(row):
                        row[col_idx].semantic_label = semantic.lower().replace(" ", "_")
            else:
                # Try to infer from data
                inferred = self._infer_from_data(table, col_idx)
                if inferred:
                    table.headers[col_idx] = inferred
                    if table.cells and col_idx < len(table.cells[0]):
                        table.cells[0][col_idx].semantic_label = inferred.lower().replace(" ", "_")
                        table.cells[0][col_idx].value = inferred

        return table

    def _match_header(self, header: str) -> Optional[str]:
        """Match header text to semantic column name."""
        header_lower = header.lower().strip()

        if not header_lower or header_lower in ("", "-", "nan", "none"):
            return None

        for semantic_name, patterns in COLUMN_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, header_lower, re.IGNORECASE):
                    return semantic_name

        return None

    def _infer_from_data(self, table: Table, col_idx: int) -> Optional[str]:
        """Infer column type from data patterns."""
        from backend.validators import GSTIN_PATTERN, PAN_PATTERN, IFSC_PATTERN

        samples = []
        for row in table.cells[1:min(len(table.cells), 11)]:  # Check first 10 data rows
            if col_idx < len(row):
                val = str(row[col_idx].value).strip()
                if val:
                    samples.append(val)

        if not samples:
            return None

        # Check if all values match GSTIN
        if all(GSTIN_PATTERN.match(s.upper()) for s in samples if len(s) == 15):
            return "GSTIN"

        # Check if all values match PAN
        if all(PAN_PATTERN.match(s.upper()) for s in samples if len(s) == 10):
            return "PAN"

        # Check if all values match IFSC
        if all(IFSC_PATTERN.match(s.upper()) for s in samples if len(s) == 11):
            return "IFSC"

        # Check if all values look like dates
        date_pattern = re.compile(r'\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4}')
        if sum(1 for s in samples if date_pattern.match(s)) > len(samples) * 0.7:
            return "Date"

        # Check if all values are sequential numbers (Sr No)
        try:
            nums = [int(re.sub(r'[^\d]', '', s)) for s in samples if re.sub(r'[^\d]', '', s)]
            if nums and nums == list(range(nums[0], nums[0] + len(nums))):
                return "Sr No"
        except (ValueError, TypeError):
            pass

        return None


# ── Document Type Classifier ───────────────────────────────────────────────

DOCUMENT_KEYWORDS = {
    DocumentType.INVOICE: [
        "invoice", "tax invoice", "bill", "gst invoice", "retail bill",
        "proforma invoice", "commercial invoice",
    ],
    DocumentType.BANK_STATEMENT: [
        "bank statement", "account statement", "transaction history",
        "passbook", "statement of account",
    ],
    DocumentType.GST_RETURN: [
        "gstr", "gst return", "gstr-1", "gstr-3b", "gstr-9",
        "gstr-2a", "gstr-2b", "gst annual",
    ],
    DocumentType.TAX_FORM: [
        "form 16", "form 16a", "tds certificate", "income tax",
        "form 26as", "ais", "tis", "challan",
    ],
    DocumentType.BALANCE_SHEET: [
        "balance sheet", "statement of affairs", "financial position",
    ],
    DocumentType.PROFIT_LOSS: [
        "profit and loss", "profit & loss", "p&l", "income statement",
        "statement of income",
    ],
    DocumentType.TRIAL_BALANCE: ["trial balance"],
    DocumentType.LEDGER: ["ledger", "general ledger", "sub ledger", "account ledger"],
    DocumentType.SALARY_SLIP: [
        "salary slip", "pay slip", "payslip", "wage slip",
        "pay stub", "salary statement",
    ],
    DocumentType.RECEIPT: ["receipt", "acknowledgement", "payment receipt"],
    DocumentType.BILL: [
        "electricity bill", "telephone bill", "water bill",
        "gas bill", "utility bill", "internet bill",
    ],
    DocumentType.VOUCHER: [
        "voucher", "payment voucher", "cash voucher",
        "journal voucher", "debit voucher", "credit voucher",
    ],
    DocumentType.CREDIT_NOTE: ["credit note", "cr note"],
    DocumentType.DEBIT_NOTE: ["debit note", "dr note"],
    DocumentType.PURCHASE_ORDER: ["purchase order", "po", "work order"],
    DocumentType.DELIVERY_NOTE: ["delivery note", "delivery challan", "dc"],
    DocumentType.QUOTATION: ["quotation", "quote", "estimate", "proforma"],
    DocumentType.CHEQUE: ["cheque", "check", "cancelled cheque"],
    DocumentType.FORM_16: ["form 16", "form no. 16"],
    DocumentType.FORM_26AS: ["form 26as", "26as"],
    DocumentType.STOCK_REGISTER: ["stock register", "inventory", "stock ledger"],
    DocumentType.FIXED_ASSET: ["fixed asset", "asset register", "depreciation"],
    DocumentType.INSURANCE: ["insurance", "policy", "premium"],
    DocumentType.LOAN_STATEMENT: ["loan statement", "emi", "loan account"],
    DocumentType.INVESTMENT_STATEMENT: [
        "investment", "mutual fund", "demat", "portfolio",
        "capital gain", "dividend",
    ],
    DocumentType.ATTENDANCE: ["attendance", "time sheet", "muster"],
    DocumentType.PAYROLL: ["payroll", "salary register", "wage register"],
}

HEADER_SIGNATURES = {
    DocumentType.BANK_STATEMENT: {"date", "narration", "debit", "credit", "balance"},
    DocumentType.INVOICE: {"description", "qty", "rate", "amount", "hsn", "gst"},
    DocumentType.SALARY_SLIP: {"basic", "hra", "da", "deduction", "net pay", "gross"},
    DocumentType.TRIAL_BALANCE: {"debit", "credit", "ledger", "account"},
    DocumentType.LEDGER: {"date", "particular", "debit", "credit", "balance"},
}


class DocumentClassifier:
    """Classifies document type from content and table structure."""

    def classify(self, text: str = "", tables: list[Table] | None = None,
                 filename: str = "") -> DocumentType:
        """Classify document type using multiple signals."""
        scores: Counter = Counter()

        # Signal 1: Filename
        if filename:
            fname_lower = filename.lower()
            for doc_type, keywords in DOCUMENT_KEYWORDS.items():
                for kw in keywords:
                    if kw in fname_lower:
                        scores[doc_type] += 3

        # Signal 2: Full text content
        if text:
            text_lower = text.lower()
            for doc_type, keywords in DOCUMENT_KEYWORDS.items():
                for kw in keywords:
                    if kw in text_lower:
                        scores[doc_type] += 2

        # Signal 3: Table headers
        if tables:
            for table in tables:
                headers_set = {h.lower().strip() for h in table.headers if h}
                for doc_type, sig_headers in HEADER_SIGNATURES.items():
                    matches = headers_set & sig_headers
                    if len(matches) >= 2:
                        scores[doc_type] += len(matches) * 2

        if scores:
            best = scores.most_common(1)[0]
            logger.debug(f"Document classified as: {best[0].value} (score={best[1]})")
            return best[0]

        return DocumentType.GENERIC_TABLE
