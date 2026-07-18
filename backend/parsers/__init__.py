"""
Parser package — Unified interface to all document parsers.
"""
from __future__ import annotations

import logging
from pathlib import Path

from backend.models import ProcessingResult
from config import Config

logger = logging.getLogger(__name__)


class ParserFactory:
    """
    Factory that selects the appropriate parser based on file extension.
    """

    def __init__(self, ocr_manager=None, preprocessor=None):
        self.ocr_manager = ocr_manager
        self.preprocessor = preprocessor

    def parse(self, file_path: str | Path, password: str | None = None) -> ProcessingResult:
        """Parse any supported file format."""
        path = Path(file_path)
        ext = path.suffix.lower().lstrip(".")
        category = Config.get_file_category(ext)

        logger.info(f"Parsing file: {path.name} (category={category}, ext={ext})")

        if category == "pdf":
            from backend.parsers.pdf_parser import PDFParser
            parser = PDFParser(ocr_manager=self.ocr_manager, preprocessor=self.preprocessor)
            return parser.parse(file_path, password=password)

        elif category == "image":
            from backend.parsers.image_parser import ImageParser
            parser = ImageParser(ocr_manager=self.ocr_manager, preprocessor=self.preprocessor)
            return parser.parse(file_path)

        elif category == "word":
            from backend.parsers.word_parser import WordParser
            return WordParser().parse(file_path)

        elif category == "excel":
            from backend.parsers.excel_parser import ExcelParser
            return ExcelParser().parse(file_path)

        elif category == "text":
            from backend.parsers.other_parsers import TextParser
            return TextParser().parse(file_path)

        elif category == "data":
            if ext in ("html", "htm"):
                from backend.parsers.other_parsers import HTMLParser
                return HTMLParser().parse(file_path)
            else:
                from backend.parsers.other_parsers import XMLJSONParser
                return XMLJSONParser().parse(file_path)

        elif category == "email":
            from backend.parsers.other_parsers import EmailParser
            return EmailParser().parse(file_path)

        elif category == "powerpoint":
            from backend.parsers.other_parsers import PPTParser
            return PPTParser().parse(file_path)

        elif category == "archive":
            from backend.parsers.other_parsers import ZIPParser
            parser = ZIPParser(process_file_callback=self.parse)
            return parser.parse(file_path)

        else:
            result = ProcessingResult()
            result.filename = path.name
            result.mark_failed(f"Unsupported file format: .{ext}")
            return result
