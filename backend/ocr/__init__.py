"""
OCR Engine Manager — Hybrid OCR pipeline with fallback chain.
Lazy-loads engines on first use and caches them in memory.
Supports: PaddleOCR → Tesseract → EasyOCR with automatic fallback.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Optional

import numpy as np

from backend.models import Cell, Table
from backend.utils import release_memory

logger = logging.getLogger(__name__)

# ── Cached engine instances (lazy-loaded) ───────────────────────────────────
_paddle_engine = None
_easy_engine = None
_engine_availability: dict[str, bool | None] = {
    "paddleocr": None,
    "tesseract": None,
    "easyocr": None,
}


def _check_engine_available(name: str) -> bool:
    """Check if an OCR engine is importable."""
    global _engine_availability
    if _engine_availability[name] is not None:
        return _engine_availability[name]

    try:
        if name == "paddleocr":
            import paddleocr  # noqa: F401
            _engine_availability[name] = True
        elif name == "tesseract":
            import pytesseract  # noqa: F401
            _engine_availability[name] = True
        elif name == "easyocr":
            import easyocr  # noqa: F401
            _engine_availability[name] = True
        else:
            _engine_availability[name] = False
    except ImportError:
        _engine_availability[name] = False
        logger.info(f"OCR engine '{name}' not available")

    return _engine_availability[name]


def _get_paddle_engine():
    """Lazy-load and cache PaddleOCR."""
    global _paddle_engine
    if _paddle_engine is None:
        from paddleocr import PaddleOCR
        logger.info("Loading PaddleOCR engine...")
        _paddle_engine = PaddleOCR(
            use_angle_cls=True,
            lang="en",
            show_log=False,
            use_gpu=False,
            enable_mkldnn=True,
            rec_batch_num=6,
        )
        logger.info("PaddleOCR loaded successfully")
    return _paddle_engine


def _get_easy_engine(languages: list[str] | None = None):
    """Lazy-load and cache EasyOCR."""
    global _easy_engine
    if _easy_engine is None:
        import easyocr
        langs = languages or ["en"]
        logger.info(f"Loading EasyOCR engine with languages: {langs}")
        _easy_engine = easyocr.Reader(langs, gpu=False)
        logger.info("EasyOCR loaded successfully")
    return _easy_engine


class OCRResult:
    """Standardized OCR result from any engine."""

    def __init__(self):
        self.text_blocks: list[dict] = []  # [{text, confidence, bbox, line_num}]
        self.full_text: str = ""
        self.engine_used: str = ""
        self.processing_time: float = 0.0
        self.page_number: int = 1

    def to_dict(self) -> dict:
        return {
            "text_blocks": self.text_blocks,
            "full_text": self.full_text,
            "engine_used": self.engine_used,
            "processing_time": round(self.processing_time, 3),
            "page_number": self.page_number,
        }


class OCREngineManager:
    """
    Manages OCR engine selection and provides a unified interface.
    Implements hybrid extraction with automatic fallback.
    """

    def __init__(self, engine_priority: list[str] | None = None,
                 confidence_threshold: float = 0.6,
                 languages: list[str] | None = None):
        self.engine_priority = engine_priority or ["paddleocr", "tesseract", "easyocr"]
        self.confidence_threshold = confidence_threshold
        self.languages = languages or ["en"]
        self._available_engines: list[str] = []
        self._detect_available_engines()

    def _detect_available_engines(self) -> None:
        """Detect which OCR engines are available."""
        for engine in self.engine_priority:
            if _check_engine_available(engine):
                self._available_engines.append(engine)
        logger.info(f"Available OCR engines: {self._available_engines}")

    @property
    def available_engines(self) -> list[str]:
        return self._available_engines.copy()

    def ocr_image(self, image: np.ndarray, page_number: int = 1) -> OCRResult:
        """
        Run OCR on an image using the best available engine.
        Falls back to the next engine if the current one fails or produces low-confidence results.
        """
        best_result: OCRResult | None = None
        best_avg_confidence: float = 0.0

        for engine_name in self._available_engines:
            try:
                logger.debug(f"Trying OCR engine: {engine_name}")
                start = time.time()

                result = self._run_engine(engine_name, image)
                result.page_number = page_number
                result.processing_time = time.time() - start

                # Calculate average confidence
                if result.text_blocks:
                    avg_conf = sum(b["confidence"] for b in result.text_blocks) / len(result.text_blocks)
                else:
                    avg_conf = 0.0

                logger.debug(
                    f"{engine_name}: {len(result.text_blocks)} blocks, "
                    f"avg confidence={avg_conf:.3f}, time={result.processing_time:.2f}s"
                )

                # If confidence is good enough, use this result
                if avg_conf >= self.confidence_threshold:
                    return result

                # Track best result as fallback
                if avg_conf > best_avg_confidence:
                    best_avg_confidence = avg_conf
                    best_result = result

            except Exception as e:
                logger.warning(f"OCR engine {engine_name} failed: {e}")
                continue

        # Return best result we found, even if below threshold
        if best_result:
            return best_result

        # All engines failed, return empty result
        logger.error("All OCR engines failed")
        empty = OCRResult()
        empty.engine_used = "none"
        return empty

    def _run_engine(self, engine_name: str, image: np.ndarray) -> OCRResult:
        """Run a specific OCR engine on an image."""
        if engine_name == "paddleocr":
            return self._run_paddleocr(image)
        elif engine_name == "tesseract":
            return self._run_tesseract(image)
        elif engine_name == "easyocr":
            return self._run_easyocr(image)
        else:
            raise ValueError(f"Unknown engine: {engine_name}")

    def _run_paddleocr(self, image: np.ndarray) -> OCRResult:
        """Run PaddleOCR."""
        engine = _get_paddle_engine()
        raw_result = engine.ocr(image, cls=True)

        result = OCRResult()
        result.engine_used = "paddleocr"

        if not raw_result or not raw_result[0]:
            return result

        texts = []
        for idx, line in enumerate(raw_result[0]):
            bbox = line[0]  # [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
            text = line[1][0]
            confidence = float(line[1][1])

            # Calculate bounding box
            xs = [p[0] for p in bbox]
            ys = [p[1] for p in bbox]
            block = {
                "text": text,
                "confidence": confidence,
                "bbox": {
                    "x1": min(xs), "y1": min(ys),
                    "x2": max(xs), "y2": max(ys),
                },
                "line_num": idx,
            }
            result.text_blocks.append(block)
            texts.append(text)

        result.full_text = "\n".join(texts)
        return result

    def _run_tesseract(self, image: np.ndarray) -> OCRResult:
        """Run Tesseract OCR."""
        import pytesseract

        result = OCRResult()
        result.engine_used = "tesseract"

        # Get detailed data
        data = pytesseract.image_to_data(
            image,
            lang="+".join(self.languages) if self.languages else "eng",
            output_type=pytesseract.Output.DICT,
            config="--psm 6"  # Assume uniform block of text
        )

        texts = []
        n_boxes = len(data["text"])
        for i in range(n_boxes):
            text = data["text"][i].strip()
            conf = int(data["conf"][i])

            if not text or conf < 0:
                continue

            confidence = conf / 100.0
            block = {
                "text": text,
                "confidence": confidence,
                "bbox": {
                    "x1": data["left"][i],
                    "y1": data["top"][i],
                    "x2": data["left"][i] + data["width"][i],
                    "y2": data["top"][i] + data["height"][i],
                },
                "line_num": data["line_num"][i],
            }
            result.text_blocks.append(block)
            texts.append(text)

        result.full_text = " ".join(texts)
        return result

    def _run_easyocr(self, image: np.ndarray) -> OCRResult:
        """Run EasyOCR."""
        engine = _get_easy_engine(self.languages)

        result = OCRResult()
        result.engine_used = "easyocr"

        raw = engine.readtext(image)

        texts = []
        for idx, (bbox, text, confidence) in enumerate(raw):
            # bbox is [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]
            xs = [p[0] for p in bbox]
            ys = [p[1] for p in bbox]
            block = {
                "text": text,
                "confidence": float(confidence),
                "bbox": {
                    "x1": min(xs), "y1": min(ys),
                    "x2": max(xs), "y2": max(ys),
                },
                "line_num": idx,
            }
            result.text_blocks.append(block)
            texts.append(text)

        result.full_text = "\n".join(texts)
        return result


class TableFromOCR:
    """
    Converts raw OCR text blocks into structured table data
    by analyzing spatial positions of text blocks.
    """

    def __init__(self, row_tolerance: float = 15.0, col_tolerance: float = 30.0):
        self.row_tolerance = row_tolerance
        self.col_tolerance = col_tolerance

    def extract_tables(self, ocr_result: OCRResult) -> list[Table]:
        """Extract tables from OCR text blocks using spatial analysis."""
        if not ocr_result.text_blocks:
            return []

        blocks = ocr_result.text_blocks

        # Sort by y-position (top to bottom)
        sorted_blocks = sorted(blocks, key=lambda b: b["bbox"]["y1"])

        # Group into rows based on y-position proximity
        rows = self._group_into_rows(sorted_blocks)

        if not rows:
            return []

        # Determine column positions
        col_positions = self._detect_columns(rows)

        # Build table grid
        table = self._build_table(rows, col_positions, ocr_result)

        if table and table.row_count > 0:
            return [table]
        return []

    def _group_into_rows(self, blocks: list[dict]) -> list[list[dict]]:
        """Group text blocks into rows based on vertical position."""
        if not blocks:
            return []

        rows: list[list[dict]] = []
        current_row: list[dict] = [blocks[0]]
        current_y = blocks[0]["bbox"]["y1"]

        for block in blocks[1:]:
            y = block["bbox"]["y1"]
            if abs(y - current_y) <= self.row_tolerance:
                current_row.append(block)
            else:
                # Sort row by x-position (left to right)
                current_row.sort(key=lambda b: b["bbox"]["x1"])
                rows.append(current_row)
                current_row = [block]
                current_y = y

        if current_row:
            current_row.sort(key=lambda b: b["bbox"]["x1"])
            rows.append(current_row)

        return rows

    def _detect_columns(self, rows: list[list[dict]]) -> list[float]:
        """Detect column positions from block x-coordinates."""
        all_x_positions: list[float] = []
        for row in rows:
            for block in row:
                all_x_positions.append(block["bbox"]["x1"])

        if not all_x_positions:
            return []

        # Cluster x-positions
        all_x_positions.sort()
        columns: list[float] = [all_x_positions[0]]

        for x in all_x_positions[1:]:
            if x - columns[-1] > self.col_tolerance:
                columns.append(x)

        return columns

    def _assign_column(self, x: float, col_positions: list[float]) -> int:
        """Assign a block to the nearest column."""
        min_dist = float("inf")
        best_col = 0
        for i, col_x in enumerate(col_positions):
            dist = abs(x - col_x)
            if dist < min_dist:
                min_dist = dist
                best_col = i
        return best_col

    def _build_table(self, rows: list[list[dict]], col_positions: list[float],
                     ocr_result: OCRResult) -> Table:
        """Build a Table from grouped rows and column positions."""
        from backend.utils import detect_data_type

        num_cols = len(col_positions)
        table = Table()
        table.source_engine = ocr_result.engine_used
        table.page_number = ocr_result.page_number

        for row_idx, row_blocks in enumerate(rows):
            cells: list[Cell] = [Cell(row=row_idx, col=c) for c in range(num_cols)]

            for block in row_blocks:
                col_idx = self._assign_column(block["bbox"]["x1"], col_positions)
                if col_idx < num_cols:
                    existing = cells[col_idx]
                    if existing.value:
                        # Merge text into same cell
                        existing.value = f"{existing.value} {block['text']}"
                        existing.raw_value = existing.value
                        existing.confidence = min(existing.confidence, block["confidence"])
                    else:
                        existing.value = block["text"]
                        existing.raw_value = block["text"]
                        existing.confidence = block["confidence"]

            # Detect data types for each cell
            for cell in cells:
                if cell.value:
                    dt, parsed, fmt = detect_data_type(str(cell.value))
                    cell.data_type = dt
                    if dt in ("number", "currency", "percentage"):
                        cell.value = parsed
                    cell.format_string = fmt

                    # First row is likely header
                    if row_idx == 0:
                        cell.is_header = True
                        cell.font_bold = True

            table.cells.append(cells)

        # Extract headers
        if table.cells:
            table.headers = [str(c.value) for c in table.cells[0]]
            table.num_rows = len(table.cells)
            table.num_cols = num_cols

        return table
