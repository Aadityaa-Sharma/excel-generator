"""
Flask routes — All API endpoints for the application.
Handles upload, conversion, preview, download, and settings.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from flask import Blueprint, current_app, jsonify, request, send_file

from backend.models import ProcessingResult, ProcessingStatus, compute_file_hash
from backend.utils import (
    cleanup_file, get_file_extension, safe_filename,
    get_human_readable_size, release_memory,
)
from config import Config

logger = logging.getLogger(__name__)

api = Blueprint("api", __name__)

# ── In-memory job store (no Redis needed) ───────────────────────────────────
# For Render free tier: simple dict-based job tracking
_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()
_file_hashes: dict[str, str] = {}  # hash → filename for duplicate detection


def _get_processor():
    """Lazy-load the document processor to avoid heavy imports at startup."""
    from backend.ocr import OCREngineManager
    from backend.preprocessing import ImagePreprocessor
    from backend.parsers import ParserFactory
    from backend.validators import FinancialValidator
    from backend.smart_detection import SmartColumnDetector, DocumentClassifier
    from backend.excel import ExcelGenerator

    return {
        "ocr_manager": OCREngineManager(
            engine_priority=Config.OCR_ENGINE_PRIORITY,
            confidence_threshold=Config.OCR_CONFIDENCE_THRESHOLD,
            languages=Config.OCR_LANGUAGES,
        ),
        "preprocessor": ImagePreprocessor(target_dpi=Config.OCR_DPI),
        "validator": FinancialValidator(),
        "column_detector": SmartColumnDetector(),
        "doc_classifier": DocumentClassifier(),
        "excel_generator": ExcelGenerator(),
    }


# Lazy-loaded processor components
_processor: dict | None = None
_processor_lock = threading.Lock()


def _ensure_processor():
    """Thread-safe lazy initialization of processor components."""
    global _processor
    if _processor is None:
        with _processor_lock:
            if _processor is None:
                logger.info("Initializing document processor...")
                _processor = _get_processor()
                logger.info("Document processor initialized")
    return _processor


# ── Health Check ────────────────────────────────────────────────────────────

@api.route("/api/health", methods=["GET"])
def health_check():
    """Health check endpoint for Render."""
    return jsonify({
        "status": "healthy",
        "app": Config.APP_NAME,
        "version": Config.APP_VERSION,
    })


# ── Upload & Convert ───────────────────────────────────────────────────────

@api.route("/api/upload", methods=["POST"])
def upload_files():
    """Upload files and start processing."""
    if "files" not in request.files:
        return jsonify({"error": "No files provided"}), 400

    files = request.files.getlist("files")
    password = request.form.get("password", None)
    merge_output = request.form.get("merge", "false").lower() == "true"

    if not files or all(f.filename == "" for f in files):
        return jsonify({"error": "No files selected"}), 400

    if len(files) > Config.MAX_FILES_PER_BATCH:
        return jsonify({"error": f"Maximum {Config.MAX_FILES_PER_BATCH} files per batch"}), 400

    job_id = str(uuid.uuid4())[:12]
    file_infos = []

    for file in files:
        if not file.filename:
            continue

        ext = get_file_extension(file.filename)
        if ext not in Config.ALLOWED_EXTENSIONS:
            continue

        # Save to temp directory
        filename = safe_filename(file.filename)
        temp_path = Config.UPLOAD_DIR / f"{job_id}_{filename}"
        Config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        file.save(str(temp_path))

        # Compute hash for duplicate detection
        file_hash = compute_file_hash(temp_path)
        duplicate_of = _file_hashes.get(file_hash)

        file_infos.append({
            "filename": filename,
            "path": str(temp_path),
            "size": os.path.getsize(str(temp_path)),
            "extension": ext,
            "hash": file_hash,
            "duplicate_of": duplicate_of,
        })

        _file_hashes[file_hash] = filename

    if not file_infos:
        return jsonify({"error": "No supported files found"}), 400

    # Create job
    with _jobs_lock:
        _jobs[job_id] = {
            "id": job_id,
            "status": "queued",
            "files": file_infos,
            "results": [],
            "progress": 0,
            "total": len(file_infos),
            "current_file": "",
            "error": None,
            "output_path": None,
            "merge": merge_output,
            "password": password,
            "created_at": time.time(),
            "started_at": None,
            "completed_at": None,
        }

    # Start processing in background thread
    thread = threading.Thread(
        target=_process_job,
        args=(job_id,),
        daemon=True,
    )
    thread.start()

    # Return duplicate warnings
    duplicates = [f for f in file_infos if f["duplicate_of"]]

    return jsonify({
        "job_id": job_id,
        "files_accepted": len(file_infos),
        "duplicates": [
            {"file": d["filename"], "duplicate_of": d["duplicate_of"]}
            for d in duplicates
        ],
        "message": f"Processing {len(file_infos)} file(s)...",
    }), 202


@api.route("/api/job/<job_id>", methods=["GET"])
def get_job_status(job_id: str):
    """Get the status of a processing job."""
    with _jobs_lock:
        job = _jobs.get(job_id)

    if not job:
        return jsonify({"error": "Job not found"}), 404

    return jsonify({
        "id": job["id"],
        "status": job["status"],
        "progress": job["progress"],
        "total": job["total"],
        "current_file": job["current_file"],
        "error": job["error"],
        "results": [
            {
                "filename": r.get("filename", ""),
                "status": r.get("status", ""),
                "tables": r.get("table_count", 0),
                "rows": r.get("total_rows", 0),
                "validations": r.get("validation_count", 0),
                "processing_time": r.get("processing_time", 0),
                "ocr_engine": r.get("ocr_engine", ""),
                "document_type": r.get("document_type", ""),
                "warnings": r.get("warnings", []),
                "error": r.get("error", ""),
            }
            for r in job.get("results", [])
        ],
    })


@api.route("/api/job/<job_id>/cancel", methods=["POST"])
def cancel_job(job_id: str):
    """Cancel a running job."""
    with _jobs_lock:
        job = _jobs.get(job_id)
        if not job:
            return jsonify({"error": "Job not found"}), 404
        job["status"] = "cancelled"

    return jsonify({"message": "Job cancelled"})


# ── Preview & Edit ──────────────────────────────────────────────────────────

@api.route("/api/job/<job_id>/preview", methods=["GET"])
def get_preview(job_id: str):
    """Get table data for preview/editing."""
    with _jobs_lock:
        job = _jobs.get(job_id)

    if not job:
        return jsonify({"error": "Job not found"}), 404

    if job["status"] not in ("completed", "ready"):
        return jsonify({"error": "Job not yet completed"}), 400

    # Return full table data for preview
    tables = job.get("table_data", [])
    validations = job.get("validation_data", [])

    return jsonify({
        "tables": tables,
        "validations": validations,
        "document_type": job.get("document_type", "unknown"),
    })


@api.route("/api/job/<job_id>/edit", methods=["POST"])
def edit_cell(job_id: str):
    """Edit a cell value in the preview."""
    with _jobs_lock:
        job = _jobs.get(job_id)

    if not job:
        return jsonify({"error": "Job not found"}), 404

    data = request.get_json()
    table_idx = data.get("table_index", 0)
    row_idx = data.get("row")
    col_idx = data.get("col")
    new_value = data.get("value")

    if row_idx is None or col_idx is None:
        return jsonify({"error": "Row and column required"}), 400

    try:
        tables = job.get("table_data", [])
        if table_idx < len(tables):
            cells = tables[table_idx].get("cells", [])
            if row_idx < len(cells) and col_idx < len(cells[row_idx]):
                cells[row_idx][col_idx]["value"] = new_value
                cells[row_idx][col_idx]["confidence"] = 1.0  # User-edited = full confidence

        return jsonify({"message": "Cell updated"})
    except (IndexError, KeyError) as e:
        return jsonify({"error": f"Edit failed: {str(e)}"}), 400


# ── Export/Download ─────────────────────────────────────────────────────────

@api.route("/api/job/<job_id>/download", methods=["GET"])
def download_result(job_id: str):
    """Download the generated Excel file."""
    with _jobs_lock:
        job = _jobs.get(job_id)

    if not job:
        return jsonify({"error": "Job not found"}), 404

    output_path = job.get("output_path")
    if not output_path or not os.path.exists(output_path):
        return jsonify({"error": "Output file not available"}), 404

    filename = Path(output_path).name
    return send_file(
        output_path,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=filename,
    )


@api.route("/api/job/<job_id>/regenerate", methods=["POST"])
def regenerate_excel(job_id: str):
    """Regenerate Excel from edited data."""
    with _jobs_lock:
        job = _jobs.get(job_id)

    if not job:
        return jsonify({"error": "Job not found"}), 404

    try:
        # Rebuild tables from edited data
        from backend.models import Cell, Table
        from backend.excel import ExcelGenerator

        result = ProcessingResult()
        result.filename = job.get("original_filename", "output")

        table_data = job.get("table_data", [])
        for td in table_data:
            table = Table()
            table.title = td.get("title", "")
            table.headers = td.get("headers", [])

            for row_data in td.get("cells", []):
                row_cells = []
                for cd in row_data:
                    cell = Cell()
                    cell.value = cd.get("value", "")
                    cell.raw_value = cd.get("raw_value", "")
                    cell.confidence = cd.get("confidence", 1.0)
                    cell.data_type = cd.get("data_type", "text")
                    cell.is_header = cd.get("is_header", False)
                    cell.font_bold = cd.get("font_bold", False)
                    cell.format_string = cd.get("format_string", "")
                    cell.semantic_label = cd.get("semantic_label", "")
                    cell.validation_error = cd.get("validation_error", "")
                    row_cells.append(cell)
                table.cells.append(row_cells)

            result.tables.append(table)

        generator = ExcelGenerator()
        output_path = generator.generate(result)

        with _jobs_lock:
            job["output_path"] = output_path

        return jsonify({"message": "Excel regenerated", "output_path": output_path})

    except Exception as e:
        return jsonify({"error": f"Regeneration failed: {str(e)}"}), 500


# ── Settings ────────────────────────────────────────────────────────────────

@api.route("/api/settings", methods=["GET"])
def get_settings():
    """Get current application settings."""
    return jsonify({
        "ocr_engine_priority": Config.OCR_ENGINE_PRIORITY,
        "confidence_threshold": Config.OCR_CONFIDENCE_THRESHOLD,
        "languages": Config.OCR_LANGUAGES,
        "max_file_size_mb": Config.MAX_CONTENT_LENGTH / (1024 * 1024),
        "max_files_per_batch": Config.MAX_FILES_PER_BATCH,
        "excel_font": Config.EXCEL_DEFAULT_FONT,
        "excel_font_size": Config.EXCEL_DEFAULT_FONT_SIZE,
        "theme": Config.DEFAULT_THEME,
        "supported_formats": sorted(Config.ALLOWED_EXTENSIONS),
    })


@api.route("/api/settings", methods=["POST"])
def update_settings():
    """Update application settings (runtime only, not persisted)."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    if "confidence_threshold" in data:
        try:
            Config.OCR_CONFIDENCE_THRESHOLD = float(data["confidence_threshold"])
        except (ValueError, TypeError):
            pass

    if "ocr_engine_priority" in data:
        Config.OCR_ENGINE_PRIORITY = data["ocr_engine_priority"]

    if "languages" in data:
        Config.OCR_LANGUAGES = data["languages"]

    # Reset processor to pick up new settings
    global _processor
    _processor = None

    return jsonify({"message": "Settings updated"})


