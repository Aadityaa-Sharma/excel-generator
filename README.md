# 📊 DocExcel — Universal Document to Excel Converter

> **"Convert any financial document into clean, structured Excel with minimal manual work."**

A production-ready web application built for **Chartered Accountants, Accountants, Auditors, Tax Consultants, Finance Teams, GST Professionals, and Students**. Processes invoices, bank statements, GST returns, tax forms, and 100+ document types with high accuracy.

---

## ✨ Features

### 📥 Input Support
- **Images**: JPG, PNG, BMP, GIF, TIFF, WebP, HEIC
- **Documents**: PDF (searchable, scanned, password-protected)
- **Office**: Word (.doc/.docx), Excel (.xls/.xlsx), PowerPoint (.ppt/.pptx)
- **Data**: XML, JSON, HTML, CSV/TXT
- **Email**: .eml, .msg
- **Archives**: ZIP (auto-extracts and processes)

### 🔍 OCR Pipeline
- **Hybrid extraction**: Native text → Table detection → OCR fallback
- **Engine priority**: PaddleOCR → Tesseract → EasyOCR
- **Smart preprocessing**: Auto-rotation, deskew, shadow removal, noise reduction
- **Multi-language**: English, Hindi, Gujarati, Marathi, Tamil, Telugu + more

### 📑 100+ Document Types
Invoices, bank statements, GST returns (GSTR-1/3B/9/2A/2B), Form 16/16A/26AS, balance sheets, P&L, trial balance, ledgers, salary slips, cheques, and many more.

### 📊 Excel Output
- Professional formatting with auto-width columns
- Frozen headers and auto-filters
- Currency, date, percentage formatting
- Low-confidence cell highlighting (yellow)
- Validation error highlighting (red)
- Summary sheet with key statistics
- Validation report sheet
- Named worksheets per table

### ✅ Financial Validation
- GSTIN format and state code validation
- PAN, IFSC format checks
- Arithmetic verification (Qty × Rate = Amount)
- GST calculation validation (CGST = SGST)
- Duplicate invoice detection
- Column total verification

### 🧠 Smart Detection
- Automatic column semantic mapping (50+ patterns)
- Document type classification (30+ types)
- Indian/international number format detection
- Currency symbol recognition

---

## 🚀 Quick Start

### Prerequisites
- Python 3.12+
- Tesseract OCR (optional but recommended)

### Local Setup

```bash
# Clone the repository
git clone <your-repo-url>
cd krishna

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install Tesseract (macOS)
brew install tesseract

# Install Tesseract (Ubuntu/Debian)
# sudo apt-get install tesseract-ocr

# Run the application
python app.py
```

Open **http://localhost:5000** in your browser.

### Single Command Run
```bash
pip install -r requirements.txt && python app.py
```

---

## 🌐 Deploy to Render

### Option 1: One-Click Deploy
1. Push this repository to GitHub
2. Go to [render.com](https://render.com) → New → Web Service
3. Connect your GitHub repo
4. Render will auto-detect `render.yaml` and configure everything

### Option 2: Manual Setup
1. Create a new **Web Service** on Render
2. Set **Build Command**: `pip install -r requirements.txt`
3. Set **Start Command**: `gunicorn app:app --config gunicorn.conf.py`
4. Add environment variables:
   - `SECRET_KEY` → Generate a random string
   - `OCR_ENGINE_PRIORITY` → `tesseract`
   - `LOG_LEVEL` → `INFO`

---

## 📁 Project Structure

```
krishna/
├── app.py                     # Flask entry point
├── config.py                  # Environment-based configuration
├── gunicorn.conf.py           # Production server config
├── requirements.txt           # Python dependencies
├── render.yaml                # Render deployment
├── Procfile                   # Process file
├── runtime.txt                # Python version
├── backend/
│   ├── routes/                # API endpoints
│   ├── ocr/                   # OCR engine wrappers (lazy-loaded)
│   ├── preprocessing/         # Image preprocessing pipeline
│   ├── parsers/               # Document format parsers
│   │   ├── pdf_parser.py      # PDF (native + OCR)
│   │   ├── image_parser.py    # Image OCR
│   │   ├── word_parser.py     # Word documents
│   │   ├── excel_parser.py    # Excel/ODS
│   │   └── other_parsers.py   # Text, HTML, XML, JSON, Email, PPT, ZIP
│   ├── validators/            # Financial validation
│   ├── smart_detection/       # Column mapping & doc classification
│   ├── excel/                 # Excel generation with formatting
│   ├── models/                # Data models (Cell, Table, Result)
│   └── utils/                 # File, format, memory utilities
├── frontend/
│   ├── index.html             # Single-page application
│   ├── css/styles.css         # Dark/light theme with glassmorphism
│   └── js/app.js              # Vanilla JS application logic
├── tests/                     # Test suite
└── logs/                      # Application logs (auto-created)
```

---

## ⚙️ Configuration

All settings are configurable via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | `dev-secret...` | Flask secret key |
| `PORT` | `5000` | Server port |
| `DEBUG` | `false` | Debug mode |
| `OCR_ENGINE_PRIORITY` | `paddleocr,tesseract,easyocr` | OCR engine order |
| `OCR_CONFIDENCE_THRESHOLD` | `0.6` | Min confidence (0-1) |
| `OCR_LANGUAGES` | `en` | OCR languages |
| `MAX_CONTENT_LENGTH` | `104857600` | Max upload size (100MB) |
| `MAX_FILES_PER_BATCH` | `100` | Max files per upload |
| `LOG_LEVEL` | `INFO` | Logging level |
| `MAX_WORKERS` | `2` | Processing threads |

---

## 🔌 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/health` | Health check |
| `POST` | `/api/upload` | Upload and start processing |
| `GET` | `/api/job/<id>` | Get job status |
| `POST` | `/api/job/<id>/cancel` | Cancel job |
| `GET` | `/api/job/<id>/preview` | Get table preview data |
| `POST` | `/api/job/<id>/edit` | Edit a cell |
| `GET` | `/api/job/<id>/download` | Download Excel |
| `POST` | `/api/job/<id>/regenerate` | Regenerate Excel after edits |
| `GET` | `/api/settings` | Get settings |
| `POST` | `/api/settings` | Update settings |
| `GET` | `/api/engines` | List available OCR engines |

---

## 🏗️ Architecture

```
Upload → Classify → Preprocess → Parse/OCR → Table Detection →
Smart Column Mapping → Financial Validation → Preview (Edit) → Excel Export
```

- **Lazy initialization**: OCR engines loaded only when first needed
- **Page-by-page processing**: Large PDFs processed page-by-page to minimize memory
- **Memory management**: Explicit cleanup after each file
- **Fallback chain**: Native extraction → OCR → preprocessing → retry
- **Background processing**: Files processed in threads, UI polls for status

---

## 📝 License

MIT License. Free for commercial and personal use.

---

Built with ❤️ for the CA and finance community.
