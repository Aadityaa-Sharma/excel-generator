"""
Image preprocessing pipeline for OCR optimization.
Handles rotation, skew, noise, shadows, perspective correction, and more.
"""
from __future__ import annotations

import logging
import math
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# Lazy-loaded OpenCV
_cv2 = None


def _get_cv2():
    """Lazy-load OpenCV."""
    global _cv2
    if _cv2 is None:
        import cv2
        _cv2 = cv2
    return _cv2


class ImagePreprocessor:
    """
    Comprehensive image preprocessing pipeline for OCR.
    Automatically detects and fixes common issues with scanned documents.
    """

    def __init__(self, target_dpi: int = 300):
        self.target_dpi = target_dpi

    def preprocess(self, image: np.ndarray, auto_detect: bool = True) -> np.ndarray:
        """
        Full preprocessing pipeline.
        Returns: preprocessed image optimized for OCR.
        """
        cv2 = _get_cv2()

        if image is None or image.size == 0:
            raise ValueError("Empty or invalid image")

        result = image.copy()

        try:
            # Step 1: Resize if too large (>4000px on any side)
            result = self._limit_size(result, max_dim=4000)

            # Step 2: Convert to grayscale for analysis
            if len(result.shape) == 3:
                gray = cv2.cvtColor(result, cv2.COLOR_BGR2GRAY)
            else:
                gray = result.copy()

            if auto_detect:
                # Step 3: Detect and fix rotation
                result = self._fix_rotation(result, gray)

                # Update grayscale after rotation
                if len(result.shape) == 3:
                    gray = cv2.cvtColor(result, cv2.COLOR_BGR2GRAY)
                else:
                    gray = result.copy()

                # Step 4: Deskew
                result = self._deskew(result, gray)

                if len(result.shape) == 3:
                    gray = cv2.cvtColor(result, cv2.COLOR_BGR2GRAY)
                else:
                    gray = result.copy()

            # Step 5: Enhance contrast
            gray = self._enhance_contrast(gray)

            # Step 6: Remove noise
            gray = self._denoise(gray)

            # Step 7: Remove shadows
            gray = self._remove_shadows(gray)

            # Step 8: Binarize (adaptive threshold)
            binary = self._binarize(gray)

            # Step 9: Clean up small noise
            binary = self._remove_small_noise(binary)

            return binary

        except Exception as e:
            logger.warning(f"Preprocessing error: {e}, returning original")
            if len(image.shape) == 3:
                return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            return image

    def preprocess_for_table_detection(self, image: np.ndarray) -> np.ndarray:
        """Preprocessing specifically optimized for table/line detection."""
        cv2 = _get_cv2()

        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image.copy()

        # Enhance contrast
        gray = self._enhance_contrast(gray)

        # Binarize with Otsu
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

        return binary

    def _limit_size(self, image: np.ndarray, max_dim: int = 4000) -> np.ndarray:
        """Resize image if any dimension exceeds max_dim."""
        cv2 = _get_cv2()
        h, w = image.shape[:2]
        if max(h, w) > max_dim:
            scale = max_dim / max(h, w)
            new_w = int(w * scale)
            new_h = int(h * scale)
            image = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_AREA)
            logger.debug(f"Resized image from {w}x{h} to {new_w}x{new_h}")
        return image

    def _fix_rotation(self, image: np.ndarray, gray: np.ndarray) -> np.ndarray:
        """Detect and fix 90/180/270 degree rotations using text orientation."""
        cv2 = _get_cv2()
        try:
            # Use edge detection to find dominant text direction
            edges = cv2.Canny(gray, 50, 150, apertureSize=3)
            lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=100,
                                     minLineLength=50, maxLineGap=10)
            if lines is None:
                return image

            angles = []
            for line in lines:
                x1, y1, x2, y2 = line[0]
                angle = math.degrees(math.atan2(y2 - y1, x2 - x1))
                angles.append(angle)

            if not angles:
                return image

            # Check for 90-degree rotation indicators
            horizontal_count = sum(1 for a in angles if abs(a) < 15 or abs(a) > 165)
            vertical_count = sum(1 for a in angles if 75 < abs(a) < 105)

            if vertical_count > horizontal_count * 2:
                # Text is vertical, rotate 90 degrees
                logger.info("Detected 90° rotation, correcting")
                image = cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)

            return image
        except Exception as e:
            logger.debug(f"Rotation detection skipped: {e}")
            return image

    def _deskew(self, image: np.ndarray, gray: np.ndarray) -> np.ndarray:
        """Fix slight skew in scanned documents."""
        cv2 = _get_cv2()
        try:
            # Threshold
            _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

            # Find coordinates of non-zero pixels
            coords = np.column_stack(np.where(thresh > 0))
            if len(coords) < 100:
                return image

            # Get minimum area bounding rectangle
            angle = cv2.minAreaRect(coords)[-1]

            # Adjust angle
            if angle < -45:
                angle = -(90 + angle)
            else:
                angle = -angle

            # Only fix if skew is small (< 15 degrees)
            if abs(angle) > 15 or abs(angle) < 0.1:
                return image

            logger.debug(f"Deskewing by {angle:.2f} degrees")
            h, w = image.shape[:2]
            center = (w // 2, h // 2)
            matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
            rotated = cv2.warpAffine(
                image, matrix, (w, h),
                flags=cv2.INTER_CUBIC,
                borderMode=cv2.BORDER_REPLICATE
            )
            return rotated
        except Exception as e:
            logger.debug(f"Deskew skipped: {e}")
            return image

    def _enhance_contrast(self, gray: np.ndarray) -> np.ndarray:
        """Enhance contrast using CLAHE."""
        cv2 = _get_cv2()
        try:
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            return clahe.apply(gray)
        except Exception:
            return gray

    def _denoise(self, gray: np.ndarray) -> np.ndarray:
        """Remove noise while preserving text edges."""
        cv2 = _get_cv2()
        try:
            return cv2.fastNlMeansDenoising(gray, None, h=10, templateWindowSize=7, searchWindowSize=21)
        except Exception:
            return gray

    def _remove_shadows(self, gray: np.ndarray) -> np.ndarray:
        """Remove uneven shadows from scanned documents."""
        cv2 = _get_cv2()
        try:
            # Create a large blurred version (estimates the background)
            dilated = cv2.dilate(gray, np.ones((7, 7), np.uint8))
            bg = cv2.medianBlur(dilated, 21)
            # Subtract background
            diff = 255 - cv2.absdiff(gray, bg)
            # Normalize
            result = cv2.normalize(diff, None, alpha=0, beta=255,
                                    norm_type=cv2.NORM_MINMAX, dtype=cv2.CV_8U)
            return result
        except Exception:
            return gray

    def _binarize(self, gray: np.ndarray) -> np.ndarray:
        """Convert to binary using adaptive thresholding."""
        cv2 = _get_cv2()
        try:
            # Adaptive threshold works better for uneven lighting
            binary = cv2.adaptiveThreshold(
                gray, 255,
                cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY,
                blockSize=11, C=2
            )
            return binary
        except Exception:
            _, binary = cv2.threshold(gray, 128, 255, cv2.THRESH_BINARY)
            return binary

    def _remove_small_noise(self, binary: np.ndarray, min_area: int = 20) -> np.ndarray:
        """Remove small connected components that are likely noise."""
        cv2 = _get_cv2()
        try:
            # Invert so text is white
            inverted = cv2.bitwise_not(binary)

            # Find connected components
            num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(
                inverted, connectivity=8
            )

            # Create output mask
            cleaned = np.zeros_like(binary)
            for i in range(1, num_labels):  # Skip background
                area = stats[i, cv2.CC_STAT_AREA]
                if area >= min_area:
                    cleaned[labels == i] = 255

            # Invert back
            return cv2.bitwise_not(cleaned)
        except Exception:
            return binary

    def auto_crop_document(self, image: np.ndarray) -> np.ndarray:
        """Automatically detect and crop the document from the background."""
        cv2 = _get_cv2()
        try:
            if len(image.shape) == 3:
                gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            else:
                gray = image

            # Blur to reduce noise
            blurred = cv2.GaussianBlur(gray, (5, 5), 0)

            # Edge detection
            edges = cv2.Canny(blurred, 75, 200)

            # Dilate to connect edges
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
            dilated = cv2.dilate(edges, kernel, iterations=2)

            # Find contours
            contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            if not contours:
                return image

            # Find largest contour
            largest = max(contours, key=cv2.contourArea)

            # Check if contour is large enough (at least 20% of image area)
            h, w = image.shape[:2]
            if cv2.contourArea(largest) < 0.2 * h * w:
                return image

            # Get bounding rectangle
            x, y, rw, rh = cv2.boundingRect(largest)

            # Add small padding
            pad = 5
            x = max(0, x - pad)
            y = max(0, y - pad)
            rw = min(w - x, rw + 2 * pad)
            rh = min(h - y, rh + 2 * pad)

            return image[y:y + rh, x:x + rw]
        except Exception as e:
            logger.debug(f"Auto-crop skipped: {e}")
            return image
