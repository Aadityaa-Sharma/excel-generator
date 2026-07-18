"""
Configuration module for Universal Document to Excel Converter.
All settings configurable via environment variables.
"""
import os
import tempfile
from pathlib import Path


class Config:
    """Base configuration class."""

    # --- Application ---
    APP_NAME: str = "Universal Document to Excel Converter"
    APP_VERSION: str = "1.0.0"
    APP_TAGLINE: str = "Convert any financial document into clean, structured Excel with minimal manual work."
    SECRET_KEY: str = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")
    DEBUG: bool = os.environ.get("DEBUG", "false").lower() == "true"
    HOST: str = os.environ.get("HOST", "0.0.0.0")
    PORT: int = int(os.environ.get("PORT", "5000"))

    # --- Paths ---
    BASE_DIR: Path = Path(__file__).resolve().parent
    TEMP_DIR: Path = Path(os.environ.get("TEMP_DIR", tempfile.gettempdir())) / "docexcel"
    UPLOAD_DIR: Path = Path(os.environ.get("UPLOAD_DIR", "")) or TEMP_DIR / "uploads"
    OUTPUT_DIR: Path = Path(os.environ.get("OUTPUT_DIR", "")) or TEMP_DIR / "outputs"
    LOG_DIR: Path = BASE_DIR / "logs"

    # --- File Upload ---
    MAX_CONTENT_LENGTH: int = int(os.environ.get("MAX_CONTENT_LENGTH", str(100 * 1024 * 1024)))  # 100MB
    MAX_FILES_PER_BATCH: int = int(os.environ.get("MAX_FILES_PER_BATCH", "100"))

    ALLOWED_EXTENSIONS: set = {
        # Images
        "jpg", "jpeg", "png", "bmp", "gif", "tiff", "tif", "webp", "heic", "heif",
        # Documents
        "pdf",
        # Word
        "doc", "docx",
        # Excel
        "xls", "xlsx",
        # PowerPoint
        "ppt", "pptx",
        # Text
        "txt", "rtf",
        # OpenOffice
        "odt", "ods",
        # Data
        "xml", "json", "html", "htm",
        # Email
        "eml", "msg",
        # Archive
        "zip",
    }

    IMAGE_EXTENSIONS: set = {"jpg", "jpeg", "png", "bmp", "gif", "tiff", "tif", "webp", "heic", "heif"}
    PDF_EXTENSIONS: set = {"pdf"}
    WORD_EXTENSIONS: set = {"doc", "docx"}
    EXCEL_EXTENSIONS: set = {"xls", "xlsx", "ods"}
    PPT_EXTENSIONS: set = {"ppt", "pptx"}
    TEXT_EXTENSIONS: set = {"txt", "rtf", "odt"}
    DATA_EXTENSIONS: set = {"xml", "json", "html", "htm"}
    EMAIL_EXTENSIONS: set = {"eml", "msg"}
    ARCHIVE_EXTENSIONS: set = {"zip"}

    # --- OCR ---
    OCR_ENGINE_PRIORITY: list = os.environ.get("OCR_ENGINE_PRIORITY", "tesseract").split(",")
    OCR_CONFIDENCE_THRESHOLD: float = float(os.environ.get("OCR_CONFIDENCE_THRESHOLD", "0.6"))
    OCR_LANGUAGES: list = os.environ.get("OCR_LANGUAGES", "en").split(",")
    OCR_DPI: int = int(os.environ.get("OCR_DPI", "300"))
    OCR_MAX_IMAGE_SIZE: int = int(os.environ.get("OCR_MAX_IMAGE_SIZE", str(50 * 1024 * 1024)))  # 50MB

    # --- Processing ---
    PAGE_BATCH_SIZE: int = int(os.environ.get("PAGE_BATCH_SIZE", "5"))
    MAX_WORKERS: int = int(os.environ.get("MAX_WORKERS", "2"))
    PROCESSING_TIMEOUT: int = int(os.environ.get("PROCESSING_TIMEOUT", "300"))  # 5 minutes per file

    # --- Excel ---
    EXCEL_DEFAULT_FONT: str = os.environ.get("EXCEL_DEFAULT_FONT", "Calibri")
    EXCEL_DEFAULT_FONT_SIZE: int = int(os.environ.get("EXCEL_DEFAULT_FONT_SIZE", "11"))
    EXCEL_HEADER_COLOR: str = os.environ.get("EXCEL_HEADER_COLOR", "1F4E79")
    EXCEL_LOW_CONFIDENCE_COLOR: str = os.environ.get("EXCEL_LOW_CONFIDENCE_COLOR", "FFFF00")
    EXCEL_ERROR_COLOR: str = os.environ.get("EXCEL_ERROR_COLOR", "FF6B6B")

    # --- Validation ---
    GSTIN_PATTERN: str = r"^\d{2}[A-Z]{5}\d{4}[A-Z]{1}[A-Z\d]{1}[Z]{1}[A-Z\d]{1}$"
    PAN_PATTERN: str = r"^[A-Z]{5}\d{4}[A-Z]{1}$"
    IFSC_PATTERN: str = r"^[A-Z]{4}0[A-Z0-9]{6}$"

    # --- Logging ---
    LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "INFO")
    LOG_FORMAT: str = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    LOG_MAX_BYTES: int = int(os.environ.get("LOG_MAX_BYTES", str(10 * 1024 * 1024)))  # 10MB
    LOG_BACKUP_COUNT: int = int(os.environ.get("LOG_BACKUP_COUNT", "3"))

    # --- Theme ---
    DEFAULT_THEME: str = os.environ.get("DEFAULT_THEME", "dark")

    @classmethod
    def ensure_directories(cls) -> None:
        """Create all required directories if they don't exist."""
        for dir_path in [cls.TEMP_DIR, cls.UPLOAD_DIR, cls.OUTPUT_DIR, cls.LOG_DIR]:
            dir_path.mkdir(parents=True, exist_ok=True)

    @classmethod
    def get_file_category(cls, extension: str) -> str:
        """Return the category of a file based on its extension."""
        ext = extension.lower().lstrip(".")
        if ext in cls.IMAGE_EXTENSIONS:
            return "image"
        if ext in cls.PDF_EXTENSIONS:
            return "pdf"
        if ext in cls.WORD_EXTENSIONS:
            return "word"
        if ext in cls.EXCEL_EXTENSIONS:
            return "excel"
        if ext in cls.PPT_EXTENSIONS:
            return "powerpoint"
        if ext in cls.TEXT_EXTENSIONS:
            return "text"
        if ext in cls.DATA_EXTENSIONS:
            return "data"
        if ext in cls.EMAIL_EXTENSIONS:
            return "email"
        if ext in cls.ARCHIVE_EXTENSIONS:
            return "archive"
        return "unknown"
