"""
Image Parser — Handles all image formats with preprocessing and OCR.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path

import numpy as np

from backend.models import ProcessingResult, ProcessingStatus, Table
from backend.utils import release_memory

logger = logging.getLogger(__name__)


class ImageParser:
    """
    Parses images (JPG, PNG, TIFF, BMP, etc.) using OCR with preprocessing.
    Handles rotation, skew, noise, and other common scanning issues.
    """

    def __init__(self, ocr_manager=None, preprocessor=None):
        self.ocr_manager = ocr_manager
        self.preprocessor = preprocessor

    def parse(self, file_path: str | Path) -> ProcessingResult:
        """Parse an image file and extract tables."""
        result = ProcessingResult()
        result.filename = Path(file_path).name
        result.file_category = "image"
        result.page_count = 1
        start_time = time.time()

        try:
            result.status = ProcessingStatus.PREPROCESSING
            image = self._load_image(str(file_path))

            if image is None:
                result.mark_failed("Failed to load image")
                return result

            # Auto-crop document from background
            if self.preprocessor:
                image = self.preprocessor.auto_crop_document(image)

            # Preprocess for OCR
            result.status = ProcessingStatus.OCR_IN_PROGRESS
            if self.preprocessor:
                processed = self.preprocessor.preprocess(image)
            else:
                processed = image

            # Run OCR
            if self.ocr_manager is None:
                result.mark_failed("No OCR engine available")
                return result

            from backend.ocr import TableFromOCR
            ocr_result = self.ocr_manager.ocr_image(processed)
            result.ocr_engine_used = ocr_result.engine_used

            # Extract tables from OCR result
            extractor = TableFromOCR()
            tables = extractor.extract_tables(ocr_result)

            if tables:
                result.tables.extend(tables)
            else:
                # Try without preprocessing as fallback
                ocr_result2 = self.ocr_manager.ocr_image(image)
                tables2 = extractor.extract_tables(ocr_result2)
                if tables2:
                    result.tables.extend(tables2)
                    result.ocr_engine_used = ocr_result2.engine_used
                else:
                    result.warnings.append("No tables detected in the image")

            result.status = ProcessingStatus.READY_FOR_REVIEW
            result.processing_time = time.time() - start_time

            # Clean up
            del image, processed
            release_memory()

        except Exception as e:
            result.mark_failed(f"Image parsing failed: {str(e)}")
            logger.error(f"Image parsing error: {e}", exc_info=True)

        return result

    def _load_image(self, file_path: str) -> np.ndarray | None:
        """Load image from file, handling various formats."""
        try:
            import cv2

            ext = Path(file_path).suffix.lower()

            # Handle HEIC/HEIF
            if ext in ('.heic', '.heif'):
                return self._load_heic(file_path)

            # Standard image loading
            image = cv2.imread(file_path, cv2.IMREAD_COLOR)

            if image is None:
                # Try with PIL as fallback
                return self._load_with_pil(file_path)

            return image

        except Exception as e:
            logger.error(f"Failed to load image {file_path}: {e}")
            return self._load_with_pil(file_path)

    def _load_with_pil(self, file_path: str) -> np.ndarray | None:
        """Load image using PIL as fallback."""
        try:
            from PIL import Image
            import cv2

            pil_image = Image.open(file_path)
            pil_image = pil_image.convert("RGB")
            img_array = np.array(pil_image)
            # Convert RGB to BGR for OpenCV
            img_array = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
            pil_image.close()
            return img_array
        except Exception as e:
            logger.error(f"PIL fallback failed: {e}")
            return None

    def _load_heic(self, file_path: str) -> np.ndarray | None:
        """Load HEIC/HEIF images."""
        try:
            from PIL import Image
            import cv2

            try:
                import pillow_heif
                pillow_heif.register_heif_opener()
            except ImportError:
                logger.warning("pillow-heif not installed, HEIC support limited")

            pil_image = Image.open(file_path)
            pil_image = pil_image.convert("RGB")
            img_array = np.array(pil_image)
            img_array = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
            pil_image.close()
            return img_array
        except Exception as e:
            logger.error(f"HEIC loading failed: {e}")
            return None