@api.route("/api/engines", methods=["GET"])
def get_available_engines():
    """Get list of available OCR engines."""
    proc = _ensure_processor()
    return jsonify({
        "available": proc["ocr_manager"].available_engines,
        "priority": Config.OCR_ENGINE_PRIORITY,
    })


# ── Processing Pipeline ────────────────────────────────────────────────────

def _process_job(job_id: str) -> None:
    """Background processing pipeline for a job."""
    with _jobs_lock:
        job = _jobs.get(job_id)
        if not job:
            return
        job["status"] = "processing"
        job["started_at"] = time.time()

    proc = _ensure_processor()
    parser_factory = ParserFactory(
        ocr_manager=proc["ocr_manager"],
        preprocessor=proc["preprocessor"],
    )

    all_tables = []
    all_validations = []
    all_results = []

    files = job["files"]
    password = job.get("password")

    for idx, file_info in enumerate(files):
        # Check if cancelled
        with _jobs_lock:
            if _jobs.get(job_id, {}).get("status") == "cancelled":
                return

            _jobs[job_id]["current_file"] = file_info["filename"]
            _jobs[job_id]["progress"] = idx

        try:
            logger.info(f"Processing file {idx + 1}/{len(files)}: {file_info['filename']}")

            # Parse document
            from backend.parsers import ParserFactory as PF
            result = parser_factory.parse(file_info["path"], password=password)
            result.file_hash = file_info["hash"]
            result.file_size = file_info["size"]

            # Smart column detection
            for table in result.tables:
                proc["column_detector"].detect_and_rename(table)

            # Document classification
            all_text = " ".join(
                " ".join(str(c.value) for c in row)
                for t in result.tables for row in t.cells
            )
            result.document_type = proc["doc_classifier"].classify(
                text=all_text,
                tables=result.tables,
                filename=file_info["filename"],
            )

            # Financial validation
            for table in result.tables:
                validations = proc["validator"].validate_table(table)
                result.validations.extend(validations)

            result.mark_completed()

            # Store results
            result_summary = {
                "filename": file_info["filename"],
                "status": result.status.value,
                "table_count": len(result.tables),
                "total_rows": sum(t.row_count for t in result.tables),
                "validation_count": len(result.validations),
                "processing_time": round(result.processing_time, 2),
                "ocr_engine": result.ocr_engine_used,
                "document_type": result.document_type.value,
                "warnings": result.warnings,
                "error": result.error_message,
            }
            all_results.append(result_summary)

            all_tables.extend(result.tables)
            all_validations.extend(result.validations)

        except Exception as e:
            logger.error(f"Error processing {file_info['filename']}: {e}", exc_info=True)
            all_results.append({
                "filename": file_info["filename"],
                "status": "failed",
                "table_count": 0,
                "total_rows": 0,
                "validation_count": 0,
                "processing_time": 0,
                "ocr_engine": "",
                "document_type": "unknown",
                "warnings": [],
                "error": str(e),
            })
        finally:
            # Clean up uploaded file
            cleanup_file(file_info["path"])
            release_memory()

    # Generate Excel
    try:
        from backend.excel import ExcelGenerator
        from backend.models import ProcessingResult as PR

        combined = PR()
        combined.filename = files[0]["filename"] if len(files) == 1 else f"batch_{job_id}"
        combined.tables = all_tables
        combined.validations = all_validations
        combined.document_type = result.document_type if 'result' in dir() else __import__('backend.models', fromlist=['DocumentType']).DocumentType.UNKNOWN

        generator = ExcelGenerator()
        output_path = generator.generate(combined)

        with _jobs_lock:
            _jobs[job_id]["output_path"] = output_path
            _jobs[job_id]["original_filename"] = combined.filename
            _jobs[job_id]["document_type"] = combined.document_type.value

            # Store table data for preview
            _jobs[job_id]["table_data"] = [t.to_dict() for t in all_tables]
            _jobs[job_id]["validation_data"] = [v.to_dict() for v in all_validations]

    except Exception as e:
        logger.error(f"Excel generation failed: {e}", exc_info=True)
        with _jobs_lock:
            _jobs[job_id]["error"] = f"Excel generation failed: {str(e)}"

    # Finalize job
    with _jobs_lock:
        job_data = _jobs.get(job_id)
        if job_data:
            job_data["status"] = "completed"
            job_data["progress"] = len(files)
            job_data["results"] = all_results
            job_data["completed_at"] = time.time()

    release_memory()
    logger.info(f"Job {job_id} completed: {len(all_tables)} tables extracted")
